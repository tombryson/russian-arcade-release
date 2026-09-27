"""Owned reading capture uses the same morphology/enrichment path as games."""
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from repositories.learning_repository import transaction
from services.ai_trial_budget import TrialDenied
from services.story_vocabulary import story_key
from tests.support import isolated_app
from utils.story_processing import process_story_words


class StoryVocabularyTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, demo=False)
        self.db = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        self.token = self.client.get('/api/v1/user-session').get_json()['csrf_token']
        self.text = 'Анна стоит перед аптекой. Она видит печь.'
        with transaction(self.db, write=True) as conn:
            self.story = conn.execute('INSERT INTO saved_stories(title,text,owner_profile_id) VALUES (?,?,?)',
                                      ('По дороге', self.text, 'personal-learning')).lastrowid
        self.source = {'story_id': self.story, 'story_key': story_key(self.text)}
        self.sync = self.app.extensions['services']['SyncService']._get()

    def lookup(self, word='аптекой', source=None):
        return self.client.get('/word-details/' + word + '?' + urlencode(source or self.source))

    def add(self, word='аптекой', lemma='аптека', pos='NOUN', source=None, token=True):
        return self.client.post('/add-vocab/' + lemma, json={'word': word, 'pos': pos, **(source or self.source)},
                                headers={'X-CSRF-Token': self.token} if token else {})

    def test_lookup_is_local_and_shows_actual_morphology_not_placeholder_translation(self):
        result = self.lookup().get_json()
        self.assertEqual((result['lemma'], result['pos'], result['grammar']['case']), ('аптека', 'NOUN', 'ablt'))
        self.assertNotIn('translation', result)
        self.assertTrue(result['can_add'])
        self.assertIn('openrussian.org', result['dictionary_url'])
        self.assertEqual(self.sync.calls, [])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], 0)

    def test_add_commits_forms_before_enriching_and_repeat_retains_identity(self):
        first = self.add()
        self.assertEqual(first.status_code, 200, first.get_data(as_text=True))
        result = first.get_json()
        self.assertTrue(result['added'])
        self.assertTrue(result['mnemonic'])
        with transaction(self.db) as conn:
            word = conn.execute('SELECT * FROM words WHERE id=?', (result['word_id'],)).fetchone()
            self.assertEqual(word['lemma'], 'аптека')
            self.assertNotEqual(word['topic'], '[]')
            self.assertGreater(word['lemma_difficulty'], 0)
            self.assertGreater(conn.execute('SELECT COUNT(*) FROM forms WHERE word_id=?', (word['id'],)).fetchone()[0], 1)
            self.assertIsNotNone(conn.execute('SELECT 1 FROM forms WHERE word_id=? AND form=?', (word['id'], 'аптекой')).fetchone())
        again = self.add().get_json()
        self.assertFalse(again['added'])
        self.assertEqual(again['word_id'], result['word_id'])
        self.assertEqual(self.lookup().get_json()['mnemonic'], result['mnemonic'])

    def test_pending_enrichment_is_explicit_and_retriable_without_duplicate_word(self):
        self.sync.pending = True
        failed = self.add()
        self.assertEqual(failed.status_code, 503)
        details = failed.get_json()['error']
        self.assertTrue(details['saved'])
        self.assertTrue(details['enrichment_pending'])
        self.sync.pending = False
        retried = self.add()
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(details['word_id'], retried.get_json()['word_id'])
        self.assertTrue(retried.get_json()['mnemonic'])

    def test_budget_denial_does_not_hide_saved_word_or_claim_enrichment(self):
        self.sync.error = TrialDenied('The daily AI allowance has been reached.')
        response = self.add()
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.get_json()['error']['saved'])
        self.assertIn('daily AI allowance', response.get_json()['error']['message'])
        self.assertTrue(self.lookup().get_json()['in_vocabulary'])

    def test_unexpected_enrichment_failure_does_not_expose_internal_error(self):
        self.sync.error = RuntimeError('provider private diagnostics')
        response = self.add()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private diagnostics', response.get_data(as_text=True))
        self.assertTrue(response.get_json()['error']['saved'])

    def test_only_words_in_current_owned_story_can_be_saved(self):
        self.assertEqual(self.lookup('трактор').status_code, 404)
        self.assertEqual(self.add(word='трактор', lemma='трактор').status_code, 404)
        self.assertEqual(self.add(lemma='кошка').status_code, 409)
        self.assertEqual(self.lookup(source=self.source | {'story_key': 'stale'}).status_code, 409)
        self.assertEqual(self.add(source=self.source | {'story_id': self.story + 1}).status_code, 404)
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',1)")
            conn.execute("UPDATE saved_stories SET owner_profile_id='other' WHERE id=?", (self.story,))
        self.assertEqual(self.lookup().status_code, 404)
        self.assertEqual(self.add().status_code, 404)
        self.assertEqual(self.sync.calls, [])

    def test_generated_unsaved_story_is_bound_to_server_session_and_stale_tabs_fail(self):
        with self.client.session_transaction() as session:
            session['current_story_data'] = {'text': self.text}
        source = {'story_key': story_key(self.text)}
        self.assertEqual(self.lookup(source=source).status_code, 200)
        with self.client.session_transaction() as session:
            session['current_story_data'] = {'text': 'У меня новая книга.'}
        self.assertEqual(self.add(source=source).status_code, 409)
        self.assertEqual(self.sync.calls, [])

    def test_homograph_requires_dictionary_supported_reading(self):
        data = self.lookup('печь').get_json()
        self.assertEqual({choice['pos'] for choice in data['choices']}, {'NOUN', 'INFN'})
        self.assertEqual(self.add('печь', 'печь', None).status_code, 422)
        chosen = self.add('печь', 'печь', 'NOUN')
        self.assertEqual(chosen.status_code, 200)
        self.assertEqual(chosen.get_json()['pos'], 'NOUN')

    def test_csrf_is_required_and_legacy_empty_posts_cannot_add_arbitrary_words(self):
        self.assertEqual(self.add(token=False).status_code, 403)
        self.assertEqual(self.client.post('/add-vocab/аптека', headers={'X-CSRF-Token': self.token}).status_code, 415)
        self.assertEqual(self.sync.calls, [])

    def test_highlighting_uses_sqlite_without_drive(self):
        self.add()
        drive = Mock()
        drive.download_vocab_list.side_effect = AssertionError('Drive should not be called')
        words = process_story_words(self.text, self.db, drive)
        self.assertTrue(next(word for word in words if word['word'] == 'аптекой')['added'])
        drive.download_vocab_list.assert_not_called()

    def test_oversized_and_type_invalid_input_stops_before_morphology_or_enrichment(self):
        with patch('services.story_vocabulary.read_word') as read, patch('services.story_vocabulary.save_word') as save:
            for word in ('а' * 101, None, 25, ['аптека'], {'word': 'аптека'}):
                self.assertEqual(self.add(word=word).status_code, 422)
            for pos in ('fake', None, 25, ['NOUN'], {'pos': 'NOUN'}):
                self.assertEqual(self.add(pos=pos).status_code, 422)
            self.assertEqual(self.lookup('а' * 101).status_code, 422)
            read.assert_not_called()
            save.assert_not_called()
        self.assertEqual(self.sync.calls, [])

    def test_reopening_word_retains_pending_topics_or_placeholder_mnemonic(self):
        saved = self.add().get_json()
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE words SET topic='[]' WHERE id=?", (saved['word_id'],))
        lookup = self.lookup().get_json()
        self.assertTrue(lookup['mnemonic'])
        self.assertTrue(lookup['enrichment_pending'])
        self.assertFalse(self.add().get_json()['enrichment_pending'])
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE words SET mnemonic=? WHERE id=?', ('Recall аптека phonetically.', saved['word_id']))
        lookup = self.lookup().get_json()
        self.assertEqual(lookup['mnemonic'], '')
        self.assertTrue(lookup['enrichment_pending'])

    def test_hyphenated_compounds_keep_their_exact_surface_and_valid_capture(self):
        passage = 'Это блюдо шеф-повара: котлета по-киевски. Мо́ре рядом.'
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE saved_stories SET text=? WHERE id=?', (passage, self.story))
        source = {'story_id': self.story, 'story_key': story_key(passage)}
        tokens = process_story_words(passage, self.db, Mock())
        self.assertEqual(''.join(token['word'] for token in tokens), passage)
        compound = next(token for token in tokens if token['word'] == 'шеф-повара')
        self.assertEqual(compound['lemma'], 'шеф-повар')
        self.assertIn('по-киевски', [token['word'] for token in tokens])
        self.assertEqual(next(token for token in tokens if token['word'] == 'Мо́ре')['lemma'], 'море')
        lookup = self.lookup('шеф-повара', source).get_json()
        self.assertEqual(lookup['lemma'], 'шеф-повар')
        added = self.add('шеф-повара', 'шеф-повар', 'NOUN', source)
        self.assertEqual(added.status_code, 200, added.get_data(as_text=True))
        self.assertEqual(added.get_json()['lemma'], 'шеф-повар')
