"""Saved translations, explicit drafts, and atomic checks/rewards for the local user."""
from datetime import datetime, timezone
import sqlite3
import json

from models.database import connect_db
from services.progression import award, legacy_profile
from utils.activity_owner import activity_profile_id


class TranslationConflict(ValueError):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class TranslationRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def list_saved(self):
        with connect_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute('''SELECT s.*, d.response AS draft,
                d.updated_at AS draft_saved_at,
                (SELECT response FROM translation_attempts a WHERE a.sentence_id=s.id ORDER BY a.id DESC LIMIT 1) AS checked_response
                FROM sentences s LEFT JOIN translation_drafts d ON d.sentence_id=s.id
                WHERE COALESCE(s.owner_profile_id,'personal-learning')=?
                ORDER BY COALESCE(d.updated_at,s.created_at) DESC, s.id DESC''', (activity_profile_id(conn),))]

    def load(self, sentence_id):
        with connect_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('''SELECT s.*, COALESCE(d.response,'') AS draft,
                COALESCE(d.revision,0) AS revision, d.updated_at AS draft_saved_at
                FROM sentences s LEFT JOIN translation_drafts d ON d.sentence_id=s.id WHERE s.id=?
                AND COALESCE(s.owner_profile_id,'personal-learning')=?''', (sentence_id, activity_profile_id(conn))).fetchone()
            if not row:
                return None
            result = dict(row)
            result['attempts'] = [dict(row) for row in conn.execute(
                'SELECT * FROM translation_attempts WHERE sentence_id=? ORDER BY id DESC', (sentence_id,))]
            result['checked_response'] = result['attempts'][0]['response'] if result['attempts'] else None
            from services.activity_evidence import load_contract, reports_for_task
            owner = activity_profile_id(conn)
            result['curriculum_contract'] = load_contract(conn, owner, 'translation', str(sentence_id))
            reports = reports_for_task(conn, owner, 'translation', str(sentence_id))
            for attempt in result['attempts']:
                if str(attempt['id']) in reports:
                    attempt['criterion_report'] = reports[str(attempt['id'])]['report']
                    attempt['criterion_support'] = reports[str(attempt['id'])]['support']
            return result

    def save_content(self, sentence, english, topic, difficulty, *, curriculum_contract=None, expected_profile=None):
        """Save an exact pair once per task level, preserving earlier practice."""
        if type(difficulty) is not int or difficulty not in range(1, 7):
            raise ValueError('Invalid level')
        if any(not isinstance(text, str) or not text.strip() or len(text) > limit
               for text, limit in [(sentence, 1000), (english, 1000), (topic, 100)]):
            raise ValueError('Invalid sentence pair')
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            owner = activity_profile_id(conn)
            if expected_profile is not None and expected_profile != owner:
                raise TranslationConflict('The selected profile changed during preparation.')
            if curriculum_contract is not None:
                from services.production_evidence import check_content
                check_content({'sentence': sentence, 'english': english, 'topic': topic, 'difficulty': difficulty},
                              'translation', curriculum_contract)
            row = conn.execute("SELECT id FROM sentences WHERE sentence=? AND english=? AND topic=? AND difficulty=? AND COALESCE(owner_profile_id,'personal-learning')=? ORDER BY id LIMIT 1",
                               (sentence, english, topic, difficulty, owner)).fetchone()
            if row:
                return row[0], False
            cursor = conn.execute('INSERT INTO sentences(sentence,english,topic,difficulty,score,audio_url,owner_profile_id) VALUES (?,?,?,?,0,?,?)',
                                  (sentence, english, topic, difficulty, '', owner))
            if curriculum_contract is not None:
                from services.activity_evidence import save_contract
                save_contract(conn, owner, 'translation', str(cursor.lastrowid), curriculum_contract)
            return cursor.lastrowid, True

    @staticmethod
    def validate_answer(response, checking=False):
        if not isinstance(response, str) or len(response) > 1000 or (checking and not response.strip()):
            raise ValueError('Invalid answer')

    @staticmethod
    def assert_revision(conn, sentence_id, revision):
        if not conn.execute("SELECT 1 FROM sentences WHERE id=? AND COALESCE(owner_profile_id,'personal-learning')=?", (sentence_id, activity_profile_id(conn))).fetchone():
            raise LookupError('Sentence not found')
        row = conn.execute('SELECT revision FROM translation_drafts WHERE sentence_id=?', (sentence_id,)).fetchone()
        if type(revision) is not int or revision != (row[0] if row else 0):
            raise TranslationConflict('Newer draft exists')

    def check_revision(self, sentence_id, revision):
        with connect_db(self.db_path) as conn:
            self.assert_revision(conn, sentence_id, revision)

    @staticmethod
    def write_draft(conn, sentence_id, response, revision):
        conn.execute('''INSERT INTO translation_drafts(sentence_id,response,revision,updated_at) VALUES (?,?,?,?)
            ON CONFLICT(sentence_id) DO UPDATE SET response=excluded.response,
            revision=excluded.revision,updated_at=excluded.updated_at''', (sentence_id, response, revision + 1, timestamp()))

    def save_draft(self, sentence_id, response, revision):
        self.validate_answer(response)
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            self.assert_revision(conn, sentence_id, revision)
            self.write_draft(conn, sentence_id, response, revision)
        return revision + 1

    @staticmethod
    def validate_assessment(assessment):
        if not isinstance(assessment, dict) or type(assessment.get('score')) is not int or not 0 <= assessment['score'] <= 4:
            raise ValueError('Invalid assessment score')
        for key in ('strength', 'next_step', 'example'):
            if not isinstance(assessment.get(key), str) or not assessment[key].strip() or len(assessment[key]) > 1000:
                raise ValueError('Invalid assessment feedback')

    def save_check(self, sentence_id, response, revision, assessment, language, *, expected_profile=None):
        self.validate_answer(response, checking=True)
        self.validate_assessment(assessment)
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            self.assert_revision(conn, sentence_id, revision)
            owner = activity_profile_id(conn)
            if expected_profile is not None and owner != expected_profile:
                raise TranslationConflict('The selected profile changed during assessment.')
            from services.activity_evidence import load_contract, save_report
            from services.production_evidence import attempt_support
            from contracts.curriculum import validate_judgements
            contract = load_contract(conn, owner, 'translation', str(sentence_id))
            report = assessment.get('criterion_report')
            if contract is not None:
                validate_judgements(contract, report, response_text=response)
            elif report is not None:
                raise ValueError('A legacy task cannot acquire criteria during assessment.')
            support = attempt_support(conn, 'translation', str(sentence_id)) if contract is not None else None
            self.write_draft(conn, sentence_id, response, revision)
            attempt = conn.execute('''INSERT INTO translation_attempts
                (sentence_id,response,score,strength,next_step,example,ui_language,created_at,coins_earned,elo_change,already_rewarded,criterion_report_json,criterion_support_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', (sentence_id, response, assessment['score'], assessment['strength'],
                assessment['next_step'], assessment['example'], language, timestamp(), 0, 0, 0,
                json.dumps(report, ensure_ascii=False) if report is not None else None,
                json.dumps(support) if support is not None else None))
            if contract is not None:
                save_report(conn, owner, 'translation', str(sentence_id), str(attempt.lastrowid), report,
                            response_text=response, support=support)
            profile_id = legacy_profile(conn)
            coins = award(conn, profile_id, activity='translation', content_key=f'translation:{sentence_id}',
                          source_key=f'translation-attempt:{attempt.lastrowid}', title='Sentence practice',
                          evidence={'score': assessment['score'], 'score_max': 4}) if profile_id else 0
            conn.execute('UPDATE translation_attempts SET coins_earned=?,already_rewarded=? WHERE id=?',
                         (coins, int(not coins), attempt.lastrowid))
        return revision + 1

    def record_reference_views(self, sentence_ids):
        """Record only references actually returned to this profile by Phrasebook."""
        from services.activity_evidence import load_contract
        with connect_db(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            owner = activity_profile_id(conn)
            for sentence_id in set(sentence_ids):
                if type(sentence_id) is not int or sentence_id < 1:
                    raise ValueError('Invalid sentence identity')
                if load_contract(conn, owner, 'translation', str(sentence_id)) is None:
                    continue
                after_id = conn.execute('SELECT MAX(id) FROM translation_attempts WHERE sentence_id=?', (sentence_id,)).fetchone()[0]
                conn.execute('INSERT OR IGNORE INTO translation_reference_views(sentence_id,profile_id,after_attempt_id) VALUES (?,?,?)',
                             (sentence_id, owner, after_id))

    def save_audio(self, sentence_id, url):
        # Generated media is local. Do not turn model/user output into an external URL.
        if not url.startswith('/static/media/') or '..' in url or any(c in url for c in ('?', '#', '\\')):
            raise ValueError('Invalid audio URL')
        with connect_db(self.db_path) as conn:
            owner = activity_profile_id(conn)
            if not conn.execute("SELECT 1 FROM sentences WHERE id=? AND COALESCE(owner_profile_id,'personal-learning')=?", (sentence_id, owner)).fetchone():
                raise LookupError('Sentence not found')
            conn.execute("UPDATE sentences SET audio_url=? WHERE id=? AND COALESCE(owner_profile_id,'personal-learning')=? AND (audio_url IS NULL OR audio_url='')", (url, sentence_id, owner))
