"""Russian event, reference and inflection checks for seven A1 plan families."""
from copy import deepcopy
import json
from pathlib import Path
import re
import unittest

from services.curriculum_situation_plans_personal import UNITS, build_plan, validate_plan


def unit(identity):
    return json.loads((Path(__file__).resolve().parents[1] / 'data/curriculum_units' / f'{identity}.json').read_text())


def family_plan(identity, family, seed='focused', mode='reading'):
    # Recent exposure to the other family gives a reproducible forced choice.
    for number in range(100):
        plan = build_plan(unit(identity), f'{seed}-{number}', mode)
        if plan['family_id'] == family:
            return plan
    raise AssertionError(f'Family not selected: {family}')


class PersonalSituationPlansTests(unittest.TestCase):
    def test_all_fourteen_families_have_valid_detached_plans_and_bounded_support(self):
        seen = set()
        for identity in UNITS:
            source = unit(identity)
            before = deepcopy(source)
            taught = {question['requirement_id'] for question in source['questions']}
            for mode in ('reading', 'listening'):
                plans = [build_plan(source, f'audit-{seed}', mode) for seed in range(40)]
                self.assertEqual(len({plan['family_id'] for plan in plans}), 2)
                for plan in plans:
                    validate_plan(plan)
                    seen.add(plan['family_id'])
                    self.assertEqual(plan['version'], 'curriculum-language-plan-v5')
                    self.assertEqual(plan['construction_contract'], 'exact-frames-v1')
                    self.assertTrue(set(plan['language_requirement_ids']) <= taught)
                    self.assertIn(len(plan['language_requirement_ids']), (1, 2))
                    self.assertLessEqual(len(plan['supported_phrases']), 5)
                    for checked_phrase in plan['checked_forms']:
                        self.assertNotIn('lemma', checked_phrase)
                        for token in checked_phrase['grammatical_checks']:
                            self.assertIn('lemma', token)
                    facts = plan['meaning_plan']['facts']
                    self.assertEqual([fact['id'] for fact in facts], ['f1', 'f2', 'f3'])
                    for fact in facts:
                        self.assertEqual(len({fact['value_ru'], *fact['alternative_frames']}), 3)
                        self.assertTrue(fact['question_en'].endswith('?'))
                        if fact['requirement_id']:
                            frame = next(row for row in plan['answer_frames'] if row['role'] == fact['role'] and row['requirement_id'] == fact['requirement_id'])
                            self.assertEqual(fact['form_key'], frame['form_key'])
                            self.assertRegex(fact['question_frame_ru'].casefold(), frame['question_pattern_ru'])
                            inventory = {row[frame['form_key']] for row in plan['checked_forms']
                                         if row.get('fact_id') == fact['id']}
                            self.assertEqual(inventory, {fact['value_ru'], *fact['alternative_frames']})
                self.assertEqual(plans[0], build_plan(source, 'audit-0', mode))
                plans[0]['meaning_plan']['facts'][0]['value_ru'] = 'changed'
                self.assertNotEqual(plans[0], build_plan(source, 'audit-0', mode))
            self.assertEqual(source, before)
        self.assertEqual(len(seen), 14)

    def test_feedback_uses_authored_fragments_and_keeps_names_readable(self):
        from services.curriculum_situation_plans_relations import UNITS as relation_units, build_plan as relation_plan
        for identities, builder in ((UNITS, build_plan), (relation_units, relation_plan)):
            for identity in identities:
                for seed in range(12):
                    plan = builder(unit(identity), f'hint-{seed}', 'reading')
                    for fact in plan['meaning_plan']['facts']:
                        detail = fact['feedback']['detail_en']
                        self.assertFalse(re.search(r'^(?:What (?:does|is|are|did|will)|Who does|How many .+ does|At what time|On which day)', detail))
                        self.assertNotEqual(detail.casefold(), fact['question_en'].rstrip('?').casefold())
                        self.assertNotIn('?', detail)
                        for person in plan['meaning_plan']['participants']:
                            for field in ('name_en', 'name_ru'):
                                name = person[field]
                                for fragment in (detail, fact['feedback']['detail_ru']):
                                    self.assertNotRegex(fragment, r'(?<!\w)' + re.escape(name.lower()) + r'(?!\w)')
        for family in ('present-individual-and-pair', 'present-reading-turns'):
            plan = family_plan('present-actions-v1', family)
            self.assertIn({'ru': 'по-русски', 'en': 'in Russian',
                           'scope': 'The language of the activity is supplied before the person or verb-form check.'},
                          plan['supported_phrases'])

    def test_recent_exposure_selects_other_relation_before_lexical_sampling(self):
        for identity in UNITS:
            first = build_plan(unit(identity), 'stable', 'reading')
            second = build_plan(unit(identity), 'stable', 'reading', [first['family_id']])
            self.assertNotEqual(first['family_id'], second['family_id'])
            repeated = build_plan(unit(identity), 'stable', 'listening', [first['family_id']])
            self.assertEqual(second['family_id'], repeated['family_id'])
            self.assertEqual(second['meaning_plan']['facts'], repeated['meaning_plan']['facts'])
            history = []
            for seed in range(20):
                plan = build_plan(unit(identity), str(seed), 'reading', history)
                history.insert(0, plan['family_id'])
            self.assertEqual(set(history.count(family) for family in set(history)), {10})

    def test_questions_do_not_reveal_other_questions_answers(self):
        for identity in UNITS:
            for seed in range(40):
                plan = build_plan(unit(identity), str(seed), 'reading')
                for fact in plan['meaning_plan']['facts']:
                    answer = re.escape(fact['value_ru'].casefold())
                    for other in plan['meaning_plan']['facts']:
                        self.assertIsNone(re.search(r'(?<!\w)' + answer + r'(?!\w)', other['question_frame_ru'].casefold()),
                                          (identity, seed, fact['value_ru'], other['question_frame_ru']))

    def test_generation_does_not_turn_a_whole_unit_into_claimed_coverage(self):
        for identity in UNITS:
            plan = build_plan(unit(identity), 'scope', 'reading')
            source = unit(identity)
            missing_target = deepcopy(source)
            selected = plan['language_requirement_ids'][0]
            missing_target['questions'] = [question for question in source['questions'] if question['requirement_id'] != selected]
            with self.assertRaisesRegex(ValueError, 'does not teach'):
                build_plan(missing_target, 'scope', 'reading')
            wrong_level = deepcopy(source)
            wrong_level['level'] = 'A2'
            with self.assertRaises(ValueError):
                build_plan(wrong_level, 'scope', 'reading')
        self.assertIsNone(build_plan({'id': 'unowned-unit'}, 'seed', 'reading'))
        for seed in ('', ' ' * 2, 'x' * 121, None):
            with self.assertRaises(ValueError):
                build_plan(unit(UNITS[0]), seed, 'reading')

    def test_pronoun_recipients_are_dative_and_belongings_keep_owner_reference(self):
        plan = family_plan(UNITS[0], 'reference-giving-and-calling')
        giving, calling, item = plan['meaning_plan']['facts']
        self.assertEqual(giving['value_ru'], 'ему')
        self.assertEqual(calling['value_ru'], 'ей')
        self.assertIn('даёт ему', giving['checked_source_frame_ru'])
        self.assertIn('звонит ей', calling['checked_source_frame_ru'])
        self.assertEqual({giving['value_ru'], *giving['alternative_frames']}, {'ему', 'ей', 'им'})
        self.assertNotIn(item['value_ru'], giving['question_frame_ru'])
        self.assertEqual(plan['language_requirement_ids'], ['a1.language.personal-pronoun-cases'])
        plan = family_plan(UNITS[0], 'reference-shared-belongings')
        self.assertEqual([fact['value_ru'].split()[0] for fact in plan['meaning_plan']['facts']], ['его', 'её', 'их'])
        self.assertEqual(plan['language_requirement_ids'], ['a1.language.pronoun-reference'])
        self.assertIn('both owners', ' '.join(plan['meaning_plan']['constraints']))

    def test_adjectives_include_neuter_invariable_and_plural_without_case_drift(self):
        observed = set()
        for seed in range(100):
            plan = build_plan(unit(UNITS[1]), str(seed), 'reading')
            validate_plan(plan)
            for fact in plan['meaning_plan']['facts']:
                for phrase in (fact['value_ru'], *fact['alternative_frames']):
                    observed.add(phrase)
                    noun = phrase.split()[-1]
                    self.assertTrue(all(other.split()[-1] == noun for other in fact['alternative_frames']))
                    self.assertNotIn('новый', phrase)  # newness overlaps with colour, so is not a distractor
            if plan['family_id'] == 'agreement-separate-sets':
                first, second, boots = plan['meaning_plan']['facts']
                self.assertNotEqual(first['subject_name'], second['subject_name'])
                self.assertNotEqual(first['value_ru'], second['value_ru'])
                self.assertTrue(boots['value_ru'].endswith('ботинки'))
        self.assertTrue({'синее пальто', 'синяя шапка', 'синие ботинки', 'белый шарф'} <= observed)

    def test_present_actions_do_not_sneak_in_an_untaught_third_conjugation(self):
        for family in ('present-individual-and-pair', 'present-reading-turns'):
            plan = family_plan(UNITS[2], family)
            verbs = {check['lemma'] for row in plan['checked_forms'] for check in row['grammatical_checks'] if 'VERB' in check['tags']}
            verbs.update(check['lemma'] for fact in plan['meaning_plan']['facts'] for check in fact['source_checks'] if 'VERB' in check['tags'])
            self.assertTrue(verbs <= {'читать', 'говорить'})
            if family == 'present-individual-and-pair':
                self.assertEqual(plan['meaning_plan']['facts'][1]['value_ru'], 'говорят')
                self.assertIn('plur', plan['checked_forms'][3]['grammatical_checks'][0]['tags'])
                self.assertNotIn('говор', plan['meaning_plan']['facts'][2]['question_frame_ru'])
            else:
                self.assertEqual(plan['language_requirement_ids'], ['a1.language.nominative-subject'])
                self.assertEqual({row['ru'] for row in plan['supported_phrases']}, {'сначала', 'потом', 'по-русски'})

    def test_schedule_keeps_when_separate_from_duration_and_timeline_agrees(self):
        schedule = family_plan(UNITS[3], 'routine-meeting-plan', mode='listening')
        day, hour, _ = schedule['meaning_plan']['facts']
        self.assertTrue(day['value_ru'].startswith(('в ', 'во ')))
        self.assertTrue(hour['value_ru'].startswith('в '))
        self.assertFalse(any(re.search(r'\d', fact['checked_source_frame_ru']) for fact in schedule['meaning_plan']['facts']))
        genders = set()
        for seed in range(40):
            plan = family_plan(UNITS[3], 'routine-three-days', str(seed))
            actor = next(person for person in plan['meaning_plan']['participants'] if person['name_ru'] == plan['meaning_plan']['facts'][0]['subject_name'])
            genders.add(actor['gender'])
            before, now, after = plan['meaning_plan']['facts']
            self.assertEqual(before['value_ru'].endswith('а'), actor['gender'] == 'feminine')
            self.assertTrue(after['value_ru'].startswith('будет '))
            self.assertIn('вчера', before['question_frame_ru'])
            self.assertIn('сегодня', now['question_frame_ru'])
            self.assertIn('завтра', after['question_frame_ru'])
            self.assertEqual(plan['language_requirement_ids'], ['a1.language.verb-tense'])
        self.assertEqual(genders, {'masculine', 'feminine'})

    def test_absence_is_not_ownership_and_a_holder_is_not_an_owner(self):
        possession = family_plan(UNITS[4], 'possession-borrow-missing-item')
        available, absent, holder = possession['meaning_plan']['facts']
        self.assertEqual(available['requirement_id'], 'a1.language.nominative-existence')
        self.assertEqual(absent['requirement_id'], 'a1.language.genitive-absence')
        self.assertIn(' нет ', absent['checked_source_frame_ru'])
        self.assertIsNone(holder['requirement_id'])
        owner = family_plan(UNITS[4], 'possession-owner-and-holder')
        first, second, holder = owner['meaning_plan']['facts']
        self.assertNotEqual(holder['subject_name'], first['subject_name'])
        self.assertNotEqual(second['subject_name'], first['subject_name'])
        self.assertTrue(holder['value_ru'].startswith('у '))
        self.assertEqual(holder['requirement_id'], 'a1.language.genitive-owner-u')
        self.assertEqual(first['requirement_id'], 'a1.language.genitive-possession')
        self.assertIn(first['value_ru'], holder['checked_source_frame_ru'])

    def test_item_transfer_never_confuses_the_thing_with_its_recipient(self):
        handover = family_plan(UNITS[5], 'recipient-handover-and-call')
        item, recipient, called = handover['meaning_plan']['facts']
        self.assertEqual(item['requirement_id'], 'a1.language.accusative-object')
        self.assertEqual(recipient['requirement_id'], 'a1.language.dative-recipient')
        self.assertNotEqual(recipient['value_ru'], called['value_ru'])
        self.assertNotIn(item['value_ru'], recipient['question_frame_ru'])
        shopping = family_plan(UNITS[5], 'recipient-buy-and-give')
        bought, given, recipient = shopping['meaning_plan']['facts']
        self.assertNotEqual(bought['subject_name'], given['subject_name'])
        self.assertNotEqual(bought['value_ru'], given['value_ru'])
        self.assertEqual(given['subject_name'], recipient['subject_name'])

    def test_social_names_need_actual_listening_and_permission_is_not_completion(self):
        names = family_plan(UNITS[6], 'social-names-and-repeat')
        first, second, repeat = names['meaning_plan']['facts']
        from utils.story_processing import get_morph
        for fact in (first, second):
            gender = next(person['gender'] for person in names['meaning_plan']['participants'] if person['name_ru'] == fact['value_ru'])
            tag = 'masc' if gender == 'masculine' else 'femn'
            for alternative in fact['alternative_frames']:
                self.assertTrue(any(tag in parse.tag for parse in get_morph().parse(alternative)))
            self.assertNotIn(fact['value_ru'], repeat['question_frame_ru'])
        self.assertIn('Повторите', repeat['checked_source_frame_ru'])
        permission = family_plan(UNITS[6], 'social-ask-permission')
        self.assertEqual(permission['language_requirement_ids'], ['a1.language.impersonal-modal'])
        self.assertIn('none of the requests has yet been answered', permission['meaning_plan']['timeline_en'])
        for fact in permission['meaning_plan']['facts']:
            self.assertIn('Можно взять', fact['checked_source_frame_ru'])
            self.assertIn('Permission has not yet been granted', fact['relation_en'])

    def test_morphology_validator_rejects_broken_forms_instead_of_normalising_them(self):
        plan = family_plan(UNITS[1], 'agreement-find-clothes')
        broken = deepcopy(plan)
        check = broken['checked_forms'][0]['grammatical_checks'][0]
        check['surface_ru'] = 'синия'
        with self.assertRaisesRegex(ValueError, 'Invalid authored form'):
            validate_plan(broken)

    def test_valid_words_do_not_mask_a_reversed_possession_or_permission_relation(self):
        absent = family_plan(UNITS[4], 'possession-borrow-missing-item')
        fact = absent['meaning_plan']['facts'][1]
        fact['checked_source_frame_ru'] = fact['checked_source_frame_ru'].replace(' нет ', ' есть ')
        with self.assertRaisesRegex(ValueError, 'governing construction'):
            validate_plan(absent)
        permission = family_plan(UNITS[6], 'social-ask-permission')
        fact = permission['meaning_plan']['facts'][0]
        fact['checked_source_frame_ru'] = fact['checked_source_frame_ru'].replace('Можно взять', 'Хочу взять')
        with self.assertRaisesRegex(ValueError, 'governing construction'):
            validate_plan(permission)
        broken = family_plan(UNITS[4], 'possession-borrow-missing-item')
        row = next(row for row in broken['checked_forms'] if row['fact_id'] == 'f2')
        row['grammatical_checks'][0]['tags'] = ['NOUN', 'datv']
        with self.assertRaisesRegex(ValueError, 'Invalid authored form'):
            validate_plan(broken)


if __name__ == '__main__':
    unittest.main()
