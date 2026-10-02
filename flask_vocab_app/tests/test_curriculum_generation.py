"""Generated situations retain deterministic marking, ownership and originals."""
import json
import sqlite3
import unittest
from unittest.mock import patch
from contracts.learning import activity_answer_text
from services.curriculum_generation import BUILDERS, build, inflect
from services.activity_evidence import validate_saved_evidence
from tests.support import isolated_app


class GrammarRulesTests(unittest.TestCase):
    def test_all_rules_produce_distinct_repeatable_valid_forms(self):
        for unit in BUILDERS:
            ids = set()
            for seed in ('one', 'two', 'three', 'four', 'five'):
                with self.subTest(unit=unit, seed=seed):
                    pack, _, questions = build(unit, seed)
                    self.assertEqual(pack, build(unit, seed)[0])
                    self.assertEqual(len(pack['items']), 6)
                    self.assertEqual(len({q['semantic'] for q in questions}), 6)
                    for q in questions:
                        self.assertEqual(q['sentence'].count('[...]'), 1)
                        self.assertEqual(q['options'].count(q['answer_text']), 1)
                    ids.update(q['semantic'] for q in questions)
            self.assertGreater(len(ids), 6, unit)
        self.assertEqual(inflect('идти', 'pres 1per plur', 'INFN'), 'идём')
        self.assertEqual(inflect('письмо', 'plur gent'), 'писем')
        self.assertEqual(inflect('тетрадь', 'sing ablt'), 'тетрадью')

    def test_renaming_a_character_does_not_erase_answer_exposure(self):
        from services.curriculum_fresh_practice import same_question
        first, _, _ = build('connected-messages-v1', '0')
        second, _, _ = build('connected-messages-v1', '1')
        changed = [(a,b) for a in first['items'] for b in second['items']
                   if a['id']==b['id'] and a['prompt']!=b['prompt']]
        self.assertTrue(changed)
        for a,b in changed:
            self.assertTrue(same_question(first,second,a['id']))

    def test_sets_cover_both_taught_functions(self):
        contrasts = {
            'location-destination-v1': {'location', 'destination'},
            'instrumental-activities-professions-v1': {
                'instrumental-activity', 'instrumental-profession'},
            'connected-messages-v1': {'reason', 'sequence'},
        }
        for unit, rules in contrasts.items():
            for seed in range(100):
                with self.subTest(unit=unit, seed=seed):
                    _, _, questions = build(unit, str(seed))
                    self.assertEqual({q['rule'] for q in questions}, rules)

    def test_personal_reference_does_not_teach_wrong_reflexive_pronouns(self):
        for n in range(10):
            _, _, qs = build('personal-reference-v1', str(n))
            for q in qs:
                if q['answer_text'] in ('меня', 'нас'):
                    self.assertTrue(q['sentence'].startswith('Он '))
                self.assertNotIn('Use the pronoun', q['prompt_ru'])

    def test_case_questions_state_the_intended_meaning(self):
        # These alternatives can form valid Russian sentences with a different
        # meaning: идти в школе, есть книги, даю письмо брата. The task must
        # specify its meaning instead of marking them wrong without context.
        for seed in range(10):
            for unit in ('location-destination-v1', 'possession-absence-v1', 'objects-recipients-v1',
                         'time-routine-v1', 'needs-company-v1', 'origins-and-destinations-v1'):
                _, _, questions = build(unit, str(seed))
                for q in questions:
                    if q['rule'] == 'destination':
                        self.assertIn('journey is heading', q['prompt'])
                        self.assertIn('куда направляются', q['prompt_ru'])
                    elif q['rule'] == 'location':
                        self.assertIn('already located', q['prompt'])
                        self.assertIn('где уже находятся', q['prompt_ru'])
                    elif q['rule'] in ('existence', 'absence', 'object'):
                        self.assertIn('one item', q['prompt'])
                        self.assertIn('одном предмете', q['prompt_ru'])
                    elif q['rule'] == 'recipient':
                        self.assertIn('person receiving', q['prompt'])
                        self.assertIn('получателя', q['prompt_ru'])
                    elif q['rule'] == 'weekday':
                        self.assertIn('single occasion', q['prompt'])
                        self.assertIn('одном дне', q['prompt_ru'])
                    elif q['rule'] == 'company':
                        self.assertIn('one companion', q['prompt'])
                        self.assertIn('одного спутника', q['prompt_ru'])
                    elif q['rule'] == 'origin':
                        self.assertIn('journey started. Refer to one place', q['prompt'])
                        self.assertIn('одно место, откуда', q['prompt_ru'])


class FreshPracticeTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']

    def start(self, key='first', unit='present-actions-v1', stage='practice'):
        response = self.client.post('/curriculum/units/' + unit + '/' + stage,
            data={'profile_id':'personal-learning', 'request_id':key, 'generation':'rules'},
            headers={'X-CSRF-Token':self.token})
        self.assertEqual(response.status_code, 303, response.get_data(as_text=True))
        return self.client.get('/api/v1/learning-sessions/' + response.location.rsplit('/',1)[-1]).json

    def pack(self, saved):
        with sqlite3.connect(self.db) as conn:
            return json.loads(conn.execute('SELECT payload FROM learning_content_versions WHERE id=?', (saved['version_id'],)).fetchone()[0])

    def complete(self, saved):
        pack = self.pack(saved)
        while saved['status'] != 'completed':
            item = next(i for i in pack['items'] if i['id'] == saved['item']['id'])
            answer = {'text':item['answer']} if item['type']=='controlled_text' else {'choice_id':item['answer']}
            result = self.client.post('/api/v1/learning-sessions/' + saved['id'] + '/attempts',
                json={'submission_id':'answer-' + saved['id'] + '-' + str(saved['revision']),
                      'expected_revision':saved['revision'], 'item_id':item['id'], 'answer':answer},
                headers={'X-CSRF-Token':self.token})
            self.assertEqual(result.status_code,200,result.get_data(as_text=True))
            saved=result.json
        return saved

    def test_new_examples_resume_replay_reward_and_frozen_history(self):
        first=self.start()
        pack=self.pack(first)
        self.assertTrue(pack['id'].startswith('curriculum-unit:g1:'))
        self.assertNotIn('answer',first['item'])
        self.assertEqual(self.start('resumed')['id'],first['id'])
        done=self.complete(first)
        self.assertEqual(done['coins_earned'],3)
        self.assertEqual(self.start('resumed')['id'],first['id'])
        second=self.start('new-set')
        other=self.pack(second)
        self.assertNotEqual({i['id'] for i in pack['items']},{i['id'] for i in other['items']})
        self.assertEqual(self.complete(second)['coins_earned'],0)
        typed=self.start('typed',stage='forms')
        self.assertEqual(self.complete(typed)['coins_earned'],0)
        self.assertEqual(self.pack(first),pack)
        with sqlite3.connect(self.db) as conn:
            validate_saved_evidence(conn)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0],0)

    def test_stale_profile_and_csrf_reject_without_allocating(self):
        for body, headers in [({'profile_id':'another','request_id':'bad','generation':'rules'},{'X-CSRF-Token':self.token}),
                             ({'profile_id':'personal-learning','request_id':'bad','generation':'rules'}, {})]:
            result=self.client.post('/curriculum/units/present-actions-v1/practice',data=body,headers=headers)
            self.assertIn(result.status_code,(403,409))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_generated_starts').fetchone()[0],0)

    def test_repeated_exact_questions_keep_prior_feedback_as_support(self):
        from services import curriculum_fresh_practice as fresh
        first=self.start(unit='social-exchanges-v1')
        self.complete(first)
        # Exhaustion must remain honest: a changed seed and option order do not
        # make known answers independent evidence.
        old=self.pack(first)
        old_seed=old['id'].rsplit(':',1)[1]
        def same_questions(conn, profile, unit, stage, request):
            return '', build(unit, old_seed, 'forms')[0]
        with patch.object(fresh,'_select',side_effect=same_questions):
            repeated=self.start('same-questions',unit='social-exchanges-v1',stage='forms')
        done=self.complete(repeated)
        self.assertTrue(all(a['feedback']['assisted'] for a in done['attempts']))
        self.assertTrue(all(a['feedback']['support']==['model_answer'] for a in done['attempts']))
        restored=self.client.get('/api/v1/learning-sessions/'+done['id']).json
        self.assertTrue(all(a['feedback']['support']==['model_answer'] for a in restored['attempts']))
        with sqlite3.connect(self.db) as conn:
            validate_saved_evidence(conn)
            reports=conn.execute('SELECT support_json FROM activity_criterion_reports WHERE source_key IN (SELECT id FROM activity_attempts WHERE session_id=?)',(repeated['id'],)).fetchall()
            self.assertTrue(all(json.loads(r[0])==['model_answer'] for r in reports))

    def test_generated_versions_cannot_be_browsed_or_started_by_another_profile(self):
        from tests.support import select_test_profile
        saved=self.start()
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',1)")
        other=self.app.test_client()
        state=select_test_profile(other,'other')
        self.assertEqual(other.get('/api/v1/learning-sessions/'+saved['id']).status_code,404)
        response=other.post('/api/v1/learning-sessions',json={'profile_id':'other',
            'version_id':saved['version_id'],'submission_id':'foreign-version'},
            headers={'X-CSRF-Token':state['csrf_token']})
        self.assertEqual(response.status_code,404)
        catalogue = other.get('/api/v1/post')
        self.assertEqual(catalogue.status_code,200)
        self.assertNotIn(saved['version_id'],json.dumps(catalogue.json['content']))

    def test_all_units_freeze_criteria_and_refuse_cross_unit_replay(self):
        for unit in BUILDERS:
            for stage in ('practice','forms'):
                with self.subTest(unit=unit, stage=stage):
                    saved = self.start(unit + '-' + stage, unit=unit, stage=stage)
                    self.assertEqual(saved['total_items'],6)
        response = self.client.post('/curriculum/units/personal-reference-v1/practice',
            data={'profile_id':'personal-learning','request_id':'present-actions-v1-practice','generation':'rules'},
            headers={'X-CSRF-Token':self.token})
        self.assertEqual(response.status_code,409)

    def test_russian_current_prompt_and_hint_respect_disclosure(self):
        with self.client.session_transaction() as session:
            session['ui_lang']='ru'
        saved=self.start(unit='personal-reference-v1')
        self.assertNotIn('Use the pronoun',saved['item']['prompt'])
        self.assertNotIn('hint',saved['item'])
