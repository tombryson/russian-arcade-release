"""Course gates use frozen authored decisions, never coins or mutable ratings."""
from copy import deepcopy
import json
import sqlite3
import unittest
from unittest.mock import patch
from flask.testing import FlaskClient

from repositories.learning_repository import LearningError, encoded, timestamp, transaction
from services import course_progression as course
from services.curriculum import curriculum
from tests.support import isolated_app, strip_course_progression


def fixture_catalogue():
    topics = [item['id'] for item in curriculum()['topics'] if item['band'] == 'A1']
    chapters = []
    for index, group in enumerate((topics[:3], topics[3:6], topics[6:8], topics[8:]), 1):
        variants = []
        for version in (1, 2):
            variant_id = f'chapter-{index}-v{version}'
            questions = []
            for number, kind in enumerate(('reading', 'reading', 'reading', 'listening', 'response'), 1):
                questions.append({'id': f'q{number}', 'kind': kind, 'prompt': f'Decision {number}',
                                  'prompt_ru': f'Вопрос {number}', 'choices': [{'id': 'a', 'text': 'Да'}, {'id': 'b', 'text': 'Нет'}],
                                  'answer': 'a', 'essential': number in (1, 4), 'hint': 'Read the address.',
                                  'hint_ru': 'Прочитайте адрес.', 'explanation': 'The letter names this address.',
                                  'explanation_ru': 'В письме указан этот адрес.'})
            variants.append({'id': variant_id, 'letter_title': 'A letter', 'letter_title_ru': 'Письмо',
                             'letter': f'Привет! Это письмо номер {version}.', 'glossary': [{'ru': 'письмо', 'en': 'letter'}],
                             'listening': {'audio_url': f'/static/audio/course/{variant_id}.mp3', 'transcript': 'Встреча в пять часов.'},
                             'questions': questions})
        chapters.append({'id': f'chapter-{index}', 'number': index, 'title': f'Chapter {index}',
                         'title_ru': f'Глава {index}', 'intro': 'Help deliver a letter.', 'intro_ru': 'Помогите доставить письмо.',
                         'topic_ids': group, 'variants': variants})
    return {'version': 1, 'band': 'A1', 'rubric_version': 'a1-checkpoint-v1', 'chapters': chapters}


