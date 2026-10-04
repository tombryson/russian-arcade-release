"""Russian constructions and event logic for the seven relational A1 units."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from services.curriculum_situation_plans_relations import UNITS, build_plan, validate_plan
from utils.story_processing import get_morph


def unit(identity):
    return json.loads((Path(__file__).resolve().parents[1] / 'data/curriculum_units' / (identity + '.json')).read_text())


def family_plan(identity, family, mode='reading'):
    for n in range(50):
        plan = build_plan(unit(identity), str(n), mode)
        if plan['family_id'] == family:
            return plan
    raise AssertionError('Family must be reachable without forced content.')


class RelationalSituationPlansTests(unittest.TestCase):
    def test_two_reachable_semantic_families_per_unit_and_mode_with_bounded_evidence(self):
        # More than names or pictures vary: each family's event relationship and
        # purpose are different before the model receives a writing request.
        for identity in UNITS:
            original = unit(identity)
            original_copy = deepcopy(original)
            for mode in ('reading', 'listening'):
                plans = [build_plan(original, f'audit-{n}', mode) for n in range(60)]
                self.assertEqual(len({p['family_id'] for p in plans}), 2, identity)
                self.assertEqual(len({p['family_contract']['relationships_en'] for p in plans}), 2)
                self.assertEqual(len({p['purpose'] for p in plans}), 2)
                self.assertEqual(plans[0], build_plan(original, 'audit-0', mode))
                for plan in plans:
                    facts = plan['meaning_plan']['facts']
                    self.assertEqual(len(facts), 3)
                    self.assertTrue(1 <= len(plan['language_requirement_ids']) <= 2)
                    self.assertLessEqual(len(plan['supported_phrases']), 5)
                    self.assertEqual(plan['version'], 'curriculum-language-plan-v5')
                    self.assertEqual(plan['construction_contract'], 'exact-frames-v1')
                    self.assertTrue(all(f['question_en'] and f['checked_source_frame_ru'] and f['feedback'] for f in facts))
                    self.assertTrue(all(len({f['value_ru'], *f['alternative_frames']}) == 3 for f in facts))
                    self.assertTrue(all(f['value_ru'] in f['checked_source_frame_ru'] for f in facts))
                    self.assertNotIn('passage', plan)
                    validate_plan(plan)
            self.assertEqual(original, original_copy)

    def test_exposure_counts_balance_families_before_sampling_words(self):
        for identity in UNITS:
            history = []
            selected = []
            for n in range(20):
                plan = build_plan(unit(identity), str(n), 'reading', history)
                selected.append(plan['family_id'])
                history.insert(0, plan['family_id'])
            self.assertEqual(sorted(selected.count(f) for f in set(selected)), [10, 10])
            first = build_plan(unit(identity), 'same-seed', 'reading')
            next_plan = build_plan(unit(identity), 'same-seed', 'listening', [first['family_id']])
            self.assertNotEqual(first['family_id'], next_plan['family_id'])
            ignored = build_plan(unit(identity), 'same-seed', 'reading', ['not-a-family', None])
            self.assertEqual(first, ignored)

    def test_modality_does_not_silently_add_untaught_requirements(self):
        for identity in UNITS:
            for n in range(20):
                read = build_plan(unit(identity), str(n), 'reading')
                heard = build_plan(unit(identity), str(n), 'listening')
                self.assertEqual(read['meaning_plan']['facts'], heard['meaning_plan']['facts'])
                self.assertEqual(read['language_requirement_ids'], heard['language_requirement_ids'])
                self.assertNotEqual(read['medium'], heard['medium'])
                self.assertFalse(any(f['role'] == 'date' for f in heard['meaning_plan']['facts']))

    def test_build_rejects_missing_teaching_and_wrong_inputs_without_mutation(self):
        self.assertIsNone(build_plan({'id': 'unsupported', 'level': 'A1'}, 'seed', 'reading'))
        for identity in UNITS:
            original = unit(identity)
            first = build_plan(original, 'seed', 'reading')
            first['meaning_plan']['facts'][0]['value_ru'] = 'changed'
            self.assertNotEqual(first, build_plan(original, 'seed', 'reading'))
            missing = deepcopy(original)
            missing['questions'] = []
            with self.assertRaisesRegex(ValueError, 'does not teach'):
                build_plan(missing, 'seed', 'reading')
            with self.assertRaises(ValueError):
                build_plan({**original, 'level': 'A2'}, 'seed', 'reading')
        for seed in ('', ' ', 's' * 121, 8):
            with self.assertRaises(ValueError):
                build_plan(unit(UNITS[0]), seed, 'reading')
        with self.assertRaises(ValueError):
            build_plan(unit(UNITS[0]), 'seed', 'writing')

    def test_current_motion_is_not_a_frequency_or_vehicle_keyword_quiz(self):
        commute = family_plan(UNITS[0], 'motion-changed-commute')
        connection = family_plan(UNITS[0], 'motion-connection-on-foot')
        regular, current, destination = commute['meaning_plan']['facts']
        self.assertEqual(regular['value_ru'], 'ходит пешком')
        self.assertIn('обычно', regular['checked_source_frame_ru'])
        self.assertIn('сегодня едет', current['checked_source_frame_ru'])
        self.assertEqual(current['role'], 'transport')
        self.assertIn('направляется', destination['question_frame_ru'])
        now, before, stop = connection['meaning_plan']['facts']
        self.assertEqual(now['value_ru'], 'идёт пешком')
        self.assertIn('после вокзала', now['question_frame_ru'])
        self.assertIn('сначала', before['checked_source_frame_ru'])
        self.assertIn('nearby', ' '.join(connection['meaning_plan']['constraints']))
        self.assertNotIn('аэропорт', stop['value_ru'])
        self.assertEqual(commute['language_requirement_ids'], ['a1.language.motion-basic-pairs', 'a1.language.prepositional-transport'])
        self.assertIsNone(destination['requirement_id'])

    def test_destination_question_does_not_reveal_the_mode_of_travel(self):
        for family in ('motion-changed-commute', 'motion-connection-on-foot'):
            plan = family_plan(UNITS[0], family)
            fact = plan['meaning_plan']['facts'][-1]
            self.assertIsNone(fact['requirement_id'])
            self.assertIn('направляется', fact['question_frame_ru'])
            self.assertNotRegex(fact['question_frame_ru'], r'идёт|едет|пешком|автобус|машин')
            self.assertIn('heading', fact['question_en'])
            self.assertIn({'ru': 'направляется', 'en': 'is heading',
                           'scope': 'Question support; this verb does not reveal whether the person is walking or using transport.'},
                          plan['supported_phrases'])

    def test_authored_hints_preserve_routine_and_future_aspect_scope(self):
        routine = family_plan(UNITS[0], 'motion-changed-commute')['meaning_plan']['facts'][0]
        self.assertIn('обычно', routine['feedback']['detail_ru'])
        self.assertIn('usually', routine['feedback']['detail_en'])
        for family, phrase in (('aspect-reading-handover', 'планирует делать завтра'),
                               ('aspect-letter-progress', 'планирует сделать завтра')):
            plan = family_plan(UNITS[3], family)
            future = plan['meaning_plan']['facts'][-1]
            self.assertIn(phrase, future['feedback']['detail_ru'])
            if family == 'aspect-reading-handover':
                self.assertTrue(future['value_ru'].startswith('будет читать'))
                self.assertNotIn('сделать', future['feedback']['detail_ru'])

    def test_transport_and_place_forms_have_checked_government(self):
        morph = get_morph()
        for identity in (UNITS[0], UNITS[4]):
            for n in range(25):
                plan = build_plan(unit(identity), str(n), 'reading')
                for fact in plan['meaning_plan']['facts']:
                    if fact['role'] not in ('transport', 'origin', 'destination', 'person_destination'):
                        continue
                    expected = {'transport': 'loct', 'origin': 'gent', 'destination': 'accs', 'person_destination': 'datv'}[fact['role']]
                    for value in [fact['value_ru'], *fact['alternative_frames']]:
                        noun = value.split()[-1]
                        self.assertTrue(any(expected in p.tag for p in morph.parse(noun)), (value, expected))

    def test_counts_use_simple_nominative_possession_not_wrong_accusative(self):
        saw_feminine_one = False
        for n in range(50):
            plan = build_plan(unit(UNITS[1]), str(n), 'reading')
            for fact in plan['meaning_plan']['facts']:
                if fact['role'] != 'quantity':
                    continue
                self.assertTrue(fact['checked_source_frame_ru'].startswith('У '))
                self.assertNotIn('купить', fact['checked_source_frame_ru'])
                # Every scored fact actually contains a counted genitive.
                self.assertFalse(fact['value_ru'].startswith(('один ', 'одна ', 'одно ')))
                saw_feminine_one |= any(v.startswith('одна ') for v in fact['alternative_frames'])
                self.assertIn(fact['form_key'], {key for row in plan['checked_forms'] for key in row})
        self.assertTrue(saw_feminine_one)
        class_plan = family_plan(UNITS[1], 'quantities-class-materials')
        ordinal = class_plan['meaning_plan']['facts'][0]
        self.assertEqual(ordinal['role'], 'ordinal')
        self.assertTrue(all(v.endswith(' урок') for v in [ordinal['value_ru'], *ordinal['alternative_frames']]))
        self.assertEqual(set(class_plan['language_requirement_ids']), {'a1.language.cardinal-and-ordinal', 'a1.language.genitive-quantity'})

    def test_needs_and_company_keep_actor_government_and_semantic_classes(self):
        errands = family_plan(UNITS[2], 'needs-sharing-an-errand')
        first, companion, second = errands['meaning_plan']['facts']
        self.assertNotEqual(first['subject_name'], second['subject_name'])
        self.assertEqual(first['subject_name'], companion['subject_name'])
        people = {p['name_ru']: p for p in errands['meaning_plan']['participants']}
        for fact in (first, second):
            self.assertTrue(fact['checked_source_frame_ru'].startswith(people[fact['subject_name']]['dative_ru'] + ' нужно '))
        for phrase in [companion['value_ru'], *companion['alternative_frames']]:
            self.assertTrue(phrase.startswith('с '))
            self.assertTrue(any('ablt' in p.tag for p in get_morph().parse(phrase.split()[-1])))
        tea = family_plan(UNITS[2], 'company-tea-preferences')
        together, one, two = tea['meaning_plan']['facts']
        self.assertEqual([together['role'], one['role'], two['role']], ['companion', 'ingredient', 'ingredient'])
        self.assertNotEqual(one['value_ru'], two['value_ru'])
        self.assertEqual(set(tea['language_requirement_ids']), {'a1.language.instrumental-company', 'a1.language.instrumental-ingredient'})
        self.assertNotIn('с сыром', str(tea['checked_forms']))

    def test_aspect_never_infers_noncompletion_from_imperfective_alone(self):
        for n in range(50):
            plan = build_plan(unit(UNITS[3]), str(n), 'reading')
            facts = plan['meaning_plan']['facts']
            people = {p['name_ru']: p for p in plan['meaning_plan']['participants']}
            for fact in facts[:2]:
                for value in [fact['value_ru'], *fact['alternative_frames']]:
                    if 'до конца' not in value and not value.startswith('ещё не'):
                        self.assertIn('но не закончил', value)
                    feminine = people[fact['subject_name']]['gender'] == 'feminine'
                    tokens = value.split()
                    if feminine:
                        self.assertTrue(any(token in ('писала', 'написала', 'читала', 'прочитала') for token in tokens))
                    else:
                        self.assertTrue(any(token in ('писал', 'написал', 'читал', 'прочитал') for token in tokens))
                self.assertEqual(fact['requirement_id'], 'a1.language.verb-aspect')
            self.assertEqual(facts[2]['requirement_id'], 'a1.language.verb-tense')
            self.assertIn('завтра', facts[2]['checked_source_frame_ru'])
            if plan['family_id'] == 'aspect-reading-handover':
                self.assertEqual(facts[2]['value_ru'], 'будет читать письмо')
                self.assertIn('does not promise finishing', ' '.join(plan['meaning_plan']['constraints']))

    def test_future_options_never_pair_result_with_its_entailed_activity(self):
        for identity in ('aspect-letter-progress', 'aspect-reading-handover'):
            for mode in ('reading', 'listening'):
                plan = family_plan(UNITS[3], identity, mode)
                future = plan['meaning_plan']['facts'][2]
                events = future['option_events']
                # Options are distinct events within the one announced plan,
                # not logical alternatives between writing and having written.
                self.assertEqual(len({(e['action_lemma'], e['object_lemma']) for e in events}), 3)
                self.assertEqual(len({e['completion'] for e in events}), 1)
                self.assertEqual({e['time'] for e in events}, {'future'})
                self.assertIn('exactly one announced future plan', ' '.join(plan['meaning_plan']['constraints']))
                if identity == 'aspect-letter-progress':
                    self.assertEqual({e['completion'] for e in events}, {'promised'})
                    self.assertNotIn('будет писать письмо', future['alternative_frames'])
                else:
                    self.assertEqual({e['completion'] for e in events}, {'unspecified'})
                    self.assertNotIn('прочитает письмо до конца', future['alternative_frames'])
                # Even an inventoried phrase cannot silently restore the old
                # activity-v-result overlap via edited event descriptors.
                events[1]['action_lemma'] = events[0]['action_lemma']
                events[1]['object_lemma'] = events[0]['object_lemma']
                with self.assertRaisesRegex(ValueError, 'distinct events'):
                    validate_plan(plan)

    def test_phrase_support_has_one_complete_expression_and_precise_gloss(self):
        for identity in UNITS:
            for n in range(20):
                plan = build_plan(unit(identity), str(n), 'reading')
                for phrase in plan['supported_phrases']:
                    self.assertNotIn(' / ', phrase['ru'])
                    self.assertNotIn('…', phrase['ru'])
                    self.assertNotIn(' / ', phrase['en'])

    def test_origins_keep_place_route_and_person_visits_distinct(self):
        route = family_plan(UNITS[4], 'origins-errand-sequence')
        from_place, next_place, later = route['meaning_plan']['facts']
        self.assertEqual([f['role'] for f in (from_place, next_place, later)], ['origin', 'destination', 'destination'])
        self.assertNotEqual(next_place['value_ru'], later['value_ru'])
        self.assertIn('потом', later['question_frame_ru'])
        visit = family_plan(UNITS[4], 'origins-family-visits')
        self.assertEqual(set(visit['language_requirement_ids']), {'a1.language.genitive-origin', 'a1.language.dative-person-destination'})
        origin, other_origin, destination = visit['meaning_plan']['facts']
        self.assertNotEqual(origin['value_ru'], other_origin['value_ru'])
        self.assertTrue(origin['value_ru'].startswith('от '))
        self.assertTrue(destination['value_ru'].startswith('к '))
        self.assertEqual(origin['subject_name'], destination['subject_name'])
        self.assertNotEqual(origin['subject_name'], other_origin['subject_name'])

    def test_connected_messages_bind_cause_to_timing_instead_of_random_clauses(self):
        for n in range(30):
            plan = build_plan(unit(UNITS[5]), str(n), 'listening')
            facts = plan['meaning_plan']['facts']
            if plan['family_id'] == 'messages-meeting-change':
                reason, time, venue = facts
                self.assertTrue(reason['value_ru'].startswith('потому что'))
                self.assertIn(time['value_ru'], ('в шесть', 'в семь'))
                self.assertIn('в пять', time['alternative_frames'])
                self.assertIsNone(venue['requirement_id'])
            else:
                trigger, reason, action = facts
                expected = {'когда урок закончится': 'потому что сейчас урок',
                            'когда работа закончится': 'потому что сейчас работает',
                            'когда встреча закончится': 'потому что сейчас на встрече'}
                self.assertEqual(expected[trigger['value_ru']], reason['value_ru'])
                self.assertTrue(action['value_ru'].startswith('позвонит '))
                self.assertIsNone(action['requirement_id'])
                self.assertEqual(trigger['requirement_id'], reason['requirement_id'])

    def test_instrumental_activity_and_profession_do_not_become_companions(self):
        for n in range(30):
            plan = build_plan(unit(UNITS[6]), str(n), 'reading')
            for fact in plan['meaning_plan']['facts']:
                self.assertFalse(fact['value_ru'].startswith('с '))
                if fact['requirement_id']:
                    self.assertTrue(any('ablt' in p.tag for p in get_morph().parse(fact['value_ru'].split()[-1])))
                if fact['form_key'] == 'future_profession':
                    self.assertIn('говорит: «В будущем я буду ', fact['checked_source_frame_ru'])
                    self.assertNotIn('будет врач', fact['checked_source_frame_ru'])
            if plan['family_id'] == 'instrumental-now-and-future':
                present, activity, future = plan['meaning_plan']['facts']
                self.assertIsNone(present['requirement_id'])
                self.assertNotEqual(present['subject_name'], future['subject_name'])
                self.assertEqual(activity['subject_name'], future['subject_name'])
                self.assertTrue(any(p.normal_form == present['value_ru'] for p in get_morph().parse(future['value_ru'])))

    def test_validator_rejects_cases_even_if_mutated_inventory_agrees(self):
        cases = [
            (UNITS[0], 'motion-changed-commute', 1, 'на автобус'),
            (UNITS[2], 'needs-sharing-an-errand', 1, 'с сестра'),
            (UNITS[4], 'origins-errand-sequence', 0, 'с школы'),
            (UNITS[4], 'origins-family-visits', 2, 'к сестру'),
            (UNITS[6], 'instrumental-now-and-future', 2, 'врач'),
        ]
        for identity, family, index, bad in cases:
            plan = family_plan(identity, family)
            fact = plan['meaning_plan']['facts'][index]
            old = fact['value_ru']
            fact['value_ru'] = bad
            fact['checked_source_frame_ru'] = fact['checked_source_frame_ru'].replace(old, bad)
            plan['checked_forms'].append({fact['form_key']: bad})
            with self.assertRaises(ValueError, msg=(identity, bad)):
                validate_plan(plan)

    def test_validator_rejects_grammatical_but_contradictory_event_relationship(self):
        plan = family_plan(UNITS[5], 'messages-call-after-activity')
        reason = plan['meaning_plan']['facts'][1]
        wrong = reason['alternative_frames'][0]
        previous = reason['value_ru']
        reason['value_ru'] = wrong
        reason['alternative_frames'][0] = previous
        reason['checked_source_frame_ru'] = reason['checked_source_frame_ru'].replace(previous, wrong)
        with self.assertRaisesRegex(ValueError, 'same activity'):
            validate_plan(plan)

    def test_validator_rejects_nominative_need_and_bad_past_agreement(self):
        need = family_plan(UNITS[2], 'needs-sharing-an-errand')
        first = need['meaning_plan']['facts'][0]
        first['checked_source_frame_ru'] = f"{first['subject_name']} нужно {first['value_ru']}."
        with self.assertRaisesRegex(ValueError, 'dative'):
            validate_plan(need)
        aspect = family_plan(UNITS[3], 'aspect-letter-progress')
        fact = aspect['meaning_plan']['facts'][0]
        person = next(p for p in aspect['meaning_plan']['participants'] if p['name_ru'] == fact['subject_name'])
        bad = 'писал письмо, но не закончил' if person['gender'] == 'feminine' else 'писала письмо, но не закончила'
        fact['value_ru'] = bad
        fact['checked_source_frame_ru'] = f"{fact['subject_name']} вчера {bad}."
        aspect['checked_forms'].append({fact['form_key']: bad})
        with self.assertRaisesRegex(ValueError, 'agreement'):
            validate_plan(aspect)


if __name__ == '__main__':
    unittest.main()
