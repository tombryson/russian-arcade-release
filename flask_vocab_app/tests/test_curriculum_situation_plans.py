"""Generated meaning contrasts stay inside their taught modality and grammar."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from services.curriculum_situation_plans import build_language_plan, LOCATION, CALENDAR, TOPICS
from utils.story_processing import get_morph


def unit(identity):
    return json.loads((Path(__file__).resolve().parents[1] / 'data/curriculum_units' / (identity + '.json')).read_text())


class SituationLanguagePlansTests(unittest.TestCase):
    def test_seeded_plans_choose_unit_purposes_without_changing_shared_data(self):
        for identity in (LOCATION, CALENDAR, TOPICS):
            for mode in ('reading', 'listening'):
                source = unit(identity)
                before = deepcopy(source)
                plans = [build_language_plan(source, str(n), mode) for n in range(60)]
                self.assertGreaterEqual(len({p['purpose'] for p in plans}), 3)
                self.assertEqual(plans[0], build_language_plan(source, '0', mode))
                self.assertEqual(source, before)
                self.assertTrue(all(p['answer_frames'] and p['contrast_rules'] for p in plans))
                plans[0]['checked_forms'][0]['lemma'] = 'changed'
                self.assertNotEqual(plans[0], build_language_plan(source, '0', mode))

    def test_location_forms_answer_the_semantic_question_not_only_the_place_name(self):
        plan = build_language_plan(unit(LOCATION), 'places', 'reading')
        self.assertEqual({f['question_ru']: f['form_key'] for f in plan['answer_frames']},
                         {'Где?': 'location', 'Куда?': 'destination'})
        for row in plan['extension_policy']['place_frames']:
            here_prep, here = row['location'].split()
            next_prep, there = row['destination'].split()
            self.assertEqual(here_prep, next_prep)
            self.assertTrue(any(p.normal_form == row['lemma'] and 'loct' in p.tag for p in get_morph().parse(here)))
            self.assertTrue(any(p.normal_form == row['lemma'] and 'accs' in p.tag for p in get_morph().parse(there)))
        self.assertIn('movement alone', ' '.join(plan['grammar_limits']))
        listening = build_language_plan(unit(LOCATION), 'places', 'listening')
        self.assertEqual({k: v for k, v in plan.items() if k != 'mode'},
                         {k: v for k, v in listening.items() if k != 'mode'})

    def test_form_examples_do_not_close_the_vocabulary_to_a_three_place_game(self):
        plans = [build_language_plan(unit(LOCATION), str(n), 'reading') for n in range(20)]
        self.assertTrue(all(p['extension_policy']['checked_forms_are_examples'] for p in plans))
        seen = {row['lemma'] for plan in plans for row in plan['checked_forms']}
        self.assertGreater(len(seen), 3)
        self.assertTrue({'магазин', 'библиотека', 'кафе'} <= seen)
        reference = {r['lemma']: r for r in plans[0]['extension_policy']['place_frames']}
        self.assertEqual(reference['библиотека']['location'], 'в библиотеке')
        self.assertEqual(reference['библиотека']['destination'], 'в библиотеку')
        self.assertEqual(reference['кафе']['location'], reference['кафе']['destination'])
        self.assertIn('another supplied, verified source', plans[0]['extension_policy']['place_rule'])
        self.assertIn('not choose в/на from morphology alone', plans[0]['extension_policy']['place_rule'])

    def test_calendar_listening_never_assumes_untaught_spoken_ordinals(self):
        source = unit(CALENDAR)
        for seed in range(30):
            read = build_language_plan(source, str(seed), 'reading')
            heard = build_language_plan(source, str(seed), 'listening')
            self.assertEqual(heard['language_requirement_ids'], ['a1.language.accusative-duration'])
            self.assertEqual({f['form_key'] for f in heard['answer_frames']}, {'duration'})
            self.assertTrue(all(set(f) == {'lemma', 'duration'} for f in heard['checked_forms']))
            self.assertIn('Do not include calendar dates', ' '.join(heard['grammar_limits']))
            self.assertEqual(set(read['language_requirement_ids']),
                             {'a1.language.genitive-calendar-month', 'a1.language.accusative-duration'})
            dates = [f for f in read['checked_forms'] if 'date_written' in f]
            self.assertEqual(len(dates), 3)
            self.assertEqual(len({f['date_written'] for f in dates}), 3)
            for form in dates:
                day, month = form['date_written'].split()
                self.assertIn(int(day), range(1, 29))
                self.assertTrue(any(p.normal_form == form['lemma'] and 'gent' in p.tag for p in get_morph().parse(month)))

    def test_duration_forms_use_taught_elapsed_lengths_without_prepositions(self):
        plan = build_language_plan(unit(CALENDAR), 'duration', 'listening')
        examples = ' '.join(e['ru'] for g in unit(CALENDAR)['groups'] for e in g['examples'])
        for row in plan['checked_forms']:
            self.assertIn(row['duration'], examples)
            self.assertFalse(row['duration'].startswith(('в ', 'через ')))
            self.assertTrue(any(p.normal_form == row['lemma'] and 'accs' in p.tag
                                for p in get_morph().parse(row['duration'].split()[-1])))

    def test_duration_choice_scales_fit_the_event_without_adding_number_prerequisites(self):
        for mode in ('reading', 'listening'):
            for seed in range(20):
                plan = build_language_plan(unit(CALENDAR), str(seed), mode)
                scope = plan['duration_context']
                expected = ['час', 'день', 'неделю'] if 'reading' in plan['recipe_id'] else ['день', 'неделю', 'месяц']
                self.assertEqual(scope['phrase_examples'], expected)
                self.assertEqual(len(set(scope['phrase_examples'])), 3)
                self.assertNotIn('минута', scope['phrase_examples'])
                self.assertNotIn('lesson', plan['setting'])
                rule = plan['extension_policy']['duration_rule']
                self.assertEqual(rule['optional_one'], ['один', 'одну'])
                self.assertTrue(rule['counts_above_one_require_taught_pattern'])
                self.assertTrue(rule['counted_forms_are_not_implied_by_familiar_lemmas'])

    def test_topic_person_and_thing_keep_one_requirement_and_complete_governed_answers(self):
        plan = build_language_plan(unit(TOPICS), 'topics', 'reading')
        self.assertEqual(plan['language_requirement_ids'], ['a1.language.prepositional-topic'])
        self.assertEqual(len(plan['contrast_rules']), 1)
        self.assertEqual({f['question_ru'] for f in plan['answer_frames']}, {'О ком?', 'О чём?'})
        rows = {f['lemma']: f for f in plan['checked_forms']}
        self.assertEqual(rows['Анна']['topic'], 'об Анне')
        self.assertEqual(rows['отдых']['topic'], 'об отдыхе')
        self.assertEqual(rows['мама']['referent_kind'], 'person')
        self.assertEqual(rows['музыка']['referent_kind'], 'thing')
        self.assertEqual(rows['книга']['topic'], 'о книге')
        self.assertEqual(rows['спорт']['topic'], 'о спорте')
        self.assertTrue(plan['extension_policy']['checked_forms_are_examples'])
        self.assertIn('Additional supported', plan['extension_policy']['topic_rule'])
        for row in rows.values():
            self.assertTrue(any(p.normal_form == row['lemma'].lower() and 'loct' in p.tag
                                for p in get_morph().parse(row['topic'].split()[-1])))
        self.assertIn('о языке', ' '.join(plan['grammar_limits']))
        self.assertIn('обо мне', ' '.join(plan['grammar_limits']))

    def test_frozen_meaning_uses_named_people_and_three_distinct_answer_relations(self):
        for identity in (LOCATION, CALENDAR, TOPICS):
            for mode in ('reading', 'listening'):
                for seed in range(30):
                    plan = build_language_plan(unit(identity), str(seed), mode)
                    meaning = plan['meaning_plan']
                    self.assertEqual(plan['version'], 'curriculum-language-plan-v3')
                    self.assertEqual([f['id'] for f in meaning['facts']], ['f1', 'f2', 'f3'])
                    participants = {p['name_ru'] for p in meaning['participants']}
                    outsiders = {meaning['writer']['name_ru'], meaning['addressee']['name_ru']}
                    self.assertEqual(len(outsiders), 2)
                    self.assertTrue(participants.isdisjoint(outsiders))
                    for fact in meaning['facts']:
                        self.assertIn(fact['subject_name'], participants)
                        self.assertEqual(len(fact['alternative_frames']), 2)
                        self.assertEqual(len({fact['value_ru'], *fact['alternative_frames']}), 3)
                        if fact['role'] == 'person':
                            self.assertNotIn(fact['value_ru'], fact['question_frame_ru'])
                        else:
                            self.assertIn(fact['subject_name'], fact['question_frame_ru'])
                        for other in meaning['facts']:
                            self.assertNotIn(fact['value_ru'].casefold(), other['question_frame_ru'].casefold())
                    meaning['facts'][0]['value_ru'] = 'changed'
                    self.assertNotEqual(plan, build_language_plan(unit(identity), str(seed), mode))

    def test_location_has_one_next_stop_and_two_current_locations(self):
        destinations = set()
        for seed in range(60):
            plan = build_language_plan(unit(LOCATION), str(seed), 'reading')
            facts = plan['meaning_plan']['facts']
            here, next_stop, other_here = facts
            self.assertEqual([f['role'] for f in facts], ['location', 'destination', 'location'])
            self.assertEqual(here['subject_name'], next_stop['subject_name'])
            self.assertNotEqual(here['subject_name'], other_here['subject_name'])
            lookup = {r['destination']: r['location'] for r in plan['extension_policy']['place_frames']}
            self.assertNotIn(lookup[next_stop['value_ru']], (here['value_ru'], other_here['value_ru']))
            self.assertNotEqual(here['value_ru'], other_here['value_ru'])
            destinations.add(next_stop['value_ru'])
        self.assertGreater(len(destinations), 10)

    def test_calendar_stay_has_one_duration_without_an_untaught_listening_date(self):
        for seed in range(30):
            for mode in ('reading', 'listening'):
                plan = build_language_plan(unit(CALENDAR), str(seed), mode)
                facts = plan['meaning_plan']['facts']
                self.assertEqual([f['role'] for f in facts],
                                 ['duration', 'location', 'date' if mode == 'reading' else 'person'])
                self.assertEqual(facts[0]['subject_name'], facts[1]['subject_name'])
                self.assertEqual(set([facts[0]['value_ru'], *facts[0]['alternative_frames']]),
                                 {'день', 'неделю', 'месяц'})
                if mode == 'reading':
                    self.assertEqual(facts[2]['subject_name'], facts[0]['subject_name'])
                else:
                    companion = facts[2]['value_ru']
                    self.assertNotEqual(companion, facts[0]['subject_name'])
                    self.assertTrue(all(companion not in f['question_frame_ru'] for f in facts))
                    self.assertFalse(any('date' in f['role'] for f in facts))
                    self.assertIn('No calendar date', plan['meaning_plan']['timeline_en'])

    def test_topics_keep_one_subject_per_speaker_and_a_shared_venue(self):
        for seed in range(30):
            plan = build_language_plan(unit(TOPICS), str(seed), 'reading')
            person, thing, venue = plan['meaning_plan']['facts']
            self.assertEqual([person['role'], thing['role'], venue['role']],
                             ['topic_person', 'topic_thing', 'location'])
            self.assertNotEqual(person['subject_name'], thing['subject_name'])
            self.assertEqual(person['subject_name'], venue['subject_name'])
            self.assertNotEqual(person['value_ru'], thing['value_ru'])
            for topic in (person, thing):
                self.assertTrue(topic['value_ru'].startswith(('о ', 'об ')))
            if person['value_ru'] == 'об Анне':
                all_names = [p['name_ru'] for p in plan['meaning_plan']['participants']]
                self.assertNotIn('Анна', all_names)
            self.assertIn('no topic changes', plan['meaning_plan']['timeline_en'])

    def test_stay_venues_are_distinct_named_cities_not_overlapping_location_types(self):
        expected = {'в Москве', 'в Петербурге', 'в Туле', 'в Самаре', 'в Омске', 'в Минске'}
        observed = set()
        for mode in ('reading', 'listening'):
            for seed in range(30):
                plan = build_language_plan(unit(CALENDAR), str(seed), mode)
                self.assertEqual(plan['meaning_plan']['venue_family'], 'named-city')
                venue = next(f for f in plan['meaning_plan']['facts'] if f['role'] == 'location')
                choices = {venue['value_ru'], *venue['alternative_frames']}
                self.assertEqual(len(choices), 3)
                self.assertTrue(choices <= expected)
                observed.update(choices)
                for row in plan['extension_policy']['place_frames']:
                    self.assertIn(row['location'], expected)
                    self.assertTrue(any(p.normal_form == row['lemma'].lower() and 'loct' in p.tag
                                        for p in get_morph().parse(row['location'].split()[-1])))
        self.assertEqual(observed, expected)

    def test_no_plan_is_inferred_from_the_level_label_or_missing_teaching(self):
        self.assertIsNone(build_language_plan(unit('present-actions-v1'), 'seed', 'reading'))
        source = unit(LOCATION)
        source['questions'] = []
        with self.assertRaises(ValueError):
            build_language_plan(source, 'seed', 'reading')
        source = unit(TOPICS)
        source['level'] = 'A2'
        with self.assertRaises(ValueError):
            build_language_plan(source, 'seed', 'reading')
        with self.assertRaises(ValueError):
            build_language_plan(unit(TOPICS), 'seed', 'speaking')
        with self.assertRaises(ValueError):
            build_language_plan(unit(TOPICS), '', 'reading')


if __name__ == '__main__':
    unittest.main()
