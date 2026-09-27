"""One contextual discovery, and explicit lexical saves without card creation."""
import copy
import json
from types import SimpleNamespace
import unittest

from repositories.learning_repository import LearningError, encoded, transaction
from services.card_metadata import GRAMMAR
from services.game_vocabulary_discovery import generate_discovery, read_word, save_word
from services.journey_vocabulary import select_examples
from services.learning_assets import import_asset
from tests.support import isolated_app


class DiscoveryProvider:
    flashcard_model = 'configured-model-for-test'

    def __init__(self):
        self.calls, self.configuration = [], []
        self.result = {'lemma': 'посылка', 'form': 'посылкой', 'pos': 'NOUN',
                       'tags': dict.fromkeys(GRAMMAR) | {'case': 'ablt', 'number': 'sing', 'gender': 'femn', 'animacy': 'inan'},
                       'sentence': 'Барсик идёт с посылкой.', 'translation': 'Barsik is walking with a parcel.',
                       'target_meaning': 'a parcel', 'notes': '', 'topic': 'post'}
        self.client = SimpleNamespace(with_options=self.with_options)
        self.refusal = None
        self.reason = 'stop'

    def with_options(self, **options):
        self.configuration.append(options)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)))

    def create(self, **request):
        self.calls.append(copy.deepcopy(request))
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=self.reason,
            message=SimpleNamespace(refusal=self.refusal, content=json.dumps(self.result, ensure_ascii=False)))])


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.provider = DiscoveryProvider()
        self.familiar = [{'lemma': 'карта', 'form': 'картой', 'sentence': 'Я пользуюсь картой.'}]

    def discover(self, known=('письмо', 'сумка')):
        return generate_discovery(self.provider, known, self.familiar, {'difficulty': 2, 'topic': 'post'}, 'seed-one')

    def test_one_configured_structured_call_returns_exact_declension_and_context(self):
        word = self.discover()
        self.assertEqual(len(self.provider.calls), 1)
        request = self.provider.calls[0]
        self.assertEqual(request['model'], self.provider.flashcard_model)
        self.assertEqual(request['reasoning_effort'], 'low')
        self.assertEqual(self.provider.configuration, [{'timeout': 60, 'max_retries': 0}])
        self.assertTrue(request['response_format']['json_schema']['strict'])
        data = json.loads(request['messages'][1]['content'])
        self.assertEqual(set(data['known_lemmas']), {'письмо', 'сумка', 'карта'})
        self.assertEqual(word['lemma'], 'посылка')
        self.assertEqual(word['form'], 'посылкой')
        self.assertEqual(word['tags']['case'], 'ablt')
        self.assertIsNone(word['word_id']); self.assertIsNone(word['form_id'])
        self.assertEqual(word['sentence'], self.provider.result['sentence'])
        self.assertEqual(word['translation'], self.provider.result['translation'])
        self.assertEqual(word['source']['kind'], 'discovery')
        self.assertEqual(word['source']['model'], self.provider.flashcard_model)
        self.assertEqual(word['metadata']['lemma_difficulty'], 2)
        self.assertTrue(word['new_word']); self.assertEqual(word['mnemonic'], '')

    def test_known_lemma_with_case_or_stress_cannot_be_reintroduced_as_new(self):
        with self.assertRaises(LearningError):
            self.discover(known=['Посы́лка'])
        self.assertEqual(len(self.provider.calls), 1)
        self.familiar.append({'lemma': 'посылка'})
        with self.assertRaises(LearningError):
            self.discover()

    def test_wrong_declension_tags_or_lemma_and_repeated_missing_form_are_rejected(self):
        initial = copy.deepcopy(self.provider.result)
        cases = [dict(lemma='письмо'), dict(form='посылку'), dict(sentence='Барсик идёт с письмом.'),
                 dict(sentence='Барсик идёт с посылкой и с посылкой.'),
                 dict(tags=initial['tags'] | {'case': 'accs'}), dict(lemma='абракадабрундия')]
        for changes in cases:
            self.provider.result = copy.deepcopy(initial) | changes
            with self.subTest(changes=changes), self.assertRaises(LearningError):
                self.discover()
        self.assertEqual(len(self.provider.calls), len(cases))

    def test_exact_conjugation_is_accepted_and_its_infinitive_remains_the_lemma(self):
        self.provider.result.update(lemma='нести', form='несёт', pos='VERB',
            tags=dict.fromkeys(GRAMMAR) | {'number': 'sing', 'tense': 'pres', 'person': '3per', 'mood': 'indc', 'aspect': 'impf'},
            sentence='Барсик несёт письмо.', translation='Barsik is carrying a letter.', target_meaning='is carrying')
        word = self.discover()
        self.assertEqual(word['lemma'], 'нести'); self.assertEqual(word['form'], 'несёт')
        self.assertEqual(word['tags']['person'], '3per')

    def test_discovery_rejects_a_different_target_in_an_existing_sentence_or_translation(self):
        for familiar in (
            {'lemma': 'идти', 'sentence': '  Барсик   идёт с посылкой! '},
            {'lemma': 'идти', 'translation': ' BARSIK IS WALKING WITH A PARCEL! '},
        ):
            self.familiar = [familiar]
            with self.subTest(familiar=familiar), self.assertRaises(LearningError):
                self.discover()
        self.assertEqual(len(self.provider.calls), 2)

    def test_refusal_truncation_and_provider_errors_are_one_failure_without_private_details(self):
        self.provider.refusal = 'No response'
        with self.assertRaises(LearningError) as error:
            self.discover()
        self.assertEqual(error.exception.code, 'discovery_unavailable')
        self.assertEqual(error.exception.details['reason'], 'response')
        self.provider.refusal = None; self.provider.reason = 'length'
        with self.assertRaises(LearningError):
            self.discover()
        self.provider.client.with_options = lambda **_: (_ for _ in ()).throw(RuntimeError('secret-key-here'))
        with self.assertLogs('services.game_vocabulary_discovery', level='WARNING') as logs:
            with self.assertRaises(LearningError) as error:
                self.discover()
        self.assertNotIn('secret-key', str(error.exception))
        self.assertNotIn('secret-key', ''.join(logs.output))
        self.assertEqual(error.exception.details['reason'], 'provider')
        self.assertIn('stage=provider', ''.join(logs.output))

    def test_morphology_failure_is_distinguished_from_provider_failure(self):
        self.provider.result['tags']['case'] = 'accs'
        with self.assertRaises(LearningError) as error:
            self.discover()
        self.assertEqual(error.exception.details['reason'], 'morphology')
        self.assertIn('Russian language checks', str(error.exception))
        self.assertEqual(len(self.provider.calls), 1)


class GameWordTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, demo=False)
        self.db = self.app.config['DB_PATH']
        self.content = {'broadcast': {'script': 'Барсик идёт с посылкой. Потом он открывает дверь.'},
                        'vocabulary_refs': [{'lemma': 'посылка', 'form': 'посылкой', 'pos': 'NOUN',
                            'tags': {'case': 'ablt', 'number': 'sing', 'gender': 'femn', 'animacy': 'inan'},
                            'sentence': 'Барсик идёт с посылкой.', 'translation': 'Barsik is walking with a parcel.',
                            'target_meaning': 'a parcel'}]}

    def test_lookup_uses_saved_context_and_does_not_write_anything(self):
        with transaction(self.db) as conn:
            result = read_word(conn, self.content, 'посылкой')
            self.assertEqual(result['lemma'], 'посылка'); self.assertEqual(result['pos'], 'NOUN')
            self.assertEqual(result['grammar']['case'], 'ablt')
            self.assertEqual(result['meaning'], 'a parcel')
            self.assertTrue(result['can_add']); self.assertFalse(result['in_vocabulary'])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0], 0)

    def test_any_real_transcript_word_can_be_added_without_inventing_its_translation(self):
        with transaction(self.db, write=True) as conn:
            details = read_word(conn, self.content, 'открывает')
            self.assertEqual(details['lemma'], 'открывать')
            self.assertNotIn('meaning', details); self.assertNotIn('translation', details)
            result = save_word(conn, self.content, 'открывает', 'открывать')
            self.assertTrue(result['added']); self.assertTrue(result['in_vocabulary'])
            form = conn.execute('SELECT form,tags FROM forms WHERE word_id=? AND form=?', (result['word_id'], 'открывает')).fetchone()
            self.assertEqual(form['form'], 'открывает')
            self.assertEqual(json.loads(form['tags'])['person'], '3per')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0], 0)

    def test_explicit_save_is_idempotent_and_keeps_forms_linked_to_the_lemma(self):
        with transaction(self.db, write=True) as conn:
            first = save_word(conn, self.content, 'посылкой', 'посылка')
            original_forms = [tuple(row) for row in conn.execute('SELECT * FROM forms ORDER BY id')]
            self.assertGreater(len(original_forms), 1)
            second = save_word(conn, self.content, 'посылкой', 'посылка')
            self.assertTrue(first['added']); self.assertFalse(second['added'])
            self.assertEqual(first['word_id'], second['word_id'])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], 1)
            self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM forms ORDER BY id')], original_forms)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
            self.assertNotIn('translation', {row['name'] for row in conn.execute('PRAGMA table_info(words)')})

    def test_existing_lowercase_pos_word_is_reused_without_duplicate_lemma(self):
        with transaction(self.db, write=True) as conn:
            word_id = conn.execute("INSERT INTO words(lemma,pos,lemma_difficulty) VALUES ('посылка','noun',2)").lastrowid
            result = save_word(conn, self.content, 'посылкой', 'посылка')
            self.assertEqual(result['word_id'], word_id); self.assertFalse(result['added'])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], 1)

    def test_explicit_add_reuses_its_context_and_picture_only_for_the_same_owner(self):
        from tests.test_card_media import MediaProvider
        asset = import_asset(self.db, self.app.extensions['learning']['assets'], MediaProvider().image, 'saved discovery picture')
        example = self.content['vocabulary_refs'][0]
        example.update(identity='original-discovery', word_id=None, form_id=None,
                       assets=[{'kind': 'image', 'id': asset}], notes='', metadata={},
                       source={'kind': 'discovery', 'origin': 'example', 'model': 'configured-model'})
        frozen = encoded(self.content)
        with self.app.app_context(), transaction(self.db, write=True) as conn:
            original = encoded(example)
            conn.execute('INSERT INTO journey_game_examples(id,profile_id,identity,content_json,created_at) VALUES (?,?,?,?,1)',
                         ('original-cache', 'personal-learning', example['identity'], original))
            result = save_word(conn, self.content, 'посылкой', 'посылка', profile_id='personal-learning')
            selected = select_examples(conn, 'personal-learning', None, {'source': 'vocabulary'}, 'next-game', limit=1)[0]
            self.assertEqual(selected['word_id'], result['word_id'])
            self.assertEqual(selected['sentence'], example['sentence'])
            self.assertEqual(selected['translation'], example['translation'])
            self.assertEqual(selected['assets'], example['assets'])
            alias = json.loads(conn.execute('SELECT content_json FROM journey_game_examples WHERE id=?', (selected['cached_id'],)).fetchone()[0])
            self.assertEqual(alias['source'], example['source'])
            self.assertEqual(alias['form_id'], selected['form_id'])
            self.assertEqual(conn.execute('SELECT content_json FROM journey_game_examples WHERE id=?', ('original-cache',)).fetchone()[0], original)
            self.assertEqual(encoded(self.content), frozen)
            foreign = select_examples(conn, None, 'other-guest', {'source': 'vocabulary'}, 'foreign', limit=1)[0]
            self.assertNotIn('sentence', foreign)
            self.assertNotIn('cached_id', foreign)
            save_word(conn, self.content, 'посылкой', 'посылка', profile_id='personal-learning')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_examples').fetchone()[0], 2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0], 0)

    def test_guest_add_keeps_guest_scope_and_does_not_overwrite_an_existing_cache(self):
        example = self.content['vocabulary_refs'][0]
        example.update(identity='guest-discovery', word_id=None, form_id=None, assets=[], notes='',
                       source={'kind': 'discovery', 'origin': 'example'})
        with self.app.app_context(), transaction(self.db, write=True) as conn:
            save_word(conn, self.content, 'посылкой', 'посылка', guest_token='guest-one')
            first = select_examples(conn, None, 'guest-one', {'source': 'vocabulary'}, 'guest', limit=1)[0]
            self.assertEqual(first['sentence'], example['sentence'])
            cached = conn.execute('SELECT * FROM journey_game_examples WHERE id=?', (first['cached_id'],)).fetchone()
            self.assertIsNone(cached['profile_id']); self.assertEqual(cached['guest_token'], 'guest-one')
            different = copy.deepcopy(self.content)
            different['vocabulary_refs'][0].update(sentence='Я любуюсь посылкой.', translation='I admire the parcel.')
            different['broadcast']['script'] = 'Я любуюсь посылкой.'
            save_word(conn, different, 'посылкой', 'посылка', guest_token='guest-one')
            self.assertEqual(conn.execute('SELECT content_json FROM journey_game_examples WHERE id=?', (cached['id'],)).fetchone()[0], cached['content_json'])
            other = select_examples(conn, None, 'guest-two', {'source': 'vocabulary'}, 'other', limit=1)[0]
            self.assertNotIn('sentence', other)

    def test_ambiguous_case_does_not_create_a_cache_that_claims_one_contextual_reading(self):
        content = {'broadcast': {'script': 'У него нет карты.'},
                   'vocabulary_refs': [{'lemma':'карта','form':'карты','pos':'NOUN', 'tags':{},
                        'sentence':'У него нет карты.', 'translation':'He has no map.', 'target_meaning':'a map',
                        'notes':'', 'assets':[], 'source':{'kind':'radio'}}]}
        with transaction(self.db, write=True) as conn:
            save_word(conn, content, 'карты', 'карта', profile_id='personal-learning')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_examples').fetchone()[0], 0)

    def test_arbitrary_words_and_wrong_lemmas_are_not_accepted_by_a_session_lookup(self):
        with transaction(self.db, write=True) as conn:
            for word in ('кошка', '../secret', 'hello'):
                with self.subTest(word=word), self.assertRaises(LearningError):
                    read_word(conn, self.content, word)
            with self.assertRaises(LearningError):
                save_word(conn, self.content, 'посылкой', 'письмо')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], 0)

    def test_homograph_asks_for_lexical_reading_and_respects_selected_pos(self):
        content = {'broadcast': {'script': 'Я хочу печь хлеб.'}, 'vocabulary_refs': []}
        with transaction(self.db, write=True) as conn:
            details = read_word(conn, content, 'печь')
            self.assertFalse(details['can_add'])
            self.assertEqual({choice['pos'] for choice in details['choices']}, {'NOUN', 'INFN'})
            with self.assertRaises(LearningError):
                save_word(conn, content, 'печь', 'печь')
            result = save_word(conn, content, 'печь', 'печь', 'INFN')
            self.assertTrue(result['added'])
            row = conn.execute('SELECT lemma,pos FROM words WHERE id=?', (result['word_id'],)).fetchone()
            self.assertEqual(tuple(row), ('печь', 'VERB'))

    def test_unresolved_case_variants_are_not_presented_as_a_known_contextual_case(self):
        content = {'broadcast': {'script': 'У него нет карты.'}, 'vocabulary_refs': []}
        with transaction(self.db, write=True) as conn:
            details = read_word(conn, content, 'карты')
            self.assertNotIn('case', details['grammar'])
            result = save_word(conn, content, 'карты', 'карта')
            cases = {json.loads(row[0])['case'] for row in conn.execute('SELECT tags FROM forms WHERE word_id=?', (result['word_id'],))}
            self.assertTrue({'nomn', 'gent', 'accs'} <= cases)

    def test_old_familiar_card_context_is_not_used_as_a_broadcast_translation(self):
        content = copy.deepcopy(self.content)
        content['vocabulary_refs'][0]['sentence'] = 'Я любуюсь посылкой.'
        with transaction(self.db) as conn:
            result = read_word(conn, content, 'посылкой')
            self.assertNotIn('translation', result); self.assertNotIn('meaning', result)
