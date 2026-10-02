"""Study actions reuse owned sources and existing stores, without changing evidence."""
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from repositories.learning_repository import LearningError, transaction
from repositories.writing_repository import WritingRepository
from services.feedback_study import _speech_examples, actions, source
from tests.support import isolated_app

ORIGINAL = 'Я в библиотеку. Потом я иду в школа.'
EXAMPLE = 'Я в библиотеке. Потом я иду в школу.'


class FeedbackStudyTests(unittest.TestCase):
    def setUp(self):
        self.sentence_service = Mock()
        self.app = isolated_app(self, {'SentenceService': self.sentence_service})
        self.client = self.app.test_client(); self.db = self.app.config['DB_PATH']
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']
        with transaction(self.db, write=True) as conn:
            self.exercise = WritingRepository.create_in_transaction(conn,
                {'title': 'Место', 'title_en': 'Where I am', 'task': 'Напишите сообщение.', 'task_en': 'Write a message.',
                 'required_words': ['библиотека', 'школа', 'идти']}, 'places', 'A1', 30, 'personal-learning')
            self.attempt = conn.execute("INSERT INTO writing_attempts(exercise_id,response,score,score_max,strength,next_step,example,ui_language,source) VALUES (?,?,5,10,?,?,?,?, 'writing-v1')",
                (self.exercise, ORIGINAL, 'The locations are clear.', 'Check the endings.', EXAMPLE, 'en')).lastrowid
        self.base = f'/study/feedback/writing/{self.attempt}'

    def post(self, url, data):
        return self.client.post(url, data=data, headers={'X-CSRF-Token': self.token})

    def counts(self):
        with transaction(self.db) as conn:
            return {name: conn.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
                    for name in ('sentences', 'words', 'forms', 'native_card_batches', 'writing_attempts', 'progression_events')}

    def test_preview_and_phrasebook_prefill_make_no_study_writes_or_provider_calls(self):
        before = self.counts()
        page = self.client.get(self.base).get_data(as_text=True)
        self.assertIn('Я в библиотеке.', page)
        self.assertNotIn(ORIGINAL, page)
        prefill = self.client.get('/sentences/saved?' + urlencode({'study_activity': 'writing', 'study_id': self.attempt, 'study_example': 1}))
        self.assertEqual(prefill.status_code, 200)
        self.assertIn('Потом я иду в школу.</textarea>', prefill.get_data(as_text=True))
        self.assertEqual(before, self.counts())
        self.sentence_service.translate_for_library.assert_not_called()

    def test_confirmed_phrasebook_save_uses_existing_dedup_and_preserves_original(self):
        data = {'sentence': 'Я в библиотеке.', 'english': 'I am in the library.', 'topic': 'places', 'difficulty': '1'}
        first = self.post('/sentence/add', data)
        self.assertEqual(first.status_code, 303)
        second = self.post('/sentence/add', data)
        self.assertEqual(first.location, second.location)
        with transaction(self.db) as conn:
            row = conn.execute('SELECT sentence,english FROM sentences WHERE sentence=?', (data['sentence'],)).fetchone()
            self.assertEqual(tuple(row), (data['sentence'], data['english']))
            self.assertEqual(conn.execute('SELECT response FROM writing_attempts WHERE id=?', (self.attempt,)).fetchone()[0], ORIGINAL)
        self.sentence_service.translate_for_library.assert_not_called()

    def test_word_action_requires_consent_then_runs_existing_morphology_and_enrichment(self):
        self.app.config.update(OPENAI_API_KEY='test-configured', NATIVE_FLASHCARDS_ENABLED=True)
        before = self.counts()
        preview = self.client.get(self.base + '?intent=flashcards')
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(before, self.counts())
        data = {'example': '0', 'reading': json.dumps(['библиотеке', 'библиотека', 'NOUN'])}
        endpoint = self.base + '/word?intent=flashcards'
        self.assertEqual(self.client.post(endpoint, data=data).status_code, 403)
        self.assertEqual(before, self.counts())
        first = self.post(endpoint, data)
        self.assertEqual(first.status_code, 303, first.get_data(as_text=True))
        self.assertTrue(first.location.startswith('/#generate?word_id='))
        word_id = int(first.location.split('=')[-1])
        with transaction(self.db) as conn:
            word = conn.execute('SELECT lemma,mnemonic,topic FROM words WHERE id=?', (word_id,)).fetchone()
            self.assertEqual(word['lemma'], 'библиотека')
            self.assertTrue(word['mnemonic']); self.assertTrue(json.loads(word['topic']))
            self.assertTrue(conn.execute('SELECT 1 FROM forms WHERE word_id=? AND form=?', (word_id, 'библиотеке')).fetchone())
            self.assertEqual(conn.execute('SELECT response FROM writing_attempts WHERE id=?', (self.attempt,)).fetchone()[0], ORIGINAL)
        counts = self.counts()
        self.assertEqual(self.post(endpoint, data).location, first.location)
        self.assertEqual(counts, self.counts())
        self.assertEqual(counts['native_card_batches'], before['native_card_batches'])

    def test_unowned_and_fabricated_text_cannot_be_used(self):
        self.app.config.update(OPENAI_API_KEY='test-configured', NATIVE_FLASHCARDS_ENABLED=True)
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('another','Another','cat','UTC',0)")
            conn.execute('UPDATE writing_exercises SET owner_profile_id=? WHERE id=?', ('another', self.exercise))
        for route in (self.base, '/sentences/saved?' + urlencode({'study_activity': 'writing', 'study_id': self.attempt, 'study_example': 0})):
            self.assertEqual(self.client.get(route).status_code, 404)
        self.assertEqual(self.post(self.base + '/word?intent=flashcards', {'example': '0', 'reading': '["библиотеке","библиотека","NOUN"]'}).status_code, 404)
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE writing_exercises SET owner_profile_id=? WHERE id=?', ('personal-learning', self.exercise))
        self.assertEqual(self.post(self.base + '/word?intent=flashcards', {'example': '0', 'reading': '["парк","парк","NOUN"]'}).status_code, 404)
        self.assertEqual(self.client.get('/sentences/saved?' + urlencode({'study_activity': 'writing', 'study_id': self.attempt, 'study_example': '-1'})).status_code, 422)

    def test_action_visibility_matches_workspace_and_generator_capability(self):
        page = self.client.get('/writing/load/' + str(self.exercise)).get_data(as_text=True)
        self.assertIn('Save sentence', page); self.assertNotIn('Make flashcards', page)
        self.app.config.update(OPENAI_API_KEY='test-configured', NATIVE_FLASHCARDS_ENABLED=True)
        page = self.client.get('/writing/load/' + str(self.exercise)).get_data(as_text=True)
        self.assertIn('Make flashcards', page)
        self.app.config.update(HOSTED_AI_TRIAL=True, AI_TRIAL_ENABLED=False, AI_TRIAL_IDENTITY="demo:test")
        self.assertEqual(self.client.get(self.base + '?intent=flashcards').status_code, 403)
        self.assertEqual(self.client.get(self.base).status_code, 200)
        self.app.config['HOSTED_AI_TRIAL'] = False
        self.app.config['PUBLIC_DEMO'] = True
        page = self.client.get('/writing/load/' + str(self.exercise)).get_data(as_text=True)
        self.assertNotIn(self.base, page)
        self.assertEqual(self.client.get(self.base).status_code, 403)
        self.app.config['PUBLIC_DEMO'] = False
        with self.app.test_request_context('/'):
            self.app.config['WORD_POST_HOUSEHOLD_ENABLED'] = True
            with transaction(self.db) as conn:
                self.assertEqual(actions(conn, 'personal-learning', 'writing', str(self.attempt)), [])

    def test_enrichment_failure_keeps_word_but_does_not_open_generator(self):
        self.app.config.update(OPENAI_API_KEY='test-configured', NATIVE_FLASHCARDS_ENABLED=True)
        with patch.object(self.app.extensions['services']['SyncService'], 'enrich_words', return_value={'pending': [1]}):
            response = self.post(self.base + '/word?intent=flashcards', {'example': '0', 'reading': '["библиотеке","библиотека","NOUN"]'})
        self.assertEqual(response.status_code, 503)
        self.assertIn('memory hint and topics are not ready', response.get_data(as_text=True))
        with transaction(self.db) as conn:
            self.assertTrue(conn.execute("SELECT 1 FROM words WHERE lemma='библиотека'").fetchone())
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0], 0)

    def test_speaking_study_example_keeps_correction_separate_from_original_and_uncertainty(self):
        report = {'speech_status': 'russian', 'transcript': ORIGINAL, 'uncertain_phrases': [],
                  'corrections': [{'original': 'в библиотеку', 'replacement': 'в библиотеке'}, {'original': 'в школа', 'replacement': 'в школу'}]}
        self.assertEqual(_speech_examples(report), ['Я в библиотеке.', 'Потом я иду в школу.'])
        self.assertEqual(report['transcript'], ORIGINAL)
        report['uncertain_phrases'] = ['в библиотеку']
        self.assertEqual(_speech_examples(report), ['Потом я иду в школу.'])
        report['speech_status'] = 'unclear'
        self.assertEqual(_speech_examples(report), [])

    def test_speaking_followups_require_owned_completed_feedback(self):
        from repositories import activity_review_repository as reviews
        from uuid import uuid4
        with transaction(self.db, write=True) as conn:
            saved = reviews.save_original(conn, profile_id='personal-learning', activity='unit_exchange', task_key='exchange',
                submission_id=uuid4().hex, task_revision=0, original={'recordings': ['original']}, task={}, contract={'level': 'A1'},
                support=[], support_receipts=[], effects_policy=reviews.DEFAULT_POLICY)
        route = '/study/feedback/unit_exchange/' + saved['id']
        self.assertEqual(self.client.get(route).status_code, 404)
        with transaction(self.db, write=True) as conn:
            _, token = reviews.claim(conn, 'personal-learning', saved['id'])
            reviews.finish(conn, 'personal-learning', saved['id'], token, {},
                {'speech_status': 'russian', 'transcript': 'Я в библиотеку.', 'uncertain_phrases': [],
                 'corrections': [{'original': 'в библиотеку', 'replacement': 'в библиотеке'}]})
            with self.assertRaisesRegex(LearningError, 'selected profile'):
                source(conn, 'other-profile', 'unit_exchange', saved['id'])
        page = self.client.get(route)
        self.assertEqual(page.status_code, 200)
        self.assertIn('Я в библиотеке.', page.get_data(as_text=True))
        with transaction(self.db) as conn:
            immutable = reviews.get(conn, 'personal-learning', saved['id'])
            self.assertEqual(immutable['original'], {'recordings': ['original']})
            self.assertNotIn('study_actions', immutable['result'])
