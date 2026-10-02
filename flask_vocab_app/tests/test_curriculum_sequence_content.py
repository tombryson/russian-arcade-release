"""Authored content is pinned; response modes and null findings remain distinct."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from contracts.curriculum import freeze_task_contract, validate_judgements, validate_task_contract
from services import curriculum_sequence_content as content
from services import curriculum_coverage as coverage
from services.curriculum_requirement_map import content_digest, requirement_index


def spec_from(contract):
    return {k: deepcopy(v) for k, v in contract.items() if k not in ('content_sha256', 'contract_sha256')}


def grammar_contract(kind='writing'):
    asset = content.load_asset('location-message-v2' if kind == 'writing' else 'location-exchange-v1')
    spec = spec_from(content.task_contract(asset, 'test:original'))
    spec['criteria'] = [c for c in spec['criteria'] if c['id'] == 'location-form']
    return freeze_task_contract(spec)


class SequenceContentTests(unittest.TestCase):
    def test_manifest_versions_and_all_task_shapes(self):
        manifest = content.load_manifest()
        self.assertEqual(manifest['completion_paths']['challenge'], ['transfer'])
        self.assertEqual(len(manifest['steps']), 8)
        for step in manifest['steps']:
            asset = content.load_asset(step['content_id'])
            self.assertEqual(step['content_sha256'], content_digest(asset))
            if asset['kind'] in ('choice', 'controlled_text', 'listening'):
                for item in asset['content']['items']:
                    contract = content.task_contract(asset, 'test:' + item['id'], item_id=item['id'])
                    self.assertEqual(contract['content']['item'], content.pack_item(asset, item['id']))
                    self.assertEqual(len(contract['criteria']), 1)
                    self.assertIn('model_answer', contract['support']['independence_breakers'])
            elif asset['kind'] == 'reading':
                contracts = content.reading_contracts(asset, 'test:read')
                self.assertEqual(set(contracts), {'0', '1', '2'})
                self.assertTrue(all(c['content']['text'] == asset['content']['passage'] for c in contracts.values()))
        v1 = json.loads((content.DATA_DIR / 'curriculum_units/location-destination-v1.json').read_text())
        self.assertEqual(v1['id'], 'location-destination-v1')
        self.assertNotEqual(v1['id'], manifest['unit_id'])

    def test_changed_content_and_wrong_adapter_rejected(self):
        manifest = content.load_manifest()
        original_read = content._read
        for mutate in (lambda m: m['steps'][1].update(content_sha256='0'*64),
                       lambda m: m['steps'][1].update(adapter='unit_exchange'),
                       lambda m: m['steps'][-1].update(effects_policy='existing-activity-effects-v1'),
                       lambda m: m['completion_paths'].update(challenge=['learn'])):
            broken = deepcopy(manifest); mutate(broken)
            with patch.object(content, '_read', side_effect=lambda directory, identity:
                              broken if directory == 'curriculum_sequences' else original_read(directory, identity)):
                with self.assertRaises(ValueError): content.load_manifest()

    def test_russian_feedback_is_frozen_without_changing_player_items(self):
        manifest = content.load_manifest()
        identities = {step['content_id'] for step in manifest['steps']}
        identities.update(identity for family in manifest['transfer_families'] for identity in family['task_ids'])
        questions = 0
        for identity in identities:
            asset = content.load_asset(identity)
            if asset['kind'] not in ('choice', 'controlled_text', 'listening'):
                continue
            for item in asset['content']['items']:
                with self.subTest(asset=identity, item=item['id']):
                    contract = content.task_contract(asset, 'test:localized', item_id=item['id'])['content']
                    self.assertEqual(contract['item'], content.pack_item(asset, item['id']))
                    self.assertEqual(contract['item']['hint'], item['hint'])
                    self.assertEqual(contract['explanation'], item['explanation'])
                    self.assertEqual(contract['explanation_ru'], item['explanation_ru'])
                    self.assertEqual(contract['item_locale_ru']['hint'], item['hint_ru'])
                    self.assertEqual(contract['title_ru'], asset['title_ru'])
                    self.assertRegex(item['hint_ru'], '[А-Яа-яЁё]')
                    self.assertRegex(item['explanation_ru'], '[А-Яа-яЁё]')
                    self.assertNotIn('hint_ru', contract['item'])
                    questions += 1
        self.assertEqual(questions, 20)
        # Old frozen runs can still allocate retries from their original asset.
        legacy = content.load_asset('location-choices-v2')
        original = legacy['content']['items'][0]
        original.pop('hint_ru'); original.pop('explanation_ru')
        saved = content.task_contract(legacy, 'test:older-frozen-run', item_id=original['id'])['content']
        self.assertNotIn('item_locale_ru', saved)
        self.assertNotIn('explanation_ru', saved)
        self.assertEqual(saved['item']['hint'], original['hint'])
        original['prompt_ru'] = 'Где сейчас Анна?'
        localized = content.task_contract(legacy, 'test:instruction', item_id=original['id'])['content']
        self.assertEqual(localized['item_locale_ru']['prompt'], 'Где сейчас Анна?')
        self.assertEqual(localized['item']['prompt'], original['prompt'])

    def test_transfer_families_change_information_to_resolve(self):
        manifest = content.load_manifest()
        self.assertEqual(len(manifest['transfer_families']), 2)
        texts = []
        for family in manifest['transfer_families']:
            self.assertEqual(len(family['task_ids']), 5)
            assets = [content.load_asset(i) for i in family['task_ids']]
            self.assertEqual({a['kind'] for a in assets}, {'reading', 'listening', 'writing', 'speaking', 'controlled_text'})
            texts.append(next(a['content']['passage'] for a in assets if a['kind'] == 'reading'))
        self.assertIn('Дима в библиотеке', texts[0])
        self.assertIn('парк закрыт', texts[1])
        teaching = content.load_asset('location-teaching-v2')['content']
        examples = ' '.join(e['ru'] for g in teaching['groups'] for e in g['examples'])
        self.assertIn('Встретимся', examples)
        self.assertIn('тоже', examples)
        self.assertIn('парк закрыт', examples)

    def test_transfer_instructions_give_place_facts_without_supplying_target_forms(self):
        names = {'school': 'школа', 'park': 'парк', 'library': 'библиотека'}
        forms = ['в школе', 'в школу', 'в парке', 'в парк', 'в библиотеке', 'в библиотеку']
        for family in content.load_manifest()['transfer_families']:
            for identity in family['task_ids']:
                asset = content.load_asset(identity)
                if asset['kind'] not in ('writing', 'speaking'):
                    continue
                with self.subTest(asset=identity):
                    task = asset['content']
                    instruction = task['task'] if asset['kind'] == 'writing' else task['scene']['instruction_ru']
                    # Russian instructions are visible without a support receipt.
                    # Supply nominative map labels, not a ready-to-copy reply.
                    for form in forms:
                        self.assertNotIn(form, instruction.casefold())
                    for key in ('current_place', 'destination', 'meeting_place', 'previous_meeting_place'):
                        if key in task['scene']:
                            self.assertIn(names[task['scene'][key]], instruction.casefold())
                    self.assertIn('где ты сейчас', instruction)
                    self.assertIn('куда идёшь', instruction)

    def test_speaking_criteria_pin_their_required_original_turns(self):
        for identity in ('location-exchange-v1', 'location-transfer-people-speaking-v1',
                         'location-transfer-update-speaking-v1'):
            with self.subTest(asset=identity):
                asset = content.load_asset(identity)
                contract = content.task_contract(asset, 'test:turn-bound-evidence')
                mapping = contract['content']['criterion_turns']
                self.assertEqual(mapping['current-place'], ['location'])
                self.assertEqual(mapping['next-place'], ['destination'])
                self.assertEqual(mapping['location-form'], ['location'])
                self.assertEqual(mapping['destination-form'], ['destination'])
                self.assertEqual(mapping['understandable-places'], ['location', 'destination'])
                for mutate in (lambda m: m.pop('location-form'),
                               lambda m: m.update(unknown=['location']),
                               lambda m: m.update(**{'current-place': []}),
                               lambda m: m.update(**{'current-place': ['missing-turn']}),
                               lambda m: m.update(**{'current-place': ['location', 'location']})):
                    broken = deepcopy(asset)
                    mutate(broken['content']['criterion_turns'])
                    with self.assertRaisesRegex(ValueError, 'Speaking criterion'):
                        content.task_contract(broken, 'test:invalid-turn-binding')

    def test_media_inventory_never_guesses_readiness(self):
        asset = content.load_asset('location-listening-v2')
        for item in asset['content']['items']: item['audio'] = None
        rows = content.media_inventory(asset)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'unavailable')
        for item in asset['content']['items']:
            item['audio'] = {'url': '/static/audio/course/../../../../.env', 'sha256': '0'*64}
        self.assertEqual(content.media_inventory(asset)[0]['status'], 'unavailable')


class ProductionContractV2Tests(unittest.TestCase):
    def test_binary_communication_does_not_accept_half_credit(self):
        asset = content.load_asset('location-message-v2')
        spec = spec_from(content.task_contract(asset, 'test:binary'))
        spec['criteria'] = [c for c in spec['criteria'] if c['id'] == 'current-place']
        contract = freeze_task_contract(spec)
        report = {'contract_sha256': contract['contract_sha256'], 'judgements': [{
            'criterion_id': 'current-place', 'outcome': 'partial', 'score': 0.5,
            'reason_code': None, 'feedback': 'The current place is understandable.',
            'evidence': [{'quote': 'Дома.', 'start': 0, 'end': 5}]}]}
        with self.assertRaisesRegex(ValueError, 'Binary communication'):
            validate_judgements(contract, report, response_text='Дома.')
        report['judgements'][0].update(outcome='satisfied', score=1)
        validate_judgements(contract, report, response_text='Дома.')

    def test_scoped_grammar_requires_v2_and_matching_feature(self):
        contract = grammar_contract()
        validate_task_contract(contract)
        for mutate in (lambda s: s.update(schema_version=1, contract_version='curriculum-task-v1'),
                       lambda s: s['criteria'][0]['feature'].update(case='accusative'),
                       lambda s: s['criteria'][0]['feature'].update(function='aspect'),
                       lambda s: s['criteria'][0].update(response_mode='contextual_selection'),
                       lambda s: s.update(contract_version=[]),
                       lambda s: s['criteria'][0].update(max_score=True)):
            spec = spec_from(contract); mutate(spec)
            with self.assertRaises(ValueError): freeze_task_contract(spec)

    def test_valid_alternative_is_unobserved_not_incorrect(self):
        contract = grammar_contract()
        report = {'contract_sha256': contract['contract_sha256'], 'judgements': [{
            'criterion_id': 'location-form', 'outcome': 'insufficient_evidence', 'score': None,
            'reason_code': 'valid_alternative', 'feedback': 'Дома communicates a place without the tested construction.',
            'evidence': [{'quote': 'Дома.', 'start': 0, 'end': 5}]}]}
        validate_judgements(contract, report, response_text='Дома.')
        for mutate in (lambda r: r['judgements'][0].update(score=0),
                       lambda r: r['judgements'][0].update(reason_code=None),
                       lambda r: r['judgements'][0].update(reason_code='unclear_audio')):
            broken = deepcopy(report); mutate(broken)
            with self.assertRaises(ValueError): validate_judgements(contract, broken, response_text='Дома.')

    def test_original_wrong_ending_cannot_be_replaced_by_corrected_span(self):
        contract = grammar_contract()
        response = 'Я сейчас в школу.'
        report = {'contract_sha256': contract['contract_sha256'], 'judgements': [{
            'criterion_id': 'location-form', 'outcome': 'not_satisfied', 'score': 0,
            'reason_code': None, 'feedback': 'For your current place, use в школе.',
            'evidence': [{'quote': response, 'start': 0, 'end': len(response)}]}]}
        validate_judgements(contract, report, response_text=response)
        fractional = deepcopy(report)
        fractional['judgements'][0].update(outcome='partial', score=1.5)
        with self.assertRaises(ValueError): validate_judgements(contract, fractional, response_text=response)
        report['judgements'][0]['evidence'][0]['quote'] = 'Я сейчас в школе.'
        with self.assertRaises(ValueError): validate_judgements(contract, report, response_text=response)

    def test_speech_uses_recording_interval_and_can_remain_unclear(self):
        contract = grammar_contract('speaking')
        report = {'contract_sha256': contract['contract_sha256'], 'judgements': [{
            'criterion_id': 'location-form', 'outcome': 'insufficient_evidence', 'score': None,
            'reason_code': 'unclear_audio', 'feedback': 'The ending was not audible.',
            'evidence': [{'start_ms': 20, 'end_ms': 400}]}]}
        validate_judgements(contract, report, audio_duration_ms=1000)
        with self.assertRaises(ValueError): validate_judgements(contract, report, audio_duration_ms=200)
        with self.assertRaises(ValueError): validate_judgements(contract, report, response_text='В школе.')


class DeliveryCoverageTests(unittest.TestCase):
    def test_total_allocation_with_later_band_gaps(self):
        with patch('sqlite3.connect', side_effect=AssertionError('No learner database')):
            report = coverage.delivery_report()
        self.assertEqual({r['requirement_id'] for r in report['requirements']}, set(requirement_index()))
        self.assertEqual(len(report['requirements']), 239)
        for row in report['requirements']:
            self.assertEqual(row['allocation']['assessment_validation'], 'not_validated')
            self.assertTrue(row['allocation']['gap'])
            if not row['requirement_id'].startswith('a1.'):
                self.assertEqual(row['allocation']['package'], 'P4')
                self.assertTrue(all(not row[s] for s in coverage.STAGES))
        speaking = next(r for r in report['requirements'] if r['requirement_id'] == 'a1.speaking.ask-and-answer')
        self.assertTrue(all(e['relation'] == 'partial' and 'Learner-initiated' in e['scope'] for e in speaking['production']))

    def test_unmapped_sequence_stage_does_not_claim_existing_teaching_is_absent(self):
        report = coverage.delivery_report()
        row = next(r for r in report['requirements'] if r['requirement_id'] == 'a1.language.verb-conjugation')
        self.assertEqual(row['allocation']['unit_status'], 'authored_candidate')
        self.assertEqual(row['allocation']['unit_candidate'], 'present-actions-v1')
        self.assertEqual(row['stage_status']['teaching'], 'not_mapped')
        self.assertEqual(row['stage_status']['assessment'], 'not_mapped')
        self.assertEqual(row['allocation']['assessment_validation'], 'not_validated')

    def test_coverage_cannot_claim_review_or_launder_modes(self):
        data = coverage.load_coverage()
        for mutate in (lambda d: d['requirements'].pop(),
                       lambda d: d['policy'].update(assessment_validated=True),
                       lambda d: d['review'].update(independently_validated=True),
                       lambda d: next(r for r in d['requirements'] if r['production'])['production'][0].update(content_sha256='0'*64),
                       lambda d: next(r for r in d['requirements'] if r['production'])['production'][0].update(relation='equivalent')):
            broken = deepcopy(data); mutate(broken)
            with self.assertRaises(ValueError): coverage.validate_coverage(broken)


class SequenceAudioPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / 'scripts'))
        spec = importlib.util.spec_from_file_location('sequence_audio_test', root / 'scripts/prepare_curriculum_sequence_audio.py')
        cls.audio = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.audio)

    def assets(self):
        asset = content.load_asset('location-listening-v2')
        return {asset['id']: asset}

    def test_duplicate_keys_do_not_spend_again_and_batch_limits_precede_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            saved, keys, todo = self.audio.plan_recordings(self.assets(), directory, lambda _: 1)
            self.assertEqual(len(todo), 1)
            provider = unittest.mock.Mock()
            with self.assertRaisesRegex(ValueError, 'limits'):
                self.audio.prepare_recordings(self.assets(), directory, {}, provider, lambda _: 1, max_new=0)
            provider.assert_not_called()

    def test_failed_generation_stops_without_retry(self):
        provider = unittest.mock.Mock()
        provider.return_value.speak.side_effect = RuntimeError('private provider body')
        config = {'ELEVENLABS_API_KEY': 'test', 'ELEVENLABS_MODEL': 'test', 'ELEVENLABS_VOICE_IDS': ['voice-a', 'voice-b']}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, r'Recording stopped \(RuntimeError\)') as error:
                self.audio.prepare_recordings(self.assets(), directory, config, provider, lambda _: 1)
            self.assertNotIn('private provider body', str(error.exception))
            self.assertEqual(provider.return_value.speak.call_count, 1)

    def test_existing_recording_is_verified_not_regenerated(self):
        provider = unittest.mock.Mock(); provider.return_value.speak.return_value = b'test audio'
        config = {'ELEVENLABS_API_KEY': 'test', 'ELEVENLABS_MODEL': 'test', 'ELEVENLABS_VOICE_IDS': ['voice-a']}
        with tempfile.TemporaryDirectory() as directory:
            self.audio.prepare_recordings(self.assets(), directory, config, provider, lambda _: 1)
            provider.reset_mock()
            self.audio.prepare_recordings(self.assets(), directory, config, provider, lambda _: 1)
            provider.assert_not_called()
            path = next(Path(directory).glob('*.mp3')); path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'missing or changed'):
                self.audio.plan_recordings(self.assets(), directory, lambda _: 1)
