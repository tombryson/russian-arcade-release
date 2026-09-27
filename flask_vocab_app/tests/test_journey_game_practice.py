"""Games continue in the native card library without duplicating lesson words."""
import hashlib
import json
import unittest
from unittest.mock import patch

from repositories.learning_repository import LearningError, encoded, transaction
from services.first_steps import chapter_content
from services.journey_vocabulary import cache_source_available, select_examples
from services.learning_assets import import_asset
from services.ai_trial_budget import TrialDenied
from tests import test_first_steps_practice as practice


class JourneyGamePracticeTests(unittest.TestCase):
    setUp = practice.FirstStepsPracticeTests.setUp
    post = practice.FirstStepsPracticeTests.post
    hello = practice.FirstStepsPracticeTests.hello
    chapter = practice.FirstStepsPracticeTests.chapter
    finish_batch = practice.FirstStepsPracticeTests.finish_batch

    def test_game_media_allowance_denial_returns_429_and_keeps_saved_example(self):
        candidate = chapter_content()['lessons'][0]['vocabulary'][0]
        endpoint = self.game(candidates=[candidate])
        batch = self.post(endpoint, status=201)
        self.gen.next(self.access, batch['id'])
        self.gen.next(self.access, batch['id'])
        saved = self.gen.read(self.access, batch['id'])
        media = self.app.extensions['learning']['card_media'].provider
        message = 'Your daily AI allowance is used. Saved practice is still available.'
        with patch.object(media, 'generate', side_effect=TrialDenied(message)):
            result = self.post('/api/v1/card-generation/batches/'+batch['id']+'/next', status=429)
        self.assertEqual(result['error'], {'code':'trial_limit', 'message':message})
        current = self.gen.read(self.access, batch['id'])
        self.assertEqual(current['saved'], 1)
        self.assertEqual(current['items'][0]['sentence'], saved['items'][0]['sentence'])
        self.assertEqual(current['items'][0]['card_id'], saved['items'][0]['card_id'])
        self.assertEqual(sum(job['status']=='saved' for job in current['items'][0]['media_jobs']), 1)
        self.assertEqual(self.post(endpoint, status=201)['id'], batch['id'])
        self.assertEqual(self.text.calls, [])

    def test_delivery_contexts_keep_inflected_forms_in_native_cards(self):
        from services.route_content import build_mission, MISSION_IDS
        for i in range(len(MISSION_IDS)):
            pack=build_mission(i)
            batch=self.post(self.game('delivery-'+str(i),candidates=pack['vocabulary_refs']),status=201)
            self.finish_batch(batch)
        with transaction(self.db) as conn:
            selections=[json.loads(r[0]) for r in conn.execute('SELECT selection FROM native_card_generation_items')]
            bridge=next(s for s in selections if s['form']=='мостом')
            self.assertEqual(bridge['lemma'],'мост')
            self.assertEqual(bridge['tags']['case'],'ablt')
            station=next(s for s in selections if s['form']=='вокзалом')
            self.assertEqual(station['lemma'],'вокзал')
            self.assertEqual(station['tags']['case'],'ablt')

    def test_selected_contexts_are_validated_and_reused_without_new_duplicates(self):
        from services.first_steps_practice import _identity
        candidates = next(item for item in chapter_content()['lessons'] if item['id'] == 'bag')['vocabulary']
        endpoint = self.game()
        chosen = _identity(candidates[1])
        for items in ([], ['foreign'], [chosen, chosen], [123], 'all', None):
            with self.subTest(items=items):
                self.post(endpoint, {'items': items}, status=400)
        batch = self.post(endpoint, {'items': [chosen]}, status=201)
        self.assertEqual(len(batch['items']), 1)
        self.assertEqual(self.post(endpoint, {'items': [chosen]}, status=201)['id'], batch['id'])
        with transaction(self.db) as conn:
            saved = json.loads(conn.execute('SELECT selection FROM native_card_generation_items').fetchone()[0])
            self.assertEqual(saved['form'], candidates[1]['form'])
            response = json.loads(conn.execute('SELECT response FROM native_card_generation_items').fetchone()[0])
            self.assertEqual(response['sentence'], candidates[1]['sentence'])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_generation_items').fetchone()[0], 1)

    def game(self, session_id='saved-game', *, lesson='bag', complete=True, owner='personal-learning', candidates=None):
        source = next(item for item in chapter_content()['lessons'] if item['id'] == lesson)
        content = {'title': 'Saved contextual game', 'vocabulary_refs': candidates if candidates is not None else source['vocabulary']}
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO journey_game_sessions '
                         '(id,profile_id,game_id,seed,request_ids_json,content_json,completed_at,created_at,updated_at) '
                         'VALUES (?,?,\'missing-stamp\',?,\'[]\',?,?,1,1)',
                         (session_id, owner, session_id, encoded(content), 2 if complete else None))
        return '/api/v1/games/sessions/' + session_id + '/flashcards'

    def test_saved_game_uses_same_native_items_as_its_lesson_and_replay(self):
        self.chapter()
        original = self.post('/api/v1/first-steps/bag/flashcards', status=201)
        game = self.post(self.game(), status=201)
        self.assertEqual(game['first_steps']['url'], '/#games/session/saved-game')
        self.assertEqual({item['id'] for item in game['items']}, {item['id'] for item in original['items']})
        self.assertEqual(game['first_steps']['reused'], 3)
        self.finish_batch(game)
        replay = self.post(self.game('replayed-game'), status=201)
        self.assertEqual(replay['id'], game['id'])
        self.assertEqual(self.text.calls, [])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0], 3)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_generation_items').fetchone()[0], 3)

    def test_frozen_inflected_word_and_meaning_survive_source_lesson_edits(self):
        endpoint = self.game(lesson='help')
        batch = self.post(endpoint, status=201)
        self.finish_batch(batch)
        with transaction(self.db) as conn:
            selections = [json.loads(row[0]) for row in conn.execute('SELECT selection FROM native_card_generation_items')]
            verb = next(item for item in selections if item['lemma'] == 'показать')
            self.assertEqual(verb['form'], 'Покажите')
            self.assertEqual(verb['tags']['mood'], 'impr')
            self.assertEqual(verb['tags']['number'], 'plur')
        self.assertEqual(self.post(endpoint, status=201)['id'], batch['id'])

    def test_game_audio_is_reused_by_native_cards_with_its_recorded_voice(self):
        self.chapter()
        key = hashlib.sha256('Это письмо.'.encode('utf-8')).hexdigest()
        audio = self.post('/api/v1/games/media/' + key + '/prepare')
        self.assertEqual(audio['status'], 'ready')
        provider = self.app.extensions['learning']['card_media'].provider
        candidate = chapter_content()['lessons'][0]['vocabulary'][0]
        batch = self.post(self.game(candidates=[candidate]), status=201)
        self.finish_batch(batch)
        speech_calls = [spec for kind, spec in provider.calls if kind == 'sentence_audio']
        self.assertEqual(len(speech_calls), 1)
        with transaction(self.db) as conn:
            recording = conn.execute('SELECT asset_id,spec_json FROM journey_game_media WHERE text_hash=?', (key,)).fetchone()
            native = conn.execute("SELECT asset_id,spec FROM native_card_media_jobs WHERE kind='sentence_audio'").fetchone()
            self.assertEqual(tuple(recording), tuple(native))

    def test_no_card_side_effects_for_incomplete_foreign_or_injected_requests(self):
        self.post(self.game(complete=False), status=409)
        self.post('/api/v1/games/sessions/missing-game/flashcards', status=404)
        endpoint = self.game('complete-game')
        self.post(endpoint, {'words': ['injected']}, status=400)
        result = self.client.post(endpoint, json={})
        self.assertEqual(result.status_code, 403)
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',1)")
        self.post(self.game('foreign-game', owner='other'), status=404)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0], 0)

    def ordinary(self):
        self.app.config['OPENAI_API_KEY'] = 'synthetic-test-key'
        batch = self.post('/api/v1/card-generation/batches', {'submission_id': 'ordinary', 'options': {
            'kind': 'ru-cloze', 'quantity': 1, 'word_id': 1, 'audio': True, 'image': True}}, status=201)
        batch = self.finish_batch(batch)
        with self.app.app_context(), transaction(self.db) as conn:
            candidate = next(record for record in select_examples(conn, 'personal-learning', None, {}, 'ordinary', 10)
                             if record.get('source', {}).get('kind') == 'card')
        return batch, candidate

    def test_ordinary_native_card_reuses_original_item_current_revision_and_schedule(self):
        original, candidate = self.ordinary()
        endpoint = self.game(candidates=[candidate])
        with transaction(self.db) as conn:
            old = conn.execute('SELECT payload FROM learning_content_versions WHERE id=?', (candidate['source']['version'],)).fetchone()
            pack = json.loads(old['payload'])
            selection_before = conn.execute('SELECT selection FROM native_card_generation_items WHERE id=?', (original['items'][0]['id'],)).fetchone()[0]
        pack['items'][0]['cue_en'] = 'a cup of coffee'
        edited = self.gen.content.import_draft(pack, access_id=self.access)
        self.gen.content.publish(self.access, edited, 'Me')
        result = self.post(endpoint, status=201)
        self.assertTrue(result['complete'])
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['id'], original['items'][0]['id'])
        self.assertEqual(result['items'][0]['card_id'], original['items'][0]['card_id'])
        self.assertEqual(result['items'][0]['english'], 'a cup of coffee')
        self.assertEqual(result['first_steps']['study_url'], '#flashcards?word_id=1')
        self.assertEqual(len(self.text.calls), 1)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_generation_items').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT selection FROM native_card_generation_items WHERE id=?', (original['items'][0]['id'],)).fetchone()[0], selection_before)
        self.app.extensions['learning']['card_authoring'].retire(self.access, original['items'][0]['card_id'])
        self.assertEqual(self.post(endpoint, status=201)['items'][0]['status'], 'removed')

    def prepared_game_word(self):
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO words(lemma,pos,topic,lemma_difficulty) VALUES ('конструкция','noun','[]',2)")
            word_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.execute('INSERT INTO forms(word_id,form,tags) VALUES (?,?,?)', (word_id, 'конструкций', encoded({'case': 'gent', 'number': 'plur'})))
            form_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        return {'word_id': word_id, 'form_id': form_id, 'lemma': 'конструкция', 'form': 'конструкций', 'pos': 'noun',
                'tags': {'case': 'gent', 'number': 'plur'}, 'sentence': 'Я занимаюсь изучением конструкций в русском языке.',
                'translation': 'I am studying constructions in Russian.', 'target_meaning': 'constructions',
                'source': {'kind': 'vocabulary', 'id': str(word_id), 'title': 'конструкция', 'url': '/vocab'}}

    def test_rewritten_objective_is_owned_through_original_pack_and_never_duplicated(self):
        original, old_candidate = self.ordinary()
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO journey_game_examples(id,profile_id,identity,word_id,form_id,content_json,created_at) VALUES (?,?,?,?,?,?,1)',
                         ('before-rewrite', 'personal-learning', old_candidate['identity'], old_candidate['word_id'], old_candidate['form_id'], encoded(old_candidate)))
        with transaction(self.db) as conn:
            pack = json.loads(conn.execute('SELECT payload FROM learning_content_versions WHERE id=?', (old_candidate['source']['version'],)).fetchone()[0])
        changed = pack['items'][0]
        changed.update(card_id='rewritten-coffee', context='Я люблю кофе.', context_meaning='I like coffee.',
                       prompt='Я люблю [[blank]].', cue_en='coffee')
        changed.pop('assets', None)
        version = self.gen.content.import_draft(pack, access_id=self.access)
        self.gen.content.publish(self.access, version, 'Me')
        with self.app.app_context(), transaction(self.db) as conn:
            examples = select_examples(conn, 'personal-learning', None, {}, 'rewrite', 10)
            current = next(record for record in examples if record.get('sentence'))
            self.assertEqual(current['source']['id'], 'rewritten-coffee')
            self.assertEqual(current['sentence'], 'Я люблю кофе.')
            self.assertFalse(cache_source_available(conn, old_candidate, 'personal-learning'))
            self.assertEqual(conn.execute('SELECT retired FROM card_definitions WHERE id=?', (original['items'][0]['card_id'],)).fetchone()[0], 1)
            self.assertFalse(any(record.get('sentence') for record in select_examples(conn, 'another-profile', None, {}, 'rewrite', 10)))
        batch = self.post(self.game(candidates=[current]), status=201)
        self.assertEqual(batch['items'][0]['card_id'], 'rewritten-coffee')
        self.assertEqual(batch['items'][0]['id'], original['items'][0]['id'])
        self.finish_batch(batch)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0], 2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_generation_items').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT retired FROM card_definitions WHERE id=?', (original['items'][0]['card_id'],)).fetchone()[0], 1)

    def test_new_game_context_keeps_existing_inflected_row_and_reuses_picture_and_audio(self):
        candidate = self.prepared_game_word()
        provider = self.app.extensions['learning']['card_media'].provider
        image = import_asset(self.db, self.gen.content.store, provider.image, 'game picture')
        audio = import_asset(self.db, self.gen.content.store, provider.mp3, 'game sentence')
        candidate['assets'] = [{'id': image, 'kind': 'image'}, {'id': audio, 'kind': 'sentence_audio'}]
        endpoint = self.game(candidates=[candidate])
        batch = self.post(endpoint, status=201)
        self.assertEqual(batch['first_steps']['study_url'], '#flashcards?topic=Journey%20games')
        batch = self.finish_batch(batch)
        self.assertEqual([kind for kind, _ in provider.calls], ['word_audio'])
        self.assertEqual(self.text.calls, [])
        with transaction(self.db) as conn:
            selection = json.loads(conn.execute('SELECT selection FROM native_card_generation_items').fetchone()[0])
            self.assertEqual(selection['form_id'], candidate['form_id'])
            self.assertEqual(selection['word_id'], candidate['word_id'])
            self.assertEqual(selection['tags'], candidate['tags'])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM forms WHERE word_id=?', (candidate['word_id'],)).fetchone()[0], 1)
            content = json.loads(conn.execute('SELECT payload FROM learning_content_versions ORDER BY created_at DESC,rowid DESC LIMIT 1').fetchone()[0])
            item = content['items'][0]
            self.assertEqual(item['answer'], 'конструкций')
            self.assertEqual(item['topic'], 'Journey games')
            self.assertEqual(item['metadata']['grammar'], candidate['tags'])
            self.assertIn({'id': image, 'kind': 'image', 'role': 'prompt'}, item['assets'])
            self.assertIn({'id': audio, 'kind': 'sentence_audio', 'role': 'answer'}, item['assets'])
            self.assertIn('Saved Journey game practice', content['source'])
            self.assertNotIn('Authored First steps', content['source'])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_media_jobs').fetchone()[0], 1)

    def test_invalid_shared_asset_kind_is_ignored_and_regenerated(self):
        candidate = self.prepared_game_word()
        provider = self.app.extensions['learning']['card_media'].provider
        image = import_asset(self.db, self.gen.content.store, provider.image, 'a picture is not speech')
        candidate['assets'] = [{'id': image, 'kind': 'sentence_audio'}, {'id': 'missing', 'kind': 'image'}]
        self.finish_batch(self.post(self.game(candidates=[candidate]), status=201))
        self.assertEqual({kind for kind, _ in provider.calls}, {'image', 'word_audio', 'sentence_audio'})

    def test_missing_form_is_resolved_under_its_existing_lemma_without_duplicate_words(self):
        candidate = self.prepared_game_word()
        candidate.update(form_id=None, form='конструкциями', tags={'case': 'ablt', 'number': 'plur'},
                         sentence='Я работаю с конструкциями.', translation='I work with constructions.')
        batch = self.post(self.game(candidates=[candidate]), status=201)
        self.finish_batch(batch)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM words WHERE lemma='конструкция'").fetchone()[0], 1)
            word = json.loads(conn.execute('SELECT selection FROM native_card_generation_items').fetchone()[0])
            self.assertEqual(word['word_id'], candidate['word_id'])
            self.assertEqual(word['tags']['case'], 'ablt')
            self.assertEqual(word['tags']['number'], 'plur')
            form = conn.execute('SELECT word_id,form FROM forms WHERE id=?', (word['form_id'],)).fetchone()
            self.assertEqual(tuple(form), (candidate['word_id'], 'конструкциями'))

    def test_native_references_reject_wrong_snapshot_identity_and_foreign_ownership(self):
        original, candidate = self.ordinary()
        game = self.post(self.game(candidates=[candidate]), status=201)
        with transaction(self.db) as conn:
            options = json.loads(conn.execute('SELECT options FROM native_card_batches WHERE id=?', (game['id'],)).fetchone()[0])
        reference = options['first_steps']['reused_items'][0]
        for change in ({'identity': 'forged'}, {'content_version_id': 'foreign'}, {'batch_id': game['id']}):
            altered = json.loads(json.dumps(options))
            altered['first_steps']['reused_items'] = [reference | change]
            with transaction(self.db, write=True) as conn:
                conn.execute('UPDATE native_card_batches SET options=? WHERE id=?', (encoded(altered), game['id']))
            with self.subTest(change=change), self.assertRaises(LearningError):
                self.gen.next(self.access, game['id'])
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE native_card_batches SET options=? WHERE id=?', (encoded(options), game['id']))
            conn.execute("UPDATE native_card_batches SET owner_id='another-profile' WHERE id=?", (original['id'],))
        with self.assertRaises(LearningError):
            self.gen.read(self.access, game['id'])
