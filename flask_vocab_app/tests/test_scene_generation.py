"""Procedural meanings, exact Russian paradigms and immutable owned games."""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
import unittest
from unittest.mock import patch

import pymorphy3

from repositories.learning_repository import transaction
from services.scene_builder import build_content, options
from services.scene_generator import FAMILIES, generate, realize, semantic_key, specifications
from services.scene_motion import surface_form
from services.journey_games import assess_answer
from tests.game_fixtures import grant_earned_game_access
from tests import test_scene_builder as scene_tests


def find_plan(family, level='A1', **features):
    return next(p for p in specifications(family, level) if all(p.get(k) == v for k, v in features.items()))


def selected_texts(row):
    return [next(c['text'] for c in slot['choices'] if c['id'] == expected)
            for slot, expected in zip(row['scene_builder']['slots'], row['expected_answer'])]


class SceneGenerationTests(unittest.TestCase):
    def test_all_semantic_plans_have_valid_independent_dictionary_forms(self):
        morph = pymorphy3.MorphAnalyzer()
        @lru_cache(None)
        def parses(form):
            return morph.parse(form)
        signatures = set()
        total = 0
        for family in FAMILIES:
            for level in ('A1', 'A2', 'B1') if family == 'motion' else ('A1',):
                plans = specifications(family, level)
                self.assertEqual(len(plans), len({semantic_key(p) for p in plans}))
                for i, plan in enumerate(plans):
                    for seed in (i, i + 10000):
                        row = realize(plan, seed)
                        total += 1
                        self.assertTrue(assess_answer(row, row['expected_answer'])['correct'])
                        for ref in row.get('vocabulary_refs', [row['vocabulary']]):
                            signature = (ref['lemma'], ref['form'], tuple(sorted(ref['grammar'].items())))
                            if signature in signatures:
                                continue
                            signatures.add(signature)
                            matches = [p for p in parses(ref['form']) if p.is_known and p.normal_form == ref['lemma']
                                       and p.tag.POS == ref['pos'] and all(getattr(p.tag, k, None) == v for k, v in ref['grammar'].items())]
                            self.assertTrue(matches, (plan, ref, row['correct_sentence']))
                            if ref.get('construction'):
                                self.assertEqual(ref['pos'], 'INFN')
                                self.assertNotIn('tense', ref['grammar'])
                                self.assertIn(ref['construction']['text'], row['correct_sentence'])
        self.assertGreater(total, 1700)
        self.assertGreater(len(signatures), 120)

    def test_many_seeds_change_meanings_not_only_names_and_balance_skills(self):
        seen = {family: set() for family in FAMILIES}
        for seed in range(100):
            for family in FAMILIES:
                level = ('A1', 'A2', 'B1')[seed % 3]
                settings = options({'grammar_focus': family, 'rounds': 10, **({'motion_level': level} if family == 'motion' else {})})
                rows = generate(seed, settings)
                self.assertEqual(rows, generate(seed, settings))
                meanings = {r['generation']['semantic_id'] for r in rows}
                self.assertEqual(len(meanings), 10)
                seen[family].update(meanings)
                skills = Counter(r['scene_builder']['skill'] for r in rows)
                self.assertLessEqual(max(skills.values()) - min(skills.values()), 1)
                for row in rows:
                    self.assertNotIn('expected_answer', row['scene_builder'])
                    self.assertNotIn('generation', row['scene_builder'])
        for family in FAMILIES:
            self.assertGreater(len(seen[family]), 25, family)
        self.assertGreater(len(seen['motion']), 250)
        self.assertGreater(len(seen['location']), 150)

    def test_names_and_wallpaper_do_not_reset_exposure_but_role_changes_do(self):
        plan = find_plan('motion', 'A2', rule='endpoint', event='arrival', mode='foot')
        rows = [realize(plan, seed) for seed in range(12)]
        self.assertGreater(len({r['generation']['actor'] for r in rows}), 1)
        self.assertEqual(len({r['generation']['semantic_id'] for r in rows}), 1)
        first = find_plan('roles', action='helps', actor='girl', order='actor-first')
        other = dict(first, actor='boy')
        self.assertNotEqual(semantic_key(first), semantic_key(other))

    def test_recent_meanings_are_excluded_and_exhaustion_is_explicit(self):
        settings = options({'grammar_focus': 'location', 'rounds': 10})
        recent = []
        for seed in range(12):
            rows = generate(seed, settings, recent)
            keys = [r['generation']['semantic_id'] for r in rows]
            self.assertFalse(set(keys) & set(recent))
            self.assertTrue(all(not r['generation']['recently_seen'] for r in rows))
            recent = keys + recent
        all_keys = [semantic_key(p) for p in specifications('roles')]
        rows = generate('exhausted', options({'grammar_focus': 'roles', 'rounds': 10}), all_keys)
        self.assertTrue(all(r['generation']['recently_seen'] for r in rows))
        self.assertEqual({r['generation']['semantic_id'] for r in rows}, set(all_keys[-10:]))

    def test_spatial_cases_and_movement_do_not_reuse_location_endings(self):
        expectations = [('table', 'on', 'на', 'столе'), ('chair', 'under', 'под', 'стулом'),
                        ('box', 'in', 'в', 'коробке'), ('shelf', 'beside', 'рядом с', 'полкой')]
        for anchor, relation, prep, noun in expectations:
            row = realize(find_plan('location', subject='cat', anchor=anchor, relation=relation, perspective='subject'), 10)
            self.assertEqual(selected_texts(row), [prep, noun])
            self.assertEqual(row['scene_builder']['scene_visual']['anchor'], anchor)
        for action, expected in ((False, ['лежит', 'полке']), (True, ['положила', 'полку'])):
            plan = find_plan('placement', subject='letter', anchor='shelf', action=action)
            row = next(realize(plan, seed) for seed in range(20) if not action or realize(plan, seed)['generation']['actor'] in ('anna', 'nina'))
            self.assertEqual(selected_texts(row), expected)
        reverse = realize(find_plan('location', subject='book', anchor='chair', relation='under', perspective='anchor'), 10)
        self.assertEqual(selected_texts(reverse), ['над', 'книгой'])
        self.assertEqual(reverse['scene_builder']['scene_visual']['relation'], 'under')

    def test_syncretic_nouns_and_adjectives_never_make_duplicate_wrong_buttons(self):
        row = realize(find_plan('roles', action='helps', actor='boy', order='actor-first'), 0)
        self.assertEqual(selected_texts(row), ['мальчик', 'девочке'])
        for part in row['scene_builder']['slots']:
            self.assertEqual(len(part['choices']), len({c['text'] for c in part['choices']}))
        cases = [('book', 'accs', 'синюю'), ('letter', 'nomn', 'синее'), ('ball', 'loct', 'синем')]
        for subject, case, answer in cases:
            row = realize(find_plan('agreement', subject=subject, color='blue', case=case), 0)
            self.assertEqual(selected_texts(row), [answer])

    def test_motion_contexts_constrain_mode_direction_aspect_and_gender(self):
        for gender, expected in [('femn', 'пришла'), ('masc', 'пришёл')]:
            self.assertEqual(surface_form('arrive-foot', gender), expected)
        self.assertEqual(surface_form('exit-foot', 'femn'), 'вышла')
        self.assertEqual(surface_form('ride', 'femn'), 'едет')
        for state, answer in [('one-way', 'идёт'), ('return-trips', 'ходит')]:
            row = realize(find_plan('motion', rule='core', mode='foot', state=state, time='present'), 0)
            self.assertEqual(selected_texts(row), [answer])
            self.assertIn('one journey' if state == 'one-way' else 'and back', row['scene_builder']['scenario'])
        future = realize(find_plan('motion', 'A2', rule='aspect', event='enter', time='infinitive'), 0)
        self.assertEqual(selected_texts(future), ['входить'])
        self.assertIn('будет входить', future['correct_sentence'])
        # A single completed visit does not license rejecting general-factual
        # imperfective приходил. That potential alternative is not offered.
        arrived = realize(find_plan('motion', 'A2', rule='endpoint', mode='foot', event='arrival'), 0)
        self.assertNotIn('приходил', [c['text'] for c in arrived['scene_builder']['slots'][0]['choices']])
        for cargo, mode, answer in [('child', 'foot', 'ведёт'), ('parcel', 'foot', 'несёт'), ('parcel', 'transport', 'везёт')]:
            row = realize(find_plan('motion', 'A2', rule='cargo', cargo=cargo, mode=mode, habit=False), 0)
            self.assertEqual(selected_texts(row), [answer])

    def test_transport_settings_and_b1_combined_routes_are_compatible(self):
        for level in ('A1', 'A2', 'B1'):
            for plan in specifications('motion', level):
                row = realize(plan, 4)
                visual = row['scene_builder']['motion_visual']
                if plan.get('vehicle') == 'train':
                    self.assertEqual(plan['place'], 'town')
                if visual['mode'] == 'transport' and visual['stage'] in ('enter', 'exit'):
                    self.assertEqual(visual['setting'], 'courtyard')
                if level == 'B1':
                    self.assertEqual(len(row['scene_builder']['slots']), 2)
                if plan.get('crossing') == 'river':
                    self.assertIn('реку по мосту', row['correct_sentence'])
        with self.assertRaises(ValueError):
            realize({'family': 'motion', 'level': 'A1', 'rule': 'invented'}, 4)


