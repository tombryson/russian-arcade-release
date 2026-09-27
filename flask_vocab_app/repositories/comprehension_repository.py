"""Owned, frozen question sets and append-only comprehension checks.

The saved story remains the library entry. Each issued question set has its own
identity. Checking answers never takes task text or media URLs from the browser.
"""
import json
import math
import re
import sqlite3

from models.database import connect_db
from repositories.learning_repository import encoded, identifier, payload_hash, timestamp
from services.activity_evidence import save_contract, load_contract, save_report
from contracts.curriculum import validate_judgements
from services.progression import award, legacy_profile
from utils.activity_owner import activity_profile_id
from utils.story_content import validate_story_title
from services.comprehension_evidence import SUPPORT_VERSION, verify_audio


class ComprehensionConflict(ValueError):
    pass


class ComprehensionBusy(ComprehensionConflict):
    pass


def request_digest(task_id, revision, answers):
    return payload_hash({'task_id': task_id, 'revision': revision, 'answers': answers})


def validate_answers(payload, answers):
    if (not isinstance(answers, list) or len(answers) != len(payload['questions'])
            or any(not isinstance(a, str) or not a.strip() or len(a) > 4000 for a in answers)):
        raise ValueError('Answer each question before checking. Keep each answer under 4,000 characters.')


def validate_assessment(payload, answers, assessment):
    if not isinstance(assessment, dict) or set(assessment) != {'feedback', 'scores', 'total_score', 'criterion_reports'}:
        raise ValueError('The reading feedback was incomplete.')
    feedback, scores = assessment['feedback'], assessment['scores']
    if (not isinstance(feedback, list) or not isinstance(scores, list)
            or len(feedback) != len(answers) or len(scores) != len(answers)
            or any(not isinstance(f, str) or not f.strip() or len(f) > 4000 for f in feedback)
            or any(type(s) not in (int, float) or not math.isfinite(s) or not 0 <= s <= 10 for s in scores)
            or type(assessment['total_score']) not in (int, float)
            or not math.isfinite(assessment['total_score'])
            or abs(assessment['total_score'] - sum(scores) / len(scores)) > 0.00001):
        raise ValueError('The reading feedback and scores do not match these answers.')
    reports = assessment['criterion_reports']
    if not isinstance(reports, dict) or set(reports) != set(payload['contracts']):
        raise ValueError('The reading criteria do not match this question set.')
    for index, contract in payload['contracts'].items():
        validate_judgements(contract, reports[index], response_text=answers[int(index)])
        if payload.get('practice_mode') == 'listening' and payload.get('audio') is None:
            if any(j['outcome'] != 'insufficient_evidence' or j['score'] is not None
                   for j in reports[index]['judgements']):
                raise ValueError('Transcript-only fallback cannot grade listening performance without a recording.')


def support_state(conn, task, *, revision=None):
    """Current support is projected from receipts; attempts save their own IDs."""
    revision = task['revision'] if revision is None else revision
    payload = task['payload']
    supported = {'model_answer'} if payload['prior_feedback'] or revision else set()
    rows = []
    if payload.get('support_version') == SUPPORT_VERSION:
        rows = conn.execute('SELECT id,kind,detail_json FROM comprehension_support_receipts '
                            'WHERE task_id=? AND profile_id=? AND revision<=? ORDER BY rowid',
                            (task['id'], task['profile_id'], revision)).fetchall()
        supported.update(row[1] for row in rows if row[1] in ('translation', 'transcript', 'hint'))
    return {'listened': any(row[1] == 'listened' for row in rows),
            'transcript_visible': payload.get('practice_mode', 'reading') != 'listening' or 'transcript' in supported,
            'support': sorted(supported), 'receipt_ids': [row[0] for row in rows]}


class ComprehensionRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    @staticmethod
    def _task(conn, task_id, owner):
        conn.row_factory = sqlite3.Row
        row = conn.execute('''SELECT t.*,s.title,s.topic,s.difficulty,s.text,
            COALESCE(tr.title,'') AS title_en
            FROM comprehension_tasks t JOIN saved_stories s ON s.id=t.story_id
            LEFT JOIN story_title_translations tr ON tr.story_id=s.id AND tr.language='en'
            WHERE t.id=? AND t.profile_id=? AND COALESCE(s.owner_profile_id,'personal-learning')=?''',
            (task_id, owner, owner)).fetchone()
        if row is None:
            raise LookupError('Story not found for this profile.')
        task = dict(row)
        task['payload'] = json.loads(task.pop('payload_json'))
        if any(task['payload'][key] != task[key] for key in ('text', 'topic', 'difficulty')):
            raise ValueError('The saved story no longer matches its question set.')
        from services.comprehension_evidence import validate_contracts
        validate_contracts(task['payload'])
        for index, contract in task['payload']['contracts'].items():
            if load_contract(conn, owner, 'comprehension', f'{task_id}:{index}') != contract:
                raise ValueError('The saved reading criteria are missing or changed.')
        task['latest'] = conn.execute('SELECT id FROM comprehension_tasks WHERE story_id=? AND profile_id=? ORDER BY rowid DESC LIMIT 1',
                                      (task['story_id'], owner)).fetchone()[0] == task_id
        return task

    def owner(self):
        with connect_db(self.db_path) as conn:
            return activity_profile_id(conn)

    def create(self, prepared, topic, difficulty, contracts, *, expected_owner, story_id=None, parent_id=None, lease_token=None,
               practice_mode=None, track_support=False, initial_transcript=False, audio=None):
        """Publish all question contracts before returning any answer form."""
        title = validate_story_title(prepared['title'])
        title_en = validate_story_title(prepared['title_en'])
        questions = prepared['questions']
        if (not isinstance(questions, list) or not 5 <= len(questions) <= 20
                or any(not isinstance(q, str) or not q.strip() or len(q) > 2000 for q in questions)
                or len(set(questions)) != len(questions)):
            raise ValueError('Use between five and twenty distinct questions.')
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            owner = activity_profile_id(conn)
            if owner != expected_owner:
                raise ComprehensionConflict('Your profile changed. Reload the story to continue.')
            prior_feedback = False
            parent = None
            if story_id is not None:
                parent = self._task(conn, parent_id, owner)
                if parent['story_id'] != story_id or not parent['latest']:
                    raise ComprehensionConflict('This story has a newer question set. Reload it to continue.')
                if not lease_token or parent['checking_token'] != lease_token or parent['checking_submission_id'] != lease_token:
                    raise ComprehensionConflict('This question request has changed. Reload the story to continue.')
                if any(parent[key] != value for key, value in [('text', prepared['text']), ('topic', topic), ('difficulty', difficulty)]):
                    raise ValueError('New questions must keep the original story.')
                prior_feedback = bool(parent['payload']['prior_feedback'] or conn.execute(
                    'SELECT 1 FROM comprehension_attempts WHERE task_id=?', (parent_id,)).fetchone())
                # Keep titles and media owned by the original saved story.
                prepared = {**prepared, 'audio_url': parent['payload']['audio_url'], 'image_url': parent['payload']['image_url']}
                practice_mode = parent['payload'].get('practice_mode', 'reading')
                track_support = parent['payload'].get('support_version') == SUPPORT_VERSION
                audio = parent['payload'].get('audio')
                conn.execute("UPDATE saved_stories SET questions=?,answers='[]',feedback='[]',score=0 WHERE id=?",
                             (encoded(questions), story_id))
                conn.execute('UPDATE comprehension_tasks SET checking_submission_id=NULL,checking_sha256=NULL,checking_started_at=NULL,checking_token=NULL WHERE id=?', (parent_id,))
            else:
                cursor = conn.execute('''INSERT INTO saved_stories(title,topic,difficulty,text,audio_url,image_url,
                    questions,answers,feedback,score,owner_profile_id) VALUES (?,?,?,?,?,?,?,'[]','[]',0,?)''',
                    (title, topic, difficulty, prepared['text'], prepared.get('audio_url', ''), prepared.get('image_url', ''), encoded(questions), owner))
                story_id = cursor.lastrowid
                conn.execute("INSERT INTO story_title_translations VALUES (?,'en',?)", (story_id, title_en))
            payload = {key: prepared.get(key, '') for key in ('text', 'questions', 'audio_url', 'image_url')}
            payload.update(topic=topic, difficulty=difficulty, contracts=contracts, prior_feedback=prior_feedback)
            if track_support:
                if practice_mode not in ('reading', 'listening'):
                    raise ValueError('Choose reading or listening practice.')
                payload.update(practice_mode=practice_mode, support_version=SUPPORT_VERSION,
                               initial_support=['transcript'] if initial_transcript and practice_mode == 'listening' and not parent else [])
                if parent:
                    payload['parent_task_id'] = parent['id']
                if practice_mode == 'listening':
                    payload['audio'] = audio
                    payload['audio_url'] = audio['url'] if audio else ''
            from services.comprehension_evidence import validate_contracts
            validate_contracts(payload)
            task_id = identifier()
            conn.execute('INSERT INTO comprehension_tasks(id,story_id,profile_id,payload_json,created_at) VALUES (?,?,?,?,?)',
                         (task_id, story_id, owner, encoded(payload), timestamp()))
            for index, contract in contracts.items():
                save_contract(conn, owner, 'comprehension', f'{task_id}:{index}', contract)
            if track_support and parent:
                for receipt in conn.execute('SELECT id,kind,detail_json FROM comprehension_support_receipts WHERE task_id=? ORDER BY rowid', (parent['id'],)).fetchall():
                    conn.execute('INSERT INTO comprehension_support_receipts VALUES (?,?,?,?,?,?,?,?,?)',
                                 (identifier(), task_id, owner, 0, identifier(), receipt[1], receipt[2], timestamp(), receipt[0]))
            elif track_support and payload['initial_support']:
                conn.execute('INSERT INTO comprehension_support_receipts VALUES (?,?,?,?,?,?,?,?,?)',
                             (identifier(), task_id, owner, 0, identifier(), 'transcript', '{}', timestamp(), None))
            return task_id, story_id

    def latest(self, story_id):
        with connect_db(self.db_path) as conn:
            owner = activity_profile_id(conn)
            row = conn.execute('SELECT id FROM comprehension_tasks WHERE story_id=? AND profile_id=? ORDER BY rowid DESC LIMIT 1', (story_id, owner)).fetchone()
            return self._task(conn, row[0], owner) if row else None

    def load(self, task_id):
        with connect_db(self.db_path) as conn:
            return self._task(conn, task_id, activity_profile_id(conn))

    def begin_questions(self, task_id, revision):
        """Claim extension before paid generation, including across browser tabs."""
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._task(conn, task_id, activity_profile_id(conn))
            if not task['latest'] or type(revision) is not int or revision != task['revision']:
                raise ComprehensionConflict('This story has a newer check or question set. Reload it to continue.')
            if task['checking_submission_id'] and timestamp() - task['checking_started_at'] < 180:
                raise ComprehensionBusy('This story is still being prepared or checked. Please wait.')
            if len(task['payload']['questions']) > 17:
                raise ComprehensionConflict('This story has enough questions. Start another story for more practice.')
            token = identifier()
            digest = payload_hash({'operation': 'questions', 'task_id': task_id, 'revision': revision})
            conn.execute('UPDATE comprehension_tasks SET checking_submission_id=?,checking_sha256=?,checking_started_at=?,checking_token=? WHERE id=?',
                         (token, digest, timestamp(), token, task_id))
            task['check_token'] = token
            return task

    def display(self, task_id):
        with connect_db(self.db_path) as conn:
            task = self._task(conn, task_id, activity_profile_id(conn))
            row = conn.execute('SELECT answers_json,assessment_json,support_json FROM comprehension_attempts WHERE task_id=? ORDER BY rowid DESC LIMIT 1', (task_id,)).fetchone()
            state = support_state(conn, task)
            result = {**task['payload'], 'title': task['title'], 'title_en': task['title_en'], 'id': task['story_id'],
                    'task_id': task_id, 'revision': task['revision'], 'submission_id': identifier(),
                    'answers': json.loads(row[0]) if row else [], 'assessment': json.loads(row[1]) if row else None,
                    'criterion_support': json.loads(row[2]) if row else [],
                    'practice_mode': task['payload'].get('practice_mode', 'reading'),
                    **{key: state[key] for key in ('listened', 'transcript_visible', 'support')}}
            if result['practice_mode'] == 'listening':
                result.pop('contracts', None)
                result['audio_available'] = False
                try:
                    verify_audio(task['payload']['audio'])
                    result['audio_available'] = True
                except ValueError:
                    pass
                result['audio_url'] = f'/comprehension/tasks/{task_id}/audio' if result['audio_available'] else ''
                result.pop('audio', None)
                if not state['transcript_visible']:
                    result.update(text='', words=[], image_url='', title='Аудирование', title_en='Listening practice', capture_key='')
            return result

    def record_support(self, task_id, revision, request_key, operation, *, word=None):
        """Persist disclosure before returning it; retries retain the receipt."""
        if (type(revision) is not int or revision < 0 or not isinstance(request_key, str)
                or not re.fullmatch(r'[a-f0-9]{32}', request_key)
                or operation not in ('listened', 'transcript', 'translation', 'hint')):
            raise ValueError('This support request is incomplete. Reload the story.')
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._task(conn, task_id, activity_profile_id(conn))
            payload = task['payload']
            if payload.get('support_version') != SUPPORT_VERSION:
                raise ValueError('This older story does not record support receipts.')
            listening = payload.get('practice_mode') == 'listening'
            if operation in ('listened', 'transcript') and not listening:
                raise ValueError('This story is reading practice.')
            detail = {}
            if operation == 'listened':
                if payload.get('audio') is None:
                    raise ComprehensionConflict('This recording is unavailable. Read the transcript to continue.')
                detail = {'audio_sha256': payload['audio']['sha256']}
            elif operation in ('translation', 'hint'):
                if not isinstance(word, str) or not 1 <= len(word) <= 100 or not re.search(r'[А-Яа-яЁё]', word):
                    raise ValueError('Choose a Russian word from this story.')
                from services.game_vocabulary_discovery import read_word
                read_word(conn, {'vocabulary_refs': [{'sentence': payload['text']}]}, word)
                if listening and not support_state(conn, task)['transcript_visible']:
                    raise ComprehensionConflict('Reveal the transcript before looking up its words.')
                detail = {'word': word}
            existing = conn.execute('SELECT revision,kind,detail_json FROM comprehension_support_receipts WHERE task_id=? AND request_key=?',
                                    (task_id, request_key)).fetchone()
            if existing:
                if tuple(existing) != (revision, operation, encoded(detail)):
                    raise ComprehensionConflict('That support request belongs to different content.')
                return {key: value for key, value in support_state(conn, task).items() if key != 'receipt_ids'}
            if not task['latest'] or task['revision'] != revision:
                raise ComprehensionConflict('This story has changed. Reload it to continue.')
            if task['checking_submission_id']:
                if timestamp() - task['checking_started_at'] < 180:
                    raise ComprehensionBusy('Wait for this answer check before using more support.')
                conn.execute('UPDATE comprehension_tasks SET checking_submission_id=NULL,checking_sha256=NULL,checking_started_at=NULL,checking_token=NULL WHERE id=?', (task_id,))
            if operation == 'listened':
                try:
                    verify_audio(payload['audio'])
                except ValueError as error:
                    raise ComprehensionConflict(str(error)) from error
            conn.execute('INSERT INTO comprehension_support_receipts VALUES (?,?,?,?,?,?,?,?,?)',
                         (identifier(), task_id, task['profile_id'], revision, request_key, operation, encoded(detail), timestamp(), None))
            return {key: value for key, value in support_state(conn, task).items() if key != 'receipt_ids'}

    def audio_path(self, task_id):
        with connect_db(self.db_path) as conn:
            task = self._task(conn, task_id, activity_profile_id(conn))
            if task['payload'].get('practice_mode') != 'listening':
                raise LookupError('Recording not found for this task.')
            return verify_audio(task['payload']['audio'])

    @staticmethod
    def _request(task_id, revision, submission_id, answers):
        if (type(revision) is not int or revision < 0 or not isinstance(submission_id, str)
                or not re.fullmatch(r'[a-f0-9]{32}', submission_id)):
            raise ValueError('This answer form is incomplete. Reload the story to continue.')
        return request_digest(task_id, revision, answers)

    @staticmethod
    def _cached(conn, task, submission_id, digest):
        row = conn.execute('SELECT * FROM comprehension_attempts WHERE task_id=? AND submission_id=?', (task['id'], submission_id)).fetchone()
        if row:
            if row['request_sha256'] != digest:
                raise ComprehensionConflict('That check belongs to different answers. Reload before checking again.')
            result = dict(row)
            result['assessment'] = json.loads(row['assessment_json'])
            result['answers'] = json.loads(row['answers_json'])
            result['support'] = json.loads(row['support_json'])
            result['revision'] = task['revision']
            result['next_submission_id'] = payload_hash({'attempt': row['id'], 'revision': task['revision']})[:32]
            return result
        return None

    def begin_check(self, task_id, revision, submission_id, answers):
        digest = self._request(task_id, revision, submission_id, answers)
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._task(conn, task_id, activity_profile_id(conn))
            validate_answers(task['payload'], answers)
            cached = self._cached(conn, task, submission_id, digest)
            if cached:
                return task, cached
            if not task['latest'] or revision != task['revision']:
                raise ComprehensionConflict('This story has a newer check or question set. Reload it to continue.')
            if task['checking_submission_id'] and timestamp() - task['checking_started_at'] < 180:
                raise ComprehensionBusy('Your answers are still being checked. Please wait.')
            # Reopening or pressing Save on unchanged, already checked answers
            # does not call a provider or mint another completion.
            previous = conn.execute('SELECT submission_id,request_sha256,answers_json FROM comprehension_attempts WHERE task_id=? ORDER BY rowid DESC LIMIT 1', (task_id,)).fetchone()
            if previous and json.loads(previous['answers_json']) == answers:
                return task, self._cached(conn, task, previous['submission_id'], previous['request_sha256'])
            if task['payload'].get('practice_mode') == 'listening':
                state = support_state(conn, task)
                if not state['listened'] and 'transcript' not in state['support']:
                    raise ComprehensionConflict('Play the recording or reveal the transcript before checking your answers.')
                if 'transcript' not in state['support']:
                    try:
                        verify_audio(task['payload']['audio'])
                    except ValueError as error:
                        raise ComprehensionConflict(str(error)) from error
            token = identifier()
            conn.execute('UPDATE comprehension_tasks SET checking_submission_id=?,checking_sha256=?,checking_started_at=?,checking_token=? WHERE id=?',
                         (submission_id, digest, timestamp(), token, task_id))
            task['check_token'] = token
            return task, None

    def abandon_check(self, task_id, submission_id, lease_token):
        with connect_db(self.db_path) as conn:
            conn.execute('UPDATE comprehension_tasks SET checking_submission_id=NULL,checking_sha256=NULL,checking_started_at=NULL,checking_token=NULL WHERE id=? AND profile_id=? AND checking_submission_id=? AND checking_token=?',
                         (task_id, activity_profile_id(conn), submission_id, lease_token))

    def finish_check(self, task_id, revision, submission_id, answers, assessment, *, expected_owner, lease_token):
        digest = self._request(task_id, revision, submission_id, answers)
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            owner = activity_profile_id(conn)
            if owner != expected_owner:
                raise ComprehensionConflict('Your profile changed. Reload the story to continue.')
            task = self._task(conn, task_id, owner)
            cached = self._cached(conn, task, submission_id, digest)
            if cached:
                return cached
            if (not task['latest'] or task['revision'] != revision or task['checking_submission_id'] != submission_id
                    or task['checking_sha256'] != digest or not lease_token or task['checking_token'] != lease_token):
                raise ComprehensionConflict('This story has changed. Reload it to continue.')
            validate_answers(task['payload'], answers)
            validate_assessment(task['payload'], answers, assessment)
            state = support_state(conn, task)
            support = state['support']
            attempt_id = identifier()
            conn.execute('''INSERT INTO comprehension_attempts VALUES (?,?,?,?,?,?,?,?,?,?)''',
                         (attempt_id, task_id, owner, submission_id, digest, encoded(answers), encoded(assessment), encoded(support), timestamp(), encoded(state['receipt_ids'])))
            for index, report in assessment['criterion_reports'].items():
                save_report(conn, owner, 'comprehension', f'{task_id}:{index}', attempt_id, report,
                            response_text=answers[int(index)], support=support)
            conn.execute('UPDATE saved_stories SET answers=?,feedback=?,score=? WHERE id=?',
                         (encoded(answers), encoded(assessment['feedback']), assessment['total_score'], task['story_id']))
            # Preserve the existing participation/topic-preparation policy. The
            # new criteria are diagnostic and create no proficiency entitlement.
            pid = legacy_profile(conn)
            if pid:
                award(conn, pid, activity='reading', content_key=f"story:{task['story_id']}",
                      source_key=f'comprehension-check:{attempt_id}', title=task['title_en'] or task['title'],
                      evidence={'score': assessment['total_score'], 'score_max': 10, 'answered_questions': len(answers),
                                'first_fresh_assessment': not support, 'course_task_context_matches': True,
                                'course_task_questions_hash': payload_hash(task['payload']['questions'])})
            conn.execute('UPDATE comprehension_tasks SET revision=revision+1,checking_submission_id=NULL,checking_sha256=NULL,checking_started_at=NULL,checking_token=NULL WHERE id=?', (task_id,))
            task['revision'] += 1
            return self._cached(conn, task, submission_id, digest)
