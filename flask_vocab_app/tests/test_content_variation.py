"""Novelty is bounded, owner-scoped and enforced without another paid call."""
import json
import asyncio
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock

from migrations import MIGRATION_DIR, upgrade_database
from services.content_variation import (HISTORY_LIMIT, RepeatedContent, bind_spec,
    provider_context, record_exposure, variation_spec)
from services.journey_vocabulary_games import build_content


class ContentVariationTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.executescript((MIGRATION_DIR / '062_content_variation.sql').read_text())

    def spec(self, owner='alice', **options):
        return variation_spec(self.conn, activity='writing', profile_id=owner, **options)

    def test_recent_context_crosses_activities_without_crossing_owners_or_guest_scopes(self):
        original = self.spec()
        record_exposure(self.conn, original, text='Анна ищет новый зонт.', identity='one', lemmas=['зонт'])
        next_spec = variation_spec(self.conn, activity='radio', profile_id='alice')
        self.assertEqual(next_spec['recent_examples'][0]['text'], 'Анна ищет новый зонт.')
        self.assertEqual(next_spec['recent_lemmas'], ['зонт'])
        self.assertEqual(self.spec('bob')['recent_examples'], [])
        self.assertEqual(variation_spec(self.conn, activity='radio', guest_token='alice')['recent_examples'], [])
        self.assertNotIn('_owner_scope', provider_context(next_spec))
        self.assertNotEqual(original['seed'], next_spec['seed'])
        self.assertNotEqual(original['situation'], next_spec['situation'])

    def test_normalized_repeat_rejected_identity_is_idempotent_and_history_bounded(self):
        spec = self.spec()
        record_exposure(self.conn, spec, text='Ёж идёт домой!', identity='one')
        record_exposure(self.conn, spec, text='Ёж идёт домой!', identity='one')
        with self.assertRaises(RepeatedContent):
            record_exposure(self.conn, spec, text='  еж идет домой. ', identity='two')
        with self.assertRaisesRegex(ValueError, 'identity'):
            record_exposure(self.conn, spec, text='Совсем другой текст.', identity='one')
        for index in range(HISTORY_LIMIT + 3):
            record_exposure(self.conn, spec, text=f'Новое упражнение {index}', identity=f'item-{index}')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM content_variation_exposures').fetchone()[0], HISTORY_LIMIT)
        self.assertEqual(len(self.spec()['recent_examples']), 12)

    def test_pending_import_rebinds_history_from_verified_current_owner(self):
        old = self.spec()
        record_exposure(self.conn, old, text='Личное упражнение Алисы.', identity='alice-one')
        old = self.spec()
        rebound = bind_spec(self.conn, old, profile_id='bob')
        self.assertEqual(rebound['recent_examples'], [])
        self.assertEqual(rebound['_owner_scope'], 'profile:bob')
        self.assertEqual(rebound['seed'], old['seed'])

    def test_migration_062_can_upgrade_existing_database_alone_without_rewriting_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration_dir = root / 'migrations'
            migration_dir.mkdir()
            (migration_dir / '062_content_variation.sql').write_text((MIGRATION_DIR / '062_content_variation.sql').read_text())
            db = root / 'workspace.sqlite'
            with sqlite3.connect(db) as conn:
                conn.executescript("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY); INSERT INTO schema_migrations VALUES(61); CREATE TABLE originals(text TEXT); INSERT INTO originals VALUES('unchanged');")
            with patch('migrations.MIGRATION_DIR', migration_dir):
                version, _ = upgrade_database(db, backup=False)
                self.assertEqual(version, 62)
                self.assertEqual(upgrade_database(db, backup=False)[0], 62)
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute('SELECT text FROM originals').fetchone()[0], 'unchanged')


def examples(count):
    return [{'identity': f'example-{index}', 'lemma': f'слово-{index}', 'form': 'слово', 'tags': {},
             'sentence': f'Это слово в упражнении {index}.', 'translation': f'The word in exercise {index}.',
             'target_meaning': 'word', 'assets': [{'kind': 'image', 'id': f'image-{index}'}]}
            for index in range(count)]


class DistinctRoundTests(unittest.TestCase):
    def build(self, game, pool):
        return build_content({'id': game, 'title': game}, pool, 'fixed-seed', 'session',
                             {'rounds': 10, 'round_policy': 'distinct-v2'}, {'kind': 'vocabulary'})

    def test_ten_picture_rounds_use_four_images_and_ten_meaningful_combinations(self):
        for game in ('pack-bag', 'pairs', 'detective'):
            with self.subTest(game=game):
                content = self.build(game, examples(4))
                signatures = set()
                images = set()
                for item in content['rounds']:
                    route = tuple(clue['text'] for clue in item['clues']) if game == 'detective' else ()
                    signatures.add((tuple(sorted(item['evidence_texts'])), route))
                    for group in ('objects', 'right', 'destinations'):
                        images.update(choice['image_url'] for choice in item.get(group, []))
                self.assertEqual(len(signatures), 10)
                self.assertEqual(len(images), 4)
                self.assertNotIn('round_policy', content['options'])

    def test_ten_text_rounds_have_ten_distinct_targets_or_matching_sets(self):
        for game in ('letter-back', 'mailbox-sort'):
            content = self.build(game, examples(10))
            self.assertEqual(len({tuple(sorted(item['evidence_texts'])) for item in content['rounds']}), 10)
            with self.assertRaisesRegex(ValueError, 'distinct'):
                self.build(game, examples(5))


class GeneratedActivityVariationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = str(Path(directory.name) / 'workspace.sqlite')
        with sqlite3.connect(self.db) as conn:
            conn.executescript((MIGRATION_DIR / '062_content_variation.sql').read_text())

    def test_writing_supplies_private_history_and_rejects_repeat_after_one_call_per_request(self):
        from services.writing_service import WritingService, WritingUnavailable
        from tests.test_writing_generated_evidence import TASK
        service = WritingService.__new__(WritingService)
        service.db_path = self.db
        service.structured = Mock(return_value=dict(TASK))
        service.generate_writing_task('family', 'C1')
        with self.assertRaises(WritingUnavailable):
            service.generate_writing_task('family', 'C1')
        self.assertEqual(service.structured.call_count, 2)
        payload = service.structured.call_args.args[3]
        self.assertEqual(payload['content_variation']['recent_examples'][0]['text'], TASK['task'])
        self.assertNotIn('_owner_scope', json.dumps(payload))

    def test_translation_rejects_same_source_and_supplies_shared_recent_context(self):
        from services.sentence_service import SentenceService, TranslationUnavailable
        service = SentenceService.__new__(SentenceService)
        service.db_path = self.db
        service._structured = Mock(return_value={'sentence': 'Мы встретились у музея.', 'english': 'We met near the museum.'})
        service.get_sentence('any', 'C1')
        with self.assertRaises(TranslationUnavailable):
            service.get_sentence('any', 'C1')
        self.assertEqual(service._structured.call_count, 2)
        self.assertTrue(service._structured.call_args.args[3]['content_variation']['recent_examples'])

    def test_comprehension_rejects_repeat_before_another_image_and_never_retries_it(self):
        from services.comprehension_service import ComprehensionService
        from tests.test_story_titles import STORY
        service = ComprehensionService.__new__(ComprehensionService)
        service.db_path = self.db
        service.get_vocab_for_topic = Mock(return_value=[])
        service._request_story = Mock(return_value=dict(STORY))
        service.generate_image = Mock(return_value='saved-image')
        asyncio.run(service.generate_story('family', 'C1'))
        with self.assertRaises(RepeatedContent):
            asyncio.run(service.generate_story('family', 'C1'))
        self.assertEqual(service._request_story.call_count, 2)
        self.assertEqual(service.generate_image.call_count, 1)
        brief = json.loads(service._request_story.call_args.args[0])
        self.assertTrue(brief['content_variation']['recent_examples'])
        self.assertNotIn('_owner_scope', json.dumps(brief))


class GenerationBudgetRouteTests(unittest.TestCase):
    def setUp(self):
        from services.comprehension_service import ComprehensionService
        from services.sentence_service import SentenceService
        from services.word_jumble_service import WordJumbleService
        from services.writing_service import WritingService
        from tests.support import isolated_app
        self.services = {name: Mock(spec=service) for name, service in (
            ('ComprehensionService', ComprehensionService), ('SentenceService', SentenceService),
            ('WordJumbleService', WordJumbleService), ('WritingService', WritingService))}
        self.app = isolated_app(self, self.services)
        self.client = self.app.test_client()
        self.headers = {'Accept': 'application/json',
            'X-CSRF-Token': self.client.get('/api/v1/user-session').json['csrf_token']}

    def counts(self):
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            return {table: conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                for table in ('writing_exercises', 'sentences', 'word_jumble_games', 'comprehension_tasks')}

    def test_generation_routes_propagate_budget_denial_without_retry_or_partial_task(self):
        from services.ai_trial_budget import TrialDenied
        before = self.counts()
        for route, service, method in (
            ('/writing/generate', 'WritingService', 'generate_writing_task'),
            ('/sentence/generate', 'SentenceService', 'get_sentence'),
            ('/word_jumble/create', 'WordJumbleService', 'create_game'),
            ('/comprehension', 'ComprehensionService', 'generate_story'),
        ):
            with self.subTest(route=route):
                provider = getattr(self.services[service], method)
                provider.side_effect = TrialDenied('The trial limit has been reached.')
                response = self.client.post(route, data={'topic': 'any', 'difficulty': 'A1', 'target_words': 30},
                                            headers=self.headers)
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.json['error']['code'], 'trial_limit')
                self.assertEqual(provider.call_count, 1)
                self.assertEqual(self.counts(), before)
        self.services['ComprehensionService'].generate_image.assert_not_called()
        self.services['ComprehensionService'].generate_audio.assert_not_called()

    def test_comprehension_audio_budget_denial_does_not_publish_a_partial_story(self):
        from services.ai_trial_budget import TrialDenied
        from tests.test_story_titles import STORY
        service = self.services['ComprehensionService']
        service.generate_story.return_value = {**STORY, 'image_url': 'already-prepared-image'}
        service.generate_audio.side_effect = TrialDenied('The trial limit has been reached.')
        before = self.counts()
        response = self.client.post('/comprehension', data={'topic': 'any', 'difficulty': 'A1'}, headers=self.headers)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json['error']['code'], 'trial_limit')
        self.assertEqual(service.generate_story.call_count, 1)
        self.assertEqual(service.generate_audio.call_count, 1)
        service.generate_image.assert_not_called()
        self.assertEqual(self.counts(), before)
        with self.client.session_transaction() as saved:
            self.assertNotIn('current_story_data', saved)


if __name__ == '__main__':
    unittest.main()