class SceneGenerationSessionTests(unittest.TestCase):
    setUp = scene_tests.SceneGameTests.setUp
    request = scene_tests.SceneGameTests.request
    token = scene_tests.SceneGameTests.token
    seed_lesson = scene_tests.SceneGameTests.seed_lesson
    start_scene = scene_tests.SceneGameTests.start_scene
    saved_content = scene_tests.SceneGameTests.saved_content
    read = scene_tests.SceneGameTests.read

    def test_new_games_use_owned_semantic_history_and_keep_saved_v3_bytes(self):
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        first = self.start_scene('motion', request_id='frozen-procedural-1')
        saved = self.saved_content(first['id'])
        second = self.start_scene('motion', request_id='fresh-procedural-2', new_game=True)
        a, b = json.loads(saved), json.loads(self.saved_content(second['id']))
        self.assertFalse({r['generation']['semantic_id'] for r in a['rounds']} & {r['generation']['semantic_id'] for r in b['rounds']})
        self.assertNotIn('generation', second['round'])
        self.assertNotIn('semantic_id', second['round']['scene_builder'])
        self.assertEqual(self.saved_content(first['id']), saved)
        with patch('services.scene_builder.build_content', side_effect=AssertionError('must read snapshot')):
            self.assertEqual(self.start_scene('motion', request_id='frozen-procedural-1')['id'], first['id'])
        old = deepcopy(a)
        old['version'] = 'scene-builder-v3'
        for row in old['rounds']:
            row.pop('generation')
        frozen = json.dumps(old, ensure_ascii=False)
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE journey_game_sessions SET content_json=? WHERE id=?', (frozen, first['id']))
        self.assertEqual(self.read(first['id'])['round']['id'], old['rounds'][0]['id'])
        self.start_scene('motion', new_game=True)
        self.assertEqual(self.saved_content(first['id']), frozen)


if __name__ == '__main__':
    unittest.main()
