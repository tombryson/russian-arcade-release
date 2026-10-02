"""Two instrumental functions are taught before bounded generated practice."""
import json
from pathlib import Path
import unittest

from contracts.learning import assess_activity_answer, validate_pack
from repositories.learning_repository import LearningError
from repositories.writing_repository import WritingRepository
from services.curriculum_coverage import delivery_report
from services.curriculum_generation import build
from services.curriculum_requirement_map import requirement_index
from services.curriculum_units import (
    LISTENING_IDS, _pack, _practice_contract, _questions, get_unit,
    listening_content, writing_task,
)
from utils.story_processing import get_morph

UNIT = 'instrumental-activities-professions-v1'
REQUIREMENTS = {'a1.language.instrumental-activity', 'a1.language.instrumental-profession'}


class InstrumentalContentTests(unittest.TestCase):
    def test_all_tested_targets_and_supplied_verb_forms_are_taught(self):
        unit = get_unit(UNIT)
        examples = ' '.join(e['ru'] for g in unit['groups'] for e in g['examples']).lower()
        for target in ('спортом', 'музыкой', 'русским языком', 'врачом', 'учителем', 'инженером',
                       'занимаюсь', 'занимаешься', 'занимается', 'занимаемся', 'занимаетесь',
                       'занимаются', 'буду', 'будешь', 'будет'):
            self.assertIn(target, examples)
        for q in unit['forms']['questions']:
            self.assertIn(q['answer'], examples)
        notes = ' '.join(g['note'] for g in unit['groups'])
        self.assertIn('without с', notes)
        self.assertIn('can describe women', notes)
        self.assertEqual(len(unit['questions']), 8)
        self.assertEqual(len(unit['forms']['questions']), 6)

    def test_narrow_source_contracts_and_current_future_reading(self):
        unit = get_unit(UNIT)
        refs = requirement_index()
        for stage in ('practice', 'forms'):
            pack = validate_pack(_pack(unit, stage))
            for item, q in zip(pack['items'], _questions(unit, stage)):
                contract = _practice_contract(unit, item, q, 'validation')
                criterion = contract['criteria'][0]
                self.assertEqual(criterion['source_refs'], refs[q['requirement_id']]['source_refs'])
                self.assertEqual(contract['purpose'], 'practice')
                if stage == 'forms':
                    self.assertIn(criterion['requirement_id'], REQUIREMENTS)
                    self.assertEqual(criterion['evidence_scope'], 'controlled_production')
                    self.assertEqual(criterion['source_refs'][0]['locator'], '§2.2.2, p. 13')
        reading = next(q for q in unit['questions'] if q['id'] == 'reading-now-future')
        self.assertEqual(next(c['text'] for c in reading['choices'] if c['id'] == reading['answer']), 'Анна')
        self.assertEqual(reading['requirement_id'], 'a1.reading.practical-information')

    def test_valid_music_alternative_is_accepted_but_other_cases_are_not(self):
        errors = ['спорт', 'музыку', 'русскому языку', 'врач', 'учителю', 'инженера']
        items = validate_pack(_pack(get_unit(UNIT), 'forms'))['items']
        for item, error in zip(items, errors):
            for answer in item['accepted_answers']:
                self.assertTrue(assess_activity_answer(item, {'text': '  ' + answer.upper() + '! '})[1])
            self.assertFalse(assess_activity_answer(item, {'text': error})[1])
        self.assertIn('музыкою', items[1]['accepted_answers'])

    def test_writing_observes_communication_not_independent_instrumental_control(self):
        task = writing_task(get_unit(UNIT))
        WritingRepository.validate_task(task)
        WritingRepository.validate_curriculum_contract(task['curriculum_contract'], task['task'], task['required_words'], 'A1')
        criteria = task['curriculum_contract']['criteria']
        self.assertEqual([c['requirement_id'] for c in criteria], ['a1.writing.connected-description'])
        self.assertIn('does not certify independent instrumental-case control', criteria[0]['expectation'])
        self.assertIn('natural paraphrases', criteria[0]['expectation'])

    def test_availability_inventory_does_not_invent_recordings_or_assessment(self):
        self.assertNotIn(UNIT, LISTENING_IDS)
        self.assertFalse(get_unit(UNIT)['listening_available'])
        with self.assertRaises(LearningError):
            listening_content(UNIT)
        report = delivery_report()
        rows = [r for r in report['requirements'] if r['requirement_id'] in REQUIREMENTS]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row['allocation']['unit_candidate'], UNIT)
            self.assertEqual(row['allocation']['unit_status'], 'authored_candidate')
            self.assertEqual(row['allocation']['assessment_validation'], 'not_validated')
            self.assertEqual(row['assessment'], [])
        catalogue = json.loads((Path(__file__).resolve().parents[1] / 'data/speaking_catalogue.json').read_text())
        scenario = get_unit(UNIT)['speaking_href'].split('/scenario/')[1].split('?')[0]
        self.assertIn(scenario, {s['id'] for s in catalogue['scenarios']})

    def test_seeded_rules_are_deterministic_grammatical_and_semantically_distinct(self):
        unique = {}
        for seed in range(100):
            pack, _, questions = build(UNIT, str(seed))
            self.assertEqual(pack, build(UNIT, str(seed))[0])
            self.assertEqual(len(pack['items']), 6)
            self.assertEqual(len({q['semantic'] for q in questions}), 6)
            for q in questions:
                unique[q['semantic']] = q
                self.assertIn(q['requirement_id'], REQUIREMENTS)
                self.assertEqual(len(q['options']), len(set(q['options'])))
                for word in q['answer_text'].split():
                    self.assertTrue(any('ablt' in p.tag for p in get_morph().parse(word)), word)
                if q['rule'] == 'instrumental-profession':
                    self.assertNotIn(q['sentence'].split()[0], ('Мы', 'Вы', 'Они'))
                    self.assertIn(q['sentence'].split()[1], ('буду', 'будешь', 'будет'))
        self.assertEqual(len(unique), 33)  # 7 persons × 3 activities + 4 × 3 professions.
        music = [q for q in unique.values() if q['answer_text'] == 'музыкой']
        self.assertTrue(all(q['accepted_answers'] == ['музыкой', 'музыкою'] for q in music))
        female = [q for q in unique.values() if q['sentence'].startswith('Она будет')]
        self.assertEqual({q['answer_text'] for q in female}, {'врачом', 'учителем', 'инженером'})
