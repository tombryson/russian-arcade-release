"""Stable target identities and honest, complete A1 evidence requirements."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.curriculum import curriculum, generation_context
from services.curriculum_targets import (
    PRIMARY_SECTIONS, RESPONSE_MODES, curriculum_targets, get_section, get_target,
    load_curriculum_targets, section_for_topic, sections_for_level,
    targets_for_section, targets_for_topic, validate_curriculum_targets,
)


class CurriculumTargetsTests(unittest.TestCase):
    def test_complete_existing_a1_objectives_and_grammar_without_changing_taxonomy(self):
        source = curriculum()
        catalogue = curriculum_targets()
        a1 = [topic for topic in source['topics'] if topic['band'] == 'A1']
        self.assertEqual(len(a1), 10)
        self.assertEqual(len(catalogue['targets']), 110)
        for topic in a1:
            targets = targets_for_topic(topic['id'])
            for field in ('objectives', 'grammar_focus'):
                for index, original_text in enumerate(topic[field]):
                    linked = [target for target in targets
                              if target['source']['field'] == field and target['source']['index'] == index]
                    expected_modes = ({'contextual_selection'} if field == 'grammar_focus' else
                                      set(RESPONSE_MODES) - {'contextual_selection'})
                    with self.subTest(topic=topic['id'], field=field, index=index):
                        self.assertEqual({target['response_mode'] for target in linked}, expected_modes)
                        self.assertTrue(all(target['source']['text'] == original_text for target in linked))
                        self.assertTrue(all(target['curriculum_version'] == source['version'] for target in linked))
        self.assertEqual(curriculum(), source)
        self.assertEqual(len(source['topics']), 50)
        self.assertTrue(all(isinstance(text, str) for topic in source['topics']
                            for text in topic['objectives'] + topic['grammar_focus']))

    def test_exact_primary_allocation_and_optional_independent_production(self):
        sections = sections_for_level()
        self.assertEqual([section['id'] for section in sections], list(PRIMARY_SECTIONS))
        self.assertEqual([len(section['primary_topic_ids']) for section in sections], [3, 2, 3, 2])
        for section in sections:
            self.assertEqual(section['primary_topic_ids'], list(PRIMARY_SECTIONS[section['id']]))
            self.assertFalse(section['independent_production_required'])
            required = targets_for_section(section['id'], required_only=True)
            self.assertEqual([target['id'] for target in required], section['required_target_ids'])
            self.assertEqual({target['topic_id'] for target in required}, set(section['primary_topic_ids']))
            self.assertTrue(all(target['evidence_kind'] != 'independent_production' for target in required))
            production = [get_target(target_id) for target_id in section['independent_production_target_ids']]
            self.assertEqual({target['response_mode'] for target in production},
                             {'independent_writing', 'independent_speaking'})
            self.assertEqual(len(production), len(section['primary_topic_ids']) * 4)
            for topic_id in section['primary_topic_ids']:
                self.assertEqual(section_for_topic(topic_id), section)

    def test_home_requirements_keep_reading_listening_form_selection_separate(self):
        required = get_section('home')['required_target_ids']
        self.assertEqual(required, [
            'a1.greetings.exchange-names.read', 'a1.family.identify-relatives.read',
            'a1.family.possessive-agreement.select', 'a1.home.locate-object.read',
            'a1.home.identify-rooms-furniture.read', 'a1.home.locate-object.listen',
            'a1.family.identify-relatives.listen', 'a1.greetings.polite-greeting.read',
        ])
        read = get_target('a1.home.locate-object.read')
        listen = get_target('a1.home.locate-object.listen')
        write = get_target('a1.home.describe-location.write')
        self.assertEqual(read['source'], listen['source'])
        self.assertEqual(read['source'], write['source'])
        self.assertEqual(len({target['response_mode'] for target in (read, listen, write)}), 3)
        self.assertNotIn(write['id'], required)

    def test_lookup_results_cannot_mutate_the_cached_catalogue(self):
        original = curriculum_targets()
        copies = [curriculum_targets()['targets'], targets_for_topic('home'),
                  targets_for_section('home'), targets_for_section('home', required_only=True)]
        for targets in copies:
            targets[0]['source']['text'] = 'Changed by a consumer'
            targets.clear()
        get_target('a1.home.locate-object.read')['supporting_grammar_target_ids'].clear()
        get_section('home')['required_target_ids'].clear()
        section_for_topic('home')['primary_topic_ids'].clear()
        sections_for_level()[0]['title_en'] = 'Changed'
        self.assertEqual(curriculum_targets(), original)
        self.assertIsNone(get_target('a1.unknown.read'))
        self.assertIsNone(get_section('unknown'))
        self.assertIsNone(section_for_topic('law'))
        self.assertEqual(targets_for_topic('law'), [])
        self.assertEqual(targets_for_section('unknown'), [])
        self.assertEqual(sections_for_level('A2'), [])

    def test_loading_needs_no_profile_or_database_and_does_not_infer_evidence(self):
        with patch('sqlite3.connect', side_effect=AssertionError('Catalogue opened a database')):
            data = load_curriculum_targets()
        policy = data['evidence_policy']
        self.assertFalse(policy['legacy_topic_scores_are_target_evidence'])
        self.assertFalse(policy['independent_production_required'])
        self.assertEqual(policy['required_target_preparation'], ['introduced', 'practised'])
        self.assertNotIn('mastered', policy['categories'])
        self.assertTrue(all('passed' not in target and 'demonstrated' not in target for target in data['targets']))

    def test_saved_generation_context_records_only_activity_relevant_a1_intent(self):
        activity_modes = {
            'reading': 'reading_selection', 'writing': 'independent_writing',
            'translation': 'independent_writing', 'word_jumble': 'independent_writing',
            'speaking': 'independent_speaking',
        }
        for activity, mode in activity_modes.items():
            context = generation_context('home', 'A1', activity)
            with self.subTest(activity=activity):
                self.assertEqual(context['target_catalogue_version'], 'a1-targets-v1')
                self.assertTrue(context['intended_target_ids'])
                self.assertTrue(all(get_target(target_id)['response_mode'] == mode
                                    for target_id in context['intended_target_ids']))
                self.assertEqual(context['objectives'], curriculum()['topics'][3]['objectives'])
                self.assertIn('establishes no target achievement', context['target_evidence_guidance'])
                self.assertNotIn('demonstrated_target_ids', context)
        context = generation_context('home', 'A1', 'writing')
        self.assertNotIn('a1.home.location-prepositions.select', context['intended_target_ids'])
        context['intended_target_ids'].clear()
        self.assertTrue(generation_context('home', 'A1', 'writing')['intended_target_ids'])
        self.assertIn('step-through reply selection is supported practice',
                      generation_context('greetings', 'A1', 'speaking')['target_evidence_guidance'])

    def test_revisited_topics_and_unmapped_bands_do_not_claim_a1_target_coverage(self):
        for topic_id, level in (('home', 'A2'), ('home', 'C2'), ('shopping', 'A1'),
                                ('grammar', 'A1'), ('unlisted', 'A1')):
            for activity in ('reading', 'writing', 'translation', 'word_jumble', 'speaking'):
                with self.subTest(topic=topic_id, level=level, activity=activity):
                    context = generation_context(topic_id, level, activity)
                    self.assertNotIn('intended_target_ids', context)
                    self.assertNotIn('target_catalogue_version', context)

    def test_invalid_source_references_are_rejected(self):
        for replacement in ({'field': 'objectives', 'index': 0, 'text': 'Invented objective'},
                            {'field': 'grammar_focus', 'index': 0, 'text': 'Wrong kind'},
                            {'field': 'objectives', 'index': -1, 'text': 'Negative position'},
                            {'field': 'objectives', 'index': True, 'text': 'Boolean position'}):
            data = curriculum_targets()
            data['targets'][0]['source'] = replacement
            with self.subTest(source=replacement), self.assertRaises(ValueError):
                validate_curriculum_targets(data)

    def test_missing_objective_mode_or_grammar_source_cannot_be_hidden_by_a_section_edit(self):
        for target_id in ('a1.home.describe-location.speak', 'a1.home.singular-plural.select'):
            data = curriculum_targets()
            data['targets'] = [target for target in data['targets'] if target['id'] != target_id]
            section = data['sections'][0]
            for group in ('required_target_ids', 'additional_practice_target_ids', 'independent_production_target_ids'):
                section[group] = [value for value in section[group] if value != target_id]
            for target in data['targets']:
                target['supporting_grammar_target_ids'] = [value for value in target['supporting_grammar_target_ids']
                                                         if value != target_id]
            with self.subTest(target=target_id), self.assertRaisesRegex(ValueError, 'Cover every A1'):
                validate_curriculum_targets(data)

    def test_duplicate_ids_and_duplicate_source_mode_are_rejected(self):
        data = curriculum_targets()
        data['targets'].append(deepcopy(data['targets'][0]))
        with self.assertRaisesRegex(ValueError, 'Target IDs'):
            validate_curriculum_targets(data)
        data = curriculum_targets()
        extra = deepcopy(data['targets'][0])
        extra['id'] = 'a1.greetings.duplicate-source.read'
        data['targets'].append(extra)
        with self.assertRaisesRegex(ValueError, 'Cover every A1'):
            validate_curriculum_targets(data)

    def test_response_modes_and_semantic_ids_cannot_be_mislabelled(self):
        for field, value in (('response_mode', 'overall_topic_score'),
                             ('response_mode', 'independent_writing'),
                             ('evidence_kind', 'independent_production'),
                             ('target_level', 'A2'), ('primary_section_id', 'market'),
                             ('id', 'a1.greetings.1.read'), ('version', True)):
            data = curriculum_targets()
            data['targets'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_curriculum_targets(data)

    def test_grammar_and_section_references_must_exist_and_belong_to_the_topic(self):
        for ref in ('a1.missing.pattern.select', 'a1.greetings.polite-greeting.read',
                    'a1.home.location-prepositions.select'):
            data = curriculum_targets()
            data['targets'][0]['supporting_grammar_target_ids'] = [ref]
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, 'Supporting grammar'):
                validate_curriculum_targets(data)
        for ref in ('a1.unknown.missing.read', 'a1.food.make-request.read'):
            data = curriculum_targets()
            data['sections'][0]['required_target_ids'][0] = ref
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                validate_curriculum_targets(data)

    def test_required_subset_cannot_silently_require_independent_production(self):
        data = curriculum_targets()
        section = data['sections'][0]
        section['required_target_ids'][0], section['independent_production_target_ids'][0] = (
            section['independent_production_target_ids'][0], section['required_target_ids'][0])
        with self.assertRaisesRegex(ValueError, 'Required receptive'):
            validate_curriculum_targets(data)
        data = curriculum_targets()
        data['evidence_policy']['legacy_topic_scores_are_target_evidence'] = True
        with self.assertRaisesRegex(ValueError, 'legacy scores'):
            validate_curriculum_targets(data)

    def test_primary_topics_are_neither_missing_repeated_nor_reassigned(self):
        for replacement in ([], ['greetings', 'family', 'family'], ['numbers', 'family', 'home']):
            data = curriculum_targets()
            data['sections'][0]['primary_topic_ids'] = replacement
            with self.subTest(topics=replacement), self.assertRaises(ValueError):
                validate_curriculum_targets(data)

    def test_file_loader_validates_before_returning_any_authored_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'targets.json'
            data = curriculum_targets()
            path.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(load_curriculum_targets(path), data)
            data['targets'] = []
            path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_curriculum_targets(path)


if __name__ == '__main__':
    unittest.main()
