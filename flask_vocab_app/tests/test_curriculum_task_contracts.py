"""Frozen tasks and reports cannot award mastery or change response modes."""
from copy import deepcopy
import unittest
from contracts.curriculum import freeze_task_contract, validate_task_contract, validate_judgements
from services.curriculum_requirement_map import requirement_index

def spec_for(requirement='a1.language.prepositional-location', mode=None, scope='reference'):
    ref = requirement_index()[requirement]
    return {'schema_version': 1, 'contract_version': 'curriculum-task-v1', 'reference_version': 'torfl-reference-v1',
            'task_id': 'a1-location-1', 'activity': 'target_practice', 'content_version': 'location-v1',
            'level': 'A1', 'topic_ids': ['home'], 'purpose': 'diagnostic',
            'content': {'prompt': 'Где Барсик?', 'choices': ['В школе.', 'В школу.'], 'answer': 'В школе.'},
            'rubric_version': 'location-rubric-v1',
            'support': {'allowed': ['hint', 'audio_replay'], 'independence_breakers': ['hint']},
            'criteria': [{'id': 'location', 'target_id': 'app.a1.location-contrast', 'requirement_id': requirement,
                          'response_mode': mode or ref['response_mode'], 'evidence_scope': scope,
                          'expectation': 'Identify the stated location.', 'max_score': 2, 'source_refs': deepcopy(ref['source_refs'])}]}

def report_for(contract, response='В школе.'):
    return {'contract_sha256': contract['contract_sha256'], 'judgements': [
        {'criterion_id': 'location', 'outcome': 'satisfied', 'score': 2, 'feedback': 'The location is identified.',
         'evidence': [{'quote': response, 'start': 0, 'end': len(response)}]}]}

class CurriculumTaskContractTests(unittest.TestCase):
    def test_canonical_defensive_snapshot(self):
        spec = spec_for(); frozen = freeze_task_contract(spec)
        self.assertEqual(frozen, freeze_task_contract(dict(reversed(list(spec.items())))))
        spec['content']['answer'] = 'Changed'
        self.assertEqual(validate_task_contract(frozen)['content']['answer'], 'В школе.')
        checked = validate_task_contract(frozen); checked['criteria'][0]['expectation'] = 'Changed'
        self.assertNotEqual(checked, frozen)

    def test_all_frozen_content_and_policy_is_bound_by_hash(self):
        frozen = freeze_task_contract(spec_for())
        for mutate in (lambda c:c['content'].update(answer='В школу.'), lambda c:c.update(rubric_version='new-version'),
                       lambda c:c['support']['independence_breakers'].clear(), lambda c:c['criteria'][0].update(max_score=3)):
            broken = deepcopy(frozen); mutate(broken)
            with self.assertRaises(ValueError): validate_task_contract(broken)

    def test_selection_cannot_become_independent_production(self):
        for rid in ('a1.writing.personal-message', 'a1.speaking.ask-and-answer'):
            with self.assertRaisesRegex(ValueError, 'exact response mode'): freeze_task_contract(spec_for(rid, 'contextual_selection'))
        with self.assertRaises(ValueError): freeze_task_contract(spec_for(mode='independent_writing'))

    def test_controlled_production_is_explicit_and_not_independent_writing(self):
        with self.assertRaises(ValueError): freeze_task_contract(spec_for(mode='controlled_text'))
        valid = freeze_task_contract(spec_for(mode='controlled_text', scope='controlled_production'))
        self.assertEqual(valid['criteria'][0]['evidence_scope'], 'controlled_production')
        for rid in ('a1.writing.personal-message', 'a1.speaking.ask-and-answer'):
            with self.assertRaisesRegex(ValueError, 'language-use reference'): freeze_task_contract(spec_for(rid, 'controlled_text', 'controlled_production'))

    def test_unknown_requirement_source_level_nonfinite_and_mastery_rejected(self):
        for mutate in (lambda s:s['criteria'][0].update(requirement_id='a1.language.invented'),
                       lambda s:s['criteria'][0].update(source_refs=[]), lambda s:s['criteria'][0].update(max_score=True),
                       lambda s:s['content'].update(invalid=float('nan')), lambda s:s.update(level='A0'),
                       lambda s:s.update(purpose='checkpoint'), lambda s:s.update(mastery=True)):
            broken = spec_for(); mutate(broken)
            with self.assertRaises(ValueError): freeze_task_contract(broken)
        with self.assertRaisesRegex(ValueError, 'above its declared level'): freeze_task_contract(spec_for('b1.language.noun-number-animacy'))

    def test_answer_revealing_support_changes_independence(self):
        for kind,rid in [('transcript','a1.listening.short-message'),('translation','a1.reading.practical-information'),('model_answer','a1.writing.personal-message')]:
            spec = spec_for(rid); spec['support']['allowed'].append(kind)
            with self.assertRaises(ValueError): freeze_task_contract(spec)
            spec['support']['independence_breakers'].append(kind); freeze_task_contract(spec)

    def test_text_judgement_needs_original_span(self):
        contract = freeze_task_contract(spec_for()); report = report_for(contract)
        self.assertEqual(validate_judgements(contract,report,response_text='В школе.'),report)
        with self.assertRaisesRegex(ValueError,'original response exactly'): validate_judgements(contract,report,response_text='В школу.')
        with self.assertRaises(ValueError): validate_judgements(contract,report)

    def test_provider_cannot_add_mastery_unknown_criteria_or_invent_scores(self):
        contract = freeze_task_contract(spec_for())
        for mutate in (lambda r:r.update(mastery=True), lambda r:r['judgements'][0].update(level_passed=True),
                       lambda r:r['judgements'][0].update(criterion_id='invented'),lambda r:r['judgements'][0].update(outcome='mastered'),
                       lambda r:r['judgements'][0].update(score=True),lambda r:r.update(contract_sha256='0'*64),
                       lambda r:r['judgements'].append(deepcopy(r['judgements'][0]))):
            report = report_for(contract);mutate(report)
            with self.assertRaises(ValueError):validate_judgements(contract,report,response_text='В школе.')

    def test_insufficient_evidence_is_unscored(self):
        contract=freeze_task_contract(spec_for());report=report_for(contract)
        row=report['judgements'][0];row.update(outcome='insufficient_evidence',score=None,evidence=[],feedback='No response was available.')
        validate_judgements(contract,report)
        row['score']=0
        with self.assertRaisesRegex(ValueError,'unscored'):validate_judgements(contract,report)

    def test_speech_needs_recording_interval_not_captions(self):
        contract=freeze_task_contract(spec_for('a1.speaking.ask-and-answer'));report=report_for(contract)
        with self.assertRaises(ValueError):validate_judgements(contract,report,response_text='В школе.',audio_duration_ms=2500)
        report['judgements'][0]['evidence']=[{'start_ms':0,'end_ms':2000}]
        validate_judgements(contract,report,audio_duration_ms=2500)
        with self.assertRaises(ValueError):validate_judgements(contract,report,audio_duration_ms=1500)
        with self.assertRaises(ValueError):validate_judgements(contract,report)
