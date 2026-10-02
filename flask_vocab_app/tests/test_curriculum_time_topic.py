"""Time/topic grammar stays taught, contextual and narrower than proficiency."""
import hashlib
import json
import re
import unittest

from contracts.learning import assess_activity_answer, validate_pack
from repositories.writing_repository import WritingRepository
from services.curriculum_coverage import delivery_report
from services.curriculum_generation import build, inflect
from services.curriculum_requirement_map import requirement_index
from services.curriculum_time_topic_generation import MONTHS, TOPICS
from services.curriculum_units import LISTENING_IDS, _pack, _practice_contract, _questions, get_unit, writing_task
from utils.story_processing import get_morph

TIME = 'calendar-and-duration-v1'
TOPIC = 'talking-about-topics-v1'
REQUIREMENTS = {
    TIME: {'a1.language.genitive-calendar-month', 'a1.language.accusative-duration'},
    TOPIC: {'a1.language.prepositional-topic'},
}


class TimeTopicTeachingTests(unittest.TestCase):
    def test_generated_target_forms_are_taught_before_testing(self):
        month_examples = ' '.join(e['ru'] for g in get_unit(TIME)['groups'] for e in g['examples']).lower()
        for month, _ in MONTHS:
            self.assertIn(month + ' → ' + inflect(month, 'sing gent'), month_examples)
        topic_examples = ' '.join(e['ru'] for g in get_unit(TOPIC)['groups'] for e in g['examples']).lower()
        for lemma, _, prep in TOPICS:
            self.assertIn(prep + ' ' + inflect(lemma, 'sing loct'), topic_examples)
        for duration in ('час', 'минуту', 'день', 'неделю', 'месяц'):
            self.assertIn(duration, month_examples)
        notes = ' '.join(g['note'] for g in get_unit(TOPIC)['groups'])
        self.assertIn('о языке', notes)
        self.assertIn('depends on sound', notes)
        self.assertIn('pronouns', notes)

    def test_contracts_use_exact_reference_scope_and_do_not_claim_assessment(self):
        index = requirement_index()
        for identity, requirements in REQUIREMENTS.items():
            unit = get_unit(identity)
            self.assertNotIn(identity, LISTENING_IDS)
            for stage in ('practice', 'forms'):
                pack = validate_pack(_pack(unit, stage))
                observed = set()
                for q, item in zip(_questions(unit, stage), pack['items']):
                    contract = _practice_contract(unit, item, q, 'sample')
                    criterion = contract['criteria'][0]
                    observed.add(criterion['requirement_id'])
                    self.assertEqual(contract['purpose'], 'practice')
                    self.assertEqual(criterion['source_refs'], index[q['requirement_id']]['source_refs'])
                    self.assertEqual(criterion['evidence_scope'], 'controlled_production' if stage == 'forms' else 'reference')
                self.assertEqual(observed, requirements)
            task = writing_task(unit)
            WritingRepository.validate_task(task)
            WritingRepository.validate_curriculum_contract(task['curriculum_contract'], task['task'], task['required_words'], 'A1')
            self.assertEqual([c['requirement_id'] for c in task['curriculum_contract']['criteria']], ['a1.writing.connected-description'])
            self.assertIn('does not certify independent case control', task['curriculum_contract']['criteria'][0]['expectation'])
        rows = {r['requirement_id']:r for r in delivery_report()['requirements']}
        for identity, requirements in REQUIREMENTS.items():
            for rid in requirements:
                self.assertEqual(rows[rid]['allocation']['unit_candidate'], identity)
                self.assertEqual(rows[rid]['allocation']['assessment_validation'], 'not_validated')
                self.assertEqual(rows[rid]['assessment'], [])

    def test_date_and_duration_mark_meaning_not_just_a_surface_ending(self):
        unique = {}
        for seed in range(100):
            pack, _, qs = build(TIME, str(seed), 'forms')
            self.assertEqual(pack, build(TIME, str(seed), 'forms')[0])
            self.assertEqual({q['rule'] for q in qs}, {'calendar-month', 'elapsed-duration'})
            self.assertEqual(len({q['semantic'] for q in qs}), 6)
            for item,q in zip(pack['items'],qs):
                unique[q['semantic']] = q
                for valid in q['accepted_answers']:
                    self.assertTrue(assess_activity_answer(item, {'text': valid.upper() + '.'})[1])
                if q['rule'] == 'calendar-month':
                    day = int(re.search(r'\b(\d+)\b', q['sentence'])[1])
                    self.assertIn(day, range(1,29))
                    self.assertTrue(any('gent' in p.tag for p in get_morph().parse(q['answer_text'])))
                    self.assertFalse(assess_activity_answer(item, {'text':'в ' + q['answer_text']})[1])
                else:
                    self.assertIn('duration, not the start time', q['meaning'])
                    if q['answer_text'] in ('неделю', 'минуту'):
                        self.assertNotIn(q['answer_text'], q['meaning_ru'])
                    for wrong_meaning in ('в два часа','первого марта','через неделю'):
                        self.assertFalse(assess_activity_answer(item, {'text':wrong_meaning})[1])
        self.assertEqual(len(unique), 17)  # Twelve months; five single-unit durations.
        weeks = [q for q in unique.values() if q['answer_text'] == 'неделю']
        self.assertEqual(weeks[0]['accepted_answers'], ['неделю','одну неделю'])

    def test_about_targets_are_prepositional_and_alternatives_are_distinct(self):
        unique = {}
        for seed in range(30):
            pack, _, qs = build(TOPIC, str(seed), 'forms')
            self.assertEqual(len(pack['items']), 6)
            for q,item in zip(qs,pack['items']):
                unique[q['semantic']] = q
                self.assertEqual(len(q['options']),len(set(q['options'])))
                self.assertTrue(any('loct' in p.tag for p in get_morph().parse(q['answer_text'])))
                self.assertTrue(assess_activity_answer(item,{'text':q['answer_text']})[1])
                for wrong in set(q['options'])-{q['answer_text']}:
                    self.assertFalse(assess_activity_answer(item,{'text':wrong})[1])
                if q['answer_text'] == 'отдыхе':
                    self.assertIn(' об [...]', q['sentence'])
                else:
                    self.assertIn(' о [...]', q['sentence'])
        self.assertEqual(len(unique),len(TOPICS))

    def test_cosmetic_context_changes_retain_prior_answer_exposure_identity(self):
        seen={}
        changes=0
        for unit in (TIME,TOPIC):
            for seed in range(15):
                _, _, qs = build(unit,str(seed))
                for q in qs:
                    previous=seen.get(q['id'])
                    if previous and previous['sentence']!=q['sentence']:
                        changes+=1
                        self.assertEqual(previous['answer_text'],q['answer_text'])
                        self.assertEqual(previous['requirement_id'],q['requirement_id'])
                    seen[q['id']]=q
        self.assertGreater(changes,10)

    def test_preexisting_g1_pack_identities_and_output_remain_frozen(self):
        # Captured from 020a6cf, before these rules were registered. Changing a
        # saved seed must never change an issued exercise or its correct answer.
        old_units = (
            'location-destination-v1', 'possession-absence-v1', 'objects-recipients-v1',
            'present-actions-v1', 'time-routine-v1', 'noun-adjective-agreement-v1',
            'personal-reference-v1', 'basic-motion-v1', 'numbers-quantities-v1',
            'social-exchanges-v1', 'needs-company-v1', 'action-aspect-v1',
            'origins-and-destinations-v1', 'connected-messages-v1',
            'instrumental-activities-professions-v1',
        )
        payload=[build(unit,seed,stage)[0] for unit in old_units
                 for seed in ('frozen-example','second-example') for stage in ('practice','forms')]
        self.assertEqual(hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
                         '44c8fdf4de0f03f57fafce81786a870f53f97fff442576262704e8aac034718c')
