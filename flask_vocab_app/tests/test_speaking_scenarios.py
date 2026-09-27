import json
import unittest
from unittest.mock import patch

from services.conversation_ai import SCENARIO
from services.conversation_policy import scenario_instructions, russian_speech
from services.speaking_scenarios import SEEDS, build_scenario, choose_scenario


class SpeakingScenarioTests(unittest.TestCase):
    def test_each_seed_has_a_complete_stable_bilingual_snapshot(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                scenario = build_scenario(seed)
                self.assertEqual(scenario, build_scenario(seed))
                self.assertEqual(json.loads(json.dumps(scenario)), scenario)
                self.assertEqual(scenario['seed'], seed)
                self.assertEqual(scenario['id'], seed)
                self.assertEqual(len(scenario['goals']), len(scenario['goals_ru']))
                self.assertEqual(len(scenario['goal_ids']), len(scenario['completion_criteria']))
                self.assertEqual(len(scenario['goal_ids']), len(scenario['goals']))
                self.assertEqual(len(set(scenario['goal_ids'])), len(scenario['goal_ids']))
                self.assertTrue(russian_speech(scenario['opening']))
                for word, price in scenario['menu'].items():
                    self.assertTrue(russian_speech(word))
                    self.assertGreater(price, 0)
                    self.assertIsInstance(price, int)
                self.assertTrue(scenario['worker_brief'])
                self.assertTrue(scenario['closing_instruction'])

    def test_snapshots_cannot_change_the_catalogue_or_another_session(self):
        snapshot = build_scenario(SEEDS[0])
        other = build_scenario(SEEDS[0])
        snapshot['menu']['чай'] = 9999
        snapshot['goals'][0] = 'Changed'
        snapshot['completion_criteria'].clear()
        self.assertEqual(build_scenario(SEEDS[0]), other)

    def test_selection_excludes_previously_used_seeds(self):
        with patch('services.speaking_scenarios.random.choice', side_effect=lambda choices: choices[0]):
            previous = []
            for _ in SEEDS:
                scenario = choose_scenario(previous)
                self.assertNotIn(scenario['seed'], previous)
                previous.insert(0, scenario['seed'])
            self.assertEqual(set(previous), set(SEEDS))
            self.assertEqual(choose_scenario(previous)['seed'], previous[-1])

    def test_exhausted_catalogue_uses_last_occurrence_not_duplicate_history(self):
        # A newest-first history can contain repeated seeds. The first
        # occurrence, not an older repeat, defines when a seed was last used.
        newest_first = [SEEDS[0], *SEEDS[1:], SEEDS[0]]
        self.assertEqual(choose_scenario(newest_first)['seed'], SEEDS[-1])

    def test_unknown_and_historical_seed_ids_do_not_exclude_new_scenarios(self):
        with patch('services.speaking_scenarios.random.choice', side_effect=lambda choices: choices[0]) as chooser:
            result = choose_scenario(['cafe-v1', 'removed-seed', None])
        self.assertEqual(result['seed'], SEEDS[0])
        self.assertEqual(chooser.call_args.args[0], list(SEEDS))
        self.assertEqual(SCENARIO['id'], 'cafe-v1')
        self.assertNotIn('seed', SCENARIO)

    def test_unknown_build_seed_is_not_silently_substituted(self):
        for invalid in ('cafe-v1', 'unknown', '', None, {}):
            with self.subTest(seed=invalid), self.assertRaises(ValueError):
                build_scenario(invalid)

    def test_every_scenario_retains_existing_russian_only_worker_boundaries(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                scenario = build_scenario(seed)
                instructions = scenario_instructions(scenario)
                self.assertIn('только по-русски', instructions)
                for word, price in scenario['menu'].items():
                    self.assertIn(f'{word}: {price} рублей', instructions)

    def test_budget_and_sold_out_situations_are_possible(self):
        budget = build_scenario('cafe-budget-v1')['menu']
        self.assertLessEqual(budget['чай'] + budget['булочка'], 250)
        self.assertLessEqual(budget['кофе'] + budget['булочка'], 250)
        self.assertGreater(budget['кофе'] + budget['пирог'], 250)
        sold_out = build_scenario('cafe-sold-out-v1')
        self.assertNotIn('булочка', sold_out['menu'])
        self.assertGreaterEqual(len(sold_out['menu']), 4)


if __name__ == '__main__':
    unittest.main()
