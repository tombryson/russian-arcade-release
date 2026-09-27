"""Durable guided dialogues with cached speech prepared at each conversation step."""
import json
from pathlib import Path
import random
import threading

from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, require_access, timestamp, transaction
from repositories.speaking_repository import catalogue, choose_variant, validate_level
from repositories.speaking_history import recent_variants
from services.ai_trial_budget import TrialDenied
from services.conversation_service import valid_key
from services.progression import award
from services.speech_provider import SpeechError
from services.step_conversation_ai import validate_dialogue
from services.trial_provider import trial_enabled


class StepConversationService:
    def __init__(self, db_path, speech, ai, config):
        self.db_path, self.speech, self.ai, self.config = db_path, speech, ai, config
        self.root = Path(db_path).resolve().parent / 'step-conversation-audio'
        self.audio_lock = threading.Lock()
        self.preparation_lock = threading.Lock()
        self.preparing = set()
        self.preparation_slots = threading.BoundedSemaphore(2)

    def _owned(self, conn, access, sid):
        profile = require_access(conn, access, timestamp())
        row = conn.execute('SELECT * FROM step_conversation_sessions WHERE id=? AND profile_id=?',
                           (sid, profile['id'])).fetchone()
        if not row:
            raise LearningError('not_found', 'This step-through conversation was not found.', 404)
        return dict(row)

    def _enabled(self):
        return not trial_enabled(self.config) or bool(self.config.get('AI_TRIAL_ENABLED'))

    def _require_provider(self, audio=False):
        if not self._enabled():
            raise TrialDenied('AI generation is paused. Saved practice is still available.')
        key = 'ELEVENLABS_API_KEY' if audio else 'OPENAI_API_KEY'
        if not self.config.get(key):
            raise LearningError('audio_unavailable' if audio else 'ai_unavailable',
                'Speech playback is not available. You can still read the dialogue.' if audio else
                'Step-through dialogue preparation is not available on this installation.', 503)

    def _history(self, conn, profile_id):
        result = []
        for row in conn.execute('SELECT id,state,created_at,target_level,scenario_json FROM step_conversation_sessions '
                                'WHERE profile_id=? ORDER BY created_at DESC,rowid DESC LIMIT 12', (profile_id,)):
            item = dict(row)
            scenario = json.loads(item.pop('scenario_json'))
            item.update(title=scenario.get('title'), title_ru=scenario.get('title_ru'), scenario=scenario)
            result.append(item)
        return result

    def history(self, access):
        with transaction(self.db_path) as conn:
            profile = require_access(conn, access, timestamp())
            return {'sessions': self._history(conn, profile['id'])}

    def options(self, access, exclude_seed=None, scenario_id='cafe', level=None):
        validate_level(level)
        with transaction(self.db_path) as conn:
            profile = require_access(conn, access, timestamp())
            listing = catalogue(conn, level)
            selected = next((item for item in listing['scenarios'] if item['id'] == scenario_id), None)
            available = selected['variant_count'] if selected else 0
            recent = recent_variants(conn, profile['id'], scenario_id, level)
            scenario = None if level is not None and selected is not None and not available else choose_variant(
                conn, scenario_id, level=level, previous_seeds=([exclude_seed] if exclude_seed else []) + recent)
            sessions = self._history(conn, profile['id'])
        return {'scenario': scenario, 'scenario_id': scenario_id, 'selected_level': level,
                'available_count': available, 'levels': listing['levels'], 'sessions': sessions,
                'configured': scenario is not None and self._enabled() and bool(self.config.get('OPENAI_API_KEY')),
                'audio_configured': self._enabled() and bool(self.config.get('ELEVENLABS_API_KEY'))}

    def start(self, access, body):
        key = valid_key(body.get('submission_id'))
        level = validate_level(body.get('target_level'))
        if not isinstance(body.get('scenario_id', 'cafe'), str):
            raise LearningError('invalid_input', 'Choose an available speaking scenario.')
        language = body.get('language', 'en')
        if language not in ('en', 'ru'):
            raise LearningError('invalid_input', 'Choose English or Russian for the interface.')
        request_hash = payload_hash({'scenario_id': body.get('scenario_id', 'cafe'),
            'scenario_seed': body.get('scenario_seed'), 'target_level': level, 'language': language})
        created = False
        with transaction(self.db_path, write=True) as conn:
            profile = require_access(conn, access, timestamp())
            previous = conn.execute('SELECT id,request_hash FROM step_conversation_sessions WHERE profile_id=? AND start_key=?',
                                    (profile['id'], key)).fetchone()
            if previous:
                if previous['request_hash'] != request_hash:
                    raise LearningError('conflict', 'This start request belongs to a different dialogue.', 409)
                sid = previous['id']
            else:
                self._require_provider()
                scenario_id = body.get('scenario_id', 'cafe')
                recent = recent_variants(conn, profile['id'], scenario_id, level)
                scenario = choose_variant(conn, scenario_id, seed=body.get('scenario_seed'), level=level, previous_seeds=recent)
                sid, created = identifier(), True
                voices = self.config.get('ELEVENLABS_VOICE_IDS') or ['']
                conn.execute('INSERT INTO step_conversation_sessions(id,profile_id,start_key,request_hash,scenario_id,variant_id,'
                    'scenario_json,target_level,language,voice_id,state,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (sid, profile['id'], key, request_hash, scenario_id, scenario['seed'], encoded(scenario),
                     scenario.get('target_level'), language, random.choice(voices), 'preparing', timestamp()))
        if created:
            if self._prepare(access, sid):
                return self._prepare_current_audio(access, sid)
        return self.read(access, sid)

    def _prepare(self, access, sid):
        # An expired durable lease does not permit overlap with a still-running
        # request in this process. Never queue requests behind slow providers.
        with self.preparation_lock:
            if sid in self.preparing:
                return
            if not self.preparation_slots.acquire(blocking=False):
                raise LearningError('busy', 'Other dialogues are being prepared. Please retry shortly.', 409)
            self.preparing.add(sid)
        try:
            return self._generate(access, sid)
        finally:
            with self.preparation_lock:
                self.preparing.discard(sid)
                self.preparation_slots.release()

    def _generate(self, access, sid):
        # Claim before leaving the transaction; concurrent explicit retries
        # cannot purchase another dialogue. A process crash expires this lease.
        with transaction(self.db_path, write=True) as conn:
            saved = self._owned(conn, access, sid)
            if saved['dialogue_json'] or saved['lease_until'] > timestamp():
                return
            self._require_provider()
            attempt = identifier()
            conn.execute("UPDATE step_conversation_sessions SET state='preparing',lease_until=?,preparation_id=?,error=NULL WHERE id=?",
                         (timestamp() + 180, attempt, sid))
        try:
            scenario = json.loads(saved['scenario_json'])
            dialogue = validate_dialogue(self.ai.step_dialogue(scenario), scenario)
            for turn in dialogue['turns']:
                turn['id'] = identifier()
                options = [{'id': identifier(), 'correct': True, **turn.pop('correct')},
                           *[{'id': identifier(), 'correct': False, **item} for item in turn.pop('distractors')]]
                random.SystemRandom().shuffle(options)
                turn['options'] = options
            with transaction(self.db_path, write=True) as conn:
                published = conn.execute("UPDATE step_conversation_sessions SET dialogue_json=?,state='active',lease_until=0,preparation_id=NULL,error=NULL "
                             'WHERE id=? AND preparation_id=? AND dialogue_json IS NULL', (encoded(dialogue), sid, attempt))
                return published.rowcount == 1
        except Exception as error:
            message = str(error) if isinstance(error, (SpeechError, TrialDenied)) else 'The dialogue could not be prepared. Please retry.'
            with transaction(self.db_path, write=True) as conn:
                conn.execute("UPDATE step_conversation_sessions SET state='failed',lease_until=0,preparation_id=NULL,error=? "
                             'WHERE id=? AND preparation_id=? AND dialogue_json IS NULL', (message, sid, attempt))
            if isinstance(error, TrialDenied):
                raise

    def retry(self, access, sid):
        with transaction(self.db_path) as conn:
            saved = self._owned(conn, access, sid)
            if saved['state'] not in ('failed', 'preparing'):
                return self._project(saved)
        if self._prepare(access, sid):
            return self._prepare_current_audio(access, sid)
        return self.read(access, sid)

    def read(self, access, sid):
        with transaction(self.db_path) as conn:
            return self._project(self._owned(conn, access, sid))

    def _url(self, sid, tid, kind):
        return f'/api/v1/step-conversations/{sid}/audio/{tid}/{kind}' if self._path(sid, tid, kind).is_file() else None

    def _path(self, sid, tid, kind):
        return self.root / f'{sid}-{tid}-{kind}.mp3'

    def _project(self, saved):
        dialogue = json.loads(saved['dialogue_json']) if saved['dialogue_json'] else None
        progress = json.loads(saved['progress_json'])
        result = {key: saved[key] for key in ('id', 'state', 'target_level', 'language', 'created_at', 'error')}
        result.update(scenario=json.loads(saved['scenario_json']), retryable=saved['state'] in ('preparing', 'failed') and saved['lease_until'] <= timestamp(),
            turn_count=len(dialogue['turns']) if dialogue else 0, completed_turns=saved['current_index'], current_turn=None,
            transcript=[], reward={'amount': saved['reward_amount'], 'basis': 'guided_step_completion'},
            audio_configured=self._enabled() and bool(self.config.get('ELEVENLABS_API_KEY')))
        if not dialogue:
            return result
        for index, turn in enumerate(dialogue['turns']):
            state = progress.get(turn['id'], {})
            if state.get('answered'):
                reply = next(item for item in turn['options'] if item['correct'])
                result['transcript'].append({'id': turn['id'], 'ordinal': index + 1, 'npc': turn['npc'],
                                             'reply': {key: reply[key] for key in ('russian', 'english')}})
            if index == saved['current_index'] and saved['state'] == 'active':
                result['current_turn'] = {'id': turn['id'], 'ordinal': index + 1, 'npc': turn['npc'], 'intent': turn['intent'],
                    'options': [{key: item[key] for key in ('id', 'russian')} for item in turn['options']],
                    'hint': turn['hint'] if state.get('hint_used') else None, 'answered': bool(state.get('answered')),
                    'feedback': state.get('feedback'), 'npc_audio_url': self._url(saved['id'], turn['id'], 'npc'),
                    'npc_audio_error': state.get('audio_errors', {}).get('npc'),
                    'reply_audio_url': self._url(saved['id'], turn['id'], 'reply') if state.get('answered') else None}
        if saved['state'] == 'completed':
            result['ending'] = dialogue['ending']
            result['ending_audio_url'] = self._url(saved['id'], 'ending', 'ending')
            result['ending_audio_error'] = progress.get('ending', {}).get('audio_errors', {}).get('ending')
        return result

    def _current(self, saved, turn_id):
        dialogue = json.loads(saved['dialogue_json']) if saved['dialogue_json'] else None
        if saved['state'] != 'active' or not dialogue or dialogue['turns'][saved['current_index']]['id'] != turn_id:
            raise LearningError('stale_turn', 'This dialogue has moved on. Reload it before continuing.', 409)
        return dialogue['turns'][saved['current_index']], json.loads(saved['progress_json'])

    def answer(self, access, sid, body):
        submission = valid_key(body.get('submission_id'))
        turn_id, option_id = valid_key(body.get('turn_id')), valid_key(body.get('option_id'))
        with transaction(self.db_path, write=True) as conn:
            saved = self._owned(conn, access, sid)
            previous = conn.execute('SELECT turn_id,option_id FROM step_conversation_answers WHERE session_id=? AND submission_id=?',
                                    (sid, submission)).fetchone()
            if previous:
                if (previous['turn_id'], previous['option_id']) != (turn_id, option_id):
                    raise LearningError('conflict', 'This answer submission belongs to a different choice.', 409)
                return self._project(saved)
            turn, progress = self._current(saved, turn_id)
            state = progress.setdefault(turn_id, {})
            if state.get('answered'):
                raise LearningError('stale_turn', 'This reply is already complete. Continue to the next line.', 409)
            option = next((item for item in turn['options'] if item['id'] == option_id), None)
            if option is None:
                raise LearningError('invalid_option', 'Choose a reply shown for this turn.')
            state.update(answered=option['correct'], feedback={'option_id': option_id, 'correct': option['correct'],
                         'explanation': option['explanation'], 'english': option['english']})
            conn.execute('INSERT INTO step_conversation_answers VALUES (?,?,?,?,?,?)',
                         (sid, submission, turn_id, option_id, int(option['correct']), timestamp()))
            conn.execute('UPDATE step_conversation_sessions SET progress_json=? WHERE id=?', (encoded(progress), sid))
            saved['progress_json'] = encoded(progress)
            return self._project(saved)

    def hint(self, access, sid, body):
        turn_id = valid_key(body.get('turn_id'))
        with transaction(self.db_path, write=True) as conn:
            saved = self._owned(conn, access, sid)
            turn, progress = self._current(saved, turn_id)
            progress.setdefault(turn['id'], {})['hint_used'] = True
            saved['progress_json'] = encoded(progress)
            conn.execute('UPDATE step_conversation_sessions SET progress_json=? WHERE id=?', (saved['progress_json'], sid))
            return self._project(saved)

    def next(self, access, sid, body):
        turn_id = valid_key(body.get('turn_id'))
        with transaction(self.db_path, write=True) as conn:
            saved = self._owned(conn, access, sid)
            dialogue = json.loads(saved['dialogue_json']) if saved['dialogue_json'] else None
            if dialogue and any(turn['id'] == turn_id for turn in dialogue['turns'][:saved['current_index']]):
                return self._project(saved)  # Replay of an already committed advance.
            turn, progress = self._current(saved, turn_id)
            if not progress.get(turn['id'], {}).get('answered'):
                raise LearningError('answer_required', 'Choose the reply that matches your intent before continuing.', 409)
            saved['current_index'] += 1
            if saved['current_index'] == len(dialogue['turns']):
                saved['state'] = 'completed'
                # Save the completed evidence before the shared course adapter
                # reads it, inside this same transaction.
                conn.execute("UPDATE step_conversation_sessions SET state='completed' WHERE id=?", (sid,))
                scenario = json.loads(saved['scenario_json'])
                saved['reward_amount'] = award(conn, saved['profile_id'], activity='speaking_step',
                    content_key=saved['variant_id'], source_key=sid, title='Step-through · ' + scenario['title'],
                    target_level=saved['target_level'], evidence={'basis': 'guided_step_completion', 'turn_count': len(dialogue['turns'])})
            conn.execute('UPDATE step_conversation_sessions SET current_index=?,state=?,reward_amount=?,completed_at=? WHERE id=?',
                         (saved['current_index'], saved['state'], saved['reward_amount'], timestamp() if saved['state'] == 'completed' else None, sid))
        # Commit the answer and advancement before requesting speech. A provider
        # failure must never undo a learner's progress or completion reward.
        return self._prepare_current_audio(access, sid)

    def _prepare_current_audio(self, access, sid):
        """Called only by a new explicit transition, never a read or replay."""
        state = self.read(access, sid)
        if not state['audio_configured']:
            return state
        if state['state'] == 'active':
            tid, kind = state['current_turn']['id'], 'npc'
        elif state['state'] == 'completed':
            tid, kind = 'ending', 'ending'
        else:
            return state
        try:
            return self.prepare_audio(access, sid, {'turn_id': tid, 'kind': kind})
        except Exception as error:
            # Save a recoverable problem instead of making the client repeat a
            # paid request automatically after receiving the dialogue.
            message = str(error) if isinstance(error, (LearningError, SpeechError, TrialDenied)) else (
                'Audio could not be prepared. Try Listen again.')
            self._audio_error(access, sid, tid, kind, message)
            return self.read(access, sid)

    def _audio_error(self, access, sid, tid, kind, message):
        with transaction(self.db_path, write=True) as conn:
            saved = self._owned(conn, access, sid)
            progress = json.loads(saved['progress_json'])
            errors = progress.setdefault(tid, {}).setdefault('audio_errors', {})
            if message:
                errors[kind] = message
            else:
                errors.pop(kind, None)
            conn.execute('UPDATE step_conversation_sessions SET progress_json=? WHERE id=?', (encoded(progress), sid))

    def _audio_turn(self, saved, tid, kind):
        if kind not in ('npc', 'reply', 'ending'):
            raise LearningError('invalid_input', 'Choose a line from this conversation.')
        dialogue = json.loads(saved['dialogue_json']) if saved['dialogue_json'] else None
        if dialogue:
            if kind == 'ending':
                if tid == 'ending' and saved['state'] == 'completed':
                    return dialogue['ending']['russian']
                raise LearningError('not_found', 'This line is not available for playback.', 404)
            progress = json.loads(saved['progress_json'])
            for index, turn in enumerate(dialogue['turns']):
                if turn['id'] == tid and index <= saved['current_index']:
                    if kind == 'npc':
                        return turn['npc']['russian']
                    if progress.get(tid, {}).get('answered'):
                        return next(option['russian'] for option in turn['options'] if option['correct'])
        raise LearningError('not_found', 'This line is not available for playback.', 404)

    def prepare_audio(self, access, sid, body):
        tid, kind = valid_key(body.get('turn_id')), body.get('kind')
        with transaction(self.db_path) as conn:
            saved = self._owned(conn, access, sid)
            text = self._audio_turn(saved, tid, kind)
        target = self._path(saved['id'], tid, kind)
        if target.is_file():
            if json.loads(saved['progress_json']).get(tid, {}).get('audio_errors', {}).get(kind):
                self._audio_error(access, sid, tid, kind, None)
            return self.read(access, sid)
        if not self.audio_lock.acquire(blocking=False):
            raise LearningError('busy', 'Speech playback is being prepared. Please wait a moment and retry.', 409)
        try:
            if not target.is_file():
                self._require_provider(audio=True)
                try:
                    audio = self.speech.speak(text, saved['voice_id'])
                except SpeechError as error:
                    raise LearningError('audio_unavailable', str(error), 502) from None
                if not isinstance(audio, bytes) or not 1 <= len(audio) <= 8 * 1024 * 1024:
                    raise LearningError('audio_unavailable', 'Speech playback could not be prepared.', 502)
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                temporary = target.with_suffix('.tmp')
                temporary.write_bytes(audio)
                temporary.replace(target)
        finally:
            self.audio_lock.release()
        self._audio_error(access, sid, tid, kind, None)
        return self.read(access, sid)

    def audio(self, access, sid, tid, kind):
        with transaction(self.db_path) as conn:
            saved = self._owned(conn, access, sid)
            self._audio_turn(saved, tid, kind)
        path = self._path(saved['id'], tid, kind)
        if not path.is_file():
            raise LearningError('not_found', 'Speech playback is not ready.', 404)
        return path
