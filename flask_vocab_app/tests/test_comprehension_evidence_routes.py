"""Generated Comprehension keeps owned task evidence through the real routes."""
import base64
from copy import deepcopy
from html.parser import HTMLParser
import json
import sqlite3
import time
import unittest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from services.comprehension_evidence import build_contracts
from services.comprehension_service import ComprehensionService
from tests.support import isolated_app, select_test_profile


PASSAGE = ('Анна сейчас в аптеке. Потом она идёт на почту. '
           'На почте Анна ждёт Диму. Дима придёт в пять часов.')
QUESTIONS = ['Где Анна сейчас?', 'Куда Анна идёт потом?', 'Кого Анна ждёт?',
             'Когда придёт Дима?', 'Где вы любите встречаться с друзьями?']
ANSWERS = ['  Анна в аптеке.\n', 'Потом она идёт на почту.', 'Она ждёт Диму.',
           '  В пять часов.  ', 'Я люблю встречаться с друзьями в парке.']


def prepared_story():
    facts = [
        ('Анна сейчас в аптеке.', 'Identify the pharmacy as Anna’s current location.'),
        ('Потом она идёт на почту.', 'Identify the post office as Anna’s next destination.'),
        ('На почте Анна ждёт Диму.', 'Identify Dima as the person Anna is waiting for.'),
        ('Дима придёт в пять часов.', 'Identify five o’clock as Dima’s arrival time.'),
    ]
    return {'title': 'Встреча после аптеки', 'title_en': 'Meeting after the pharmacy',
            'text': PASSAGE, 'questions': QUESTIONS.copy(), 'topic_id': 'places',
            'image_url': '/static/media/test-story.png',
            'reading_focus': [{'question_index': index, 'requirement_id': 'a1.reading.practical-information',
                               'passage_excerpt': quote, 'expectation': expectation}
                              for index, (quote, expectation) in enumerate(facts)]}


def assessment_for(payload, answers):
    reports = {}
    for index, contract in payload['contracts'].items():
        answer = answers[int(index)]
        quote = answer.strip()
        start = answer.index(quote)
        reports[index] = {'contract_sha256': contract['contract_sha256'], 'judgements': [{
            'criterion_id': 'reading-focus', 'outcome': 'satisfied', 'score': 2,
            'feedback': 'You found the requested detail in the text.',
            'evidence': [{'quote': quote, 'start': start, 'end': start + len(quote)}]}]}
    return {'feedback': ['Your answer conveys the meaning.'] * len(answers),
            'scores': [8] * len(answers), 'total_score': 8.0, 'criterion_reports': reports}