class CourseContentTests(unittest.TestCase):
    def test_pre_course_schema_is_not_backfilled_or_required_by_older_migrations(self):
        with sqlite3.connect(':memory:') as conn:
            self.assertIsNone(course.course_snapshot(conn, 'earlier-profile'))
            metadata = {'_course': {'topic_id': 'greetings', 'level': 'A1', 'score': 1, 'assisted': False}}
            self.assertFalse(course.record_evidence(conn, 'earlier-profile', 'event', 'first_delivery', 'welcome', 'A1', metadata, timestamp()))

    def test_real_authored_course_validates(self):
        self.assertEqual(len(course.validate_course(json.loads(course.DATA_FILE.read_text()))['chapters']), 4)

    def test_validator_rejects_disconnected_or_incomplete_assessments(self):
        original = fixture_catalogue()
        self.assertIs(course.validate_course(original), original)
        mutations = [
            lambda item: item.update(version=2),
            lambda item: item['chapters'].pop(),
            lambda item: item['chapters'][0].update(topic_ids=['invented']),
            lambda item: item['chapters'][0].update(title_ru=''),
            lambda item: item['chapters'][0]['variants'][0]['questions'][0].update(answer='missing'),
            lambda item: item['chapters'][0]['variants'][0]['questions'][0].update(hint_ru=''),
            lambda item: item['chapters'][0]['variants'][0]['questions'][0].update(essential='yes'),
            lambda item: item['chapters'][0]['variants'][0]['listening'].update(audio_url='https://example.com/audio'),
            lambda item: item['chapters'][0]['variants'][1]['questions'].pop(),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = deepcopy(original)
                mutate(data)
                with self.assertRaises(ValueError):
                    course.validate_course(data)


class CourseProgressionTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = fixture_catalogue()
        self.patcher = patch.object(course, '_catalogue', return_value=self.catalogue)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        default = patch.object(course, 'default_release_id', return_value='a1-v1')
        default.start()
        self.addCleanup(default.stop)
        self.app = isolated_app(self)
        self.app.config['COURSE_DEFAULT_RELEASE'] = 'a1-v1'
        self.db = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        response = self.client.get('/api/v1/course')
        self.assertEqual(response.status_code, 200)
        self.pid, self.token = response.json['profile_id'], response.json['csrf_token']
        self.counter = 0

    def post(self, path, data):
        return self.client.post('/api/v1/course/' + path, json=data, headers={'X-CSRF-Token': self.token})

    def start(self, chapter='chapter-1', request_id=None, challenge=True):
        self.counter += 1
        return self.post(f'chapters/{chapter}/checkpoint', {'request_id': request_id or f'start-{self.counter}', 'challenge': challenge})

    def answers(self, attempt_id):
        with transaction(self.db) as conn:
            row = conn.execute('SELECT frozen_json FROM course_checkpoint_attempts WHERE id=?', (attempt_id,)).fetchone()
        return {question['id']: question['answer'] for question in json.loads(row['frozen_json'])['variant']['questions']}

    def submit(self, attempt_id, answers=None, submission_id=None, listened=True):
        self.counter += 1
        if listened:
            self.assertEqual(self.post(f'checkpoints/{attempt_id}/listened', {}).status_code, 200)
        return self.post(f'checkpoints/{attempt_id}/answer', {'answers': answers or self.answers(attempt_id),
                                                           'submission_id': submission_id or f'submit-{self.counter}'})

    def evidence(self, topic_id, activity='reading', content=None, *, score=0.8, assisted=False,
                 level='A1', pid=None, record=True):
        self.counter += 1
        event_id = f'event-{self.counter}'
        content = content or f'task-{self.counter}'
        pid = pid or self.pid
        metadata = {'_course': {'topic_id': topic_id, 'level': level, 'score': score, 'assisted': assisted}}
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO progression_events VALUES (?,?,?,?,?,?,?,?,?,?,NULL)',
                         (event_id, pid, activity, event_id, content, 'Practice', 'activity', level, encoded(metadata), timestamp()))
            if record:
                course.record_evidence(conn, pid, event_id, activity, content, level, metadata, timestamp())
        return event_id

    def prepare(self, chapter='chapter-1'):
        authored = next(item for item in self.catalogue['chapters'] if item['id'] == chapter)
        for topic in authored['topic_ids']:
            self.evidence(topic, 'reading')
            self.evidence(topic, 'writing')

    def state(self):
        return self.client.get('/api/v1/course').json

    def test_reads_are_side_effect_free_and_historical_events_do_not_backfill(self):
        self.evidence(self.catalogue['chapters'][0]['topic_ids'][0], record=False)
        with transaction(self.db) as conn:
            before = conn.total_changes
            for _ in range(3):
                value = course.course_snapshot(conn, self.pid)
            self.assertEqual(conn.total_changes, before)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_evidence').fetchone()[0], 0)
        self.assertEqual(value['progress'], 0)
        self.assertEqual([item['status'] for item in value['chapters']], ['practice', 'locked', 'locked', 'locked'])
        self.assertEqual(value['unlocked_levels'], ['A1'])
        self.assertTrue(value['chapters'][0]['topics'][0]['objectives'])
        self.assertEqual({link['activity'] for link in value['chapters'][0]['topics'][0]['links']}, set(course.ACTIVITIES))
        for later in value['chapters'][1:]:
            self.assertEqual((later['title'], later['title_ru'], later['intro'], later['intro_ru']), ('', '', '', ''))
            self.assertEqual(later['topics'], [])

    def test_distinct_successful_tasks_and_two_families_are_required(self):
        topics = self.catalogue['chapters'][0]['topic_ids']
        for topic in topics:
            self.evidence(topic, content=topic + '-repeat', assisted=True)
            self.evidence(topic, content=topic + '-repeat')
            self.evidence(topic, content=topic + '-repeat', score=0.9)
            self.evidence(topic, content=topic + '-new')
        chapter = self.state()['chapters'][0]
        self.assertEqual(chapter['preparation_policy'], 'a1-course-practice-v1')
        self.assertIsNone(chapter['target_preparation_progress'])
        self.assertTrue(all(topic['completed'] for topic in chapter['topics']))
        self.assertEqual([topic['successful_tasks'] for topic in chapter['topics']], [2, 2, 2])
        self.assertEqual(chapter['status'], 'practice')
        self.assertEqual(chapter['progress'], 0.5)
        self.evidence(topics[0], activity='writing', assisted=True)
        self.assertEqual(self.state()['chapters'][0]['status'], 'ready')
        self.assertEqual(self.start(challenge=False).status_code, 200)

    def test_unsuccessful_or_wrong_level_evidence_does_not_count_then_correction_does(self):
        topic = self.catalogue['chapters'][0]['topic_ids'][0]
        self.evidence(topic, content='same', score=0.69)
        self.evidence(topic, level='A2')
        self.evidence('unknown-topic')
        self.evidence(topic, activity='review')
        self.assertEqual(self.state()['chapters'][0]['topics'][0]['successful_tasks'], 0)
        self.evidence(topic, content='same', assisted=True, score=0.7)
        self.assertEqual(self.state()['chapters'][0]['topics'][0]['successful_tasks'], 1)

    def test_saved_task_level_and_activity_family_normalization_work_with_tuple_connections(self):
        topic = self.catalogue['chapters'][0]['topic_ids'][0]
        events = [(self.evidence(topic, activity=activity, record=False), activity)
                  for activity in ('speaking', 'speaking_step', 'first_delivery')]
        with sqlite3.connect(self.db) as conn:
            for event_id, activity in events:
                conn.execute('UPDATE progression_events SET target_level=NULL WHERE id=?', (event_id,))
                event = conn.execute('SELECT content_key,evidence_json FROM progression_events WHERE id=?', (event_id,)).fetchone()
                self.assertTrue(course.record_evidence(conn, self.pid, event_id, activity, event[0], None, json.loads(event[1]), timestamp()))
                self.assertFalse(course.record_evidence(conn, self.pid, event_id, activity, event[0], None, json.loads(event[1]), timestamp()))
            self.assertIsNone(conn.row_factory)
            chapter = course.course_snapshot(conn, self.pid)['chapters'][0]
            self.assertEqual(chapter['activity_count'], 2)
            self.assertEqual(chapter['topics'][0]['successful_tasks'], 3)
            self.assertIsNone(conn.row_factory)
            self.assertEqual({row[0] for row in conn.execute('SELECT activity FROM course_evidence')}, {'reading', 'speaking'})

    def test_later_preparation_does_not_skip_sequential_gate(self):
        self.prepare('chapter-2')
        later = self.state()['chapters'][1]
        self.assertEqual((later['status'], later['progress']), ('locked', 0))
        self.assertEqual(later['topics'], [])
        self.assertEqual(self.state()['progress'], 0)
        self.assertEqual(self.start('chapter-2').status_code, 403)
        self.assertEqual(self.start(challenge=False).status_code, 403)
        attempt = self.start().json
        passed = self.submit(attempt['id']).json
        self.assertTrue(passed['result']['passed'])
        self.assertEqual(passed['course']['current_chapter_id'], 'chapter-2')
        self.assertEqual(passed['course']['progress'], 1)
        self.assertEqual(passed['course']['chapters'][1]['title'], 'Chapter 2')
        self.assertTrue(all(topic['successful_tasks'] == 2 for topic in passed['course']['chapters'][1]['topics']))
        self.assertEqual(self.start('chapter-2', challenge=False).status_code, 200)

    def test_old_start_and_submission_receipts_do_not_reveal_future_stops(self):
        attempt = self.start(request_id='old-start').json
        answers = self.answers(attempt['id'])
        result = self.submit(attempt['id'], answers, submission_id='old-answer').json
        # Reproduce stored pre-redaction presentation without changing the
        # frozen attempt, answer or outcome that these receipts must preserve.
        for table, column, request_id, response in (
            ('course_checkpoint_requests', 'request_id', 'old-start', attempt),
            ('course_checkpoint_submissions', 'submission_id', 'old-answer', result),
        ):
            old = deepcopy(response)
            for chapter in old['course']['chapters']:
                if chapter['status'] == 'locked':
                    chapter.update(title='Future story spoiler', title_ru='Будущая история', intro='Future event',
                                   topics=[{'id': 'future-topic'}], progress=0.5)
            with transaction(self.db, write=True) as conn:
                conn.execute(f'UPDATE {table} SET response_json=? WHERE profile_id=? AND {column}=?',
                             (encoded(old), self.pid, request_id))
        self.assertEqual(self.start(request_id='old-start').json, attempt)
        self.assertEqual(self.submit(attempt['id'], answers, submission_id='old-answer').json, result)

    def test_reversal_drops_preparation_until_pass_and_replacement_can_preserve_it(self):
        topic = self.catalogue['chapters'][0]['topic_ids'][0]
        first = self.evidence(topic, content='shared')
        second = self.evidence(topic, content='shared')
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE progression_events SET reversed_at=? WHERE id=?', (timestamp(), first))
        self.assertEqual(self.state()['chapters'][0]['topics'][0]['successful_tasks'], 1)
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE progression_events SET reversed_at=? WHERE id=?', (timestamp(), second))
        self.assertEqual(self.state()['chapters'][0]['topics'][0]['successful_tasks'], 0)
        self.prepare()
        self.submit(self.start(challenge=False).json['id'])
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE progression_events SET reversed_at=?', (timestamp(),))
        self.assertEqual(self.state()['chapters'][0]['status'], 'passed')
        self.assertEqual(self.state()['current_chapter_id'], 'chapter-2')

    def test_active_checkpoint_resumes_and_start_idempotency_is_exact(self):
        initial = self.start(request_id='stable').json
        self.post(f"checkpoints/{initial['id']}/listened", {})
        self.assertEqual(initial, self.start(request_id='stable').json)
        resumed = self.start(request_id='second').json
        self.assertEqual(initial['id'], resumed['id'])
        self.assertTrue(resumed['listened'])
        self.assertEqual(self.start(request_id='stable', challenge=False).status_code, 409)
        self.assertEqual(self.start('chapter-2', request_id='stable').status_code, 409)

    def test_active_api_never_exposes_answers_explanations_or_transcript(self):
        attempt = self.start().json
        self.assertNotIn('result', attempt)
        self.assertNotIn('transcript', attempt['listening'])
        for question in attempt['questions']:
            self.assertEqual(set(question), {'id', 'kind', 'prompt', 'prompt_ru', 'choices'})
        self.assertEqual(attempt['glossary'], [{'ru': 'письмо', 'en': 'letter'}])
        partial = self.post(f"checkpoints/{attempt['id']}/answer", {'answers': {'q1': 'b'}, 'submission_id': 'partial'})
        self.assertEqual(partial.status_code, 400)
        self.assertNotIn('feedback', partial.json['error'])
        resumed = self.client.get('/api/v1/course/checkpoints/' + attempt['id']).json
        self.assertNotIn('result', resumed)
        self.assertNotIn('answers', resumed)
        self.assertNotIn('selected_answer', json.dumps(resumed))

    def test_listening_and_essential_decisions_are_required_but_perfection_is_not(self):
        attempt = self.start().json
        answers = self.answers(attempt['id'])
        self.assertEqual(self.submit(attempt['id'], answers, listened=False).status_code, 409)
        answers['q1'] = 'b'  # 80% with an essential decision wrong is a retry.
        result = self.submit(attempt['id'], answers).json
        self.assertEqual((result['result']['score'], result['result']['total']), (4, 5))
        self.assertFalse(result['result']['passed'])
        self.assertFalse(result['result']['essential_passed'])
        self.assertEqual(result['result']['feedback'][0]['selected_answer'], 'b')
        retry = self.start().json
        self.assertNotEqual(retry['letter'], attempt['letter'])
        answers = self.answers(retry['id']); answers['q2'] = 'b'
        result = self.submit(retry['id'], answers).json
        self.assertTrue(result['result']['passed'])
        self.assertTrue(result['result']['essential_passed'])
        self.assertEqual(result['status'], 'passed')

    def test_support_reveals_only_requested_help_and_requires_an_independent_retry(self):
        attempt = self.start().json
        hint = self.post(f"checkpoints/{attempt['id']}/support", {'kind': 'hint', 'question_id': 'q2'}).json
        self.assertTrue(hint['support_used'])
        self.assertNotIn('hint', hint['questions'][0])
        self.assertIn('hint', hint['questions'][1])
        self.assertNotIn('transcript', hint['listening'])
        transcript = self.post(f"checkpoints/{attempt['id']}/support", {'kind': 'transcript'}).json
        self.assertIn('transcript', transcript['listening'])
        self.assertEqual(self.post(f"checkpoints/{attempt['id']}/support", {'kind': 'hint', 'question_id': 'unknown'}).status_code, 400)
        result = self.submit(attempt['id']).json
        self.assertEqual(result['result']['score'], result['result']['total'])
        self.assertFalse(result['result']['passed'])
        self.assertEqual(result['status'], 'retry')
        retry = self.start().json
        self.assertFalse(retry['support_used'])
        self.assertTrue(self.submit(retry['id']).json['result']['passed'])

    def test_submissions_replay_exactly_and_changed_payload_or_second_check_is_rejected(self):
        attempt = self.start().json
        answers = self.answers(attempt['id'])
        answers['q2'] = 'b'
        first = self.submit(attempt['id'], answers, submission_id='submission').json
        replay = self.submit(attempt['id'], answers, submission_id='submission').json
        self.assertEqual(first, replay)
        self.assertEqual(first, self.client.get('/api/v1/course/checkpoints/' + attempt['id']).json)
        self.assertEqual({item['question_id']: item['selected_answer'] for item in first['result']['feedback']}, answers)
        self.assertEqual(first['result']['feedback'][1]['answer'], 'a')
        self.assertFalse(first['result']['feedback'][1]['correct'])
        self.assertTrue(first['result']['essential_passed'])
        with transaction(self.db) as conn:
            saved = conn.execute('SELECT answers_json,result_json FROM course_checkpoint_attempts WHERE id=?', (attempt['id'],)).fetchone()
        self.assertEqual(json.loads(saved['answers_json']), answers)
        self.assertNotIn('selected_answer', saved['result_json'])
        answers['q3'] = 'b'
        self.assertEqual(self.submit(attempt['id'], answers, submission_id='submission').status_code, 409)
        self.assertEqual(self.submit(attempt['id'], submission_id='different').status_code, 409)
        self.assertIn('transcript', first['listening'])
        self.assertEqual(len(first['result']['feedback']), 5)
        self.assertEqual(self.start().status_code, 409)

    def test_course_endpoints_are_unavailable_without_course_migration(self):
        with transaction(self.db, write=True) as conn:
            strip_course_progression(conn)
        endpoints = [
            ('GET', '/api/v1/course', None),
            ('GET', '/api/v1/course/checkpoints/missing', None),
            ('POST', '/api/v1/course/chapters/chapter-1/checkpoint', {'request_id': 'before-course'}),
            ('POST', '/api/v1/course/checkpoints/missing/answer', {'answers': {}, 'submission_id': 'before-course'}),
            ('POST', '/api/v1/course/checkpoints/missing/support', {'kind': 'transcript'}),
            ('POST', '/api/v1/course/checkpoints/missing/listened', {}),
        ]
        for method, path, data in endpoints:
            with self.subTest(path=path):
                response = self.client.open(path, method=method, json=data, headers={'X-CSRF-Token': self.token})
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json['error'], {'code': 'course_unavailable',
                                                         'message': 'The course is temporarily unavailable.'})
        self.assertEqual(self.client.get('/api/v1/progression').status_code, 200)

    def test_frozen_content_and_rubric_survive_authoring_updates(self):
        attempt = self.start().json
        self.catalogue['rubric_version'] = 'future-rubric'
        self.catalogue['chapters'][0]['variants'][0]['questions'][1]['answer'] = 'b'
        self.catalogue['chapters'][0]['variants'][0]['letter'] = 'Новое письмо.'
        with patch.dict(course.RUBRIC, {'minimum_score': 1.0}):
            answers = self.answers(attempt['id']); answers['q3'] = 'b'
            result = self.submit(attempt['id'], answers).json
        self.assertEqual(result['letter'], attempt['letter'])
        self.assertTrue(result['result']['passed'])
        with transaction(self.db) as conn:
            row = conn.execute('SELECT content_version,rubric_version FROM course_checkpoint_attempts WHERE id=?', (attempt['id'],)).fetchone()
        self.assertEqual(tuple(row), (1, 'a1-checkpoint-v1'))

    def test_all_passes_unlock_a2_without_minting_rewards_or_changing_ratings(self):
        with transaction(self.db) as conn:
            before = tuple(conn.execute('SELECT lingocoins,elo_rating FROM users WHERE user_id=1').fetchone())
            entries = conn.execute('SELECT COUNT(*) FROM progression_entries').fetchone()[0]
        for number in range(1, 5):
            result = self.submit(self.start('chapter-' + str(number)).json['id']).json
        self.assertEqual(result['course']['unlocked_levels'], ['A1', 'A2'])
        self.assertTrue(result['course']['completed'])
        self.assertEqual(result['course']['progress'], 1)
        self.assertIsNone(result['course']['current_chapter_id'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_entries').fetchone()[0], entries)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 0)
            self.assertEqual(tuple(conn.execute('SELECT lingocoins,elo_rating FROM users WHERE user_id=1').fetchone()), before)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 4)

    def test_profile_isolation_applies_to_progress_attempts_support_and_receipts(self):
        self.prepare()
        attempt = self.start().json
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)", (timestamp(),))
            self.assertEqual(course.course_snapshot(conn, 'other')['progress'], 0)
            for operation in (
                lambda: course.checkpoint_read(conn, 'other', attempt['id']),
                lambda: course.checkpoint_listened(conn, 'other', attempt['id']),
                lambda: course.checkpoint_support(conn, 'other', attempt['id'], 'transcript'),
                lambda: course.checkpoint_answer(conn, 'other', attempt['id'], {'q1': 'a'}, 'other-submission'),
            ):
                with self.assertRaises(LearningError) as caught:
                    operation()
                self.assertEqual(caught.exception.status, 404)
            other = course.checkpoint_start(conn, 'other', 'chapter-1', 'shared-id', True)
            mine = course.checkpoint_start(conn, self.pid, 'chapter-1', 'shared-id', True)
            self.assertNotEqual(other['id'], mine['id'])
            event = conn.execute('SELECT event_id FROM course_evidence LIMIT 1').fetchone()[0]
            metadata = {'_course': {'topic_id': self.catalogue['chapters'][0]['topic_ids'][0], 'level': 'A1', 'score': 1, 'assisted': False}}
            self.assertFalse(course.record_evidence(conn, 'other', event, 'reading', 'unrelated', 'A1', metadata, timestamp()))
        selected = self.client.post('/api/v1/user-session/select', json={'profile_id': 'other'}, headers={'X-CSRF-Token': self.token})
        self.assertEqual(selected.status_code, 200)
        self.token = self.client.get('/api/v1/course').json['csrf_token']
        self.assertEqual(self.client.get('/api/v1/course/checkpoints/' + attempt['id']).status_code, 404)
        self.assertEqual(self.post(f"checkpoints/{attempt['id']}/support", {'kind': 'transcript'}).status_code, 404)
        self.assertEqual(self.post(f"checkpoints/{attempt['id']}/listened", {}).status_code, 404)

    def test_api_enforces_access_csrf_and_strict_payloads(self):
        signed_out = FlaskClient(self.app)
        self.assertEqual(signed_out.get('/api/v1/course').status_code, 401)
        self.assertEqual(self.client.post('/api/v1/course/chapters/chapter-1/checkpoint', json={'request_id': 'no-csrf'}).status_code, 403)
        self.assertEqual(self.post('chapters/chapter-1/checkpoint', {'request_id': 'bad', 'challenge': 'true'}).status_code, 400)
        self.assertEqual(self.post('chapters/chapter-1/checkpoint', {'request_id': 'bad', 'correct': True}).status_code, 400)
        self.assertEqual(self.start('missing').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/course/checkpoints/missing').status_code, 404)
        attempt = self.start().json
        self.assertEqual(self.post(f"checkpoints/{attempt['id']}/listened", {'listened': True}).status_code, 400)
        self.assertEqual(self.post(f"checkpoints/{attempt['id']}/support", {'kind': 'transcript', 'question_id': 'q1'}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
