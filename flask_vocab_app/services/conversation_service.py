"""Local conversation pilot. Durable turns, bounded jobs, immutable audio and hypotheses.

Only explicit submission/retry starts work. Read/poll requests never call providers.
Jobs checkpoint each expensive result. Expired leases can be retried after restart.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import tempfile
import threading

from repositories.learning_repository import LearningError, encoded, identifier, require_access, timestamp, transaction
from services.conversation_ai import SCENARIO
from services.speech_provider import SpeechError, audio_info, wav_copy

CASES = json.loads((Path(__file__).resolve().parents[1] / 'data/speech_cases.json').read_text())


def valid_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', value):
        raise LearningError('invalid_input', 'Use a valid submission identifier.')
    return value


class ConversationService:
    def __init__(self, db_path, speech, ai, config):
        self.db_path, self.speech, self.ai, self.config = db_path, speech, ai, config
        self.root = Path(db_path).resolve().parent / 'conversation-audio'
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='conversation')
        self.slots = threading.BoundedSemaphore(2)
        self.greeting_lock = threading.Lock()

    def _owned(self, conn, access, session_id):
        profile = require_access(conn, access, timestamp())
        row = conn.execute('SELECT * FROM conversation_sessions WHERE id=? AND profile_id=?', (session_id, profile['id'])).fetchone()
        if not row:
            raise LearningError('not_found', 'This conversation was not found.', 404)
        return dict(row)

    def options(self, access):
        with transaction(self.db_path) as conn:
            profile = require_access(conn, access, timestamp())
            sessions = [dict(r) for r in conn.execute('SELECT id,mode,state,created_at FROM conversation_sessions WHERE profile_id=? ORDER BY created_at DESC LIMIT 12', (profile['id'],))]
        return {'scenario': SCENARIO, 'cases': CASES, 'sessions': sessions,
                'transcription_model': self.config['CONVERSATION_TRANSCRIPTION_MODEL'],
                'comparison_model': self.config['CONVERSATION_COMPARISON_MODEL'],
                'conversation_model': self.config['CONVERSATION_MODEL'],
                'configured': bool(self.config.get('OPENROUTER_API_KEY') and self.config.get('OPENAI_API_KEY')),
                'audio_configured': bool(self.config.get('ELEVENLABS_API_KEY'))}

    def start(self, access, body):
        key = valid_key(body.get('submission_id'))
        mode = body.get('mode', 'conversation')
        if mode not in ('conversation', 'lab'):
            raise LearningError('invalid_input', 'Choose a conversation or a speech test.')
        language = 'ru' if body.get('language') == 'ru' else 'en'
        with transaction(self.db_path, write=True) as conn:
            profile = require_access(conn, access, timestamp())
            previous = conn.execute('SELECT * FROM conversation_sessions WHERE profile_id=? AND start_key=?', (profile['id'], key)).fetchone()
            if previous:
                if previous['mode'] != mode or previous['ui_language'] != language:
                    raise LearningError('conflict', 'This submission was used for a different activity.', 409)
                sid = previous['id']
            else:
                sid = identifier()
                conn.execute('INSERT INTO conversation_sessions(id,profile_id,mode,scenario_json,voice_id,ui_language,start_key,created_at) VALUES (?,?,?,?,?,?,?,?)',
                    (sid, profile['id'], mode, encoded(SCENARIO), random.choice(self.config['ELEVENLABS_VOICE_IDS']), language, key, timestamp()))
        return self.read(access, sid)

    def read(self, access, sid):
        with transaction(self.db_path) as conn:
            session = self._owned(conn, access, sid)
            turns = [dict(r) for r in conn.execute('SELECT * FROM conversation_turns WHERE session_id=? ORDER BY ordinal', (sid,))]
        result = {k: session[k] for k in ('id','profile_id','mode','state','created_at')}
        result['scenario'] = json.loads(session['scenario_json'])
        result['greeting_audio_url'] = f'/api/v1/conversations/{sid}/greeting/audio' if (self.root / (sid + '-greeting.mp3')).is_file() else None
        result['turns'] = []
        for t in turns:
            item = {k: t[k] for k in ('id','ordinal','state','duration_seconds','case_id','assessment_state','audio_state','error','assessment_error','audio_error')}
            for column, field in [('transcript_json','transcript'),('comparisons_json','comparisons'),('reply_json','reply'),('assessment_json','assessment')]:
                item[field] = json.loads(t[column]) if t[column] else None
                if field == 'transcript' and item[field]:
                    # Full provider output stays stored, but the player only needs display fields.
                    item[field] = {k: item[field][k] for k in ('text','model','style','words','latency_ms')}
            item['recording_url'] = f'/api/v1/conversations/{sid}/turns/{t["id"]}/audio/original'
            item['reply_audio_url'] = f'/api/v1/conversations/{sid}/turns/{t["id"]}/audio/reply' if t['reply_audio_filename'] else None
            unfinished = t['state'] != 'ready' or t['assessment_state'] in ('pending','running','failed') or t['audio_state'] in ('pending','failed')
            item['retryable'] = unfinished and t['lease_until'] <= timestamp()
            item['working'] = unfinished and t['lease_until'] > timestamp()
            result['turns'].append(item)
        return result

    def submit(self, access, sid, body, data, extension):
        key = valid_key(body.get('submission_id'))
        if extension not in ('webm','ogg','mp4','m4a','mp3','wav') or not 1 <= len(data) <= 8 * 1024 * 1024:
            raise LearningError('invalid_audio', 'Use an audio recording up to 8 MB.')
        case_id = body.get('case_id') or None
        fingerprint = hashlib.sha256(data + encoded({'case_id': case_id}).encode()).hexdigest()
        with transaction(self.db_path) as conn:
            self._owned(conn, access, sid)
            previous = conn.execute('SELECT * FROM conversation_turns WHERE session_id=? AND submission_id=?', (sid,key)).fetchone()
            if previous:
                if previous['request_hash'] != fingerprint:
                    raise LearningError('conflict', 'This submission contains a different recording.', 409)
                return self.read(access, sid)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
            source = Path(tmp) / ('original.' + extension)
            source.write_bytes(data)
            try:
                duration = audio_info(source)
            except SpeechError as error:
                raise LearningError('invalid_audio', str(error)) from None
            with transaction(self.db_path, write=True) as conn:
                session = self._owned(conn, access, sid)
                previous = conn.execute('SELECT * FROM conversation_turns WHERE session_id=? AND submission_id=?', (sid,key)).fetchone()
                if previous:
                    if previous['request_hash'] != fingerprint:
                        raise LearningError('conflict', 'This submission contains a different recording.', 409)
                    tid = previous['id']
                else:
                    if session['state'] != 'active':
                        raise LearningError('completed', 'Start a new conversation to keep practising.', 409)
                    count = conn.execute('SELECT COUNT(*) FROM conversation_turns WHERE session_id=?', (sid,)).fetchone()[0]
                    if count >= 8:
                        raise LearningError('turn_limit', 'You have finished eight turns. Start a new conversation to continue.', 409)
                    if conn.execute("SELECT 1 FROM conversation_turns WHERE session_id=? AND state!='ready'", (sid,)).fetchone():
                        raise LearningError('turn_pending', 'Wait for the reply or retry the previous recording first.', 409)
                    if session['mode'] == 'lab' and case_id not in {c['id'] for c in CASES}:
                        raise LearningError('invalid_case', 'Choose a test sentence.')
                    if session['mode'] == 'conversation' and case_id:
                        raise LearningError('invalid_case', 'Test sentences belong in the speech lab.')
                    tid = identifier()
                    filename = f'{tid}.{extension}'
                    shutil.copyfile(source, self.root / filename)
                    conn.execute('INSERT INTO conversation_turns(id,session_id,ordinal,submission_id,request_hash,audio_filename,duration_seconds,case_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                        (tid,sid,count + 1,key,fingerprint,filename,duration,case_id,timestamp()))
        self.dispatch(tid)
        return self.read(access, sid)

    def retry(self, access, sid, tid):
        with transaction(self.db_path) as conn:
            self._owned(conn, access, sid)
            if not conn.execute('SELECT 1 FROM conversation_turns WHERE id=? AND session_id=?', (tid,sid)).fetchone():
                raise LearningError('not_found', 'Recording not found.', 404)
        self.dispatch(tid)
        return self.read(access, sid)

    def dispatch(self, tid):
        if not self.slots.acquire(blocking=False):
            return  # Durable queued turn offers retry; no unbounded provider queue.
        try:
            with transaction(self.db_path, write=True) as conn:
                t = conn.execute('SELECT * FROM conversation_turns WHERE id=?', (tid,)).fetchone()
                if not t or t['lease_until'] > timestamp() or (t['state']=='ready' and t['assessment_state'] in ('ready','skipped') and t['audio_state'] in ('ready','skipped')):
                    self.slots.release()
                    return
                conn.execute('UPDATE conversation_turns SET lease_until=?,error=NULL WHERE id=?', (timestamp()+300,tid))
            self.executor.submit(self._work, tid)
        except Exception:
            self.slots.release()
            raise

    def _save(self, tid, **fields):
        with transaction(self.db_path, write=True) as conn:
            conn.execute('UPDATE conversation_turns SET '+','.join(k+'=?' for k in fields)+' WHERE id=?', (*fields.values(),tid))

    def _work(self, tid):
        try:
            with transaction(self.db_path) as conn:
                turn = dict(conn.execute('SELECT * FROM conversation_turns WHERE id=?', (tid,)).fetchone())
                session = dict(conn.execute('SELECT * FROM conversation_sessions WHERE id=?', (turn['session_id'],)).fetchone())
                prior = [dict(r) for r in conn.execute('SELECT transcript_json,reply_json FROM conversation_turns WHERE session_id=? AND ordinal<? ORDER BY ordinal', (turn['session_id'],turn['ordinal']))]
            scenario = json.loads(session['scenario_json'])
            if turn['transcript_json']:
                transcript = json.loads(turn['transcript_json'])
            else:
                self._save(tid, state='running')
                with tempfile.TemporaryDirectory(dir=self.root) as tmp:
                    wav = Path(tmp) / 'speech.wav'
                    wav_copy(self.root / turn['audio_filename'], wav)
                    transcript = self.speech.transcribe(wav)
                self._save(tid, transcript_json=encoded(transcript))
            history = [{'role':'assistant','text':scenario['opening']}]
            for p in prior:
                if p['transcript_json']: history.append({'role':'user','text':json.loads(p['transcript_json'])['text']})
                if p['reply_json']: history.append({'role':'assistant','text':json.loads(p['reply_json'])['russian']})
            context = history[-1]['text']
            history.append({'role':'user','text':transcript['text']})
            if session['mode'] == 'lab':
                self._lab(tid, turn, transcript)
                return
            # Assessment can complete independently while the worker prepares the spoken reply.
            with ThreadPoolExecutor(max_workers=1) as assess_pool:
                if turn['assessment_state'] != 'ready':
                    assess_pool.submit(self._assess, tid, transcript['text'], context, session['ui_language'])
                reply = json.loads(turn['reply_json']) if turn['reply_json'] else self.ai.reply(scenario, history)
                self._save(tid, reply_json=encoded(reply), state='ready', error=None)
                if not turn['reply_audio_filename']:
                    try:
                        audio = self.speech.speak(reply['russian'], session['voice_id'])
                        filename = tid + '-reply.mp3'
                        (self.root / filename).write_bytes(audio)
                        self._save(tid, reply_audio_filename=filename, audio_state='ready', audio_error=None)
                    except SpeechError as error:
                        self._save(tid, audio_state='failed', audio_error=str(error))
        except Exception as error:
            self._save(tid, state='failed', error=str(error) if isinstance(error,SpeechError) else 'This turn could not finish. Your recording is kept; retry it.')
        finally:
            self._save(tid, lease_until=0)
            self.slots.release()

    def _assess(self, tid, text, context, language):
        self._save(tid, assessment_state='running', assessment_error=None)
        try:
            result = self.ai.assess(text, context, language)
            self._save(tid, assessment_json=encoded(result), assessment_state='ready')
        except Exception as error:
            self._save(tid, assessment_state='failed', assessment_error=str(error) if isinstance(error,SpeechError) else 'Feedback could not finish. Please retry.')

    def _lab(self, tid, turn, transcript):
        comparisons = json.loads(turn['comparisons_json']) if turn['comparisons_json'] else []
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
            wav = Path(tmp) / 'speech.wav'
            wav_copy(self.root / turn['audio_filename'], wav)
            for provider, style in [('mai','clean'),('openai','verbatim')]:
                previous = next((r for r in comparisons if r['provider']==provider), None)
                if previous and 'transcription' in previous:
                    continue
                comparisons = [r for r in comparisons if r['provider'] != provider]
                try:
                    comparisons.append({'provider':provider,'transcription':self.speech.transcribe(wav,provider=provider,style=style)})
                except SpeechError as error:
                    comparisons.append({'provider':provider,'error':str(error)})
                self._save(tid, comparisons_json=encoded(comparisons))
        failed = any('error' in r for r in comparisons)
        self._save(tid,state='ready',assessment_state='failed' if failed else 'skipped',audio_state='skipped',
                   assessment_error='One comparison failed. Retry to finish it.' if failed else None)

    def finish(self, access, sid):
        with transaction(self.db_path, write=True) as conn:
            self._owned(conn, access, sid)
            if conn.execute("SELECT 1 FROM conversation_turns WHERE session_id=? AND state!='ready'", (sid,)).fetchone():
                raise LearningError('turn_pending', 'Finish the current reply before ending the conversation.', 409)
            conn.execute("UPDATE conversation_sessions SET state='completed' WHERE id=?", (sid,))
        return self.read(access, sid)

    def greeting(self, access, sid):
        with self.greeting_lock:
            with transaction(self.db_path) as conn:
                session = self._owned(conn, access, sid)
            path = self.root / (sid + '-greeting.mp3')
            if not path.is_file():
                try:
                    data = self.speech.speak(json.loads(session['scenario_json'])['opening'], session['voice_id'])
                except SpeechError as error:
                    raise LearningError('audio_failed', str(error), 503) from None
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                path.write_bytes(data)
        return self.read(access, sid)

    def audio(self, access, sid, tid, kind):
        with transaction(self.db_path) as conn:
            self._owned(conn, access, sid)
            t = conn.execute('SELECT * FROM conversation_turns WHERE id=? AND session_id=?', (tid,sid)).fetchone()
            filename = t['audio_filename' if kind=='original' else 'reply_audio_filename'] if t and kind in ('original','reply') else None
        if not filename or not (self.root / filename).is_file():
            raise LearningError('not_found', 'Audio is not available yet.', 404)
        return self.root / filename

    def delete(self, access, sid):
        with self.greeting_lock:
            return self._delete(access, sid)

    def _delete(self, access, sid):
        with transaction(self.db_path, write=True) as conn:
            self._owned(conn, access, sid)
            turns = conn.execute('SELECT * FROM conversation_turns WHERE session_id=?', (sid,)).fetchall()
            if any(t['lease_until']>timestamp() for t in turns):
                raise LearningError('turn_pending', 'Wait for processing to finish before deleting this recording.', 409)
            conn.execute('DELETE FROM conversation_sessions WHERE id=?', (sid,))
        for t in turns:
            for filename in (t['audio_filename'], t['reply_audio_filename']):
                if filename: (self.root / filename).unlink(missing_ok=True)
        (self.root / (sid + '-greeting.mp3')).unlink(missing_ok=True)
        return {'deleted':True}
