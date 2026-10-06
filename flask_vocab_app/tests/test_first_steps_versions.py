"""The beginner revision keeps old attempts separate and records guided practice."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from repositories.learning_repository import transaction
from services.first_steps import (DEFAULT_VERSION, LEGACY_VERSION, LESSON_IDS,
                                  chapter_content, completed_lessons)
from tests import test_first_steps as legacy


class FirstStepsVersionTests(unittest.TestCase):
    token = legacy.FirstStepsTests.token
    request = legacy.FirstStepsTests.request
    hello = legacy.FirstStepsTests.hello
    balance = legacy.FirstStepsTests.balance
    counts = legacy.FirstStepsTests.counts
    create_profile = legacy.FirstStepsTests.create_profile

    def setUp(self):
        legacy.FirstStepsTests.setUp(self)
        self.content = chapter_content()

    def post(self, lesson, operation, data=None, *, version=None, status=200, client=None):
        suffix = '?version=' + version if version else ''
        return self.request(f'/api/v1/first-steps/{lesson}/{operation}{suffix}', data,
                            client=client, status=status)

    def read(self, lesson=None, *, version=None, client=None):
        path = '/api/v1/first-steps' + ('/' + lesson if lesson else '')
        if version:
            path += '?version=' + version
        response = (client or self.client).get(path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json

    def definition(self, lesson, version=DEFAULT_VERSION):
        return next(item for item in chapter_content(version)['lessons'] if item['id'] == lesson)

    def prepare(self, lesson, *, version=DEFAULT_VERSION):
        state = self.post(lesson, 'start', version=version)
        for card in self.definition(lesson, version)['teaching']:
            state = self.post(lesson, 'learn', {'teaching_id': card['id']}, version=version)
        return state

    def finish(self, lesson, *, version=DEFAULT_VERSION):
        self.prepare(lesson, version=version)
        for question in self.definition(lesson, version)['questions']:
            self.post(lesson, 'answer', {'question_id': question['id'], 'answer': question['answer']}, version=version)
            self.post(lesson, 'continue', {'question_id': question['id']}, version=version)
        return self.post(lesson, 'complete', version=version)

    def test_default_sequence_reuses_hello_but_does_not_complete_revised_bag_from_old_work(self):
        chapter = self.read()
        self.assertEqual(chapter['version'], DEFAULT_VERSION)
        self.assertEqual(chapter['chapter_id'], 'first-steps-v2')
        self.assertEqual([lesson['id'] for lesson in chapter['lessons']], list(LESSON_IDS))
        self.assertEqual([lesson['status'] for lesson in chapter['lessons']], ['available', 'locked', 'locked', 'locked', 'locked'])
        self.hello()
        old = self.finish('bag', version=LEGACY_VERSION)
        with transaction(self.db) as conn:
            frozen = dict(conn.execute('SELECT * FROM first_steps_attempts WHERE id=?', (old['attempt']['id'],)).fetchone())
            receipts = [tuple(row) for row in conn.execute('SELECT * FROM progression_events')]
            welcome_count = conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='first_delivery'").fetchone()[0]
        chapter = self.read()
        self.assertEqual(chapter['completed_count'], 1)
        self.assertEqual(chapter['next_lesson']['id'], 'bag')
        self.assertEqual(chapter['previous_chapter']['href'], '#first-steps?version=first-steps-v1')
        self.assertEqual(chapter['previous_chapter']['completed_count'], 2)
        revised = self.read('bag')
        self.assertIsNone(revised['attempt'])
        self.assertEqual(revised['previous_lesson']['href'], '#first-steps/bag?version=first-steps-v1')
        self.post('introductions', 'start', status=409)
        new = self.post('bag', 'start')
        self.assertNotEqual(new['attempt']['id'], old['attempt']['id'])
        self.assertEqual(new['attempt']['version'], DEFAULT_VERSION)
        self.assertEqual(new['attempt']['phase'], 'learn')
        self.assertEqual(self.read('bag', version=LEGACY_VERSION)['attempt'], old['attempt'])
        self.assertEqual(self.read('bag', version=LEGACY_VERSION)['updated_lesson_href'], '#first-steps/bag?version=first-steps-v2')
        with transaction(self.db) as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM first_steps_attempts WHERE id=?', (old['attempt']['id'],)).fetchone()), frozen)
            self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM progression_events')], receipts)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='first_delivery'").fetchone()[0], welcome_count)

    def test_explicit_old_edition_and_legacy_only_urls_keep_the_old_sequence(self):
        self.hello()
        self.finish('bag', version=LEGACY_VERSION)
        old = self.post('directions', 'start')
        self.assertEqual(old['version'], LEGACY_VERSION)
        self.assertEqual(old['attempt']['version'], LEGACY_VERSION)
        self.assertEqual(old['lesson']['href'], '#first-steps/directions?version=first-steps-v1')
        self.assertEqual(self.read('directions')['attempt']['id'], old['attempt']['id'])
        self.assertEqual(self.read(version=LEGACY_VERSION)['updated_chapter_href'], '#first-steps?version=first-steps-v2')
        before = self.counts()
        for version in ('unknown', 'first-steps-v3', ''):
            path = '/api/v1/first-steps?version=' + version
            self.assertEqual(self.client.get(path).status_code, 400)
            self.request('/api/v1/first-steps/bag/start?version=' + version, status=400)
        self.post('directions', 'start', version=DEFAULT_VERSION, status=404)
        self.post('introductions', 'start', version=LEGACY_VERSION, status=404)
        self.assertEqual(self.counts(), before)

    def test_hints_do_not_reveal_teaching_or_listening_transcript_before_answer(self):
        self.hello()
        definition = self.definition('bag')
        first = definition['questions'][0]
        self.post('bag', 'start')
        self.post('bag', 'review', {'question_id': first['id']}, status=409)
        self.assertEqual(self.read('bag')['teaching_cards'], [])
        ready = self.prepare('bag')
        self.assertFalse(ready['attempt']['question']['hint_available'])
        self.assertNotIn('review_available', ready['attempt']['question'])
        self.assertEqual(ready['teaching_cards'], [])
        self.assertNotIn('answer', ready['attempt']['question'])
        for question in definition['questions']:
            qid = question['id']
            if question.get('audio_url'):
                current = self.read('bag')['attempt']['question']
                self.assertEqual(current['audio_url'], question['audio_url'])
                self.assertTrue(current['hint_available'])
                self.assertNotIn('hint', current)
                self.assertNotIn('audio_text', current)
                self.assertNotIn('transcript', current)
                supported = self.post('bag', 'hint', {'question_id': qid})
                self.assertEqual(supported['attempt']['question']['hint'], 'Replay the recording and focus on the word after это.')
                for response in (supported, self.read('bag'), self.post('bag', 'hint', {'question_id': qid}),
                                 self.post('bag', 'review', {'question_id': qid})):
                    self.assertNotIn('audio_text', response['attempt']['question'])
                    self.assertNotIn('transcript', response['attempt']['question'])
                    self.assertEqual(response['teaching_cards'], [])
            else:
                for operation in ('hint', 'review'):
                    self.post('bag', operation, {'question_id': qid}, status=409)
                self.assertEqual(self.read('bag')['teaching_cards'], [])
                self.assertNotIn('hint', self.read('bag')['attempt']['question'])
            answered = self.post('bag', 'answer', {'question_id': qid, 'answer': question['answer']})
            self.assertEqual(answered['attempt']['answers'][-1]['hint_used'], bool(question.get('audio_url')))
            if question.get('audio_url'):
                self.assertEqual(answered['attempt']['question']['transcript'], question['transcript'])
            self.post('bag', 'continue', {'question_id': qid})
        self.post('bag', 'review', {'question_id': first['id'], 'teaching_cards': []}, status=400)

    def test_saved_answer_revealing_hints_are_suppressed_without_rewriting_history(self):
        self.hello()
        ready = self.prepare('bag')
        question = self.definition('bag')['questions'][0]
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE first_steps_attempts SET hints_json=? WHERE id=?',
                         (json.dumps([question['id']]), ready['attempt']['id']))
            frozen = dict(conn.execute('SELECT * FROM first_steps_attempts WHERE id=?', (ready['attempt']['id'],)).fetchone())
        for response in (self.read('bag'), self.post('bag', 'start')):
            self.assertFalse(response['attempt']['question']['hint_available'])
            self.assertNotIn('hint', response['attempt']['question'])
            self.assertEqual(response['teaching_cards'], [])
        with transaction(self.db) as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM first_steps_attempts WHERE id=?', (ready['attempt']['id'],)).fetchone()), frozen)
        answered = self.post('bag', 'answer', {'question_id': question['id'], 'answer': question['answer']})
        self.assertTrue(answered['attempt']['answers'][0]['hint_used'])

    def test_existing_bag_listening_uses_sentences_but_preserves_earlier_answer_labels(self):
        self.hello()
        ready = self.prepare('bag')
        definition = self.definition('bag')
        original = deepcopy(definition)
        listening = original['questions'][-1]
        listening['prompt'] = 'Listen. Which thing did you hear?'
        listening['feedback'] = 'The speaker says «Это сумка» — “This is a bag”.'
        old_choices = {'map': 'карта', 'bag': 'сумка', 'letter': 'письмо'}
        for choice in listening['choices']:
            choice['text'] = old_choices[choice['id']]
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE first_steps_attempts SET content_json=? WHERE id=?',
                         (json.dumps(original), ready['attempt']['id']))
        for question in definition['questions'][:-1]:
            self.post('bag', 'answer', {'question_id': question['id'], 'answer': question['answer']})
            self.post('bag', 'continue', {'question_id': question['id']})
        with transaction(self.db) as conn:
            before = dict(conn.execute('SELECT * FROM first_steps_attempts WHERE id=?', (ready['attempt']['id'],)).fetchone())
        current = self.read('bag')['attempt']['question']
        self.assertEqual(current['prompt'], 'Listen. Which sentence did you hear?')
        self.assertEqual(current['choices'], definition['questions'][-1]['choices'])
        self.assertNotIn('transcript', current)
        self.assertNotIn('audio_text', current)
        with transaction(self.db) as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM first_steps_attempts WHERE id=?', (ready['attempt']['id'],)).fetchone()), before)
        body = {'question_id': listening['id'], 'answer': 'letter'}
        answered = self.post('bag', 'answer', body)
        feedback = answered['attempt']['answers'][-1]
        self.assertFalse(feedback['correct'])
        self.assertEqual(feedback['answer_text'], 'Это письмо.')
        self.assertEqual(feedback['correct_answer'], 'Это сумка.')
        self.assertEqual(feedback['feedback'], 'This is a bag.')
        self.assertEqual(self.read('bag')['attempt'], answered['attempt'])
        self.assertEqual(self.post('bag', 'answer', body)['attempt'], answered['attempt'])
        with transaction(self.db, write=True) as conn:
            after = dict(conn.execute('SELECT * FROM first_steps_attempts WHERE id=?', (ready['attempt']['id'],)).fetchone())
            self.assertEqual(after['content_json'], before['content_json'])
            saved = json.loads(after['answers_json'])
            self.assertEqual({key: value for key, value in saved.items() if key != listening['id']}, json.loads(before['answers_json']))
            # An answer recorded before the correction retains its original labels.
            saved[listening['id']].pop('presentation_version')
            conn.execute('UPDATE first_steps_attempts SET answers_json=? WHERE id=?', (json.dumps(saved), ready['attempt']['id']))
        historical = self.read('bag')['attempt']['answers'][-1]
        self.assertEqual(historical['answer_text'], 'письмо')
        self.assertEqual(historical['correct_answer'], 'сумка')
        self.assertEqual(historical['feedback'], listening['feedback'])

    def test_saved_grammar_question_gets_strategy_hint_without_changing_frozen_content(self):
        self.hello()
        self.finish('bag')
        self.finish('introductions')
        ready = self.prepare('gender')
        qid = ready['attempt']['question']['id']
        with transaction(self.db) as conn:
            content = conn.execute('SELECT content_json FROM first_steps_attempts WHERE id=?', (ready['attempt']['id'],)).fetchone()[0]
        self.assertIn('masculine', json.loads(content)['questions'][0]['hint'])
        hinted = self.post('gender', 'hint', {'question_id': qid})
        self.assertEqual(hinted['attempt']['question']['hint'], 'Look at the noun’s last letter and recall the ending patterns.')
        self.assertEqual(hinted['teaching_cards'], [])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT content_json FROM first_steps_attempts WHERE id=?', (ready['attempt']['id'],)).fetchone()[0], content)

    def test_full_new_sequence_earns_participation_once_without_reading_ratings_or_story_checkpoint(self):
        self.hello()
        baseline = self.balance()['skill']
        with transaction(self.db) as conn:
            old_checkpoints = [tuple(row) for row in conn.execute('SELECT * FROM journey_progress')]
        for lesson in LESSON_IDS[1:]:
            if lesson == 'gender':
                first = self.prepare(lesson)
                self.assertEqual(first['attempt']['question']['choices_language'], 'en')
            result = self.finish(lesson)
            self.assertEqual(result['attempt']['version'], DEFAULT_VERSION)
            self.assertEqual(self.balance()['skill'], baseline)
        self.assertTrue(self.read()['complete'])
        self.assertEqual(self.read()['completed_count'], 5)
        before = self.counts(), self.balance()
        with patch('services.first_steps.timestamp', return_value=2_000_000_000):
            self.assertFalse(self.post('ownership', 'complete')['reward']['awarded_now'])
            self.assertEqual(self.post('ownership', 'start')['attempt'], result['attempt'])
        self.assertEqual((self.counts(), self.balance()), before)
        with transaction(self.db) as conn:
            events = conn.execute("SELECT evidence_json FROM progression_events WHERE activity='first_steps'").fetchall()
            self.assertEqual(len(events), 4)
            for row in events:
                receipt = json.loads(row[0])
                self.assertEqual(receipt['basis'], 'guided_intro_practice')
                self.assertTrue(receipt['supported'])
                self.assertNotIn('_skill', receipt)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM course_target_observations WHERE activity='first_steps'").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='first_delivery'").fetchone()[0], 1)
            # Participation can unlock coin thresholds, but never completes the
            # old post-office directions checkpoint on the learner's behalf.
            self.assertFalse(conn.execute("SELECT 1 FROM journey_progress WHERE world_id='post-office' AND completed_at IS NOT NULL").fetchone())
            for old in old_checkpoints:
                self.assertIn(old, [tuple(row) for row in conn.execute('SELECT * FROM journey_progress')])

    def test_guest_claim_transfers_both_editions_without_replaying_hello_or_losing_partial_work(self):
        self.hello(profile=False)
        old = self.finish('bag', version=LEGACY_VERSION)
        new = self.finish('bag')
        self.post('introductions', 'start')
        card = self.definition('introductions')['teaching'][0]
        partial = self.post('introductions', 'learn', {'teaching_id': card['id']})
        self.assertEqual(self.read()['pending_reward'], 6)
        profile = self.create_profile()
        self.assertEqual(self.read('bag', version=LEGACY_VERSION)['attempt'], old['attempt'])
        self.assertEqual(self.read('bag')['attempt'], new['attempt'])
        self.assertEqual(self.read('introductions')['attempt'], partial['attempt'])
        self.assertEqual(self.balance(profile)['balance'], 9)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_steps_attempts WHERE guest_token IS NOT NULL').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_steps_attempts WHERE profile_id=?', (profile,)).fetchone()[0], 3)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='first_delivery'").fetchone()[0], 1)
            self.assertEqual(len(completed_lessons(conn, profile, version=DEFAULT_VERSION)), 2)
            self.assertEqual(len(completed_lessons(conn, profile, version=LEGACY_VERSION)), 2)
            self.assertEqual(len(completed_lessons(conn, profile)), 3)

    def test_new_teaching_and_answers_stay_frozen_when_authored_content_changes(self):
        self.hello()
        started = self.post('bag', 'start')
        changed = deepcopy(self.content)
        changed['lessons'][0]['teaching'][0]['word'] = 'Changed teaching'
        changed['lessons'][0]['questions'][0]['feedback'] = 'Changed feedback'
        with patch('services.first_steps.chapter_content', return_value=changed):
            self.assertEqual(self.read('bag')['attempt'], started['attempt'])
            self.assertEqual(self.post('bag', 'start')['attempt'], started['attempt'])
        self.assertEqual(self.read('bag')['attempt']['teaching'], self.definition('bag')['teaching'][0])

    def test_review_remains_owned_csrf_protected_and_cannot_submit_personal_name_or_scores(self):
        self.hello()
        ready = self.prepare('bag')
        body = {'question_id': ready['attempt']['question']['id']}
        path = '/api/v1/first-steps/bag/review?version=first-steps-v2'
        self.assertEqual(self.client.post(path, json=body).status_code, 403)
        self.assertEqual(self.client.post(path, json=body, headers={'X-CSRF-Token': self.token(), 'X-Profile-ID': 'somebody-else'}).status_code, 409)
        for extra in ({'name': 'Tom'}, {'score': 1}, {'profile_id': 'other'}, {'version': LEGACY_VERSION}):
            self.request(path, body | extra, status=400)
        other = self.app.test_client()
        self.hello(profile=False, client=other)
        self.assertIsNone(self.read('bag', client=other)['attempt'])
        self.post('bag', 'review', body, client=other, status=409)


class FirstStepsPracticeVersionTests(unittest.TestCase):
    from tests.test_first_steps_practice import FirstStepsPracticeTests as _Helpers
    setUp = _Helpers.setUp
    post = _Helpers.post
    hello = _Helpers.hello
    finish_batch = _Helpers.finish_batch

    def complete(self, version):
        self.hello()
        for lesson in chapter_content(version)['lessons']:
            base = '/api/v1/first-steps/' + lesson['id'] + '/'
            suffix = '?version=' + version
            self.post(base + 'start' + suffix)
            for card in lesson['teaching']:
                self.post(base + 'learn' + suffix, {'teaching_id': card['id']})
            for question in lesson['questions']:
                self.post(base + 'answer' + suffix, {'question_id': question['id'], 'answer': question['answer']})
                self.post(base + 'continue' + suffix, {'question_id': question['id']})
            self.post(base + 'complete' + suffix)

    def test_chapter_practice_requires_completion_of_the_requested_edition(self):
        self.complete(LEGACY_VERSION)
        self.post('/api/v1/first-steps/chapter/flashcards?version=' + DEFAULT_VERSION, status=409)
        self.post('/api/v1/first-steps/practice/word-jumble?version=' + DEFAULT_VERSION, status=409)
        legacy = self.post('/api/v1/first-steps/chapter/flashcards?version=' + LEGACY_VERSION, status=201)
        self.assertEqual(legacy['first_steps']['url'], '/#first-steps?version=' + LEGACY_VERSION)
        self.post('/api/v1/first-steps/bag/flashcards?version=unknown', status=400)
        self.post('/api/v1/first-steps/practice/word-jumble?version=unknown', status=400)

    def test_revised_chapter_native_cards_use_existing_media_pipeline_and_versioned_origin(self):
        self.complete(DEFAULT_VERSION)
        batch = self.post('/api/v1/first-steps/chapter/flashcards?version=' + DEFAULT_VERSION, status=201)
        self.assertEqual(batch['first_steps']['url'], '/#first-steps?version=' + DEFAULT_VERSION)
        self.assertEqual(batch['first_steps']['version'], DEFAULT_VERSION)
        self.assertGreater(batch['total'], 3)
        done = self.finish_batch(batch)
        repeated = self.post('/api/v1/first-steps/chapter/flashcards?version=' + DEFAULT_VERSION, status=201)
        self.assertEqual(repeated['id'], done['id'])
        self.assertEqual(self.text.calls, [])
        result = self.post('/api/v1/first-steps/practice/word-jumble?version=' + DEFAULT_VERSION, status=201)
        self.assertEqual(result, self.post('/api/v1/first-steps/practice/word-jumble?version=' + DEFAULT_VERSION, status=201))
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
