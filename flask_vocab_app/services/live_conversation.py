"""Speaking: WebRTC media, server event capture and deferred audio review.

The sideband saves exactly the PCM received from the provider, before ASR. Its
sample clock starts on attachment, independently of provider transcript timing.
No transcript, timing heuristic or client event awards coins or changes Elo.
"""
from array import array
from concurrent.futures import ThreadPoolExecutor
import base64
import hashlib
import json
from pathlib import Path
import random
import threading
import time
import wave

from repositories.learning_repository import LearningError, encoded, identifier, require_access, timestamp, transaction
from services.conversation_service import valid_key
from services.speech_provider import SpeechError
from services.speaking_scenarios import public_scenario
from repositories.speaking_repository import catalogue, choose_variant, validate_level
from repositories.speaking_history import recent_variants
from services.speaking_review import SpeakingReviewService
from services.speaking_lifecycle import NaturalEnding
from services.trial_live_budget import LiveTrialBudget, TRIAL_SECONDS
from services.ai_trial_budget import TrialDenied
from services.activity_evidence import save_contract, load_contract, reports_for_task
from services.speaking_evidence import speaking_task_contract, speaking_criterion_labels


class LiveConversationService:
    def __init__(self, db_path, provider, speech, ai, config, assessor=None):
        self.db_path, self.provider, self.speech, self.ai, self.config = db_path, provider, speech, ai, config
        self.root = Path(db_path).resolve().parent / 'live-conversation-audio'
        self.lock = threading.RLock()
        self.connections = {}
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='live-notes')
        self.slots = threading.BoundedSemaphore(2)
        self.reviews = SpeakingReviewService(db_path, self.root, assessor) if assessor else None
        self.trial_budget = LiveTrialBudget(config)
        self.max_seconds = TRIAL_SECONDS if self.trial_budget.enabled else 300

    def _owned(self, conn, access, sid):
        profile = require_access(conn, access, timestamp())
        row = conn.execute('SELECT * FROM live_conversation_sessions WHERE id=? AND profile_id=?', (sid, profile['id'])).fetchone()
        if not row:
            raise LearningError('not_found', 'This live conversation was not found.', 404)
        return dict(row)

    def scenarios(self, access, level=None):
        with transaction(self.db_path) as conn:
            require_access(conn, access, timestamp())
            return catalogue(conn, level)

    def options(self, access, exclude_seed=None, scenario_id='cafe', level=None):
        validate_level(level)
        with transaction(self.db_path) as conn:
            profile = require_access(conn, access, timestamp())
            recent = [dict(r) for r in conn.execute('SELECT id,state,created_at,scenario_json,scenario_id FROM live_conversation_sessions WHERE profile_id=? ORDER BY created_at DESC,rowid DESC LIMIT 12', (profile['id'],))]
            seeds = recent_variants(conn, profile['id'], scenario_id, level)
            listing = catalogue(conn, level)
            selected = next((item for item in listing['scenarios'] if item['id'] == scenario_id), None)
            available_count = selected['variant_count'] if selected else 0
            if level is not None and selected is not None and not available_count:
                snapshot = None
            else:
                snapshot = choose_variant(conn, scenario_id, level=level, previous_seeds=([exclude_seed] if exclude_seed else [])+seeds)
        for item in recent:
            scenario = json.loads(item.pop('scenario_json'))
            item.update(title=scenario.get('title'), title_ru=scenario.get('title_ru'))
        return {'scenario': public_scenario(snapshot), 'scenario_id':scenario_id, 'sessions': recent,
                'selected_level':level, 'available_count':available_count, 'levels':listing['levels'],
                'configured': bool(self.config.get('OPENAI_API_KEY')),
                'notes_configured': bool(self.config.get('OPENROUTER_API_KEY')),
                'model': self.config['LIVE_CONVERSATION_MODEL'], 'max_seconds': self.max_seconds}

    def start(self, access, body):
        key = valid_key(body.get('submission_id'))
        language = 'ru' if body.get('language') == 'ru' else 'en'
        level = validate_level(body.get('target_level', body.get('level')))
        if 'target_level' in body and 'level' in body and body['target_level'] != body['level']:
            raise LearningError('invalid_input', 'Choose one target level for this conversation.')
        with transaction(self.db_path, write=True) as conn:
            profile = require_access(conn, access, timestamp())
            previous = conn.execute('SELECT * FROM live_conversation_sessions WHERE profile_id=? AND start_key=?', (profile['id'], key)).fetchone()
            if previous:
                if previous['language'] != language:
                    raise LearningError('conflict', 'This start request belongs to a different conversation.', 409)
                if body.get('scenario_id') and body['scenario_id'] != previous['scenario_id']:
                    raise LearningError('conflict', 'This start request belongs to a different scenario.', 409)
                if body.get('scenario_seed') and body['scenario_seed'] != json.loads(previous['scenario_json']).get('seed'):
                    raise LearningError('conflict', 'This start request belongs to a different situation.', 409)
                if level is not None and level != previous['target_level']:
                    raise LearningError('conflict', 'This start request belongs to a different speaking level.', 409)
                sid = previous['id']
            else:
                sid = identifier()
                scenario_id = body.get('scenario_id','cafe')
                if not isinstance(scenario_id,str):
                    raise LearningError('invalid_input', 'Choose an available speaking scenario.')
                recent = recent_variants(conn, profile['id'], scenario_id, level)
                scenario = choose_variant(conn, scenario_id, level=level, seed=body.get('scenario_seed'),previous_seeds=recent, persist=True)
                conn.execute('INSERT INTO live_conversation_sessions(id,profile_id,start_key,scenario_json,language,model,backend_model,voice,created_at,heartbeat_at,scenario_id,variant_id,target_level) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (sid, profile['id'], key, encoded(scenario), language, self.config['LIVE_CONVERSATION_MODEL'],
                     self.config['CONVERSATION_MODEL'], random.choice(self.config['LIVE_CONVERSATION_VOICES']), timestamp(), timestamp(),scenario_id,scenario['seed'],scenario.get('target_level')))
                contract = speaking_task_contract(scenario)
                if contract is not None:
                    save_contract(conn, profile['id'], 'speaking', sid, contract)
        return self.read(access, sid)

    def read(self, access, sid):
        with transaction(self.db_path) as conn:
            session = self._owned(conn, access, sid)
            rows = conn.execute('SELECT * FROM live_conversation_recordings WHERE session_id=? ORDER BY ordinal', (sid,)).fetchall()
            events = conn.execute("SELECT payload_json FROM live_conversation_events WHERE session_id=? AND type IN ('session.input_transcript.delta','session.output_transcript.delta') ORDER BY id", (sid,)).fetchall()
            review = self.reviews.read(conn, sid) if self.reviews else None
            if review and review['state'] == 'ready' and review['report']:
                contract = load_contract(conn, session['profile_id'], 'speaking', sid)
                if contract is not None:
                    saved = reports_for_task(conn, session['profile_id'], 'speaking', sid).get(sid)
                    if saved is None or saved['report'] != review['report'].get('criterion_report'):
                        raise LearningError('unavailable', 'The saved criterion review could not be verified.', 503)
                    review['report']['criterion_details'] = [{
                        **speaking_criterion_labels(contract, item['criterion_id']),
                        'outcome': item['outcome'], 'feedback': item['feedback']}
                        for item in saved['report']['judgements']]
        result = {k: session[k] for k in ('id','state','created_at','started_at','ended_at','model','voice','error','end_reason','scenario_id','variant_id','target_level')}
        result['review'] = review
        result.update(scenario=public_scenario(json.loads(session['scenario_json'])), captions=[json.loads(r[0]) for r in events], recordings=[],
                      connected=sid in self.connections, finalized=session['final_usage_json'] is not None)
        result['needs_recovery'] = session['state'] in ('connecting','live','ending') and sid not in self.connections
        for row in rows:
            item = {k: row[k] for k in ('id','ordinal','start_sample','sample_count','sample_rate','state','error')}
            item['audio_url'] = f'/api/v1/live-conversations/{sid}/recordings/{row["id"]}'
            transcript = json.loads(row['transcript_json']) if row['transcript_json'] else None
            item['transcript'] = {k: transcript.get(k) for k in ('text','words','model','style')} if transcript else None
            item['assessment'] = json.loads(row['assessment_json']) if row['assessment_json'] else None
            item['retryable'] = row['state'] in ('queued','failed','analysing') and row['lease_until'] <= timestamp()
            result['recordings'].append(item)
        return result

    def connect(self, access, sid, body):
        sdp = body.get('sdp')
        if not isinstance(sdp, str) or not sdp.startswith('v=0') or len(sdp) > 65536 or 'm=audio ' not in sdp:
            raise LearningError('invalid_input', 'The browser did not provide a valid audio connection.')
        digest = hashlib.sha256(sdp.encode()).hexdigest()
        # A connect request is serialized so retrying an HTTP request never starts
        # a second paid session. A new browser peer must start a new activity.
        with self.lock:
            with transaction(self.db_path) as conn:
                session = self._owned(conn, access, sid)
            if session['offer_hash']:
                if session['offer_hash'] == digest and sid in self.connections and session['answer_sdp']:
                    return {'sdp': session['answer_sdp'], 'server_controlled': self.trial_budget.enabled}
                raise LearningError('connection_used', 'Start a new live conversation to reconnect.', 409)
            if session['state'] != 'new':
                raise LearningError('completed', 'Start a new live conversation.', 409)
            if len(self.connections) >= 2:
                raise LearningError('busy', 'Finish another live conversation before starting this one.', 409)
            self.trial_budget.reserve(session, json.loads(session['scenario_json']))
            self._session(sid, state='connecting', offer_hash=digest, heartbeat_at=timestamp())
            provider_id = None
            try:
                provider_id, answer = self.provider.create(session, json.loads(session['scenario_json']), sdp)
                self._session(sid, provider_id=provider_id, answer_sdp=answer)
                runtime = {'stop': threading.Event(), 'ready': threading.Event(), 'closed': threading.Event(), 'error': None}
                with transaction(self.db_path) as conn:
                    latest = conn.execute('SELECT state FROM live_conversation_sessions WHERE id=?',(sid,)).fetchone()
                if latest['state'] != 'connecting':
                    runtime['stop'].set()
                self.connections[sid] = runtime
                thread = threading.Thread(target=self._listen, args=(sid, provider_id, runtime), daemon=True, name='live-voice-' + sid[:8])
                thread.start()
                if not runtime['ready'].wait(18) or runtime['error']:
                    runtime['stop'].set()
                    raise SpeechError('The recording connection could not start. Please start a new conversation.')
                return {'sdp': answer, 'server_controlled': self.trial_budget.enabled}
            except Exception as error:
                if sid not in self.connections:
                    if provider_id and self.trial_budget.enabled:
                        try:
                            self.provider.hangup(provider_id)
                        except Exception:
                            pass
                    self.trial_budget.finish(sid)
                message = str(error) if isinstance(error, SpeechError) else 'The live connection could not start.'
                self._session(sid, state='failed', error=message, ended_at=timestamp(), answer_sdp=None)
                raise LearningError('voice_unavailable', message, 502) from None

    def _session(self, sid, **fields):
        with transaction(self.db_path, write=True) as conn:
            conn.execute('UPDATE live_conversation_sessions SET ' + ','.join(k+'=?' for k in fields) + ' WHERE id=?', (*fields.values(), sid))

    def heartbeat(self, access, sid):
        with transaction(self.db_path, write=True) as conn:
            self._owned(conn, access, sid)
            conn.execute('UPDATE live_conversation_sessions SET heartbeat_at=? WHERE id=?', (timestamp(), sid))
        return self.read(access, sid)

    def finish(self, access, sid):
        with transaction(self.db_path) as conn:
            session = self._owned(conn, access, sid)
        runtime = self.connections.get(sid)
        if runtime:
            runtime['stop'].set()
        elif session['state'] not in ('completed','interrupted','failed'):
            # Server restarted or browser never connected. Do not pretend a final
            # provider usage event was received. Recordings stay recoverable.
            self._session(sid, state='interrupted', ended_at=timestamp(), answer_sdp=None, end_reason='interrupted')
            if session['provider_id']:
                # Use the tracked executor so workspace eviction/guest expiry
                # cannot delete the database before final usage is recorded.
                self.executor.submit(self._close_orphan, sid, session['provider_id'])
        if not runtime:
            self._recover_recordings(sid)
            if self.reviews and json.loads(session['scenario_json']).get('seed'):
                self.reviews.request(sid)
        return self.read(access, sid)

    def review(self, access, sid):
        with self.lock:
            with transaction(self.db_path) as conn:
                self._owned(conn, access, sid)
            if sid in self.connections:
                raise LearningError('busy', 'Finish the conversation before reviewing it.', 409)
            if not self.reviews:
                raise LearningError('unavailable', 'Speaking reviews are unavailable.', 503)
            self.reviews.request(sid, retry=True)
        return self.read(access, sid)

    def _recover_recordings(self, sid):
        with transaction(self.db_path) as conn:
            rows = conn.execute("SELECT id,filename FROM live_conversation_recordings WHERE session_id=? AND state='capturing'",(sid,)).fetchall()
        for row in rows:
            try:
                if Path(row['filename']).name != row['filename']:
                    raise ValueError()
                with wave.open(str(self.root / row['filename'])) as audio:
                    count = audio.getnframes()
                    if audio.getframerate()!=24000 or audio.getnchannels()!=1 or audio.getsampwidth()!=2:
                        raise ValueError()
                with transaction(self.db_path,write=True) as conn:
                    conn.execute('UPDATE live_conversation_recordings SET state=?,sample_count=? WHERE id=?',('queued' if count>=4800 else 'silent',count,row['id']))
                if count>=4800:
                    self.dispatch(row['id'])
            except (OSError,ValueError,wave.Error,EOFError):
                with transaction(self.db_path,write=True) as conn:
                    conn.execute("UPDATE live_conversation_recordings SET state='failed',error=? WHERE id=?",('This recording was interrupted before it could be saved completely.',row['id']))

    def _close_orphan(self, sid, provider_id):
        try:
            with self.provider.attach(provider_id) as ws:
                ws.send(encoded({'type':'session.close'}))
                until=time.monotonic()+12
                while time.monotonic()<until:
                    event=json.loads(ws.recv(timeout=1))
                    if event.get('type')=='session.closed':
                        self._event(sid,event)
                        self._session(sid,final_usage_json=encoded(event.get('usage',{})))
                        self.trial_budget.finish(sid, event.get('usage'))
                        return
        except Exception:
            pass  # Already-expired provider sessions have no recoverable usage.
        if self.trial_budget.enabled:
            try:
                self.provider.hangup(provider_id)
            finally:
                self.trial_budget.finish(sid)

    def _event(self, sid, event):
        kind = event.get('type', '')
        if kind not in ('session.input_transcript.delta','session.output_transcript.delta','session.started','session.closed','error'):
            return
        if 'transcript.delta' in kind:
            if not isinstance(event.get('delta'), str):
                return
            payload = {k: event[k] for k in ('type','event_id','delta','start_ms','end_ms') if k in event}
        elif kind == 'session.closed':
            payload = {'type': kind, 'usage': event.get('usage')}
        else:
            payload = {'type': kind}
        with transaction(self.db_path, write=True) as conn:
            conn.execute('INSERT OR IGNORE INTO live_conversation_events(session_id,event_key,type,payload_json,created_at) VALUES (?,?,?,?,?)',
                         (sid, event.get('event_id') or identifier(), kind, encoded(payload), timestamp()))

    def _listen(self, sid, provider_id, runtime):
        recorder = _ReceivedAudio(self, sid)
        with transaction(self.db_path) as conn:
            scenario = json.loads(conn.execute('SELECT scenario_json FROM live_conversation_sessions WHERE id=?', (sid,)).fetchone()[0])
        ending = NaturalEnding(scenario)
        delegation = None
        if self.trial_budget.enabled:
            from services.trial_live_delegation import TrialLiveDelegation
            delegation = TrialLiveDelegation(self.config, scenario, ending, executor=self.executor)
        closing_at = None
        started = time.monotonic()
        checked_at = 0
        heartbeat_expired = False
        finalized = False
        time_warning = False
        final_usage = None
        greeting_sent = False
        try:
            with self.provider.attach(provider_id) as ws:
                runtime['ready'].set()
                while True:
                    now = time.monotonic()
                    if now - checked_at >= 1:
                        with transaction(self.db_path) as conn:
                            row = conn.execute('SELECT heartbeat_at FROM live_conversation_sessions WHERE id=?', (sid,)).fetchone()
                        heartbeat_expired = not row or timestamp() - row[0] > 35
                        checked_at = now
                    expired = heartbeat_expired or now - started >= self.max_seconds
                    if delegation and closing_at is None:
                        for command in delegation.tick():
                            ws.send(encoded(command))
                    natural_reason = ending.tick(now) if closing_at is None else None
                    if (runtime['stop'].is_set() or expired or natural_reason) and closing_at is None:
                        reason = ('user_ended' if runtime['stop'].is_set() else 'connection_lost' if heartbeat_expired
                                  else 'time_limit' if expired else natural_reason)
                        self._session(sid, state='ending', end_reason=reason)
                        if natural_reason and reason == natural_reason:
                            with transaction(self.db_path,write=True) as conn:
                                conn.execute('INSERT OR IGNORE INTO live_conversation_events(session_id,event_key,type,payload_json,created_at) VALUES (?,?,?,?,?)',
                                             (sid,'natural-ending','speaking.ending',encoded(ending.completion),timestamp()))
                        ws.send(encoded({'type':'session.close'}))
                        closing_at = time.monotonic()
                    if now - started >= self.max_seconds - 30 and not time_warning and closing_at is None:
                        time_warning = True
                        ws.send(encoded({'type':'session.instructions.append','event_id':identifier(),'delegation_id':None,
                            'content':'До конца беседы осталось около 30 секунд. Заверши текущую беседу естественно, без новых тем. Дай собеседнику ответить и попрощаться. Не объявляй таймер или оценку.'}))
                    if closing_at is not None and time.monotonic() - closing_at > 12:
                        break
                    try:
                        event = json.loads(ws.recv(timeout=1))
                    except TimeoutError:
                        continue
                    kind = event.get('type')
                    if delegation and not greeting_sent and kind in ('session.started', 'session.usage.updated', 'session.input_audio.append'):
                        greeting_sent = True
                        ws.send(encoded({'type': 'session.instructions.append', 'event_id': identifier(),
                            'delegation_id': None, 'content': 'Поприветствуй собеседника сейчас только по-русски: «' +
                            str(scenario.get('opening_ru') or scenario.get('opening') or 'Здравствуйте!') + '» Затем слушай.'}))
                    if kind == 'session.input_audio.append':
                        recorder.append(base64.b64decode(event['audio'], validate=True))
                    if closing_at is None:
                        for command in ending.receive(event, now=time.monotonic()):
                            ws.send(encoded(command))
                        if delegation:
                            for command in delegation.receive(event):
                                ws.send(encoded(command))
                    self._event(sid, event)
                    if kind == 'session.started':
                        self._session(sid, state='live', started_at=timestamp())
                    if kind == 'session.closed':
                        final_usage = event.get('usage', {})
                        self._session(sid, state='completed', final_usage_json=encoded(event.get('usage', {})))
                        finalized = True
                        break
                    if kind == 'error':
                        self._session(sid, error='The voice connection reported a problem. End this conversation and try a new one.')
        except Exception:
            runtime['error'] = 'The live connection was interrupted. Your saved recordings are kept.'
            self._session(sid, error=runtime['error'])
        finally:
            try:
                if delegation:
                    delegation.close()
                if self.trial_budget.enabled and not finalized:
                    try:
                        self.provider.hangup(provider_id)
                    except Exception:
                        pass
                try:
                    self.trial_budget.finish(sid, final_usage)
                finally:
                    recorder.finish()
            finally:
                if not finalized:
                    self._session(sid, state='interrupted')
                self._session(sid, ended_at=timestamp(), answer_sdp=None)
                try:
                    if self.trial_budget.enabled:
                        # Finish metered delegation, transcription and grading in
                        # order; independent jobs must not exhaust their own
                        # account's concurrency allowance.
                        self.executor.submit(self._trial_review, sid, scenario, delegation)
                    elif self.reviews and scenario.get('seed'):
                        self.reviews.request(sid)
                finally:
                    runtime['ready'].set()
                    runtime['closed'].set()
                    self.connections.pop(sid, None)

    def _trial_review(self, sid, scenario, delegation):
        pending = delegation.pending[2] if delegation and delegation.pending else None
        if pending and not pending.cancelled():
            try:
                pending.result(timeout=25)
            except TimeoutError:
                return  # Leave saved audio available for an explicit retry.
            except Exception:
                pass
        with transaction(self.db_path) as conn:
            queued = conn.execute("SELECT id FROM live_conversation_recordings WHERE session_id=? AND state='queued'", (sid,)).fetchall()
        for row in queued:
            self.slots.acquire()
            self._analyse(row['id'])
        if self.reviews and scenario.get('seed'):
            self.reviews.request(sid)

    def dispatch(self, rid):
        if not self.slots.acquire(blocking=False):
            return
        with transaction(self.db_path, write=True) as conn:
            row = conn.execute('SELECT state,lease_until FROM live_conversation_recordings WHERE id=?', (rid,)).fetchone()
            if not row or row['state'] in ('capturing','ready','silent') or row['lease_until'] > timestamp():
                self.slots.release()
                return
            conn.execute("UPDATE live_conversation_recordings SET state='analysing',lease_until=?,error=NULL WHERE id=?", (timestamp()+180, rid))
        self.executor.submit(self._analyse, rid)

    def _analyse(self, rid):
        try:
            with transaction(self.db_path) as conn:
                row = dict(conn.execute('SELECT r.*,s.language,s.scenario_json FROM live_conversation_recordings r JOIN live_conversation_sessions s ON s.id=r.session_id WHERE r.id=?', (rid,)).fetchone())
            transcript = json.loads(row['transcript_json']) if row['transcript_json'] else self.speech.transcribe(self.root / row['filename'])
            with transaction(self.db_path, write=True) as conn:
                conn.execute('UPDATE live_conversation_recordings SET transcript_json=? WHERE id=?', (encoded(transcript),rid))
            # New Speaking sessions get one independent audio review after the
            # call. Retain MAI's original transcription for comparison without
            # generating a second, potentially contradictory set of comments.
            assessment = None if json.loads(row['scenario_json']).get('seed') else self.ai.assess(transcript['text'],
                'This is a continuous excerpt of the customer speaking in a café role-play. '
                'It may include pauses and multiple short replies. Do not infer missing speech at clip boundaries. '
                'Assess the customer words only; the server has not acoustically verified this transcript. '
                + row['scenario_json'], row['language'])
            with transaction(self.db_path, write=True) as conn:
                conn.execute("UPDATE live_conversation_recordings SET assessment_json=?,state='ready',error=NULL WHERE id=?", (encoded(assessment) if assessment else None,rid))
        except Exception as error:
            message = str(error) if isinstance(error,SpeechError) else 'Language notes could not finish. Your recording is saved.'
            with transaction(self.db_path, write=True) as conn:
                conn.execute("UPDATE live_conversation_recordings SET state='failed',error=? WHERE id=?", (message,rid))
        finally:
            with transaction(self.db_path, write=True) as conn:
                conn.execute('UPDATE live_conversation_recordings SET lease_until=0 WHERE id=?', (rid,))
            self.slots.release()
            # Drain this activity's durable queue without making UI reads start work.
            with transaction(self.db_path) as conn:
                next_row = conn.execute("SELECT id FROM live_conversation_recordings WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
            if next_row:
                self.dispatch(next_row[0])

    def retry(self, access, sid, rid):
        self.audio(access, sid, rid)
        self.dispatch(rid)
        return self.read(access, sid)

    def audio(self, access, sid, rid):
        with transaction(self.db_path) as conn:
            self._owned(conn, access, sid)
            row = conn.execute('SELECT filename,state FROM live_conversation_recordings WHERE id=? AND session_id=?', (rid,sid)).fetchone()
        if not row or row['state'] == 'capturing':
            raise LearningError('not_found','This recording is not ready.',404)
        path = self.root / row['filename']
        if path.name != row['filename'] or not path.is_file():
            raise LearningError('not_found','This recording was not found.',404)
        return path

    def delete(self, access, sid):
        with self.lock:
            with transaction(self.db_path, write=True) as conn:
                self._owned(conn, access, sid)
                if sid in self.connections or (self.reviews and sid in self.reviews.running) or conn.execute('SELECT 1 FROM live_conversation_recordings WHERE session_id=? AND lease_until>?', (sid,timestamp())).fetchone() or conn.execute("SELECT 1 FROM speaking_reviews WHERE session_id=? AND (state='queued' OR lease_until>?)", (sid,timestamp())).fetchone():
                    raise LearningError('busy','End the conversation and let language notes finish before deleting it.',409)
                files = [r[0] for r in conn.execute('SELECT filename FROM live_conversation_recordings WHERE session_id=?',(sid,))]
                conn.execute("DELETE FROM activity_criterion_reports WHERE contract_id IN "
                             "(SELECT id FROM activity_task_contracts WHERE activity='speaking' AND task_key=?)", (sid,))
                conn.execute("DELETE FROM activity_task_contracts WHERE activity='speaking' AND task_key=?", (sid,))
                conn.execute('DELETE FROM live_conversation_sessions WHERE id=?',(sid,))
            for filename in files:
                if Path(filename).name == filename:
                    (self.root / filename).unlink(missing_ok=True)
        return {'deleted':True}


class _ReceivedAudio:
    """Contiguous, untrimmed mono PCM. Silence only chooses excerpt boundaries."""
    def __init__(self, service, sid):
        self.service, self.sid = service, sid
        self.writer = None
        self.total = self.count = self.ordinal = self.silence = self.peak = 0
        self.rid = None

    def append(self, data):
        if not data:
            return
        if len(data) % 2:
            raise ValueError('Incomplete PCM sample')
        if self.writer is None:
            self.service.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.rid = identifier()
            self.ordinal += 1
            filename = self.rid + '.wav'
            self.writer = wave.open(str(self.service.root / filename), 'wb')
            self.writer.setparams((1,2,24000,0,'NONE','not compressed'))
            with transaction(self.service.db_path, write=True) as conn:
                conn.execute('INSERT INTO live_conversation_recordings(id,session_id,ordinal,filename,start_sample,created_at) VALUES (?,?,?,?,?,?)',
                    (self.rid,self.sid,self.ordinal,filename,self.total,timestamp()))
        self.writer.writeframes(data)
        samples = array('h', data)
        peak = max(abs(value) for value in samples)
        self.peak = max(self.peak,peak)
        self.silence = self.silence + len(samples) if peak < 300 else 0
        self.count += len(samples)
        self.total += len(samples)
        if self.count >= 40*24000 or (self.count >= 8*24000 and self.silence >= 24000 and self.peak >= 300):
            self.finish()

    def finish(self):
        if self.writer is None:
            return
        self.writer.close()
        state = 'silent' if self.peak < 20 or self.count < 4800 else 'queued'
        with transaction(self.service.db_path, write=True) as conn:
            conn.execute('UPDATE live_conversation_recordings SET sample_count=?,state=? WHERE id=?',(self.count,state,self.rid))
        rid = self.rid
        self.writer = None
        self.count = self.silence = self.peak = 0
        if state == 'queued' and not self.service.trial_budget.enabled:
            self.service.dispatch(rid)
