"""Complete published route, durable drafts and shared native follow-ups."""
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from repositories.learning_repository import transaction
from services.course_progression import course_catalogue
from services import course_progression, course_releases
from tests.support import isolated_app
from tests.test_card_media import MediaProvider
from tests.test_personal_flashcards import Provider


class CourseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()
        self.app = isolated_app(self, {'OpenAIService': self.provider, 'CardMediaProvider': MediaProvider()})
        self.app.config['COURSE_DEFAULT_RELEASE'] = 'a1-journey-v2'
        self.db = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        initial = self.client.get('/api/v1/course').json
        self.pid, self.csrf = initial['profile_id'], initial['csrf_token']
        with self.client.session_transaction() as saved:
            self.access = saved['personal_access_id']
        self.n = 0
        if initial['release_id'] != 'a1-journey-v2':
            self.post('releases/a1-journey-v2/switch', {'from_release_id': initial['release_id'], 'request_id': 'move-v2'})

    def post(self, path, body, status=200):
        response = self.client.post('/api/v1/course/' + path, json=body, headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(response.status_code, status, response.text)
        return response.json

    def start(self, chapter='home'):
        self.n += 1
        return self.post(f'chapters/{chapter}/checkpoint', {'request_id': f'start-{self.n}', 'release_id': 'a1-journey-v2', 'challenge': True})

    def frozen(self, attempt_id):
        with transaction(self.db) as conn:
            return json.loads(conn.execute('SELECT frozen_json FROM course_checkpoint_attempts WHERE id=?', (attempt_id,)).fetchone()[0])

    def finish(self, attempt, answers=None):
        self.n += 1
        self.post(f"checkpoints/{attempt['id']}/listened", {})
        answers = answers or {q['id']: q['answer'] for q in self.frozen(attempt['id'])['variant']['questions']}
        return self.post(f"checkpoints/{attempt['id']}/answer", {'answers': answers, 'submission_id': f'answer-{self.n}'})

    def test_all_four_milestones_and_no_answer_metadata_in_public_choices(self):
        for chapter in ('home', 'postoffice', 'market', 'leavingtown'):
            attempt = self.start(chapter)
            self.assertEqual(len(attempt['questions']), 16 if chapter == 'leavingtown' else 8)
            self.assertFalse('transcript' in attempt['listening'])
            self.assertFalse('consequence' in attempt)
            for question in attempt['questions']:
                self.assertNotIn('answer', question)
                self.assertNotIn('target_ids', question)
                self.assertTrue(all(set(c) == {'id', 'text'} for c in question['choices']))
            result = self.finish(attempt)
            self.assertTrue(result['result']['passed'])
            self.assertEqual(result['original_letter_state'], 'sealed')
            self.assertTrue(result['consequence'])
        self.assertTrue(result['course']['completed'])
        self.assertEqual(result['course']['unlocked_levels'], ['A1', 'A2'])
        self.assertEqual(result['course']['completed_milestones'], 4)
        self.assertEqual({x['kind'] for x in result['result']['component_results']}, {'reading', 'listening', 'language', 'response'})
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 0)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_future_stops_reveal_only_after_passing_and_free_practice_stays_available(self):
        authored = course_catalogue('a1-journey-v2')
        current = self.client.get('/api/v1/course').json
        self.assertEqual(current['chapter_count'], 4)
        self.assertEqual(current['chapters'][0]['title'], authored['chapters'][0]['title'])
        for chapter in current['chapters'][1:]:
            self.assertEqual(chapter['status'], 'locked')
            for field in ('title', 'title_ru', 'intro', 'intro_ru'):
                self.assertEqual(chapter[field], '')
            for field in ('topics', 'objectives', 'preparation'):
                self.assertEqual(chapter[field], [])
            self.assertIsNone(chapter['target_coverage'])
            self.assertEqual((chapter['progress'], chapter['preparation_progress']), (0, 0))
            self.assertEqual((chapter['activity_preparation_progress'], chapter['target_preparation_progress']), (0, 0))
            self.assertEqual(chapter['preparation_basis'], 'none')
        self.post('chapters/market/checkpoint', {'request_id': 'later-letter', 'challenge': True}, 403)
        standalone = self.post('chapters/market/practice', {'request_id': 'later-free-practice'})
        self.assertEqual(standalone['status'], 'active')
        self.assertTrue(standalone['current_item']['teaching'])
        after = self.finish(self.start())['course']
        self.assertEqual(after['chapters'][0]['status'], 'passed')
        self.assertEqual(after['chapters'][1]['title'], authored['chapters'][1]['title'])
        self.assertTrue(after['chapters'][1]['topics'])
        self.assertEqual(after['chapters'][2]['title'], '')
        self.assertEqual(course_catalogue('a1-journey-v2'), authored)

    def test_existing_learner_explicit_switch_preserves_active_letter_and_earned_access(self):
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT OR REPLACE INTO course_enrolments VALUES (?,'A1','a1-v1',1,'schema-044')", (self.pid,))
            conn.execute("INSERT INTO course_continuation_entitlements VALUES (?,'A2','a1-v1','legacy-course-completion',1)", (self.pid,))
        old = self.post('chapters/a1-post-office/checkpoint', {'request_id': 'old', 'release_id': 'a1-v1', 'challenge': True})
        before = self.frozen(old['id'])
        preview = self.client.get('/api/v1/course').json['release_upgrade']
        self.assertEqual(preview['active_attempts'][0]['id'], old['id'])
        self.assertEqual(preview['retained_access'], ['A2'])
        request = {'from_release_id': 'a1-v1', 'request_id': 'explicit-switch'}
        changed = self.post('releases/a1-journey-v2/switch', request)
        self.assertEqual(changed['unlocked_levels'], ['A1', 'A2'])
        self.assertEqual(changed['current_chapter_id'], 'home')
        self.assertEqual(changed, self.post('releases/a1-journey-v2/switch', request))
        self.assertEqual(self.frozen(old['id']), before)
        self.assertEqual(self.client.get('/api/v1/course/checkpoints/' + old['id']).json['status'], 'active')
        self.assertEqual(changed['previous_courses'][0]['attempts'][0]['id'], old['id'])

    def test_fresh_profile_is_unenrolled_until_first_preparation_command(self):
        with transaction(self.db) as conn:
            self.assertIsNone(conn.execute('SELECT * FROM course_enrolments WHERE profile_id=?', (self.pid,)).fetchone())
        self.post('chapters/home/practice', {'request_id': 'begin'})
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT release_id FROM course_enrolments WHERE profile_id=?', (self.pid,)).fetchone()[0], 'a1-journey-v2')

    def test_explicit_course_identity_is_read_only_and_unknown_levels_stay_unavailable(self):
        with transaction(self.db) as conn:
            before = [tuple(row) for row in conn.execute('SELECT * FROM course_enrolments')]
        historical = self.client.get('/api/v1/course?release_id=a1-v1&band=A1')
        self.assertEqual(historical.status_code, 200)
        self.assertEqual(historical.json['release_id'], 'a1-v1')
        self.assertEqual(historical.json['current_release_id'], 'a1-journey-v2')
        self.assertFalse(historical.json['is_current_release'])
        self.assertEqual(self.client.get('/api/v1/course?band=A1').json['release_id'], 'a1-journey-v2')
        for query, status, code in [('band=A2', 404, 'course_release_unavailable'),
                                    ('release_id=not-published', 404, 'course_release_unavailable'),
                                    ('release_id=a1-v1&band=A2', 400, 'invalid_input'),
                                    ('band=', 400, 'invalid_input'),
                                    ('release_id=a1-v1&release_id=a1-journey-v2', 400, 'invalid_input')]:
            with self.subTest(query=query):
                response = self.client.get('/api/v1/course?' + query)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json['error']['code'], code)
        self.post('chapters/a1-post-office/checkpoint', {'request_id': 'historical-start', 'release_id': 'a1-v1', 'challenge': True}, 409)
        with transaction(self.db) as conn:
            self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM course_enrolments')], before)

    def test_preparation_receipt_stays_bound_after_enrolment_changes(self):
        body = {'request_id': 'bound-preparation', 'release_id': 'a1-journey-v2'}
        saved = self.post('chapters/home/practice', body)
        self.assertEqual(saved['target_catalogue_version'], 'a1-targets-v1')
        self.assertEqual(saved['content_version'], 'a1-target-practice-v1')
        self.assertEqual(saved['coverage']['practice_href'], '/#journey/release/a1-journey-v2/practice/start/home')
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE course_enrolments SET release_id='a1-v1' WHERE profile_id=?", (self.pid,))
        self.assertEqual(self.post('chapters/home/practice', body), saved)
        self.assertEqual(self.client.get('/api/v1/course/practice/' + saved['id']).json, saved)
        self.post('chapters/home/practice', dict(body, request_id='new-start'), 409)
        self.post('chapters/home/practice', dict(body, release_id='a1-v1'), 409)

    def test_legacy_letter_has_no_native_card_generation_contract(self):
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT OR REPLACE INTO course_enrolments VALUES (?,'A1','a1-v1',1,'schema-044')", (self.pid,))
        attempt = self.post('chapters/a1-post-office/checkpoint', {'request_id': 'legacy-card', 'release_id': 'a1-v1', 'challenge': True})
        self.finish(attempt)
        result = self.post(f"checkpoints/{attempt['id']}/flashcards", {}, 404)
        self.assertEqual(result['error']['code'], 'flashcards_unavailable')

    def test_component_minimum_prevents_a_pass_with_both_replies_wrong(self):
        for chapter in ('home', 'postoffice', 'market'):
            self.finish(self.start(chapter))
        attempt = self.start('leavingtown')
        questions = self.frozen(attempt['id'])['variant']['questions']
        answers = {q['id']: q['answer'] for q in questions}
        for q in questions:
            if q['kind'] == 'response':
                answers[q['id']] = next(c['id'] for c in q['choices'] if c['id'] != q['answer'])
        result = self.finish(attempt, answers)
        self.assertEqual(result['result']['score'], 14)
        self.assertFalse(result['result']['passed'])
        self.assertEqual(result['course']['completed_milestones'], 3)

    def test_server_draft_conflict_and_supported_retry_keep_exact_work(self):
        attempt = self.start()
        q = attempt['questions'][0]
        draft = {q['id']: q['choices'][0]['id']}
        saved = self.post(f"checkpoints/{attempt['id']}/draft", {'answers': draft, 'revision': 0})
        self.assertEqual((saved['draft_answers'], saved['draft_revision']), (draft, 1))
        self.post(f"checkpoints/{attempt['id']}/draft", {'answers': {}, 'revision': 0}, 409)
        self.post(f"checkpoints/{attempt['id']}/support", {'kind': 'hint', 'question_id': q['id']})
        result = self.finish(attempt)
        self.assertFalse(result['result']['passed'])
        fresh = self.start()
        self.assertNotEqual(self.frozen(fresh['id'])['variant']['id'], self.frozen(attempt['id'])['variant']['id'])
        self.assertEqual(self.client.get('/api/v1/course/checkpoints/' + attempt['id']).json['draft_answers'], draft)

    def test_preparation_policy_is_frozen_without_rewriting_content_or_earned_passes(self):
        published = {release_id: (course_releases.DATA_DIR / release['catalogue_file']).read_bytes()
                     for release_id, release in course_releases.RELEASES.items()}
        attempt = self.start()
        frozen = self.frozen(attempt['id'])
        self.assertEqual(frozen['preparation_policy'], 'activity-or-target-practice-v1')
        self.assertEqual(frozen['rubric']['minimum_correct'], 7)
        self.assertTrue(self.finish(attempt)['result']['passed'])
        tables = ('course_checkpoint_attempts', 'course_chapter_passes', 'course_continuation_entitlements')
        with transaction(self.db) as conn:
            saved = {table: [tuple(row) for row in conn.execute('SELECT * FROM ' + table)] for table in tables}
        with patch.object(course_progression, 'JOURNEY_PREPARATION_POLICY', 'later-preparation-policy'):
            current = self.client.get('/api/v1/course').json
            self.assertEqual(current['preparation_policy'], 'later-preparation-policy')
            self.assertEqual(current['completed_milestones'], 1)
            self.assertEqual(self.post('chapters/home/checkpoint', {
                'request_id': 'start-1', 'release_id': 'a1-journey-v2', 'challenge': True}), attempt)
        self.assertEqual(self.frozen(attempt['id']), frozen)
        with transaction(self.db) as conn:
            self.assertEqual({table: [tuple(row) for row in conn.execute('SELECT * FROM ' + table)] for table in tables}, saved)
        for release_id, content in published.items():
            release = course_releases.RELEASES[release_id]
            self.assertEqual((course_releases.DATA_DIR / release['catalogue_file']).read_bytes(), content)
            self.assertEqual(sha256(content).hexdigest(), release['catalogue_sha256'])

    def test_transcript_allows_supported_practice_without_claiming_listening(self):
        attempt = self.start()
        self.post(f"checkpoints/{attempt['id']}/support", {'kind': 'transcript'})
        answers = {q['id']: q['answer'] for q in self.frozen(attempt['id'])['variant']['questions']}
        result = self.post(f"checkpoints/{attempt['id']}/answer", {'answers': answers, 'submission_id': 'accessible-practice'})
        self.assertFalse(result['result']['passed'])
        self.assertFalse(result['listened'])
        self.assertEqual(result['status'], 'retry')
        with transaction(self.db) as conn:
            observations = conn.execute('SELECT target_id FROM course_target_observations WHERE checkpoint_id=?', (attempt['id'],)).fetchall()
        listening_targets = {target for question in self.frozen(attempt['id'])['variant']['questions']
                             if question['kind'] == 'listening' for target in question['target_ids']}
        self.assertTrue(listening_targets)
        self.assertTrue(observations)
        self.assertFalse(listening_targets & {row['target_id'] for row in observations})

    def test_reply_reuses_existing_writing_and_keeps_owner(self):
        attempt = self.start()
        self.post(f"checkpoints/{attempt['id']}/writing", {'request_id': 'reply'}, 409)
        self.finish(attempt)
        result = self.post(f"checkpoints/{attempt['id']}/writing", {'request_id': 'reply'})
        self.assertEqual(result, self.post(f"checkpoints/{attempt['id']}/writing", {'request_id': 'reply-again'}))
        self.assertEqual(self.client.get(result['href']).status_code, 200)
        with transaction(self.db) as conn:
            rows = conn.execute('SELECT owner_profile_id,task FROM writing_exercises').fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['owner_profile_id'], self.pid)
            self.assertEqual(rows[0]['task'], self.frozen(attempt['id'])['variant']['writing_task']['task'])

    def test_native_clozes_keep_authoritative_context_and_all_media(self):
        attempt = self.start()
        self.finish(attempt)
        batch = self.post(f"checkpoints/{attempt['id']}/flashcards", {}, 201)
        again = self.post(f"checkpoints/{attempt['id']}/flashcards", {}, 201)
        self.assertEqual(batch['id'], again['id'])
        generator = self.app.extensions['learning']['generator']
        for _ in range(30):
            batch = generator.next(self.access, batch['id'])
            if batch['complete']:
                break
        self.assertTrue(batch['complete'])
        self.assertTrue(all(i['status'] == 'saved' for i in batch['items']))
        self.assertEqual({j['kind'] for i in batch['items'] for j in i['media_jobs']}, {'image', 'word_audio', 'sentence_audio'})
        self.assertEqual(self.provider.calls, [])
        with transaction(self.db) as conn:
            items = [json.loads(row[0]) for row in conn.execute('SELECT response FROM native_card_generation_items WHERE batch_id=?', (batch['id'],))]
        expected = self.frozen(attempt['id'])['variant']['flashcard_candidates']
        self.assertEqual({i['sentence'] for i in items}, {c['sentence'] for c in expected})

    def test_all_authored_clozes_resolve_through_existing_morphology_and_card_contract(self):
        from services.lesson_cards import LessonCards
        generator = self.app.extensions['learning']['generator']
        checked = 0
        with transaction(self.db, write=True) as conn:
            for chapter in course_catalogue('a1-journey-v2')['chapters']:
                for variant in chapter['variants']:
                    for candidate in variant['flashcard_candidates']:
                        with self.subTest(variant=variant['id'], form=candidate['form']):
                            word = LessonCards.resolve(conn, candidate | {'surface': candidate['form']})
                            generator.pack('checked-candidate', word, {'kind': 'ru-cloze'},
                                           {'english': candidate['target_meaning'], 'sentence': candidate['sentence'],
                                            'sentence_english': candidate['translation'], 'notes': candidate.get('notes', '')})
                            checked += 1
        self.assertEqual(checked, 22)

    def test_preparation_api_and_shared_pipeline_capture(self):
        state = self.post('chapters/home/practice', {'request_id': 'prep', 'release_id': 'a1-journey-v2'})
        self.assertIsNone(state['current_item']['question'])
        # The learner cannot send their own sentence or an invented meaning.
        attempt = self.start()
        self.post(f"checkpoints/{attempt['id']}/vocabulary", {'word': 'сумка', 'request_id': 'word'}, 409)
        self.finish(attempt)
        self.post(f"checkpoints/{attempt['id']}/vocabulary", {'word': 'вертолёт', 'request_id': 'outside'}, 404)
        pipeline = self.app.extensions['services']['SyncService']
        with patch.object(pipeline, 'enrich_words', return_value={'pending': []}) as enrich:
            result = self.post(f"checkpoints/{attempt['id']}/vocabulary", {'word': 'сумка', 'lemma': 'сумка', 'pos': 'NOUN', 'request_id': 'word'})
        enrich.assert_called_once_with([result['word_id']])
        self.assertTrue(result['flashcards_href'].endswith(str(result['word_id'])))
