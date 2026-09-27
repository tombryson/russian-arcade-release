"""Planning references must not become claims about a learner's proficiency."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from markupsafe import escape

from services import torfl_requirements as torfl
from services.curriculum import curriculum, generation_context
from services.vocabulary_topics import TOPICS
from tests.support import isolated_app


class TorflReferenceTests(unittest.TestCase):
    def setUp(self):
        torfl._catalogue.cache_clear()
        self.addCleanup(torfl._catalogue.cache_clear)

    def test_each_published_level_has_sourced_requirements_in_five_domains(self):
        for level in ('A1', 'A2', 'B1', 'B2'):
            with self.subTest(level=level):
                reference = torfl.reference_for_level(level)
                torfl.validate_reference(reference)
                self.assertEqual({r['domain'] for r in reference['requirements']},
                                 {'language_use', 'reading', 'listening', 'writing', 'speaking'})
                source_ids = {source['id'] for source in reference['sources']}
                for requirement in reference['requirements']:
                    self.assertTrue(requirement['source_refs'])
                    self.assertTrue(all(ref['source_id'] in source_ids and ref['locator'].strip()
                                        for ref in requirement['source_refs']))

    def test_cumulative_reference_preserves_earlier_requirements_and_deduplicates_sources(self):
        levels = [torfl.reference_for_level(level) for level in ('A1', 'A2', 'B1', 'B2')]
        cumulative = torfl.reference_for_level('B2', cumulative=True)
        expected_ids = [item['id'] for level in levels for item in level['requirements']]
        self.assertEqual([item['id'] for item in cumulative['requirements']], expected_ids)
        self.assertEqual(len(expected_ids), len(set(expected_ids)))
        expected_sources = {source['id']: source for level in levels for source in level['sources']}
        self.assertEqual(cumulative['sources'], list(expected_sources.values()))
        self.assertEqual(sum(source['id'] == 'msu-b1-2009' for source in cumulative['sources']), 1)
        # Public callers must not be able to mutate the cached catalogue.
        cumulative['requirements'][0]['expectation'] = 'Changed by caller'
        cumulative['sources'][0]['note'] = 'Changed by caller'
        fresh = torfl.reference_for_level('B2', cumulative=True)
        self.assertNotEqual(fresh['requirements'][0]['expectation'], 'Changed by caller')
        self.assertNotEqual(fresh['sources'][0]['note'], 'Changed by caller')

    def test_conflicting_metadata_cannot_reuse_a_source_id_across_levels(self):
        references = {level: torfl.reference_for_level(level) for level in torfl.LEVELS}
        shared = next(source for source in references['B2']['sources'] if source['id'] == 'msu-b1-2009')
        shared['edition'] = 'Different unverified edition'
        with tempfile.TemporaryDirectory(prefix='torfl-conflict-') as temporary:
            directory = Path(temporary)
            for level, data in references.items():
                (directory / f'{level}.json').write_text(json.dumps(data), encoding='utf-8')
            with patch.object(torfl, 'DATA_DIR', directory):
                torfl._catalogue.cache_clear()
                with self.assertRaisesRegex(ValueError, 'Shared source IDs'):
                    torfl.reference_for_level('B2', cumulative=True)

    def test_incomplete_or_misattributed_sources_are_rejected(self):
        original = torfl.reference_for_level('A1')
        mutations = {
            'missing edition': lambda data: data['sources'][0].pop('edition'),
            'missing provenance': lambda data: data['sources'][0].update(note=''),
            'insecure source URL': lambda data: data['sources'][0].update(url='http://example.org/source.pdf'),
            'unknown source kind': lambda data: data['sources'][0].update(kind='unverified'),
            'duplicate source ID': lambda data: data['sources'].append(deepcopy(data['sources'][0])),
            'unlisted cited source': lambda data: data['requirements'][0]['source_refs'][0].update(source_id='missing'),
            'no page or section': lambda data: data['requirements'][0]['source_refs'][0].update(locator=''),
        }
        for name, mutate in mutations.items():
            with self.subTest(problem=name):
                broken = deepcopy(original)
                mutate(broken)
                with self.assertRaises(ValueError):
                    torfl.validate_reference(broken)

    def test_selection_cannot_be_registered_as_independent_production(self):
        for domain in ('writing', 'speaking'):
            with self.subTest(domain=domain):
                broken = torfl.reference_for_level('A1')
                item = next(r for r in broken['requirements'] if r['domain'] == domain)
                item['response_mode'] = 'contextual_selection'
                with self.assertRaisesRegex(ValueError, 'Selection cannot stand in'):
                    torfl.validate_reference(broken)
        broken = torfl.reference_for_level('B1')
        listening = next(r for r in broken['requirements'] if r['id'] == 'b1.listening.stress-intonation')
        listening['domain'] = 'language_use'
        with self.assertRaisesRegex(ValueError, 'Selection cannot stand in'):
            torfl.validate_reference(broken)

    def test_unknown_topics_missing_domains_and_broken_inheritance_are_rejected(self):
        original = torfl.reference_for_level('A2')
        mutations = {
            'invented topic': lambda data: data['requirements'][0].update(topic_ids=['first_steps']),
            'ambiguous wildcard': lambda data: data['requirements'][0].update(topic_ids=['*', 'food']),
            'missing speaking': lambda data: data.update(requirements=[r for r in data['requirements'] if r['domain'] != 'speaking']),
            'skipped predecessor': lambda data: data.update(extends='B1'),
            'duplicate requirement': lambda data: data['requirements'].append(deepcopy(data['requirements'][0])),
        }
        for name, mutate in mutations.items():
            with self.subTest(problem=name):
                broken = deepcopy(original)
                mutate(broken)
                with self.assertRaises(ValueError):
                    torfl.validate_reference(broken)

    def test_case_functions_require_an_explicit_recognised_case(self):
        for case in (None, '', 'locative', 'genitive-or-accusative'):
            with self.subTest(case=case):
                broken = torfl.reference_for_level('B1')
                item = next(r for r in broken['requirements'] if r['category'] == 'cases')
                if case is None:
                    item.pop('case')
                else:
                    item['case'] = case
                with self.assertRaisesRegex(ValueError, 'identify its case'):
                    torfl.validate_reference(broken)
        broken = torfl.reference_for_level('B1')
        item = next(r for r in broken['requirements'] if r['domain'] == 'language_use')
        item['category'] = 'unclassified_grammar'
        with self.assertRaisesRegex(ValueError, 'named grammatical category'):
            torfl.validate_reference(broken)

    def test_grammar_grouping_names_all_six_cases_without_losing_requirements(self):
        for level in ('A1', 'A2', 'B1', 'B2'):
            expected = torfl.reference_for_level(level)['requirements']
            for language in ('en', 'ru'):
                with self.subTest(level=level, language=language):
                    groups = torfl.requirement_groups(level, language)['groups']
                    displayed = []
                    for group in groups:
                        if group['id'] == 'language_use':
                            sections = group['sections']
                            labels = {section['label'] for section in sections}
                            expected_case_labels = {
                                labels[0 if language == 'en' else 1]
                                for labels in torfl.CASE_LABELS.values()
                            }
                            self.assertLessEqual(expected_case_labels, labels)
                            displayed.extend(item['id'] for section in sections for item in section['items'])
                        else:
                            self.assertFalse(group['sections'])
                            displayed.extend(item['id'] for item in group['items'])
                    self.assertCountEqual(displayed, [item['id'] for item in expected])
                    self.assertEqual(len(displayed), len(set(displayed)))

    def test_generated_requirements_document_matches_the_catalogue(self):
        root = Path(__file__).resolve().parents[2]
        script = root / 'scripts' / 'render_curriculum_requirements.py'
        spec = importlib.util.spec_from_file_location('requirements_renderer_test', script)
        renderer = importlib.util.module_from_spec(spec)
        # The command-line renderer adjusts its import path. Keep that local to
        # this import so the regression test does not affect other modules.
        with patch.object(sys, 'path', list(sys.path)):
            spec.loader.exec_module(renderer)
        expected = (root / 'docs' / 'curriculum-requirements.md').read_text(encoding='utf-8')
        self.assertEqual(renderer.render(), expected,
                         'Regenerate docs/curriculum-requirements.md after changing the catalogue.')

    def test_higher_level_demands_take_priority_when_revisiting_an_a1_topic(self):
        for activity in ('reading', 'writing', 'translation', 'word_jumble', 'speaking'):
            with self.subTest(activity=activity):
                context = generation_context('food', 'B2', activity)
                self.assertEqual(context['topic_band'], 'A1')
                self.assertEqual(context['target_level'], 'B2')
                brief = context['proficiency_reference']
                self.assertEqual(brief['scope'], 'teaching_reference')
                self.assertTrue(brief['requirements'])
                self.assertTrue(all(item['id'].startswith('b2.') for item in brief['requirements']))
                self.assertLessEqual(len(brief['requirements']), 8)

    def test_sentence_generation_does_not_inherit_essay_or_audio_requirements(self):
        for level in ('A1', 'A2', 'B1', 'B2'):
            for activity in ('translation', 'word_jumble'):
                with self.subTest(level=level, activity=activity):
                    brief = torfl.generation_reference('food', level, activity)
                    self.assertTrue(brief['requirements'])
                    self.assertEqual({item['domain'] for item in brief['requirements']}, {'language_use'})
                    self.assertEqual({item['response_mode'] for item in brief['requirements']}, {'contextual_selection'})
                    self.assertLessEqual(len(brief['requirements']), 8)

    def test_generation_briefs_remain_small_and_respect_the_activity_evidence(self):
        activity_domains = {
            'reading': 'reading', 'writing': 'writing', 'speaking': 'speaking',
            'translation': 'language_use', 'word_jumble': 'language_use',
        }
        for level in ('A1', 'A2', 'B1', 'B2'):
            for activity, domain in activity_domains.items():
                with self.subTest(level=level, activity=activity):
                    brief = torfl.generation_reference('greetings', level, activity)
                    self.assertTrue(brief['requirements'])
                    self.assertLessEqual(len(brief['requirements']), 8)
                    self.assertLessEqual({item['domain'] for item in brief['requirements']}, {domain, 'language_use'})
                    self.assertNotIn('listening_selection', {item['response_mode'] for item in brief['requirements']})
                    self.assertIn('Reply selection is not spoken production', brief['use'])
                    self.assertIn('written answers do not establish listening', brief['use'])

    def test_unresearched_levels_are_not_silently_given_a_lower_level_reference(self):
        for level in ('C1', 'C2', 'C1-C2', 'unlisted'):
            with self.subTest(level=level):
                self.assertIsNone(torfl.reference_for_level(level))
                self.assertIsNone(torfl.requirement_groups(level))
                self.assertIsNone(torfl.generation_reference('food', level, 'reading'))
        for level in ('C1', 'C2'):
            context = generation_context('food', level, 'reading')
            self.assertEqual(context['target_level'], level)
            self.assertNotIn('proficiency_reference', context)
        self.assertIsNone(torfl.generation_reference('food', 'B2', 'unlisted-activity'))


class TorflCurriculumPageTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, demo=False, signed_in=False)
        self.client = self.app.test_client()

    def database_snapshot(self):
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            return tuple(conn.iterdump())

    def test_curriculum_links_to_readable_outcomes_and_fifty_topics_without_writes(self):
        before = self.database_snapshot()
        with patch('utils.lazy.LazyService._get', side_effect=AssertionError('Curriculum resolved a provider')):
            response = self.client.get('/curriculum')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.database_snapshot(), before)
        html = response.text
        self.assertNotIn('<details class="curriculum-', html)
        self.assertNotIn('Level requirements', html)
        for level in ('A1', 'A2', 'B1', 'B2'):
            self.assertIn(f'href="/curriculum/levels/{level}"', html)
            page = self.client.get(f'/curriculum/levels/{level}')
            self.assertEqual(page.status_code, 200)
            self.assertIn('Learning outcomes', page.text)
            self.assertNotIn('<details class="curriculum-', page.text)
            for domain in ('language_use', 'reading', 'listening', 'writing', 'speaking'):
                self.assertIn(f'id="{domain}"', page.text)
            for label, _ in torfl.CASE_LABELS.values():
                self.assertIn(f'<h3>{label}</h3>', page.text)
            for item in torfl.reference_for_level(level)['requirements']:
                self.assertIn(f'<li>{escape(item["label_en"])}</li>', page.text)
        self.assertEqual(self.database_snapshot(), before)
        for level in ('C1', 'C2', 'C1-C2'):
            self.assertNotIn(f'href="/curriculum/levels/{level}"', html)
            self.assertEqual(self.client.get(f'/curriculum/levels/{level}').status_code, 404)
        topic_ids = re.findall(r'id="topic-([a-z_]+)"', html)
        self.assertEqual(len(topic_ids), 50)
        self.assertEqual(set(topic_ids), {topic['id'] for topic in curriculum()['topics']})
        self.assertEqual(set(topic_ids), set(TOPICS) - {'grammar'})

    def test_outcomes_preserve_language_and_prior_level_navigation(self):
        with self.client.session_transaction() as session:
            session['ui_lang'] = 'ru'
        page = self.client.get('/curriculum/levels/A2', headers={'HX-Target': 'mainContent'})
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('<!DOCTYPE', page.text)
        self.assertIn('Результаты обучения', page.text)
        self.assertIn('href="/curriculum/levels/A1"', page.text)
        self.assertIn('href="/curriculum#level-A2"', page.text)

    def test_outcome_content_uses_the_selected_ui_language(self):
        with self.client.session_transaction() as session:
            session['ui_lang'] = 'ru'
        response = self.client.get('/curriculum/levels/B1', headers={'HX-Target': 'mainContent'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<!DOCTYPE', response.text)
        self.assertIn('Результаты обучения', response.text)
        for _, label in torfl.CASE_LABELS.values():
            self.assertEqual(response.text.count(f'<h3>{label}</h3>'), 1)
        for group in torfl.requirement_groups('B1', 'ru')['groups']:
            self.assertIn(f'>{group["label"]}</h2>', response.text)
            self.assertIn(group['items'][0]['label_ru'], response.text)


if __name__ == '__main__':
    unittest.main()
