"""Owned pilot envelopes. Task versions and submitted originals are append-only."""
import json
import re

from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, require_access, timestamp, transaction

DOMAINS = ('language_use', 'reading', 'listening', 'writing', 'speaking')


def key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', value):
        raise LearningError('invalid_input', 'Use a valid submission identifier.')
    return value


def response_for(task, value, *, complete=False):
    if not isinstance(value, dict):
        raise LearningError('invalid_input', 'Save a response object.')
    if value == {'unavailable': True} and type(value.get('unavailable')) is bool and task['domain'] in ('listening', 'speaking'):
        return value
    if task['format'] == 'choice_set':
        answers = value.get('answers')
        items = {item['id']: item for item in task['items']}
        if (set(value) != {'answers'} or not isinstance(answers, dict) or not set(answers) <= set(items)
                or any(not isinstance(answer, str) or answer not in {c['id'] for c in items[item]['choices']}
                       for item, answer in answers.items()) or (complete and set(answers) != set(items))):
            raise LearningError('invalid_input', 'Choose one answer for each question before checking.')
    elif task['format'] == 'writing':
        text = value.get('text')
        if (set(value) != {'text'} or not isinstance(text, str) or len(text) > 12000
                or '\x00' in text or (complete and not text.strip())):
            raise LearningError('invalid_input', 'Write your response before checking (up to 12,000 characters).')
    elif value != {}:
        raise LearningError('invalid_input', 'Speaking needs the original recording, not a typed transcript.')
    return value


def empty_response(task):
    return {'answers': {}} if task['format'] == 'choice_set' else {'text': ''} if task['format'] == 'writing' else {}


def support_for(conn, component):
    rows = conn.execute('SELECT id,kind FROM assessment_pilot_support WHERE component_id=? ORDER BY rowid', (component['id'],)).fetchall()
    support = {row['kind'] for row in rows if row['kind'] != 'listened'}
    if component['prior_feedback']:
        support.add('model_answer')
    return sorted(support), [row['id'] for row in rows], any(row['kind'] == 'listened' for row in rows)


class AssessmentPilotRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def owned(self, conn, access, session_id):
        profile = require_access(conn, access, timestamp())
        row = conn.execute('SELECT * FROM assessment_pilot_sessions WHERE id=? AND profile_id=?', (session_id, profile['id'])).fetchone()
        if row is None:
            raise LearningError('not_found', 'This assessment was not found for the selected learner.', 404)
        if payload_hash(json.loads(row['blueprint_json'])) != row['blueprint_sha256']:
            raise LearningError('invalid_saved_task', 'The saved assessment needs review.', 409)
        return row

    @staticmethod
    def current(conn, session, domain):
        if domain not in DOMAINS:
            raise LearningError('not_found', 'Choose one of the five components.', 404)
        row = conn.execute('SELECT * FROM assessment_pilot_components WHERE session_id=? AND profile_id=? AND domain=? ORDER BY ordinal DESC LIMIT 1',
                           (session['id'], session['profile_id'], domain)).fetchone()
        if row is None or payload_hash(json.loads(row['task_json'])) != row['task_sha256']:
            raise LearningError('invalid_saved_task', 'The saved component needs review.', 409)
        return row

    @staticmethod
    def request(conn, sid, request_key, operation, body):
        key(request_key)
        fingerprint = payload_hash(body)
        row = conn.execute('SELECT operation,request_sha256 FROM assessment_pilot_requests WHERE session_id=? AND request_key=?', (sid, request_key)).fetchone()
        if row:
            if tuple(row) != (operation, fingerprint):
                raise LearningError('conflict', 'That submission belongs to a different request.', 409)
            return False
        conn.execute('INSERT INTO assessment_pilot_requests VALUES (?,?,?,?,?)', (sid, request_key, operation, fingerprint, timestamp()))
        return True

    @staticmethod
    def revision(component, revision):
        if type(revision) is not int or revision != component['revision']:
            raise LearningError('stale_revision', 'This component changed in another tab. Reload to keep your saved work.', 409)

    @staticmethod
    def identity(component, component_id):
        if component_id != component['id']:
            raise LearningError('stale_component', 'This form has been replaced. Reload before answering the new task.', 409)

    @staticmethod
    def editable(conn, component):
        if conn.execute('SELECT 1 FROM assessment_pilot_submissions WHERE component_id=?', (component['id'],)).fetchone():
            raise LearningError('already_submitted', 'This original response is saved. Choose another form to try again.', 409)

    @staticmethod
    def add_component(conn, session_id, profile_id, blueprint, domain):
        forms = blueprint['forms'][domain]
        previous = conn.execute('SELECT c.task_json FROM assessment_pilot_components c JOIN assessment_pilot_sessions s ON s.id=c.session_id '
                                'WHERE c.profile_id=? AND c.domain=? AND s.blueprint_id=? ORDER BY c.rowid', (profile_id, domain, blueprint['id'])).fetchall()
        seen = [json.loads(row[0])['form_id'] for row in previous]
        task = next((form for form in forms if form['form_id'] not in seen), forms[len(seen) % len(forms)])
        prior_feedback = bool(conn.execute('''SELECT 1 FROM assessment_pilot_components c JOIN assessment_pilot_submissions s ON s.component_id=c.id
            JOIN assessment_pilot_reviews r ON r.submission_id=s.id WHERE c.profile_id=? AND c.task_sha256=? AND r.state='ready' LIMIT 1''',
            (profile_id, payload_hash(task))).fetchone())
        ordinal = conn.execute('SELECT COUNT(*) FROM assessment_pilot_components WHERE session_id=? AND domain=?', (session_id, domain)).fetchone()[0]
        conn.execute('INSERT INTO assessment_pilot_components(id,session_id,profile_id,domain,ordinal,task_json,task_sha256,draft_json,repeated,prior_feedback,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                     (identifier(), session_id, profile_id, domain, ordinal, encoded(task), payload_hash(task), encoded(empty_response(task)), int(task['form_id'] in seen), int(prior_feedback), timestamp()))

    def start(self, access, body, blueprint, *, enabled=True, language='en'):
        if set(body) != {'submission_id'}:
            raise LearningError('invalid_input', 'Use the assessment start form.')
        submission_id = key(body.get('submission_id'))
        with transaction(self.db_path, write=True) as conn:
            profile = require_access(conn, access, timestamp())
            prior = conn.execute('SELECT id FROM assessment_pilot_sessions WHERE profile_id=? AND start_key=?', (profile['id'], submission_id)).fetchone()
            if prior:
                return prior[0]
            resumed = conn.execute("SELECT r.session_id FROM assessment_pilot_requests r JOIN assessment_pilot_sessions s ON s.id=r.session_id WHERE s.profile_id=? AND r.request_key=? AND r.operation='start'",
                                   (profile['id'], submission_id)).fetchone()
            if resumed:
                return resumed[0]
            # One unfinished envelope is resumed, even after pilot enrolment is disabled.
            active = self.active(conn, profile['id'])
            if active:
                self.request(conn, active, submission_id, 'start', body)
                return active
            if not enabled:
                raise LearningError('pilot_unavailable', 'New pilot attempts are paused. Saved work remains available.', 409)
            sid = identifier()
            conn.execute('INSERT INTO assessment_pilot_sessions VALUES (?,?,?,?,?,?,?,?)',
                         (sid, profile['id'], blueprint['id'], encoded(blueprint), payload_hash(blueprint), submission_id, language, timestamp()))
            for domain in DOMAINS:
                self.add_component(conn, sid, profile['id'], blueprint, domain)
            return sid

    @staticmethod
    def active(conn, profile):
        for (sid,) in conn.execute('SELECT id FROM assessment_pilot_sessions WHERE profile_id=? ORDER BY rowid DESC', (profile,)).fetchall():
            unfinished = conn.execute('''SELECT 1 FROM assessment_pilot_components c
                LEFT JOIN assessment_pilot_submissions s ON s.component_id=c.id
                LEFT JOIN assessment_pilot_reviews r ON r.submission_id=s.id
                WHERE c.session_id=? AND c.ordinal=(SELECT MAX(other.ordinal) FROM assessment_pilot_components other WHERE other.session_id=c.session_id AND other.domain=c.domain)
                AND (r.state IS NULL OR r.state!='ready') LIMIT 1''', (sid,)).fetchone()
            if unfinished:
                return sid
        return None

    def draft(self, access, sid, domain, body):
        if set(body) != {'submission_id', 'component_id', 'expected_revision', 'response'}:
            raise LearningError('invalid_input', 'Use the saved component form.')
        with transaction(self.db_path, write=True) as conn:
            session = self.owned(conn, access, sid)
            if not self.request(conn, sid, body.get('submission_id'), 'draft:' + domain, body):
                return
            component = self.current(conn, session, domain)
            self.identity(component, body.get('component_id'))
            self.revision(component, body.get('expected_revision')); self.editable(conn, component)
            response = response_for(json.loads(component['task_json']), body.get('response'))
            conn.execute('UPDATE assessment_pilot_components SET draft_json=?,revision=revision+1 WHERE id=?', (encoded(response), component['id']))

    def support(self, access, sid, domain, body, verify_audio):
        if set(body) != {'submission_id', 'component_id', 'expected_revision', 'kind'}:
            raise LearningError('invalid_input', 'Use the saved support form.')
        with transaction(self.db_path, write=True) as conn:
            session = self.owned(conn, access, sid)
            if not self.request(conn, sid, body.get('submission_id'), 'support:' + domain, body):
                return
            component = self.current(conn, session, domain)
            self.identity(component, body.get('component_id'))
            self.revision(component, body.get('expected_revision')); self.editable(conn, component)
            task, kind = json.loads(component['task_json']), body.get('kind')
            if kind not in ('hint', 'listened', 'transcript') or (kind != 'hint' and domain != 'listening'):
                raise LearningError('invalid_input', 'Choose support available for this component.')
            detail = {}
            if kind == 'listened':
                verify_audio(task)
                detail = {'audio_sha256': task['audio']['sha256']}
            conn.execute('INSERT INTO assessment_pilot_support VALUES (?,?,?,?,?,?,?)',
                         (identifier(), component['id'], session['profile_id'], kind, encoded(detail), component['revision'], timestamp()))
            conn.execute('UPDATE assessment_pilot_components SET revision=revision+1 WHERE id=?', (component['id'],))

    def submit(self, access, sid, domain, body, *, audio=None, publish_audio=None):
        if set(body) != {'submission_id', 'component_id', 'expected_revision', 'response'}:
            raise LearningError('invalid_input', 'Use the saved component form.')
        request = {**body, 'audio': audio}
        with transaction(self.db_path, write=True) as conn:
            session = self.owned(conn, access, sid)
            if not self.request(conn, sid, body.get('submission_id'), 'submit:' + domain, request):
                return None
            component = self.current(conn, session, domain)
            self.identity(component, body.get('component_id'))
            self.revision(component, body.get('expected_revision')); self.editable(conn, component)
            task = json.loads(component['task_json'])
            response = response_for(task, body.get('response'), complete=True)
            supported, receipts, listened = support_for(conn, component)
            if domain == 'listening' and not listened and 'transcript' not in supported and response != {'unavailable': True}:
                raise LearningError('listen_first', 'Play the recording or reveal the transcript before checking.', 409)
            if domain == 'speaking' and not audio and response != {'unavailable': True}:
                raise LearningError('recording_required', 'Record your own response, or mark speaking unavailable.')
            if domain != 'speaking' and audio:
                raise LearningError('invalid_input', 'Only Speaking accepts a recording.')
            if audio and response == {'unavailable': True}:
                raise LearningError('invalid_input', 'A recorded response cannot also be marked unavailable.')
            if publish_audio is not None:
                publish_audio()
            submission = identifier()
            conn.execute('INSERT INTO assessment_pilot_submissions VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         (submission, component['id'], session['profile_id'], body['submission_id'], payload_hash(request), encoded(response), encoded(supported), encoded(receipts), encoded(audio) if audio else None, component['revision'], timestamp()))
            conn.execute("INSERT INTO assessment_pilot_reviews(submission_id,state,updated_at) VALUES (?,'pending',?)", (submission, timestamp()))
            conn.execute('UPDATE assessment_pilot_components SET draft_json=?,revision=revision+1 WHERE id=?', (encoded(response), component['id']))
            return submission

    def retry(self, access, sid, body):
        selected = body.get('components')
        if (set(body) != {'submission_id', 'components'} or not isinstance(selected, list) or not selected
                or any(not isinstance(item, dict) or set(item) != {'domain', 'component_id'} or item.get('domain') not in DOMAINS for item in selected)
                or len(selected) != len({item['domain'] for item in selected})):
            raise LearningError('invalid_input', 'Choose distinct components to try again.')
        with transaction(self.db_path, write=True) as conn:
            session = self.owned(conn, access, sid)
            if not self.request(conn, sid, body.get('submission_id'), 'retry', body):
                return
            for item in selected:
                domain = item['domain']
                component = self.current(conn, session, domain)
                self.identity(component, item['component_id'])
                prior = conn.execute('SELECT s.id AS submission_id,r.state,r.lease_until,r.updated_at FROM assessment_pilot_submissions s JOIN assessment_pilot_reviews r ON r.submission_id=s.id WHERE s.component_id=?', (component['id'],)).fetchone()
                now = timestamp()
                if (not prior or (prior['state'] == 'pending' and prior['updated_at'] + 240 > now)
                        or (prior['state'] == 'running' and prior['lease_until'] > now)):
                    raise LearningError('component_busy', 'Save this component before choosing another form; wait for any current review.', 409)
                if prior['state'] in ('pending', 'running'):
                    # Moving on retires an expired review atomically. Otherwise
                    # its late model answer could appear after a future same-form
                    # retry has already frozen its prior-feedback condition.
                    conn.execute("UPDATE assessment_pilot_reviews SET state='failed',claim_token=NULL,lease_until=0,error=?,updated_at=? WHERE submission_id=?",
                                 ('This review expired before another form was requested. The original response is saved.', now, prior['submission_id']))
                self.add_component(conn, sid, session['profile_id'], json.loads(session['blueprint_json']), domain)

    def claim_review(self, access, sid, domain, *, body=None, submission_id=None):
        if body is not None and set(body) != {'submission_id', 'component_id'}:
            raise LearningError('invalid_input', 'Use the saved review form.')
        with transaction(self.db_path, write=True) as conn:
            session = self.owned(conn, access, sid)
            component = self.current(conn, session, domain)
            if body is not None and not self.request(conn, sid, body.get('submission_id'), 'review:' + domain, body):
                return None
            if body is not None:
                self.identity(component, body.get('component_id'))
            row = conn.execute('SELECT s.*,r.state,r.lease_until FROM assessment_pilot_submissions s JOIN assessment_pilot_reviews r ON r.submission_id=s.id WHERE s.component_id=?', (component['id'],)).fetchone()
            if not row or (submission_id and row['id'] != submission_id):
                raise LearningError('not_submitted', 'Submit this component before requesting feedback.', 409)
            if row['state'] == 'ready' or (row['state'] == 'running' and row['lease_until'] > timestamp()):
                return None
            token = identifier()
            conn.execute("UPDATE assessment_pilot_reviews SET state='running',claim_token=?,lease_until=?,error=NULL,updated_at=? WHERE submission_id=?", (token, timestamp()+240, timestamp(), row['id']))
            return dict(session), dict(component), dict(row), token

    def finish_review(self, submission_id, token, *, report=None, error=None):
        with transaction(self.db_path, write=True) as conn:
            row = conn.execute('SELECT p.archived FROM assessment_pilot_submissions s JOIN learning_profiles p ON p.id=s.profile_id WHERE s.id=?', (submission_id,)).fetchone()
            if not row:
                return
            # The result belongs to the saved owner; a browser/profile switch
            # during network work neither redirects it nor changes rewards.
            conn.execute('UPDATE assessment_pilot_reviews SET state=?,report_json=?,error=?,claim_token=NULL,lease_until=0,updated_at=? WHERE submission_id=? AND claim_token=?',
                         ('ready' if report is not None else 'failed', encoded(report) if report is not None else None, error, timestamp(), submission_id, token))
