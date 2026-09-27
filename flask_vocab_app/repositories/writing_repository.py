"""Writing content, exact drafts and append-only checks for local practice."""
import json
import re
import sqlite3
from datetime import datetime, timezone

from models.database import connect_db
from services.progression import award, legacy_profile
from utils.activity_owner import activity_profile_id
from services.curriculum import normalize_level
from contracts.curriculum import validate_task_contract, validate_judgements
from services.activity_evidence import save_contract, load_contract, save_report, reports_for_task


class WritingConflict(ValueError):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def word_count(text):
    return len(re.findall(r"[^\W_]+(?:[-’'][^\W_]+)*", text, re.UNICODE))


class WritingRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    @staticmethod
    def decode(row):
        item = dict(row)
        try:
            words = json.loads(item['required_words'])
            # Historical imports sometimes escaped Unicode inside JSON strings.
            item['required_words'] = [re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m[1],16)), word)
                for word in words if isinstance(word,str)] if isinstance(words,list) else []
        except (ValueError, TypeError):
            item['required_words'] = []
        return item

    def list_saved(self):
        with connect_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [self.decode(row) for row in conn.execute('''SELECT e.*, m.title,m.title_en,m.task_en,
                COALESCE(d.response,e.user_response,'') AS draft, COALESCE(d.revision,0) AS revision,d.updated_at AS draft_saved_at,
                (SELECT response FROM writing_attempts a WHERE a.exercise_id=e.id ORDER BY a.id DESC LIMIT 1) AS checked_response
                FROM writing_exercises e LEFT JOIN writing_details m ON m.exercise_id=e.id
                LEFT JOIN writing_drafts d ON d.exercise_id=e.id
                WHERE COALESCE(e.owner_profile_id,'personal-learning')=?
                ORDER BY COALESCE(d.updated_at,e.created_at) DESC,e.id DESC''', (activity_profile_id(conn),))]

    def load(self, exercise_id):
        item = next((item for item in self.list_saved() if item['id'] == exercise_id), None)
        if item is None:
            return None
        with connect_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            profile_id = activity_profile_id(conn)
            item['curriculum_contract'] = load_contract(conn, profile_id, 'writing', str(exercise_id))
            reports = reports_for_task(conn, profile_id, 'writing', str(exercise_id))
            item['attempts'] = [dict(row) for row in conn.execute(
                'SELECT * FROM writing_attempts WHERE exercise_id=? ORDER BY id DESC', (exercise_id,))]
            for attempt in item['attempts']:
                if str(attempt['id']) in reports:
                    attempt['criterion_report'] = reports[str(attempt['id'])]['report']
                    attempt['criterion_support'] = reports[str(attempt['id'])]['support']
        return item

    @staticmethod
    def validate_answer(response, checking=False):
        if not isinstance(response,str) or len(response) > 20000 or (checking and not response.strip()):
            raise ValueError('Invalid writing')

    @staticmethod
    def validate_task(task):
        if not isinstance(task,dict):
            raise ValueError('Invalid task')
        for key, limit in [('title',100),('title_en',100),('task',3000),('task_en',3000)]:
            if not isinstance(task.get(key),str) or not task[key].strip() or len(task[key]) > limit:
                raise ValueError('Invalid task text')
        words = task.get('required_words')
        if not isinstance(words,list) or not 3 <= len(words) <= 5 or any(
                not isinstance(word,str) or not word.strip() or len(word) > 80 for word in words):
            raise ValueError('Invalid task words')

    def create(self, task, topic, difficulty, target_words):
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            return self.create_in_transaction(conn, task, topic, difficulty, target_words, activity_profile_id(conn))

    @staticmethod
    def validate_curriculum_contract(contract, task, required_words, difficulty):
        frozen = validate_task_contract(contract)
        if (frozen['activity'] != 'writing'
                or frozen['level'] != normalize_level(difficulty, legacy='writing')
                or frozen['content'].get('task') != task
                or frozen['content'].get('required_words') != required_words
                or any(item['response_mode'] not in ('controlled_text', 'independent_writing')
                       for item in frozen['criteria'])):
            raise ValueError('Writing criteria must describe this exact text task and level.')
        # Existing Writing feedback always includes an example. A subsequent
        # check may use it and must remain usable as supported practice.
        if 'model_answer' not in frozen['support']['independence_breakers']:
            raise ValueError('Writing criteria must account for example feedback on later checks.')
        return frozen

    @staticmethod
    def create_in_transaction(conn, task, topic, difficulty, target_words, profile_id):
        """Use the same validated task store for generated and authored work."""
        WritingRepository.validate_task(task)
        normalize_level(difficulty, legacy='writing')
        if target_words not in (30,100,300):
            raise ValueError('Invalid setup')
        if not isinstance(topic,str) or not topic.strip() or len(topic) > 100:
            raise ValueError('Invalid topic')
        contract = None
        if 'curriculum_contract' in task:
            contract = WritingRepository.validate_curriculum_contract(
                task['curriculum_contract'], task['task'], task['required_words'], difficulty)
            for key in ('title', 'title_en', 'task_en'):
                if key in contract['content'] and contract['content'][key] != task[key]:
                    raise ValueError('Frozen Writing instructions must match their saved display text.')
            if ('requested_topic' in contract['content']
                    and contract['content']['requested_topic'] != topic):
                raise ValueError('Frozen Writing topic provenance must match the requested topic.')
        cursor = conn.execute('''INSERT INTO writing_exercises
            (topic,difficulty,task,required_words,min_words,user_response,created_at,owner_profile_id) VALUES (?,?,?,?,?,'',?,?)''',
            (topic,difficulty,task['task'],json.dumps(task['required_words'],ensure_ascii=False),target_words,timestamp(),profile_id))
        exercise_id = cursor.lastrowid
        conn.execute('INSERT INTO writing_details(exercise_id,title,title_en,task_en) VALUES (?,?,?,?)',
                     (exercise_id,task['title'],task['title_en'],task['task_en']))
        if contract is not None:
            save_contract(conn, profile_id, 'writing', str(exercise_id), contract)
        return exercise_id

    @staticmethod
    def assert_revision(conn, exercise_id, revision):
        if not conn.execute("SELECT 1 FROM writing_exercises WHERE id=? AND COALESCE(owner_profile_id,'personal-learning')=?",(exercise_id,activity_profile_id(conn))).fetchone():
            raise LookupError('Writing not found')
        row = conn.execute('SELECT revision FROM writing_drafts WHERE exercise_id=?',(exercise_id,)).fetchone()
        if type(revision) is not int or revision != (row[0] if row else 0):
            raise WritingConflict('Newer draft exists')

    def check_revision(self, exercise_id, revision):
        with connect_db(self.db_path) as conn:
            self.assert_revision(conn,exercise_id,revision)

    @staticmethod
    def validate_assessment(assessment):
        if not isinstance(assessment,dict) or type(assessment.get('score')) is not int or not 0 <= assessment['score'] <= 10:
            raise ValueError('Invalid score')
        for key in ('strength','next_step','example'):
            if not isinstance(assessment.get(key),str) or not assessment[key].strip() or len(assessment[key]) > 1500:
                raise ValueError('Invalid advice')

    def save(self, exercise_id, response, revision, assessment=None, language='en'):
        self.validate_answer(response, checking=assessment is not None)
        if assessment is not None:
            self.validate_assessment(assessment)
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            self.assert_revision(conn,exercise_id,revision)
            owner = activity_profile_id(conn)
            contract = load_contract(conn, owner, 'writing', str(exercise_id)) if assessment is not None else None
            report = assessment.get('criterion_report') if assessment is not None else None
            if contract is not None:
                # Reject before writing the draft. The shared writer validates
                # again against the inserted attempt in this same transaction.
                validate_judgements(contract, report, response_text=response)
            elif report is not None:
                raise ValueError('This task had no saved criteria before assessment.')
            support = ['model_answer'] if contract is not None and conn.execute(
                'SELECT 1 FROM writing_attempts WHERE exercise_id=? LIMIT 1', (exercise_id,)).fetchone() else []
            conn.execute('''INSERT INTO writing_drafts(exercise_id,response,revision,updated_at) VALUES (?,?,?,?)
                ON CONFLICT(exercise_id) DO UPDATE SET response=excluded.response,
                revision=excluded.revision,updated_at=excluded.updated_at''',(exercise_id,response,revision+1,timestamp()))
            if assessment is not None:
                attempt = conn.execute('''INSERT INTO writing_attempts
                    (exercise_id,response,score,score_max,strength,next_step,example,ui_language,created_at,source)
                    VALUES (?,?,?,10,?,?,?,?,?,'writing-v1')''',
                    (exercise_id,response,assessment['score'],assessment['strength'],assessment['next_step'],assessment['example'],language,timestamp()))
                if contract is not None:
                    save_report(conn, owner, 'writing', str(exercise_id), str(attempt.lastrowid), report,
                                response_text=response, support=support)
                profile_id = legacy_profile(conn)
                if profile_id:
                    award(conn, profile_id, activity='writing', content_key=f'writing:{exercise_id}',
                          source_key=f'writing-attempt:{attempt.lastrowid}', title='Writing',
                          evidence={'score': assessment['score'], 'score_max': 10})
        return revision+1
