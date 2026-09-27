"""Five separate diagnostic observations, with saved originals and explicit review retries."""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import wave

from contracts.curriculum import validate_judgements
from repositories.assessment_pilot_repository import AssessmentPilotRepository, DOMAINS, key, response_for, support_for
from repositories.learning_repository import LearningError, encoded, payload_hash, require_access, timestamp, transaction
from services.assessment_pilot_content import blueprint, freeze_task
from services.curriculum_requirement_map import requirement_index
from services.speech_provider import SpeechError, audio_info, wav_copy
from services.speaking_evidence import validate_speaking_judgements

MAX_UPLOAD = 8 * 1024 * 1024
REVIEW_ERROR = 'Feedback is unavailable. Your original response is saved. Retry the review when you are ready.'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _safe_bytes(root, filename, expected_hash, expected_size):
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise ValueError('Invalid recording filename.')
    root = Path(root).resolve()
    path = root / filename
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError('The original recording is unavailable.')
    data = path.read_bytes()
    if len(data) != expected_size or digest(data) != expected_hash:
        raise ValueError('The original recording has changed.')
    return path, data


def verify_recording(root, audio):
    _safe_bytes(root, audio['filename'], audio['sha256'], audio['size_bytes'])
    path, _ = _safe_bytes(root, audio['assessment_filename'], audio['assessment_sha256'], audio['assessment_size_bytes'])
    with wave.open(str(path), 'rb') as stream:
        count, rate = stream.getnframes(), stream.getframerate()
        if (stream.getnchannels() != 1 or stream.getsampwidth() != 2 or not 8000 <= rate <= 48000
                or not 0.2 <= count / rate <= 90 or len(stream.readframes(count)) != count * 2
                or count * 1000 // rate != audio['duration_ms']):
            raise ValueError('Invalid saved original-audio review source.')
    return path


def make_report(task, response, support, *, criterion_report, feedback, model, audio=None, production_feedback=None):
    source = audio['sha256'] if audio else digest((response['text'] if task['domain'] == 'writing' else encoded(response)).encode())
    validate_judgements(task['contract'], criterion_report,
                        response_text=response.get('text') if task['domain'] == 'writing' else encoded(response) if task['format'] == 'choice_set' else None,
                        audio_duration_ms=audio['duration_ms'] if audio else None)
    judgements = criterion_report['judgements']
    outcome = ('more_evidence_needed' if any(item['outcome'] == 'insufficient_evidence' for item in judgements)
               else 'demonstrated_in_task' if all(item['outcome'] == 'satisfied' for item in judgements) else 'practise_and_retry')
    provenance = production_feedback['assessment_provenance'] if production_feedback is not None else {
        'model': model, 'prompt_sha256': digest(model.encode()), 'rubric_version': task['contract']['rubric_version']}
    return {'criterion_report': criterion_report, 'feedback': feedback, 'outcome': outcome,
            'support': support, 'assisted': bool(set(support) & set(task['contract']['support']['independence_breakers'])),
            'source_sha256': source, 'assessor': {'version': 'assessment-pilot-v1', **provenance}, 'audio_source': audio,
            'production_feedback': deepcopy(production_feedback)}


def unmeasured(task, response, support, feedback, audio=None):
    report = {'contract_sha256': task['contract']['contract_sha256'], 'judgements': [
        {'criterion_id': criterion['id'], 'outcome': 'insufficient_evidence', 'score': None,
         'feedback': feedback, 'evidence': []} for criterion in task['contract']['criteria']]}
    return make_report(task, response, support, criterion_report=report, feedback=feedback, model='unmeasured', audio=audio)


class AssessmentPilotService:
    def __init__(self, db_path, writing, speaking, config):
        self.db_path, self.writing, self.speaking, self.config = db_path, writing, speaking, dict(config)
        self.repository = AssessmentPilotRepository(db_path)
        self.static = Path(__file__).resolve().parents[1] / 'static'
        self.root = Path(db_path).resolve().parent / 'assessment-pilot-audio'

    def published(self):
        result = blueprint()
        manifest_path = self.static / 'audio/course/assessment-pilot/manifest.json'
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, ValueError):
            manifest = {}
        clips = manifest.get('clips', {})
        for index, task in enumerate(result['forms']['listening']):
            clip = clips.get('a1-pilot-' + task['form_id'] + '-v1', clips.get(task['form_id'], {}))
            audio = None
            try:
                path = self.static / task['audio_url'].removeprefix('/static/')
                data = path.read_bytes()
                if (clip.get('text_sha256', clip.get('transcript_sha256')) != digest(task['transcript'].encode())
                        or clip.get('audio_sha256') != digest(data)):
                    raise ValueError('Pilot source does not match its manifest.')
                audio = {'url': task['audio_url'], 'sha256': digest(data), 'size_bytes': len(data),
                         'duration_ms': int(clip['duration_ms']) if 'duration_ms' in clip else int(clip['duration'] * 1000)}
            except (OSError, ValueError, KeyError, TypeError):
                pass
            result['forms']['listening'][index] = freeze_task(task, audio=audio)
        return result

    def verify_listening(self, task):
        audio = task.get('audio')
        if not audio:
            raise LearningError('audio_unavailable', 'This recording is unavailable. Reveal the transcript for supported practice.', 409)
        root = self.static.resolve()
        path = root / audio['url'].removeprefix('/static/')
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
                raise ValueError()
            data = path.read_bytes()
            if len(data) != audio['size_bytes'] or digest(data) != audio['sha256']:
                raise ValueError()
        except (OSError, ValueError):
            raise LearningError('audio_unavailable', 'The original recording is unavailable. Reveal the transcript for supported practice.', 409) from None
        return path

    def catalogue(self, access):
        public = blueprint()
        listening_available = all(task.get('audio') for task in self.published()['forms']['listening'])
        with transaction(self.db_path) as conn:
            profile = require_access(conn, access, timestamp())
            active = self.repository.active(conn, profile['id'])
            history = [dict(row) for row in conn.execute('SELECT id,created_at FROM assessment_pilot_sessions WHERE profile_id=? ORDER BY rowid DESC LIMIT 12', (profile['id'],))]
        return {'profile_id': profile['id'], 'blueprint': {name: public[name] for name in ('id', 'title', 'title_ru', 'level', 'limitations', 'domains')},
                'enabled': bool(self.config.get('ASSESSMENT_PILOT_ENABLED', True) and not self.config.get('PUBLIC_DEMO')),
                'availability_message': None if listening_available else 'Listening is unavailable. You can check the other skills now.',
                'recordings_ready': bool(listening_available),
                'configured': {'listening': bool(listening_available), **{domain: bool(self.config.get('OPENAI_API_KEY')) for domain in ('writing', 'speaking')}},
                'active_session': self.read(access, active) if active else None,
                'sessions': [{**row, 'status': self.read(access, row['id'])['status']} for row in history]}

    def start(self, access, body, language='en'):
        published = self.published()
        sid = self.repository.start(access, body, published, language=language,
                                    enabled=bool(self.config.get('ASSESSMENT_PILOT_ENABLED', True) and not self.config.get('PUBLIC_DEMO')))
        return self.read(access, sid)

    def _attempt(self, row, sid, task):
        result = {'id': row['id'], 'submission_id': row['submission_key'], 'created_at': row['created_at'],
                  'review_status': 'review_unavailable' if row['state'] == 'failed' or (row['state'] == 'running' and row['lease_until'] <= timestamp()) or (row['state'] == 'pending' and row['review_updated_at'] + 240 <= timestamp()) else 'reviewing' if row['state'] in ('pending', 'running') else 'ready',
                  'response': json.loads(row['response_json']), 'support': json.loads(row['support_json']), 'error': row['error']}
        if row['audio_json']:
            result['recording_url'] = f'/api/v1/assessment-pilot/sessions/{sid}/submissions/{row["id"]}/audio'
        if row['state'] == 'ready':
            report = json.loads(row['report_json'])
            refs = requirement_index()
            criteria = {item['id']: item for item in task['contract']['criteria']}
            result.update({name: report[name] for name in ('outcome', 'feedback', 'assisted')})
            if report['production_feedback'] is not None:
                fields = ('score', 'strength', 'next_step', 'example') if task['domain'] == 'writing' else ('transcript', 'speech_status', 'grammar', 'fluency', 'corrections', 'uncertainty')
                result['production_feedback'] = {name: report['production_feedback'][name] for name in fields}
            result['criteria'] = [{**{name: judgement[name] for name in ('outcome', 'score', 'feedback')},
                'id': judgement['criterion_id'], 'label': refs[criteria[judgement['criterion_id']]['requirement_id']]['label_en'],
                'label_ru': refs[criteria[judgement['criterion_id']]['requirement_id']]['label_ru'],
                'max_score': criteria[judgement['criterion_id']]['max_score']} for judgement in report['criterion_report']['judgements']]
        return result

    def read(self, access, sid):
        with transaction(self.db_path) as conn:
            session = self.repository.owned(conn, access, sid)
            saved = json.loads(session['blueprint_json'])
            result = {'id': sid, 'profile_id': session['profile_id'], 'blueprint_id': session['blueprint_id'],
                      'title': saved['title'], 'title_ru': saved['title_ru'], 'created_at': session['created_at'],
                      'diagnostic': True, 'limitations': saved['limitations'], 'components': []}
            for domain in DOMAINS:
                current = self.repository.current(conn, session, domain)
                task = json.loads(current['task_json'])
                support, _, listened = support_for(conn, current)
                component = {name: task[name] for name in ('domain', 'title', 'title_ru', 'prompt', 'prompt_ru', 'format')}
                component.update(id=current['id'], form_id=task['form_id'], revision=current['revision'], draft=json.loads(current['draft_json']),
                                 support=support, repeated=bool(current['repeated']), attempt=None, history=[], state='draft' if current['revision'] else 'not_started')
                if task['format'] == 'choice_set':
                    component['questions'] = [{name: item[name] for name in ('id', 'prompt', 'choices')} for item in task['items']]
                if domain == 'reading':
                    component['passage'] = task['passage']
                if 'hint' in support:
                    component['hint'] = task['hint']
                if domain == 'listening':
                    available = True
                    try:
                        self.verify_listening(task)
                    except LearningError:
                        available = False
                    component.update(audio_available=available, audio_url=f'/api/v1/assessment-pilot/sessions/{sid}/components/listening/audio' if available else None,
                                     listened=listened, transcript_visible='transcript' in support)
                    if component['transcript_visible']:
                        component['passage'] = task['transcript']
                rows = conn.execute('''SELECT s.*,r.state,r.report_json,r.error,r.lease_until,r.updated_at AS review_updated_at,c.task_json,c.id AS task_identity
                    FROM assessment_pilot_components c JOIN assessment_pilot_submissions s ON s.component_id=c.id
                    JOIN assessment_pilot_reviews r ON r.submission_id=s.id WHERE c.session_id=? AND c.domain=? ORDER BY c.ordinal DESC''', (sid, domain)).fetchall()
                for row in rows:
                    attempt = self._attempt(row, sid, json.loads(row['task_json']))
                    if row['task_identity'] == current['id']:
                        component['attempt'] = attempt
                        component['state'] = 'reviewed' if attempt['review_status'] == 'ready' else attempt['review_status']
                    else:
                        component['history'].append(attempt)
                result['components'].append(component)
            result['status'] = 'complete' if all(c['state'] == 'reviewed' for c in result['components']) else 'in_progress'
            return result

    def draft(self, access, sid, domain, body):
        self.repository.draft(access, sid, domain, body)
        return self.read(access, sid)

    def support(self, access, sid, domain, body):
        self.repository.support(access, sid, domain, body, self.verify_listening)
        return self.read(access, sid)

    def retry(self, access, sid, body):
        self.repository.retry(access, sid, body)
        return self.read(access, sid)

    @contextmanager
    def staged_recording(self, access, sid, domain, body, data, extension):
        if domain != 'speaking' or extension not in ('wav', 'webm', 'ogg', 'mp4', 'm4a', 'mp3') or not 1 <= len(data) <= MAX_UPLOAD:
            raise LearningError('invalid_audio', 'Use an original audio recording of up to 8 MB.')
        key(body.get('submission_id'))
        cached_audio = None
        with transaction(self.db_path) as conn:
            session = self.repository.owned(conn, access, sid)
            component = self.repository.current(conn, session, domain)
            previous = conn.execute('''SELECT s.audio_json FROM assessment_pilot_submissions s JOIN assessment_pilot_components c ON c.id=s.component_id
                WHERE c.session_id=? AND c.domain=? AND s.submission_key=?''', (sid, domain, body['submission_id'])).fetchone()
            if previous and previous[0]:
                audio = json.loads(previous[0])
                if audio['sha256'] != digest(data) or audio['filename'].rsplit('.', 1)[-1] != extension:
                    raise LearningError('conflict', 'That submission contains a different recording.', 409)
                cached_audio = audio
            else:
                self.repository.identity(component, body.get('component_id'))
                self.repository.revision(component, body.get('expected_revision'))
                self.repository.editable(conn, component)
                response_for(json.loads(component['task_json']), body.get('response'), complete=True)
        if cached_audio:
            yield cached_audio, None
            return
        identity = payload_hash({'session': sid, 'submission': body['submission_id']})[:32]
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            original = Path(directory) / (identity + '.' + extension)
            original.write_bytes(data)
            audio_info(original)
            converted = Path(directory) / (identity + '-review.wav')
            native = False
            if extension == 'wav':
                with wave.open(str(original), 'rb') as stream:
                    native = stream.getnchannels() == 1 and stream.getsampwidth() == 2 and 8000 <= stream.getframerate() <= 48000
            if native:
                converted.write_bytes(data)
            else:
                wav_copy(original, converted)
            reviewed = converted.read_bytes()
            with wave.open(str(converted), 'rb') as stream:
                duration = stream.getnframes() * 1000 // stream.getframerate()
            manifest = {'id': identity, 'filename': original.name, 'sha256': digest(data), 'size_bytes': len(data),
                        'duration_ms': duration, 'assessment_filename': converted.name,
                        'assessment_sha256': digest(reviewed), 'assessment_size_bytes': len(reviewed)}
            created = []
            def publish():
                for source, expected in ((original, data), (converted, reviewed)):
                    destination = self.root / source.name
                    try:
                        os.link(source, destination)
                        created.append(destination)
                        destination.chmod(0o600)
                    except FileExistsError:
                        _safe_bytes(self.root, source.name, digest(expected), len(expected))
                verify_recording(self.root, manifest)
            try:
                yield manifest, publish
            except BaseException:
                # Failed/stale transactions leave no new permanent originals.
                # A concurrent successful retry owns its already saved files.
                with transaction(self.db_path) as conn:
                    saved = conn.execute("SELECT 1 FROM assessment_pilot_submissions WHERE json_extract(audio_json,'$.id')=?", (identity,)).fetchone()
                if not saved:
                    for path in created:
                        path.unlink(missing_ok=True)
                raise

    def submit(self, access, sid, domain, body, *, data=None, extension=None):
        if data is not None:
            with self.staged_recording(access, sid, domain, body, data, extension) as (audio, publish):
                submission = self.repository.submit(access, sid, domain, body, audio=audio, publish_audio=publish)
        else:
            submission = self.repository.submit(access, sid, domain, body)
        if submission:
            self.review(access, sid, domain, submission_id=submission)
        return self.read(access, sid)

    def review(self, access, sid, domain, *, body=None, submission_id=None):
        issued = self.repository.claim_review(access, sid, domain, body=body, submission_id=submission_id)
        if issued:
            session, component, submission, token = issued
            try:
                task = json.loads(component['task_json']); response = json.loads(submission['response_json'])
                support = json.loads(submission['support_json'])
                audio = json.loads(submission['audio_json']) if submission['audio_json'] else None
                if response == {'unavailable': True}:
                    report = unmeasured(task, response, support, 'This component was not measured. Your other results remain available.')
                elif task['format'] == 'choice_set':
                    with transaction(self.db_path) as conn:
                        _, _, listened = support_for(conn, component)
                    if domain == 'listening' and (not task.get('audio') or not listened):
                        report = unmeasured(task, response, support, 'Transcript practice is saved. Listening was not measured without playback of the original recording.')
                    else:
                        if domain == 'listening':
                            self.verify_listening(task)
                        text = encoded(response); judgements = []
                        for criterion, item in zip(task['contract']['criteria'], task['items']):
                            chosen = response['answers'][item['id']]
                            # Cite the exact saved response field, including its
                            # item identity when multiple items chose the same ID.
                            quote = encoded(item['id']) + ':' + encoded(chosen)
                            start = text.index(quote)
                            correct = chosen == item['answer']
                            judgements.append({'criterion_id': criterion['id'], 'outcome': 'satisfied' if correct else 'not_satisfied',
                                'score': criterion['max_score'] if correct else 0, 'feedback': item['explanation'],
                                'evidence': [{'quote': quote, 'start': start, 'end': start + len(quote)}]})
                        report = make_report(task, response, support, criterion_report={'contract_sha256': task['contract']['contract_sha256'], 'judgements': judgements},
                                             feedback='These observations describe only this sample. Review the individual questions before another form.', model='authored-key-v1')
                elif domain == 'writing':
                    assessed = self.writing.assess_writing(task['task'], task['required_words'], task['target_words'], response['text'],
                                                          difficulty='A1', language=session['language'], topic=task['topic_id'], curriculum_contract=task['contract'], include_provenance=True)
                    report = make_report(task, response, support, criterion_report=assessed['criterion_report'],
                                         feedback=assessed['strength'] + '\n' + assessed['next_step'], model=assessed['assessment_provenance']['model'], production_feedback=assessed)
                else:
                    path = verify_recording(self.root, audio)
                    assessed = self.speaking.assess(path, task['scenario'], [], session['language'], curriculum_contract=task['contract'], include_provenance=True)
                    validate_speaking_judgements(task['contract'], assessed, audio['duration_ms'])
                    verify_recording(self.root, audio)
                    report = make_report(task, response, support, criterion_report=assessed['criterion_report'],
                                         feedback=assessed['summary'] + '\n' + assessed['next_step'], model=assessed['assessment_provenance']['model'], audio=audio, production_feedback=assessed)
                self.repository.finish_review(submission['id'], token, report=report)
            except Exception:
                # Keep provider payloads, private speech and credentials out of
                # error responses. An explicit fresh review request may retry.
                self.repository.finish_review(submission['id'], token, error=REVIEW_ERROR)
        return self.read(access, sid)

    def listening_audio(self, access, sid):
        with transaction(self.db_path) as conn:
            session = self.repository.owned(conn, access, sid)
            task = json.loads(self.repository.current(conn, session, 'listening')['task_json'])
        return self.verify_listening(task)

    def original_audio(self, access, sid, submission_id):
        with transaction(self.db_path) as conn:
            session = self.repository.owned(conn, access, sid)
            row = conn.execute('SELECT s.audio_json FROM assessment_pilot_submissions s JOIN assessment_pilot_components c ON c.id=s.component_id WHERE s.id=? AND c.session_id=? AND s.profile_id=?',
                               (submission_id, sid, session['profile_id'])).fetchone()
        if not row or not row[0]:
            raise LearningError('not_found', 'This recording was not found.', 404)
        audio = json.loads(row[0])
        try:
            verify_recording(self.root, audio)
            return _safe_bytes(self.root, audio['filename'], audio['sha256'], audio['size_bytes'])[0]
        except (OSError, ValueError, wave.Error, EOFError):
            raise LearningError('audio_unavailable', 'The original recording is unavailable; its saved review is retained.', 409) from None
