"""One durable audio review after a call; reading a page never starts paid work."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import wave

from repositories.learning_repository import LearningError, encoded, timestamp, transaction
from services.speech_provider import SpeechError
from services.activity_evidence import load_contract, save_report
from services.speaking_evidence import recorded_audio_source, verify_audio_source, validate_speaking_judgements


class SpeakingReviewService:
    def __init__(self, db_path, audio_root, assessor):
        self.db_path, self.root, self.assessor = db_path, Path(audio_root), assessor
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='speaking-review')
        self.lock = threading.RLock()
        self.running = set()

    def read(self, conn, sid):
        row = conn.execute('SELECT * FROM speaking_reviews WHERE session_id=?', (sid,)).fetchone()
        if not row:
            return None
        return {'state': row['state'], 'report': json.loads(row['report_json']) if row['report_json'] else None,
                'error': row['error'], 'retryable': row['state'] in ('failed', 'queued', 'analysing')
                and row['lease_until'] <= timestamp() and sid not in self.running
                and not (row['state'] == 'queued' and self.running)}

    def request(self, sid, retry=False):
        with self.lock, transaction(self.db_path, write=True) as conn:
            session = conn.execute('SELECT state FROM live_conversation_sessions WHERE id=?', (sid,)).fetchone()
            if not session or session['state'] not in ('completed', 'interrupted', 'failed'):
                raise LearningError('busy', 'Finish the conversation before reviewing it.', 409)
            if conn.execute("SELECT 1 FROM live_conversation_recordings WHERE session_id=? AND state='capturing'", (sid,)).fetchone():
                raise LearningError('busy', 'The recording is still being saved.', 409)
            existed = conn.execute('SELECT 1 FROM speaking_reviews WHERE session_id=?', (sid,)).fetchone()
            if existed and not retry:
                return
            conn.execute('INSERT OR IGNORE INTO speaking_reviews(session_id,created_at,updated_at) VALUES (?,?,?)', (sid,timestamp(),timestamp()))
            row = conn.execute('SELECT state,lease_until FROM speaking_reviews WHERE session_id=?', (sid,)).fetchone()
            if row['state'] == 'ready' or row['lease_until'] > timestamp() or sid in self.running:
                return
            conn.execute("UPDATE speaking_reviews SET state='queued',error=NULL,updated_at=? WHERE session_id=?", (timestamp(),sid))
        self.dispatch()

    def dispatch(self):
        with self.lock:
            if self.running:
                return
            with transaction(self.db_path, write=True) as conn:
                row = conn.execute("SELECT session_id FROM speaking_reviews WHERE state='queued' AND lease_until<=? ORDER BY created_at LIMIT 1", (timestamp(),)).fetchone()
                if not row:
                    return
                sid = row[0]
                conn.execute("UPDATE speaking_reviews SET state='analysing',lease_until=?,updated_at=? WHERE session_id=?", (timestamp()+240,timestamp(),sid))
            self.running.add(sid)
            self.executor.submit(self._work, sid)

    def _work(self, sid):
        try:
            with transaction(self.db_path) as conn:
                session = dict(conn.execute('SELECT * FROM live_conversation_sessions WHERE id=?', (sid,)).fetchone())
                previous = conn.execute('SELECT state FROM speaking_reviews WHERE session_id=?', (sid,)).fetchone()
                if previous is not None and previous[0] == 'ready':
                    return
                contract = load_contract(conn, session['profile_id'], 'speaking', sid)
                recordings = [dict(r) for r in conn.execute('SELECT * FROM live_conversation_recordings WHERE session_id=? ORDER BY ordinal', (sid,))]
                # Assistant context only: the independent audio pass must not be
                # primed with an ASR system's possibly corrected learner words.
                fragments = [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM live_conversation_events WHERE session_id=? AND type='session.output_transcript.delta' ORDER BY id", (sid,))]
                dialogue = []
                last_end = -10000
                for fragment in fragments:
                    start, end = fragment.get('start_ms', 0), fragment.get('end_ms', 0)
                    text = fragment.get('delta', '')
                    if dialogue and start - last_end < 1800 and len(dialogue[-1]['content']) + len(text) < 2000:
                        dialogue[-1]['content'] += text
                    else:
                        dialogue.append({'role':'assistant', 'content':text})
                    last_end = end
            if not recordings or not any(r['sample_count'] >= 4800 and r['state'] != 'silent' for r in recordings):
                raise SpeechError('There is not enough recorded speech to review. Try another conversation.')
            self.root.mkdir(parents=True, exist_ok=True)
            # Preserve continuous sample timing, including listening pauses.
            # This temporary copy is private and removed on success or failure.
            with tempfile.TemporaryDirectory(prefix='review-', dir=self.root) as directory:
                audio_path = Path(directory) / 'learner.wav'
                source = self._assemble(recordings, audio_path)
                options = {'curriculum_contract': contract} if contract is not None else {}
                report = self.assessor.assess(audio_path, json.loads(session['scenario_json']), dialogue, session['language'], **options)
                if contract is not None:
                    validate_speaking_judgements(contract, report, source['duration_ms'])
                    report = {**report, 'audio_source': source}
                elif 'criterion_report' in report or 'audio_source' in report:
                    raise ValueError('An old Speaking task cannot acquire criterion evidence after the conversation.')
            with transaction(self.db_path, write=True) as conn:
                if contract is not None:
                    # Re-read both persisted metadata and original bytes after
                    # provider work, before committing any report or rewards.
                    verify_audio_source(conn, session['profile_id'], sid, source, audio_root=self.root)
                conn.execute("UPDATE speaking_reviews SET state='ready',report_json=?,error=NULL,lease_until=0,updated_at=? WHERE session_id=?", (encoded(report),timestamp(),sid))
                if contract is not None:
                    save_report(conn, session['profile_id'], 'speaking', sid, sid, report['criterion_report'], audio_source=source)
                from services.progression import award_speaking
                award_speaking(conn, session, report)
                from services.course_targets import record_speaking_targets
                record_speaking_targets(conn, session['profile_id'], sid)
        except Exception as error:
            message = str(error) if isinstance(error, SpeechError) else 'Your speaking review could not finish. The recordings are saved; please try again.'
            with transaction(self.db_path, write=True) as conn:
                conn.execute("UPDATE speaking_reviews SET state='failed',error=?,lease_until=0,updated_at=? WHERE session_id=?", (message,timestamp(),sid))
        finally:
            with self.lock:
                self.running.discard(sid)
                self.dispatch()

    def _assemble(self, recordings, target):
        try:
            return recorded_audio_source(recordings, self.root, target_path=target)
        except (ValueError, OSError, wave.Error, EOFError) as error:
            raise SpeechError(str(error) if isinstance(error, ValueError) else
                              'The saved recording could not be read safely. It has been kept.') from error