class HiddenFields(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.fields = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and attrs.get('type') == 'hidden' and attrs.get('name'):
            self.fields[attrs['name']] = attrs.get('value', '')


class ComprehensionEvidenceRouteTests(unittest.TestCase):
    def setUp(self):
        self.prepared = prepared_story()
        # Keep the real repository, contract validators, templates and routes.
        # Only provider-facing operations return fixed synthetic content.
        self.service = ComprehensionService.__new__(ComprehensionService)
        self.service.generate_story = AsyncMock(return_value=deepcopy(self.prepared))
        self.service.prepare_story_from_text = AsyncMock(return_value=deepcopy(self.prepared))
        self.service.generate_image = Mock(return_value='/static/media/test-story.png')
        self.service.generate_audio = Mock(return_value='/static/media/test-story.mp3')
        self.service.assess_task = Mock(side_effect=assessment_for)
        self.service.generate_additional_questions = Mock(return_value=['Как зовут девушку?'])
        self.drive = Mock()
        self.drive.download_vocab_list.return_value = ''
        self.app = isolated_app(self, {'ComprehensionService': self.service, 'GoogleDriveService': self.drive})
        self.db = self.app.config['DB_PATH']
        self.service.db_path = self.db
        self.client = self.app.test_client()
        self.refresh_csrf()

    def refresh_csrf(self):
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']

    def generate(self):
        response = self.client.post('/comprehension', data={'topic': 'places', 'difficulty': 'A1'},
                                    headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        fields = HiddenFields(response.get_data(as_text=True)).fields
        self.assertTrue(fields.get('task_id'), response.get_data(as_text=True))
        return fields

    def submit(self, fields, *, answers=None, path='/comprehension/answer', **overrides):
        return self.client.post(path, data={**fields, 'answers[]': answers if answers is not None else ANSWERS,
                                            **overrides}, headers={'HX-Request': 'true'})

    def rows(self, table):
        with sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]

    def snapshot(self):
        return {table: self.rows(table) for table in (
            'saved_stories', 'comprehension_tasks', 'comprehension_attempts', 'activity_task_contracts',
            'activity_criterion_reports', 'progression_events', 'progression_entries',
            'course_target_observations', 'course_chapter_passes', 'course_continuation_entitlements')}

    def test_generation_freezes_before_answer_check_and_reload_keep_exact_response(self):
        fields = self.generate()
        tasks = self.rows('comprehension_tasks')
        self.assertEqual(len(tasks), 1)
        payload = json.loads(tasks[0]['payload_json'])
        self.assertEqual(payload['contracts'], build_contracts(self.prepared, 'places', 'A1', track_support=True))
        self.assertEqual(payload['questions'], QUESTIONS)
        self.assertEqual(payload['text'], PASSAGE)
        self.assertEqual(len(self.rows('activity_task_contracts')), 4)
        self.assertEqual(self.rows('comprehension_attempts'), [])
        self.assertEqual(self.rows('activity_criterion_reports'), [])
        self.assertEqual(self.rows('progression_entries'), [])
        self.service.assess_task.assert_not_called()

        checked = self.submit(fields)
        self.assertEqual(checked.status_code, 200, checked.get_data(as_text=True))
        self.service.assess_task.assert_called_once_with(payload, ANSWERS)
        attempts = self.rows('comprehension_attempts')
        self.assertEqual(len(attempts), 1)
        self.assertEqual(json.loads(attempts[0]['answers_json']), ANSWERS)
        self.assertEqual(len(self.rows('activity_criterion_reports')), 4)
        # The reflection question keeps useful ordinary feedback but no reading claim.
        self.assertEqual(set(json.loads(attempts[0]['assessment_json'])['criterion_reports']), {'0', '1', '2', '3'})
        self.assertEqual(json.loads(attempts[0]['support_json']), [])
        self.assertEqual(len(self.rows('progression_entries')), 1)
        before_reload = self.snapshot()
        reloaded = self.client.get('/comprehension/load/' + fields['story_id'])
        self.assertEqual(reloaded.status_code, 200)
        html = reloaded.get_data(as_text=True)
        self.assertIn('Understanding the message', html)
        self.assertIn('  Анна в аптеке.\n</textarea>', html)
        self.assertEqual(HiddenFields(html).fields['task_revision'], '1')
        self.assertEqual(self.snapshot(), before_reload)
        self.assertEqual(self.service.assess_task.call_count, 1)

    def test_hidden_story_questions_level_and_media_cannot_override_saved_task(self):
        fields = self.generate()
        checked = self.submit(fields, story_text=base64.b64encode('Подменённый текст'.encode()).decode(),
                              questions_b64=base64.b64encode(b'["Wrong question"]').decode(),
                              story_title='Wrong title', topic='law', difficulty='B2',
                              image_url='https://untrusted.example/image', audio_url='https://untrusted.example/audio')
        self.assertEqual(checked.status_code, 200)
        passed = self.service.assess_task.call_args.args[0]
        self.assertEqual((passed['text'], passed['questions'], passed['topic'], passed['difficulty']),
                         (PASSAGE, QUESTIONS, 'places', 'A1'))
        saved = self.rows('saved_stories')[0]
        self.assertEqual(saved['audio_url'], '/static/media/test-story.mp3')
        self.assertEqual(saved['image_url'], '/static/media/test-story.png')
        self.assertEqual(saved['title'], self.prepared['title'])

    def test_missing_task_identity_cannot_fall_back_to_legacy_check_save_or_more(self):
        fields = self.generate()
        del fields['task_id']
        before = self.snapshot()
        for path in ('/comprehension/answer', '/comprehension/save', '/comprehension/generate_more_questions'):
            with self.subTest(path=path):
                self.assertEqual(self.submit(fields, path=path).status_code, 409)
        self.service.assess_task.assert_not_called()
        self.service.generate_additional_questions.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_same_submission_and_save_unchanged_answers_reuse_report_and_reward(self):
        fields = self.generate()
        first = self.submit(fields)
        self.assertEqual(first.status_code, 200)
        after_first = self.snapshot()
        duplicate = self.submit(fields)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(self.snapshot(), after_first)
        fresh_fields = {**fields, **HiddenFields(first.get_data(as_text=True)).fields}
        self.assertEqual(self.submit(fresh_fields, path='/comprehension/save').status_code, 200)
        self.assertEqual(self.snapshot(), after_first)
        self.assertEqual(self.service.assess_task.call_count, 1)

    def test_removing_both_ids_cannot_check_a_frozen_story_through_the_legacy_form(self):
        fields = self.generate()
        del fields['task_id']
        del fields['story_id']
        self.service.evaluate_answers = Mock(side_effect=AssertionError('Frozen story reached the legacy assessor'))
        before = self.snapshot()
        for path in ('/comprehension/answer', '/comprehension/save', '/comprehension/generate_more_questions'):
            with self.subTest(path=path):
                response = self.submit(fields, path=path)
                self.assertEqual(response.status_code, 409)
        self.service.evaluate_answers.assert_not_called()
        self.service.assess_task.assert_not_called()
        self.service.generate_additional_questions.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_new_submission_with_stale_revision_fails_before_provider(self):
        fields = self.generate()
        self.assertEqual(self.submit(fields).status_code, 200)
        before = self.snapshot()
        response = self.submit(fields, answers=['Исправленный ответ.'] * 5, submission_id=uuid4().hex)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.service.assess_task.call_count, 1)
        self.assertEqual(self.snapshot(), before)

    def test_changed_answer_keeps_prior_report_and_marks_later_check_as_supported(self):
        fields = self.generate()
        first = self.submit(fields)
        self.assertEqual(first.status_code, 200)
        original_attempt = self.rows('comprehension_attempts')[0]
        original_reports = self.rows('activity_criterion_reports')
        fields.update(HiddenFields(first.get_data(as_text=True)).fields)
        changed = ANSWERS.copy()
        changed[0] = 'Сейчас Анна находится в аптеке.'
        self.assertEqual(self.submit(fields, answers=changed).status_code, 200)
        attempts = self.rows('comprehension_attempts')
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0], original_attempt)
        self.assertEqual(json.loads(attempts[1]['support_json']), ['model_answer'])
        reports = self.rows('activity_criterion_reports')
        self.assertEqual(len(reports), 8)
        self.assertEqual(reports[:4], original_reports)
        self.assertEqual(len(self.rows('progression_entries')), 1)
        self.assertEqual(self.service.assess_task.call_count, 2)

    def test_another_profile_cannot_load_check_save_or_extend_task(self):
        fields = self.generate()
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',1)")
        select_test_profile(self.client, 'other')
        self.refresh_csrf()
        before = self.snapshot()
        self.assertEqual(self.client.get('/comprehension/load/' + fields['story_id']).status_code, 404)
        for path in ('/comprehension/answer', '/comprehension/save', '/comprehension/generate_more_questions'):
            with self.subTest(path=path):
                self.assertEqual(self.submit(fields, path=path).status_code, 404)
        self.service.assess_task.assert_not_called()
        self.service.generate_additional_questions.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_more_questions_publish_new_identity_without_changing_old_contracts(self):
        fields = self.generate()
        checked = self.submit(fields)
        self.assertEqual(checked.status_code, 200)
        fields.update(HiddenFields(checked.get_data(as_text=True)).fields)
        old_task = self.rows('comprehension_tasks')[0]
        old_contracts = self.rows('activity_task_contracts')
        old_attempts = self.rows('comprehension_attempts')
        old_reports = self.rows('activity_criterion_reports')
        more = self.submit(fields, path='/comprehension/generate_more_questions')
        self.assertEqual(more.status_code, 200, more.get_data(as_text=True))
        new_fields = HiddenFields(more.get_data(as_text=True)).fields
        self.assertNotEqual(new_fields['task_id'], fields['task_id'])
        self.assertEqual(new_fields['story_id'], fields['story_id'])
        self.assertEqual(self.rows('comprehension_tasks')[0], old_task)
        self.assertEqual(self.rows('activity_task_contracts')[:4], old_contracts)
        self.assertEqual(self.rows('comprehension_attempts'), old_attempts)
        self.assertEqual(self.rows('activity_criterion_reports'), old_reports)
        new_payload = json.loads(self.rows('comprehension_tasks')[1]['payload_json'])
        self.assertEqual(new_payload['questions'], QUESTIONS + ['Как зовут девушку?'])
        self.assertTrue(new_payload['prior_feedback'])
        self.assertEqual(set(new_payload['contracts']), {'0', '1', '2', '3'})
        for index in new_payload['contracts']:
            self.assertNotEqual(new_payload['contracts'][index]['contract_sha256'],
                                json.loads(old_task['payload_json'])['contracts'][index]['contract_sha256'])
        self.assertEqual(self.submit(new_fields, answers=ANSWERS + ['Её зовут Анна.']).status_code, 200)
        latest_attempt = self.rows('comprehension_attempts')[-1]
        self.assertEqual(json.loads(latest_attempt['support_json']), ['model_answer'])

    def test_invalid_provider_evidence_leaves_no_attempt_report_or_reward(self):
        fields = self.generate()
        before = self.snapshot()
        def invalid(payload, answers):
            output = assessment_for(payload, answers)
            output['criterion_reports']['0']['judgements'][0]['evidence'][0]['quote'] = 'Invented answer'
            return output
        self.service.assess_task.side_effect = invalid
        response = self.submit(fields)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn('Invented answer', response.get_data(as_text=True))

    def test_obsolete_question_set_cannot_spend_on_generating_more_questions(self):
        fields = self.generate()
        self.assertEqual(self.submit(fields, path='/comprehension/generate_more_questions').status_code, 200)
        self.service.generate_additional_questions.reset_mock()
        before = self.snapshot()
        obsolete = self.submit(fields, path='/comprehension/generate_more_questions')
        self.assertEqual(obsolete.status_code, 409)
        self.service.generate_additional_questions.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_active_check_prevents_spending_on_an_additional_question_set(self):
        fields = self.generate()
        with sqlite3.connect(self.db) as conn:
            conn.execute('UPDATE comprehension_tasks SET checking_submission_id=?,checking_started_at=? WHERE id=?',
                         (uuid4().hex, int(time.time()), fields['task_id']))
        before = self.snapshot()
        busy = self.submit(fields, path='/comprehension/generate_more_questions')
        self.assertEqual(busy.status_code, 409)
        self.service.generate_additional_questions.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_concurrent_more_questions_request_is_rejected_before_second_provider_call(self):
        fields = self.generate()
        calls = []
        nested_status = []
        def generate_while_another_tab_submits(*args):
            calls.append(args)
            if len(calls) == 1:
                nested = self.submit(fields, path='/comprehension/generate_more_questions')
                nested_status.append(nested.status_code)
            return ['Как зовут девушку?']
        self.service.generate_additional_questions.side_effect = generate_while_another_tab_submits
        response = self.submit(fields, path='/comprehension/generate_more_questions')
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(nested_status, [409])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.rows('comprehension_tasks')), 2)
        self.assertEqual(self.rows('comprehension_attempts'), [])
        self.assertEqual(self.rows('progression_entries'), [])

    def test_revision_change_during_provider_work_prevents_partial_check(self):
        fields = self.generate()
        before = self.snapshot()
        def racing_assessment(payload, answers):
            with sqlite3.connect(self.db) as conn:
                conn.execute('UPDATE comprehension_tasks SET revision=revision+1 WHERE id=?', (fields['task_id'],))
            return assessment_for(payload, answers)
        self.service.assess_task.side_effect = racing_assessment
        self.assertEqual(self.submit(fields).status_code, 409)
        after = self.snapshot()
        self.assertEqual(after['comprehension_tasks'][0]['revision'], 1)
        after['comprehension_tasks'][0]['revision'] = before['comprehension_tasks'][0]['revision']
        self.assertEqual(after, before)

    def test_storage_failure_rolls_back_attempt_reports_story_and_reward(self):
        fields = self.generate()
        before = self.snapshot()
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TRIGGER fail_reading_evidence BEFORE INSERT ON activity_criterion_reports BEGIN SELECT RAISE(ABORT,'test transaction failure'); END")
        response = self.submit(fields)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn('test transaction failure', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
