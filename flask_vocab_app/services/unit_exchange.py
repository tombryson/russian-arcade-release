"""A bounded, owned two-turn Speaking task using original audio review."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import wave

from flask import session, has_request_context

from contracts.curriculum import validate_task_contract, validate_judgements
from repositories import activity_review_repository as reviews
from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, timestamp, transaction
from services.activity_review_submissions import _binding, _outcome, prior_feedback, safe_scene
from services.assessment_pilot import verify_recording, _safe_bytes
from services.speech_provider import SpeechError, audio_info, wav_copy
from utils.activity_owner import activity_profile_id


def _profile(conn):
    if has_request_context():
        from utils.household_access import active_profile_id
        return active_profile_id(conn)
    return activity_profile_id(conn)


def owned_task(conn, profile_id, identity):
    row = conn.execute('SELECT * FROM curriculum_unit_exchanges WHERE id=? AND profile_id=?', (identity, profile_id)).fetchone()
    if row is None:
        raise LearningError('not_found', 'This Speaking task is not available for the selected profile.', 404)
    task = dict(row)
    task['asset'] = json.loads(task.pop('asset_json'))
    task['contract'] = json.loads(task.pop('contract_json'))
    validate_task_contract(task['contract'])
    from services.curriculum_sequence_content import task_contract
    if task_contract(task['asset'], identity, purpose='diagnostic') != task['contract']:
        raise ValueError('The Speaking task changed after allocation.')
    return task


def create_in_transaction(conn, profile_id, asset, contract_factory):
    if asset['kind'] != 'speaking' or len(asset['content']['turns']) != 2:
        raise ValueError('A unit exchange needs exactly two authored prompts.')
    identity = identifier()
    contract = contract_factory(asset, identity, purpose='diagnostic')
    conn.execute('INSERT INTO curriculum_unit_exchanges VALUES (?,?,?,?,0,?)',
                 (identity, profile_id, encoded(asset), encoded(contract), timestamp()))
    from services.activity_evidence import save_contract
    save_contract(conn, profile_id, 'unit_exchange', identity, contract)
    return {'activity': 'unit_exchange', 'task_key': identity, 'href': f'/#unit-exchange/{identity}'}


def exchange_work_state(conn, profile_id, identity):
    owned_task(conn, profile_id, identity)
    row = conn.execute("SELECT review_status FROM activity_review_submissions WHERE profile_id=? AND activity='unit_exchange' AND task_key=? ORDER BY rowid DESC LIMIT 1", (profile_id, identity)).fetchone()
    if row:
        return row[0]
    return 'draft' if conn.execute('SELECT 1 FROM curriculum_unit_exchange_turns WHERE exchange_id=?', (identity,)).fetchone() else 'not_started'


def scenario_for_contract(contract):
    content = contract['content']
    return {'scenario_id': 'curriculum-unit-exchange', 'seed': contract['content_version'], 'title': 'Two short replies',
            'target_level': contract['level'], 'scene': content['scene'], 'turns': content['turns'],
            'goals': [{'id': criterion['id'], 'label': criterion['expectation']}
                      for criterion in contract['criteria'] if criterion['evidence_scope'] == 'reference']}


def audio_root(db_path):
    return Path(db_path).resolve().parent / 'unit-exchange-audio'


def recorded_source(conn, profile_id, identity, root=None):
    """Reconstruct a canonical waveform only from saved, hash-verified originals."""
    task = owned_task(conn, profile_id, identity)
    if root is None:
        db_path = conn.execute('PRAGMA database_list').fetchone()[2]
        root = audio_root(db_path)
    rows = {r['turn_id']: dict(r) for r in conn.execute('SELECT * FROM curriculum_unit_exchange_turns WHERE exchange_id=? AND profile_id=?', (identity, profile_id))}
    data, recordings, position = bytearray(), [], 0
    for turn in task['asset']['content']['turns']:
        if turn['id'] not in rows:
            raise LearningError('incomplete_exchange', 'Save both replies before requesting feedback.', 409)
        manifest = json.loads(rows[turn['id']]['audio_json'])
        path = verify_recording(Path(root), manifest)
        with wave.open(str(path), 'rb') as clip:
            if clip.getframerate() != 16000 or clip.getnchannels() != 1 or clip.getsampwidth() != 2:
                raise ValueError('The saved review recording has unsupported audio parameters.')
            raw = clip.readframes(clip.getnframes())
        length = len(raw) // 2
        data.extend(raw)
        recordings.append({'turn_id': turn['id'], 'sha256': manifest['sha256'], 'assessment_sha256': manifest['assessment_sha256'],
                           'start_ms': position * 1000 // 16000, 'end_ms': (position + length) * 1000 // 16000})
        position += length
    out = io.BytesIO()
    with wave.open(out, 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000); output.writeframes(bytes(data))
    waveform = out.getvalue()
    return {'sha256': hashlib.sha256(waveform).hexdigest(), 'duration_ms': position * 1000 // 16000, 'recordings': recordings}, waveform


def turn_windows(contract, recordings, duration_ms):
    """Bind each heard prompt to its own immutable learner recording interval."""
    turns = contract['content']['turns']
    mapping = contract['content'].get('criterion_turns')
    if (not isinstance(recordings, list) or len(recordings) != len(turns)
            or not isinstance(mapping, dict)
            or set(mapping) != {criterion['id'] for criterion in contract['criteria']}):
        raise ValueError('Speaking criteria need their recorded reply boundaries.')
    known = {turn['id'] for turn in turns}
    for required in mapping.values():
        if (not isinstance(required, list) or not required or any(value not in known for value in required)
                or len(set(required)) != len(required)):
            raise ValueError('A Speaking criterion refers to an unknown reply.')
    end, windows = 0, []
    for turn, recorded in zip(turns, recordings):
        if (not isinstance(recorded, dict) or recorded.get('turn_id') != turn['id']
                or type(recorded.get('start_ms')) is not int or type(recorded.get('end_ms')) is not int
                or recorded['start_ms'] != end or recorded['end_ms'] <= end):
            raise ValueError('The Speaking reply intervals are incomplete or out of order.')
        end = recorded['end_ms']
        windows.append({'turn_id': turn['id'], 'prompt': turn['prompt'],
                        'start_ms': recorded['start_ms'], 'end_ms': end,
                        'criterion_ids': [identity for identity, required in mapping.items() if turn['id'] in required]})
    if type(duration_ms) is not int or end != duration_ms:
        raise ValueError('The Speaking replies do not cover the original audio.')
    return windows


def validate_turn_evidence(contract, report, source):
    """One reply cannot establish that a different question was answered."""
    windows = {item['turn_id']: item for item in turn_windows(contract, source['recordings'], source['duration_ms'])}
    validate_judgements(contract, report['criterion_report'], audio_duration_ms=source['duration_ms'])
    for judgement in report['criterion_report']['judgements']:
        required = contract['content']['criterion_turns'][judgement['criterion_id']]
        covered = set()
        for span in judgement['evidence']:
            matches = {turn_id for turn_id in required
                       if windows[turn_id]['start_ms'] <= span['start_ms'] < span['end_ms'] <= windows[turn_id]['end_ms']}
            if not matches:
                raise ValueError('Speaking evidence lies outside its elicited reply.')
            covered.update(matches)
        if judgement['score'] is not None and covered != set(required):
            raise ValueError('Scored Speaking criteria need evidence from every required reply.')
    return report


def saved_review(conn, profile_id, identity, source_key, *, root=None):
    saved = reviews.get(conn, profile_id, source_key)
    if saved['activity'] != 'unit_exchange' or saved['task_key'] != identity or not saved['result']:
        raise ValueError('The original-audio report belongs to a different task.')
    source, _ = recorded_source(conn, profile_id, identity, root)
    if source != saved['result']['audio_source']:
        raise ValueError('The saved original recordings have changed.')
    validate_turn_evidence(saved['contract'], saved['result'], source)
    return saved['result']['criterion_report'], source


class UnitExchangeService:
    def __init__(self, db_path, assessor):
        self.db_path, self.assessor = db_path, assessor
        self.root = audio_root(db_path)

    @staticmethod
    def _current(conn, task):
        saved = {row[0] for row in conn.execute('SELECT turn_id FROM curriculum_unit_exchange_turns WHERE exchange_id=?', (task['id'],))}
        return next((turn for turn in task['asset']['content']['turns'] if turn['id'] not in saved), None)

    @staticmethod
    def _prompt_path(turn):
        audio = turn.get('audio')
        if not isinstance(audio, dict) or not isinstance(audio.get('url'), str) or not audio['url'].startswith('/static/audio/'):
            raise LearningError('audio_unavailable', 'This spoken prompt is unavailable. Return to the lesson and try another activity.', 409)
        root = Path(__file__).resolve().parents[1] / 'static'
        path = root / audio['url'].removeprefix('/static/')
        try:
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError()
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != audio['sha256'] or len(data) != audio['size_bytes']:
                raise ValueError()
            return path
        except (ValueError, KeyError, OSError):
            raise LearningError('audio_unavailable', 'The original spoken prompt is unavailable.', 409) from None

    def read(self, identity):
        with transaction(self.db_path) as conn:
            owner = _profile(conn)
            task = owned_task(conn, owner, identity)
            _binding(conn, owner, 'unit_exchange', identity)
            from services.curriculum_sequences import activity_context
            context = activity_context(conn, owner, 'unit_exchange', identity)
            current = self._current(conn, task)
            turns = []
            for turn in task['asset']['content']['turns']:
                found = conn.execute('SELECT 1 FROM curriculum_unit_exchange_turns WHERE exchange_id=? AND turn_id=?', (identity, turn['id'])).fetchone()
                turns.append({'id': turn['id'], 'saved': bool(found), 'recording_url': f'/api/v1/unit-exchanges/{identity}/turns/{turn["id"]}/audio' if found else None})
            availability = 'available'
            if current:
                try:
                    self._prompt_path(current)
                    available = True
                except LearningError:
                    available = False; availability = 'audio_unavailable'
                playbacks = conn.execute('SELECT COUNT(*) FROM curriculum_unit_exchange_playback WHERE exchange_id=? AND turn_id=?', (identity, current['id'])).fetchone()[0]
                current = {'id': current['id'], 'audio_url': f'/api/v1/unit-exchanges/{identity}/turns/{current["id"]}/prompt-audio' if available else None,
                           'audio_available': available, 'listened': bool(playbacks), 'playbacks': playbacks,
                           'plays_remaining': max(0, 1 + task['asset']['content'].get('repeat_limit', 1) - playbacks)}
            saved = conn.execute("SELECT * FROM activity_review_submissions WHERE profile_id=? AND activity='unit_exchange' AND task_key=? ORDER BY rowid DESC LIMIT 1", (owner, identity)).fetchone()
            result = reviews.public(reviews.decode(saved)) if saved else {}
            from services.feedback_study import actions as study_actions
            followups = study_actions(conn, owner, 'unit_exchange', saved['id']) if saved and saved['review_status'] == 'reviewed' else []
            ru = has_request_context() and session.get('ui_lang') == 'ru'
            closing_audio = None
            if current is None:
                try:
                    self._prompt_path(task['asset']['content']['closing'])
                    closing_audio = f'/api/v1/unit-exchanges/{identity}/closing-audio'
                except LearningError:
                    pass
            return {'id': identity, 'profile_id': owner, 'revision': task['revision'], 'title': task['asset']['title'], 'title_ru': task['asset']['title_ru'],
                    'prompt': 'Послушайте Нину и ответьте. Две короткие реплики.' if ru else 'Listen and reply to Nina. Two short replies.',
                    'scene': safe_scene(task['asset']['content']),
                    'current_turn': current, 'turns': turns, 'work_state': exchange_work_state(conn, owner, identity),
                    'availability': result.get('availability', availability), 'condition': 'unverified',
                    'support': reviews.decode(saved)['support'] if saved else [], 'submission_id': result.get('id'),
                    'feedback': result.get('feedback'), 'outcome': result.get('outcome'),
                    'study_actions': followups,
                    'closing': task['asset']['content']['closing']['text'] if current is None else None,
                    'closing_audio_url': closing_audio,
                    'origin': {'href': context['lesson_url'] if context else '/curriculum/units/' + task['asset']['unit_id'], 'title': 'Вернуться к уроку' if ru else 'Back to lesson'}}

    def listened(self, identity, turn_id, data):
        if not isinstance(data, dict) or set(data) != {'submission_id', 'expected_revision'}:
            raise LearningError('invalid_input', 'Use the current playback controls.')
        digest = payload_hash({'task': identity, 'turn': turn_id, **data})
        with transaction(self.db_path, write=True) as conn:
            owner = _profile(conn); task = owned_task(conn, owner, identity)
            previous = conn.execute('SELECT request_sha256 FROM curriculum_unit_exchange_playback WHERE profile_id=? AND request_id=?', (owner, data['submission_id'])).fetchone()
            if previous:
                if previous[0] != digest:
                    raise LearningError('submission_conflict', 'That playback receipt belongs to another prompt.', 409)
            else:
                turn = self._current(conn, task)
                if not turn or turn['id'] != turn_id or task['revision'] != data['expected_revision']:
                    raise LearningError('stale_revision', 'Reload the saved exchange before continuing.', 409)
                self._prompt_path(turn)
                count = conn.execute('SELECT COUNT(*) FROM curriculum_unit_exchange_playback WHERE exchange_id=? AND turn_id=?', (identity, turn_id)).fetchone()[0]
                if count > task['asset']['content'].get('repeat_limit', 1):
                    raise LearningError('replay_limit', 'This prompt has reached its replay limit.', 409)
                conn.execute('INSERT INTO curriculum_unit_exchange_playback VALUES (?,?,?,?,?,?,?)',
                             (identity, owner, turn_id, data['submission_id'], digest, turn['audio']['sha256'], timestamp()))
                conn.execute('UPDATE curriculum_unit_exchanges SET revision=revision+1 WHERE id=?', (identity,))
        return self.read(identity)

    def record(self, identity, turn_id, data, extension, request_id, revision):
        if extension not in ('wav', 'webm', 'mp4', 'ogg', 'mp3') or not 0 < len(data) <= 8 * 1024 * 1024 or not request_id:
            raise LearningError('invalid_audio', 'Send a playable original recording no longer than 60 seconds.')
        digest = payload_hash({'task': identity, 'turn': turn_id, 'audio_sha256': hashlib.sha256(data).hexdigest(), 'revision': revision})
        with transaction(self.db_path) as conn:
            owner = _profile(conn); owned_task(conn, owner, identity)
            previous = conn.execute('SELECT request_sha256 FROM curriculum_unit_exchange_turns WHERE profile_id=? AND request_id=?', (owner, request_id)).fetchone()
            if previous:
                if previous[0] != digest:
                    raise LearningError('submission_conflict', 'This recording identity belongs to another reply.', 409)
                return self.read(identity)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        published = []
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            clip_id = identifier(); original = Path(directory) / f'{clip_id}.{extension}'; original.write_bytes(data)
            if audio_info(original) > 60:
                raise LearningError('invalid_audio', 'Keep this reply under 60 seconds.')
            target = Path(directory) / f'{clip_id}-review.wav'
            native = False
            if extension == 'wav':
                with wave.open(str(original), 'rb') as audio:
                    native = audio.getframerate() == 16000 and audio.getnchannels() == 1 and audio.getsampwidth() == 2
            if native:
                target.write_bytes(data)
            else:
                wav_copy(original, target)
            converted = target.read_bytes()
            with wave.open(str(target), 'rb') as audio:
                duration = audio.getnframes() * 1000 // audio.getframerate()
            manifest = {'id': clip_id, 'filename': original.name, 'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data),
                        'duration_ms': duration, 'assessment_filename': target.name, 'assessment_sha256': hashlib.sha256(converted).hexdigest(), 'assessment_size_bytes': len(converted)}
            try:
                with transaction(self.db_path, write=True) as conn:
                    if _profile(conn) != owner:
                        raise LearningError('profile_changed', 'Your profile changed. Reopen this exchange.', 409)
                    task = owned_task(conn, owner, identity); turn = self._current(conn, task)
                    policy = _binding(conn, owner, 'unit_exchange', identity)
                    if not turn or turn['id'] != turn_id or task['revision'] != revision:
                        raise LearningError('stale_revision', 'The exchange changed. Reload your saved replies.', 409)
                    self._prompt_path(turn)
                    if not conn.execute('SELECT 1 FROM curriculum_unit_exchange_playback WHERE exchange_id=? AND turn_id=?', (identity, turn_id)).fetchone():
                        raise LearningError('listen_first', 'Listen to this prompt before recording your reply.', 409)
                    for source in (original, target):
                        destination = self.root / source.name; os.link(source, destination); destination.chmod(0o600); published.append(destination)
                    verify_recording(self.root, manifest)
                    conn.execute('INSERT INTO curriculum_unit_exchange_turns VALUES (?,?,?,?,?,?,?)',
                                 (identity, owner, turn_id, request_id, digest, encoded(manifest), timestamp()))
                    conn.execute('UPDATE curriculum_unit_exchanges SET revision=revision+1 WHERE id=?', (identity,))
                    if self._current(conn, task) is None:
                        source, _ = recorded_source(conn, owner, identity, self.root)
                        records = [dict(row) for row in conn.execute('SELECT turn_id,audio_json FROM curriculum_unit_exchange_turns WHERE exchange_id=? ORDER BY rowid', (identity,))]
                        receipts = [row[0] for row in conn.execute('SELECT request_id FROM curriculum_unit_exchange_playback WHERE exchange_id=? ORDER BY rowid', (identity,))]
                        reviews.save_original(conn, profile_id=owner, activity='unit_exchange', task_key=identity, submission_id='exchange-' + identity,
                            task_revision=revision + 1, original={'recordings': [{'turn_id': row['turn_id'], 'audio': json.loads(row['audio_json'])} for row in records], 'audio_source': source},
                            task={'asset': task['asset'], 'language': session.get('ui_lang', 'en') if has_request_context() else 'en'}, contract=task['contract'],
                            support=['model_answer'] if prior_feedback(conn, owner, 'unit_exchange', {'asset': task['asset']}) else [], support_receipts=receipts, effects_policy=policy)
            except BaseException:
                for path in published:
                    path.unlink(missing_ok=True)
                raise
        return self.read(identity)

    def review(self, identity):
        with transaction(self.db_path, write=True) as conn:
            owner = _profile(conn); task = owned_task(conn, owner, identity)
            policy = _binding(conn, owner, 'unit_exchange', identity)
            row = conn.execute("SELECT id FROM activity_review_submissions WHERE profile_id=? AND activity='unit_exchange' AND task_key=?", (owner, identity)).fetchone()
            if row is None:
                raise LearningError('incomplete_exchange', 'Save both replies before requesting feedback.', 409)
            saved, token = reviews.claim(conn, owner, row[0])
            if (saved['effects_policy'] != policy or saved['contract'] != task['contract']
                    or saved['task']['asset'] != task['asset']):
                raise LearningError('invalid_saved_task', 'The saved prompt bundle changed. Your recordings remain saved.', 409)
        if token is None:
            return self.read(identity)
        try:
            with transaction(self.db_path) as conn:
                source, waveform = recorded_source(conn, owner, identity, self.root)
            scenario = scenario_for_contract(task['contract'])
            dialogue = [{'role': 'assistant', 'content': turn['prompt']} for turn in task['asset']['content']['turns']]
            with tempfile.TemporaryDirectory(dir=self.root) as directory:
                path = Path(directory) / 'review.wav'; path.write_bytes(waveform)
                report = self.assessor.assess(path, scenario, dialogue, saved['task']['language'],
                    curriculum_contract=saved['contract'], include_provenance=True, recording_turns=source['recordings'])
            validate_judgements(saved['contract'], report['criterion_report'], audio_duration_ms=source['duration_ms'])
            from services.speaking_evidence import validate_speaking_judgements
            validate_speaking_judgements(saved['contract'], report, source['duration_ms'])
            validate_turn_evidence(saved['contract'], report, source)
            with transaction(self.db_path, write=True) as conn:
                if _profile(conn) != owner:
                    raise LearningError('profile_changed', 'Your profile changed. Reopen the saved exchange.', 409)
                reviews.assert_lease(conn, owner, saved['id'], token)
                policy = _binding(conn, owner, 'unit_exchange', identity)
                current, _ = recorded_source(conn, owner, identity, self.root)
                if current != source or policy != saved['effects_policy']:
                    raise ValueError('Original recording or effects policy changed.')
                result = {**report, 'audio_source': source, 'outcome': _outcome([report['criterion_report']])}
                reviews.finish(conn, owner, saved['id'], token, {'activity': 'unit_exchange', 'id': saved['id']}, result)
                from services.activity_evidence import save_report
                save_report(conn, owner, 'unit_exchange', identity, saved['id'], report['criterion_report'], audio_source=source, support=saved['support'])
                if policy != reviews.TRANSFER_POLICY:
                    from services.progression import award_speaking
                    award_speaking(conn, {'id': 'unit-exchange:' + identity, 'profile_id': owner, 'created_at': task['created_at'],
                                         'ended_at': timestamp(), 'scenario_json': encoded(scenario)},
                        {**report, 'assisted': bool(saved['support']),
                         'skill_evidence_eligible': not any(j['outcome'] == 'insufficient_evidence' for j in report['criterion_report']['judgements'])})
        except Exception as error:
            from services.ai_trial_budget import TrialDenied
            with transaction(self.db_path, write=True) as conn:
                reviews.fail(conn, owner, saved['id'], token, 'budget_exhausted' if isinstance(error, TrialDenied) else 'provider_unavailable')
            if isinstance(error, LearningError):
                raise
        return self.read(identity)

    def original_audio(self, identity, turn_id):
        with transaction(self.db_path) as conn:
            owner = _profile(conn); owned_task(conn, owner, identity)
            row = conn.execute('SELECT audio_json FROM curriculum_unit_exchange_turns WHERE exchange_id=? AND profile_id=? AND turn_id=?', (identity, owner, turn_id)).fetchone()
            if row is None:
                raise LearningError('not_found', 'That original recording is unavailable.', 404)
            audio = json.loads(row[0]); verify_recording(self.root, audio)
            return _safe_bytes(self.root, audio['filename'], audio['sha256'], audio['size_bytes'])[0]

    def prompt_audio(self, identity, turn_id):
        with transaction(self.db_path) as conn:
            task = owned_task(conn, _profile(conn), identity)
            turn = self._current(conn, task)
            if not turn or turn['id'] != turn_id:
                raise LearningError('not_found', 'Open the current spoken prompt.', 404)
            return self._prompt_path(turn)

    def closing_audio(self, identity):
        with transaction(self.db_path) as conn:
            task = owned_task(conn, _profile(conn), identity)
            if self._current(conn, task) is not None:
                raise LearningError('incomplete_exchange', 'Save both replies before the closing line.', 409)
            return self._prompt_path(task['asset']['content']['closing'])
