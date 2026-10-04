"""Passage selection preserves frozen text, assistance and lexical identity."""
import unittest
from uuid import uuid4

from repositories.learning_repository import transaction
from services.curriculum_situation_content import validate_output
from tests import test_curriculum_situations as situations
from tests.test_curriculum_situation_content import situation_response


class PracticeVocabularyTests(unittest.TestCase):
    # Share the source-v2 provider-free task fixture without inheriting tests.
    # Its extra homographs exercise capture, not the v6 unfamiliar-word limit.
    setUpClass = classmethod(situations.CurriculumSituationIntegrationTests.setUpClass.__func__)
    setUp = situations.CurriculumSituationIntegrationTests.setUp
    speech = situations.CurriculumSituationIntegrationTests.speech
    post = situations.CurriculumSituationIntegrationTests.post
    start = situations.CurriculumSituationIntegrationTests.start
    prepare = situations.CurriculumSituationIntegrationTests.prepare
    player = situations.CurriculumSituationIntegrationTests.player
    pack = situations.CurriculumSituationIntegrationTests.pack
    command = situations.CurriculumSituationIntegrationTests.command

    def generate(self, request, provider):
        response = situation_response(request)
        homograph = 'Она видит печь и хочет печь.' if getattr(self, 'repeated_homograph', False) else 'Она видит печь.'
        response['text'] += ' Анна стоит перед аптекой. ' + homograph
        response['new_vocabulary'] = [{'lemma': 'аптека', 'form': 'аптекой', 'pos': 'NOUN',
            'sentence': 'Анна стоит перед аптекой.', 'meaning_en': 'pharmacy'}]
        if getattr(self, 'repeated_homograph', False):
            response['new_vocabulary'].append({'lemma': 'печь', 'form': 'печь', 'pos': 'NOUN',
                'sentence': homograph, 'meaning_en': 'oven'})
        return validate_output(request, response)

    def ready(self, mode='reading'):
        state = self.prepare(self.start(mode))
        if state['state'] != 'ready':
            state = self.prepare(state)
        return self.player(state)

    def word_body(self, saved, word='аптекой', **extra):
        pack = self.pack(saved)
        text = pack['items'][0].get('passage') or pack['items'][0]['transcript']
        return {'submission_id': uuid4().hex, 'expected_revision': saved['revision'],
                'item_id': saved['item']['id'], 'word': word, 'offset': text.index(word), **extra}

    def word(self, saved, *, capture=False, status=200, body=None, **extra):
        return self.post('/api/v1/learning-sessions/' + saved['id'] + ('/words' if capture else '/words/lookup'),
                         body or self.word_body(saved, **extra), status=status)

    def test_lookup_keeps_selected_sentence_meaning_and_optional_saving(self):
        saved = self.ready()
        frozen = self.pack(saved)
        looked = self.word(saved)
        self.assertEqual((looked['word']['word'], looked['word']['lemma'], looked['word']['meaning']),
                         ('аптекой', 'аптека', 'pharmacy'))
        self.assertEqual(looked['word']['context'], 'Анна стоит перед аптекой.')
        self.assertNotIn('hint', looked['item'])
        self.assertEqual(looked['revision'], saved['revision'] + 1)
        with transaction(self.db) as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM words WHERE lemma='аптека'").fetchone())
        self.assertEqual(self.app.extensions['services']['SyncService']._get().calls, [])
        later_offset = frozen['items'][0]['passage'].rindex('письмо')
        later = self.word(looked, word='письмо', offset=later_offset)
        self.assertEqual(later['word']['context'], 'Анна хочет прочитать письмо ещё раз, а потом написать ответ.')
        self.assertEqual(self.pack(later), frozen)

    def test_capture_reuses_morphology_enrichment_and_idempotent_receipt(self):
        saved = self.word(self.ready())
        body = self.word_body(saved, lemma='аптека', pos='NOUN')
        added = self.word(saved, capture=True, body=body)
        retried = self.word(saved, capture=True, body=body)
        self.assertEqual(added, retried)
        self.assertTrue(added['word']['mnemonic'])
        again = self.word(added, capture=True, lemma='аптека', pos='NOUN')
        self.assertFalse(again['word']['added'])
        self.assertEqual(added['word']['word_id'], again['word']['word_id'])
        with transaction(self.db) as conn:
            word = conn.execute('SELECT * FROM words WHERE id=?', (added['word']['word_id'],)).fetchone()
            self.assertNotEqual(word['topic'], '[]')
            self.assertGreater(conn.execute('SELECT COUNT(*) FROM forms WHERE word_id=?', (word['id'],)).fetchone()[0], 1)
            # This is the same vocabulary inventory consumed by flashcard/game preparation.
            from services.journey_vocabulary import _vocabulary
            records = [row for row in _vocabulary(conn) if row['word_id'] == word['id']]
            self.assertTrue(any(row['form'] == 'аптекой' for row in records))

    def test_pending_enrichment_commits_support_and_can_finish_without_duplicate(self):
        saved = self.ready()
        sync = self.app.extensions['services']['SyncService']._get()
        sync.pending = True
        body = self.word_body(saved, lemma='аптека', pos='NOUN')
        failed = self.word(saved, capture=True, body=body, status=503)['error']
        self.assertTrue(failed['saved'])
        self.assertEqual(failed['current_session']['revision'], saved['revision'] + 1)
        self.assertTrue(failed['current_session']['word']['enrichment_pending'])
        retained = self.client.get('/api/v1/learning-sessions/' + saved['id'] + '/words').get_json()['words']
        self.assertEqual(retained[0]['context'], 'Анна стоит перед аптекой.')
        self.assertEqual(retained[0]['word_id'], failed['word_id'])
        sync.pending = False
        finished = self.word(saved, capture=True, body=body)
        self.assertEqual(failed['word_id'], finished['word']['word_id'])
        self.assertFalse(finished['word']['enrichment_pending'])

    def test_word_help_marks_remaining_reading_answers_without_rewriting_prior_answers(self):
        saved = self.ready()
        pack = self.pack(saved)
        first = self.command(saved, 'attempts', answer={'choice_id': pack['items'][0]['answer']})
        helped = self.word(first)
        self.assertFalse(helped['attempts'][0]['feedback']['assisted'])
        self.assertNotIn('hint', helped['item'])
        for item in pack['items'][1:]:
            helped = self.command(helped, 'attempts', answer={'choice_id': item['answer']})
            self.assertTrue(helped['attempts'][-1]['feedback']['assisted'])
            self.assertIn('hint', helped['attempts'][-1]['feedback']['support'])
        self.assertFalse(helped['attempts'][0]['feedback']['assisted'])

    def test_listening_lookup_requires_transcript_and_retains_support_receipts(self):
        saved = self.ready('listening')
        self.assertIsNone(saved['item']['transcript'])
        self.assertEqual(self.client.get('/api/v1/learning-sessions/' + saved['id'] + '/words').get_json()['words'], [])
        denied = self.word(saved, status=409)
        self.assertEqual(denied['error']['code'], 'transcript_required')
        revealed = self.command(saved, 'transcript')
        helped = self.word(revealed)
        pack = self.pack(saved)
        for item in pack['items']:
            helped = self.command(helped, 'attempts', answer={'choice_id': item['answer']})
            self.assertIn('transcript', helped['attempts'][-1]['feedback']['support'])
            self.assertTrue(helped['attempts'][-1]['feedback']['assisted'])

    def test_ambiguity_requires_a_valid_reading_and_occurrence(self):
        saved = self.ready()
        looked = self.word(saved, word='печь')
        self.assertEqual({choice['pos'] for choice in looked['word']['choices']}, {'NOUN', 'INFN'})
        self.assertIsNone(looked['word']['lemma'])
        self.word(looked, word='печь', capture=True, lemma='кошка', pos='NOUN', status=409)
        chosen = self.word(looked, word='печь', capture=True, lemma='печь', pos='NOUN')
        self.assertEqual(chosen['word']['pos'], 'NOUN')
        self.word(chosen, word='аптекой', offset=0, status=422)
        self.word(chosen, word='аптекой', offset=True, status=422)
        self.word(chosen, body=self.word_body(chosen) | {'sentence': 'Made up context'}, status=400)

    def test_sentence_annotation_cannot_resolve_repeated_homographs_at_either_offset(self):
        self.repeated_homograph = True
        saved = self.ready()
        text = self.pack(saved)['items'][0]['passage']
        offsets = (text.index('печь'), text.rindex('печь'))
        for offset, chosen_pos in zip(offsets, ('NOUN', 'INFN')):
            looked = self.word(saved, word='печь', offset=offset)
            self.assertEqual(looked['word']['context'], 'Она видит печь и хочет печь.')
            self.assertIsNone(looked['word']['lemma'])
            self.assertEqual({choice['pos'] for choice in looked['word']['choices']}, {'NOUN', 'INFN'})
            self.assertNotIn('meaning', looked['word'])
            saved = self.word(looked, word='печь', offset=offset, capture=True, lemma='печь', pos=chosen_pos)
        kept = self.client.get('/api/v1/learning-sessions/' + saved['id'] + '/words').get_json()['words']
        self.assertEqual([(word['source']['word_offset'], word['pos']) for word in kept],
                         [(offsets[0], 'NOUN'), (offsets[1], 'INFN')])
        for word in kept:
            self.assertNotIn('meaning', word)
            self.assertEqual(word['context'][word['source']['context_offset']:][:len(word['word'])], word['word'])

    def test_captured_source_is_retrievable_after_completion_without_inventing_an_example(self):
        saved = self.ready()
        pack = self.pack(saved)
        path = '/api/v1/learning-sessions/' + saved['id'] + '/words'
        looked = self.word(saved)
        self.assertEqual(self.client.get(path).get_json()['words'], [])
        annotated = self.word(looked, capture=True, lemma='аптека', pos='NOUN')
        # A fresh capture action must still retain only one identical source.
        repeated = self.word(annotated, capture=True, lemma='аптека', pos='NOUN')
        kept = self.word(repeated, capture=True, word='письмо', lemma='письмо', pos='NOUN')
        for item in pack['items']:
            kept = self.command(kept, 'attempts', answer={'choice_id': item['answer']})
        self.assertEqual(kept['status'], 'completed')
        sync = self.app.extensions['services']['SyncService']._get()
        calls = len(sync.calls)
        # A new browser session retrieves the durable provenance, not UI state.
        fresh = self.app.test_client()
        response = fresh.get(path)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        records = response.get_json()['words']
        self.assertEqual(len(records), 2)
        pharmacy, letter = records
        self.assertEqual((pharmacy['word'], pharmacy['lemma'], pharmacy['context'], pharmacy['meaning']),
                         ('аптекой', 'аптека', 'Анна стоит перед аптекой.', 'pharmacy'))
        self.assertEqual((letter['word'], letter['lemma'], letter['context']),
                         ('письмо', 'письмо', 'Она читает письмо от друга.'))
        self.assertNotIn('meaning', letter)
        for record in records:
            self.assertNotIn('translation', record)
            self.assertFalse(record['prepared_example'])
            source = record['source']
            self.assertEqual(source['session_id'], saved['id'])
            self.assertEqual(source['version_id'], saved['version_id'])
            self.assertEqual(source['item_id'], saved['item']['id'])
            self.assertEqual(pack['items'][0]['passage'][source['word_offset']:][:len(record['word'])], record['word'])
        with transaction(self.db) as conn:
            self.assertIsNone(conn.execute('SELECT 1 FROM journey_game_examples WHERE word_id IN (?,?)',
                                          (pharmacy['word_id'], letter['word_id'])).fetchone())
        self.assertEqual(len(sync.calls), calls)
        self.assertEqual(fresh.get('/api/v1/learning-sessions/' + saved['id']).get_json()['revision'], kept['revision'])

    def test_csrf_stale_revision_and_other_learner_do_not_disclose_words(self):
        saved = self.ready()
        path = '/api/v1/learning-sessions/' + saved['id'] + '/words/lookup'
        self.assertEqual(self.client.post(path, json=self.word_body(saved)).status_code, 403)
        helped = self.word(saved)
        self.assertEqual(self.word(saved, status=409)['error']['code'], 'stale_revision')
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',1)")
            conn.execute("UPDATE learning_sessions SET profile_id='other' WHERE id=?", (saved['id'],))
        self.word(helped, status=404)
        self.assertEqual(self.client.get('/api/v1/learning-sessions/' + saved['id'] + '/words').status_code, 404)
