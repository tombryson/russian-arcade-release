"""Frozen Writing diagnostics stay attached to owned responses, never mastery."""
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from contracts.curriculum import freeze_task_contract
from repositories.writing_repository import WritingRepository
from services.curriculum_requirement_map import requirement_index
from services.torfl_requirements import VERSION
from services.writing_service import WritingService, WritingUnavailable
from tests.support import isolated_app, select_test_profile
from tests.test_writing_cleanup import ADVICE
from tests.test_writing_generated_evidence import generated_task


TASK = {'title': 'Где вы сейчас?', 'title_en': 'Where are you now?',
        'task': 'Сообщите другу, где вы сейчас и куда пойдёте потом.',
        'task_en': 'Tell a friend where you are now and where you will go next.',
        'required_words': ['школа', 'парк', 'идти']}
RESPONSE = '  Я в школе.\nПотом я иду в парк. '


def contract():
    refs = requirement_index()
    criteria = []
    for name, rid, expectation in (
        ('location', 'a1.language.prepositional-location', 'Say where you are using a stationary location phrase.'),
        ('destination', 'a1.language.accusative-destination', 'Say where you will go using a destination phrase.'),
    ):
        criteria.append({'id': name, 'target_id': f'writing-diagnostic.{name}', 'requirement_id': rid,
                         'response_mode': 'controlled_text', 'evidence_scope': 'controlled_production',
                         'expectation': expectation, 'max_score': 2, 'source_refs': refs[rid]['source_refs']})
    return freeze_task_contract({
        'schema_version': 1, 'contract_version': 'curriculum-task-v1', 'reference_version': VERSION,
        'task_id': 'writing-location-diagnostic', 'activity': 'writing', 'content_version': 'v1',
        'level': 'A1', 'topic_ids': ['home', 'places'], 'purpose': 'diagnostic',
        'content': {'task': TASK['task'], 'required_words': deepcopy(TASK['required_words'])},
        'rubric_version': 'writing-location-diagnostic-v1',
        'support': {'allowed': ['model_answer'], 'independence_breakers': ['model_answer']},
        'criteria': criteria,
    })


def report(frozen=None, response=RESPONSE, *, insufficient=False):
    frozen = frozen or contract()
    judgements = []
    for criterion, quote in zip(frozen['criteria'], ('в школе', 'в парк')):
        empty = insufficient and criterion['id'] == 'destination'
        start = response.index(quote) if not empty else 0
        judgements.append({'criterion_id': criterion['id'],
                           'outcome': 'insufficient_evidence' if empty else 'satisfied',
                           'score': None if empty else 2,
                           'feedback': 'Add where you will go next.' if empty else 'The phrase makes your meaning clear.',
                           'evidence': [] if empty else [{'quote': quote, 'start': start, 'end': start + len(quote)}]})
    return {'contract_sha256': frozen['contract_sha256'], 'judgements': judgements}


class WritingCriterionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.service = WritingService.__new__(WritingService)
        self.service.client = Mock()
        self.app = isolated_app(self, {'WritingService': self.service})
        self.db = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']
        self.repo = WritingRepository(self.db)
        self.frozen = contract()
        self.exercise_id = self.repo.create({**TASK, 'curriculum_contract': self.frozen}, 'home', 'A1', 30)
        self.output({**ADVICE, 'criterion_report': report(self.frozen)})

    def output(self, assessment):
        self.service.client.responses.create.return_value = SimpleNamespace(
            status='completed', output_text=json.dumps(assessment))

    def submit(self, *, revision=0, response=RESPONSE, **extra):
        return self.client.post('/writing/assess', data={
            'exercise_id': self.exercise_id, 'revision': revision, 'user_response': response, **extra},
            headers={'Accept': 'application/json'})

    def snapshot(self):
        tables = ('writing_exercises', 'writing_details', 'writing_drafts', 'writing_attempts',
                  'activity_task_contracts', 'activity_criterion_reports', 'progression_events',
                  'progression_entries', 'course_target_observations', 'course_chapter_passes')
        with sqlite3.connect(self.db) as conn:
            return {name: conn.execute('SELECT * FROM ' + name + ' ORDER BY rowid').fetchall() for name in tables}

    def test_contract_is_frozen_with_task_and_invalid_creation_is_atomic(self):
        loaded = self.repo.load(self.exercise_id)
        self.assertEqual(loaded['curriculum_contract'], self.frozen)
        self.frozen['content']['task'] = 'Changed after creation'
        self.assertEqual(self.repo.load(self.exercise_id)['curriculum_contract']['content']['task'], TASK['task'])
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.repo.create({**TASK, 'curriculum_contract': self.frozen}, 'home', 'A1', 30)
        with self.assertRaises(ValueError):
            self.repo.create({**TASK, 'curriculum_contract': contract()}, 'home', 'A2', 30)
        with self.assertRaises(ValueError):
            self.repo.create({**TASK, 'task': 'Опишите друга.', 'curriculum_contract': contract()}, 'home', 'A1', 30)
        self.assertEqual(self.snapshot(), before)

    def test_real_provider_path_uses_only_saved_contract_and_exact_response(self):
        before = self.snapshot()
        result = self.submit(curriculum_contract='forged', criterion_report='forged', task='forged', score=10)
        self.assertEqual(result.status_code, 200, result.json)
        sent = self.service.client.responses.create.call_args.kwargs
        payload = json.loads(sent['input'][1]['content'])
        self.assertEqual(payload['curriculum_contract'], self.frozen)
        self.assertEqual(payload['russian_answer'], RESPONSE)
        self.assertNotIn('curriculum', payload)
        self.assertTrue(sent['text']['format']['strict'])
        properties = sent['text']['format']['schema']['properties']
        self.assertFalse(properties['criterion_report']['additionalProperties'])
        current = self.repo.load(self.exercise_id)
        self.assertEqual(current['draft'], RESPONSE)
        self.assertEqual(current['attempts'][0]['criterion_report'], report(self.frozen))
        self.assertEqual(current['attempts'][0]['criterion_support'], [])
        html = result.json['feedback']
        self.assertIn('What this response shows', html)
        self.assertIn('Where something is', html)
        self.assertIn(ADVICE['strength'], html)
        self.assertNotIn('a1.language.', html)
        self.assertNotIn('writing-diagnostic.', html)
        after = self.snapshot()
        self.assertEqual(after['course_target_observations'], before['course_target_observations'])
        self.assertEqual(after['course_chapter_passes'], before['course_chapter_passes'])

    def test_insufficient_evidence_is_null_not_a_zero_or_pass(self):
        answer = 'Я в школе.'
        self.output({**ADVICE, 'criterion_report': report(self.frozen, answer, insufficient=True)})
        result = self.submit(response=answer)
        self.assertEqual(result.status_code, 200, result.json)
        judgement = self.repo.load(self.exercise_id)['attempts'][0]['criterion_report']['judgements'][1]
        self.assertIsNone(judgement['score'])
        self.assertEqual(judgement['outcome'], 'insufficient_evidence')
        self.assertIn('Not enough evidence', result.json['feedback'])

    def test_invalid_reports_save_no_draft_score_evidence_or_rewards(self):
        self.repo.save(self.exercise_id, 'Earlier saved draft.', 0)
        before = self.snapshot()
        invalid = []
        wrong_quote = report(self.frozen)
        wrong_quote['judgements'][0]['evidence'][0]['quote'] = 'в школу'
        invalid.append(wrong_quote)
        wrong_offset = report(self.frozen)
        wrong_offset['judgements'][0]['evidence'][0]['start'] = True
        invalid.append(wrong_offset)
        wrong_hash = report(self.frozen)
        wrong_hash['contract_sha256'] = '0' * 64
        invalid.append(wrong_hash)
        duplicate = report(self.frozen)
        duplicate['judgements'][1]['criterion_id'] = 'location'
        invalid.append(duplicate)
        wrong_score = report(self.frozen)
        wrong_score['judgements'][0]['score'] = 1
        invalid.append(wrong_score)
        invented = report(self.frozen)
        invented['mastery'] = True
        invalid.append(invented)
        invalid.append(None)
        for value in invalid:
            with self.subTest(report=value):
                assessment = {**ADVICE, 'criterion_report': value} if value is not None else dict(ADVICE)
                self.output(assessment)
                self.assertEqual(self.submit(revision=1).status_code, 503)
                self.assertEqual(self.snapshot(), before)

    def test_provider_repairs_only_unique_verbatim_offsets_before_saving(self):
        original = report(self.frozen)
        incorrect = deepcopy(original)
        incorrect['judgements'][0]['evidence'][0]['start'] += 1
        before = self.snapshot()
        # Persistence itself must still reject wrong evidence. Only the
        # provider adapter grounds a unique literal quotation first.
        with self.assertRaises(ValueError):
            self.repo.save(self.exercise_id, RESPONSE, 0, {**ADVICE, 'criterion_report': incorrect})
        self.assertEqual(self.snapshot(), before)
        self.output({**ADVICE, 'criterion_report': incorrect})
        result = self.submit()
        self.assertEqual(result.status_code, 200, result.json)
        saved = self.repo.load(self.exercise_id)
        self.assertEqual(saved['draft'], RESPONSE)
        self.assertEqual(saved['attempts'][0]['criterion_report'], original)

    def test_repository_revalidates_report_and_report_write_failure_rolls_back(self):
        broken = report(self.frozen)
        broken['judgements'][0]['evidence'][0]['quote'] = 'Invented quote'
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.repo.save(self.exercise_id, RESPONSE, 0, {**ADVICE, 'criterion_report': broken})
        self.assertEqual(self.snapshot(), before)
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TRIGGER fail_criterion_report BEFORE INSERT ON activity_criterion_reports BEGIN SELECT RAISE(ABORT,'test failure'); END")
        self.assertEqual(self.submit().status_code, 503)
        self.assertEqual(self.snapshot(), before)

    def test_later_checks_keep_history_and_record_prior_example_support(self):
        self.assertEqual(self.submit().status_code, 200)
        first = self.repo.load(self.exercise_id)['attempts'][0]
        self.assertEqual(self.submit(revision=1).status_code, 200)
        attempts = self.repo.load(self.exercise_id)['attempts']
        self.assertEqual(attempts[1], first)
        self.assertEqual(attempts[0]['criterion_support'], ['model_answer'])
        self.assertNotEqual(attempts[0]['id'], attempts[1]['id'])

    def test_stale_revision_is_rechecked_after_provider_before_any_report_write(self):
        self.repo.save(self.exercise_id, 'First draft.', 0)
        self.assertEqual(self.submit(revision=0).status_code, 409)
        self.service.client.responses.create.assert_not_called()
        def racing_review(**kwargs):
            self.repo.save(self.exercise_id, 'Newer tab draft.', 1)
            return SimpleNamespace(status='completed', output_text=json.dumps({**ADVICE, 'criterion_report': report(self.frozen)}))
        self.service.client.responses.create.side_effect = racing_review
        self.assertEqual(self.submit(revision=1).status_code, 409)
        current = self.repo.load(self.exercise_id)
        self.assertEqual((current['draft'], current['revision'], current['attempts']), ('Newer tab draft.', 2, []))
        self.assertEqual(self.snapshot()['activity_criterion_reports'], [])

    def test_foreign_profile_cannot_read_or_check_contract(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',1)")
        select_test_profile(self.client, 'other')
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']
        self.assertEqual(self.client.get(f'/writing/load/{self.exercise_id}').status_code, 404)
        self.assertEqual(self.submit().status_code, 404)
        self.service.client.responses.create.assert_not_called()
        self.assertEqual(self.snapshot()['activity_criterion_reports'], [])

    def test_ordinary_tasks_remain_uncontracted_and_cannot_acquire_report_on_check(self):
        ordinary = self.repo.create(TASK, 'home', 'A1', 30)
        self.assertIsNone(self.repo.load(ordinary)['curriculum_contract'])
        self.output(ADVICE)
        assessed = self.service.assess_writing(TASK['task'], TASK['required_words'], 30, RESPONSE, 'A1', topic='home')
        self.repo.save(ordinary, RESPONSE, 0, assessed)
        payload = json.loads(self.service.client.responses.create.call_args.kwargs['input'][1]['content'])
        self.assertNotIn('curriculum_contract', payload)
        self.assertIn('curriculum', payload)
        self.assertNotIn('criterion_report', self.repo.load(ordinary)['attempts'][0])
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.repo.save(ordinary, RESPONSE, 1, {**ADVICE, 'criterion_report': report(self.frozen)})
        self.assertEqual(self.snapshot(), before)

    def test_contract_requiring_audio_is_rejected_before_provider(self):
        spec = {key: deepcopy(value) for key, value in self.frozen.items()
                if key not in ('contract_sha256', 'content_sha256')}
        reference = requirement_index()['a1.speaking.ask-and-answer']
        spec['criteria'][0].update(requirement_id=reference['id'], response_mode='independent_speaking',
                                   evidence_scope='reference', source_refs=reference['source_refs'])
        bad = freeze_task_contract(spec)
        with self.assertRaises(ValueError):
            self.service.assess_writing(TASK['task'], TASK['required_words'], 30, RESPONSE, 'A1', curriculum_contract=bad)
        self.service.client.responses.create.assert_not_called()

    def test_generator_cannot_publish_a_model_supplied_contract(self):
        self.output({**generated_task(), 'curriculum_contract': self.frozen})
        before = self.snapshot()
        with self.assertRaises(WritingUnavailable):
            self.service.generate_writing_task('family', 'A1', 30)
        self.assertEqual(self.snapshot(), before)

    def test_generated_free_writing_freezes_focus_before_saving_and_assessing(self):
        self.output(generated_task())
        task = self.service.generate_writing_task('any', 'A1', 30)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.repo.create({**task, 'task_en': 'Different hidden demands.'}, 'any', 'A1', 30)
        with self.assertRaises(ValueError):
            self.repo.create(task, 'home', 'A1', 30)
        self.assertEqual(self.snapshot(), before)
        self.exercise_id = self.repo.create(task, 'any', 'A1', 30)
        loaded = self.repo.load(self.exercise_id)
        self.assertEqual(loaded['topic'], 'any')
        frozen = loaded['curriculum_contract']
        self.assertEqual(frozen['content']['topic_id'], 'family')
        answer = 'Привет! Я живу с мамой. Мы живём вместе.'
        judgement = {'contract_sha256': frozen['contract_sha256'], 'judgements': [{
            'criterion_id': frozen['criteria'][0]['id'], 'outcome': 'satisfied', 'score': 2,
            'feedback': 'Your friend can understand who you live with.',
            'evidence': [{'quote': answer, 'start': 0, 'end': len(answer)}]}]}
        self.output({**ADVICE, 'criterion_report': judgement})
        result = self.submit(response=answer)
        self.assertEqual(result.status_code, 200, result.json)
        payload = json.loads(self.service.client.responses.create.call_args.kwargs['input'][1]['content'])
        self.assertEqual(payload['curriculum_contract'], frozen)
        checked = self.repo.load(self.exercise_id)
        self.assertEqual(checked['attempts'][0]['criterion_report'], judgement)
        self.assertIn('What this response shows', result.json['feedback'])
        self.assertIn(ADVICE['strength'], result.json['feedback'])


if __name__ == '__main__':
    unittest.main()
