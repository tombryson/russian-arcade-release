"""Scene facts, component grading, owned snapshots and correction flows."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import unittest
from tests.game_fixtures import grant_earned_game_access
from unittest.mock import patch

from repositories.learning_repository import LearningError, identifier, transaction
from services.journey_games import assess_answer, normalise_answer
from services.scene_builder import FAMILIES, build_content, curriculum, item, options, slot
from tests.support import select_test_profile
from tests import test_journey_games as existing


class SceneContentTests(unittest.TestCase):
    def test_each_focus_has_ten_distinct_complete_rounds_and_frozen_choices(self):
        all_rounds=curriculum()
        self.assertGreaterEqual(len(all_rounds),50)
        self.assertEqual(len({r['id'] for r in all_rounds}),len(all_rounds))
        for focus in (*FAMILIES,'mixed'):
            pack=build_content('seed',options({'grammar_focus':focus,'rounds':10}))
            self.assertEqual(len(pack['rounds']),10)
            self.assertEqual(len({r['id'] for r in pack['rounds']}),10)
            self.assertEqual(build_content('seed',options({'grammar_focus':focus,'rounds':10})),pack)
            for row in pack['rounds']:
                scene=row['scene_builder']
                self.assertEqual(len(scene['segments']),len(scene['slots'])+1)
                self.assertEqual(normalise_answer(row,row['expected_answer'],'scene-builder'),row['expected_answer'])
                self.assertTrue(assess_answer(row,row['expected_answer'])['correct'])
                self.assertEqual(row['answer_audio'][0]['audio_key'],hashlib.sha256(row['correct_sentence'].encode()).hexdigest())
                self.assertTrue(row['hint_ru'])
        mixed=build_content('seed',options({'grammar_focus':'mixed','rounds':10}))
        self.assertEqual({family:sum(r['scene_builder']['family']==family for r in mixed['rounds']) for family in FAMILIES},dict.fromkeys(FAMILIES,2))

    def test_case_and_preposition_are_graded_independently(self):
        row=next(r for r in curriculum() if r['id']=='position-under')
        result=assess_answer(row,['preposition:under','noun:prepositional'])
        self.assertEqual((result['score'],result['matched'],result['total']),(.5,1,2))
        result=assess_answer(row,['preposition:on','noun:instrumental'])
        self.assertEqual(result['score'],.5)
        for answer in (['preposition:under'],['noun:instrumental','preposition:under'],['preposition:invented','noun:instrumental']):
            with self.assertRaises(LearningError):
                normalise_answer(row,answer,'scene-builder')

    def test_options_reject_foreign_sources_and_invalid_counts(self):
        for value in ({'grammar_focus':'invented'},{'rounds':True},{'rounds':100},{'source':'vocabulary'},{'rounds':'5'}):
            with self.assertRaises(LearningError):
                options(value)

    def test_motion_options_default_to_a1_and_accept_only_supported_levels(self):
        for focus in ('motion','mixed'):
            self.assertEqual(options({'grammar_focus':focus}),options({'grammar_focus':focus,'motion_level':'A1'}))
            for level in ('A1','A2','B1'):
                self.assertEqual(options({'grammar_focus':focus,'motion_level':level})['motion_level'],level)
            for level in ('B2','a1','',None,True,1,[],{}):
                with self.subTest(focus=focus,level=level),self.assertRaises(LearningError):
                    options({'grammar_focus':focus,'motion_level':level})
        for focus in FAMILIES:
            if focus!='motion':
                self.assertNotIn('motion_level',options({'grammar_focus':focus}))
                with self.assertRaises(LearningError):
                    options({'grammar_focus':focus,'motion_level':'A1'})

    def test_motion_levels_have_distinct_material_and_plausible_complete_choices(self):
        motion=[row for row in curriculum() if row['scene_builder']['family']=='motion']
        self.assertEqual({row['scene_builder']['level'] for row in motion},{'A1','A2','B1'})
        for level in ('A1','A2','B1'):
            rows=[row for row in motion if row['scene_builder']['level']==level]
            with self.subTest(level=level):
                self.assertGreaterEqual(len({row['id'] for row in rows}),10)
                self.assertGreaterEqual(len({row['correct_sentence'] for row in rows}),10)
                for row in rows:
                    scene=row['scene_builder']
                    self.assertTrue(scene['skill'])
                    self.assertIsInstance(scene['motion_visual'],dict)
                    self.assertTrue(scene['motion_visual'])
                    for part in scene['slots']:
                        choices=part['choices']
                        self.assertGreaterEqual(len(choices),2)
                        self.assertLessEqual(len(choices),6)
                        self.assertEqual(len({choice['id'] for choice in choices}),len(choices))
                        self.assertEqual(len({choice['text'] for choice in choices}),len(choices))
                    self.assertEqual(len(scene['segments']),len(scene['slots'])+1)
                    self.assertEqual(len(row['slot_explanations']),len(scene['slots']))
                    self.assertEqual(len(row['vocabulary_refs']),len(scene['slots']))
                    self.assertTrue(scene['scenario'])
                    self.assertTrue(scene['scenario_ru'])
                    self.assertTrue(row['hint_ru'])
                    self.assertEqual(normalise_answer(row,row['expected_answer'],'scene-builder'),row['expected_answer'])
                    self.assertTrue(assess_answer(row,row['expected_answer'])['correct'])
                if level=='B1':
                    self.assertTrue(any(len(row['scene_builder']['slots'])==2 for row in rows))

    def test_motion_pack_selection_is_level_filtered_diverse_and_repeatable(self):
        for level in ('A1','A2','B1'):
            eligible=[row for row in curriculum()
                if row['scene_builder']['family']=='motion' and row['scene_builder']['level']==level]
            available_skills=Counter(row['scene_builder']['skill'] for row in eligible)
            for seed in ('seed','another-seed','third-seed'):
                for count in (5,10):
                    settings=options({'grammar_focus':'motion','motion_level':level,'rounds':count})
                    pack=build_content(seed,settings)
                    with self.subTest(level=level,seed=seed,count=count):
                        self.assertEqual(pack,build_content(seed,settings))
                        self.assertEqual(len({row['id'] for row in pack['rounds']}),count)
                        self.assertEqual({row['scene_builder']['family'] for row in pack['rounds']},{'motion'})
                        self.assertEqual({row['scene_builder']['level'] for row in pack['rounds']},{level})
                        self.assertEqual(pack['version'],'scene-builder-v3')
                        self.assertEqual(pack['lesson_version'],'scene-builder-v1:motion')
                        self.assertEqual(
                            {(ref['lemma'],ref['form'],ref['sentence']) for ref in pack['vocabulary_refs']},
                            {(ref['lemma'],ref['form'],ref['sentence']) for row in pack['rounds'] for ref in row['vocabulary_refs']})
                        skills=Counter(row['scene_builder']['skill'] for row in pack['rounds'])
                        self.assertEqual(len(skills),min(count,len(available_skills)))
                        for skill,selected in skills.items():
                            if selected<available_skills[skill]:
                                self.assertLessEqual(max(skills.values())-selected,1)
                            available_answers={tuple(row['expected_answer']) for row in eligible if row['scene_builder']['skill']==skill}
                            selected_answers={tuple(row['expected_answer']) for row in pack['rounds'] if row['scene_builder']['skill']==skill}
                            self.assertEqual(len(selected_answers),min(selected,len(available_answers)))
            mixed=build_content('seed',options({'grammar_focus':'mixed','motion_level':level,'rounds':10}))
            self.assertEqual(Counter(row['scene_builder']['family'] for row in mixed['rounds']),dict.fromkeys(FAMILIES,2))
            self.assertEqual({row['scene_builder']['level'] for row in mixed['rounds'] if row['scene_builder']['family']=='motion'},{level})
            self.assertEqual(mixed['lesson_version'],'scene-builder-v1:mixed')

    def test_a1_teaches_core_pairs_across_tenses_and_simple_setting_off(self):
        rows=[row for row in curriculum() if row['scene_builder'].get('level')=='A1']
        targets=[target for row in rows for target in row['vocabulary_refs']]
        for lemma in ('идти','ходить','ехать','ездить'):
            with self.subTest(lemma=lemma):
                forms=[target for target in targets if target['lemma']==lemma]
                self.assertTrue({'pres','past'}.issubset({target['grammar'].get('tense') for target in forms}))
                future=[row for row in rows if 'будет '+lemma in row['correct_sentence']]
                self.assertTrue(future,'A1 must teach the analytical future of '+lemma)
                for row in future:
                    target=next(target for target in row['vocabulary_refs'] if target['lemma']==lemma)
                    self.assertEqual(target['form'],lemma)
                    self.assertEqual(target['pos'],'INFN')
                    self.assertEqual(target['grammar'].get('aspect'),'impf')
                    self.assertTrue({'tense','person','number'}.isdisjoint(target['grammar']))
                    self.assertEqual(target['construction'],{
                        'text':'будет '+lemma,'tense':'futr','person':'3per','number':'sing'})
        self.assertTrue({'пойти','поехать'}.issubset({target['lemma'] for target in targets}))
        present_choices=[{choice['text'] for choice in part['choices']}
                         for row in rows for part in row['scene_builder']['slots']]
        self.assertIn({'идёт','ходит'},present_choices)
        self.assertIn({'едет','ездит'},present_choices)

    def test_a2_teaches_prefix_aspect_and_extended_motion_pairs_as_answers(self):
        rows=[row for row in curriculum() if row['scene_builder'].get('level')=='A2']
        targets=[target for row in rows for target in row['vocabulary_refs']]
        for imperfective,perfective in (('входить','войти'),('приходить','прийти'),('уходить','уйти')):
            with self.subTest(pair=(imperfective,perfective)):
                self.assertTrue(any(target['lemma']==imperfective and target['grammar'].get('aspect')=='impf' for target in targets))
                self.assertTrue(any(target['lemma']==perfective and target['grammar'].get('aspect')=='perf' for target in targets))
        extended={'нести','носить','вести','водить','везти','возить'}
        self.assertTrue(extended.issubset({target['lemma'] for target in targets}))
        for row in rows:
            for target in row['vocabulary_refs']:
                if target.get('construction'):
                    self.assertEqual(target['pos'],'INFN')
                    self.assertEqual(target['construction']['tense'],'futr')
                    self.assertIn(target['construction']['text'],row['correct_sentence'])
                    self.assertNotIn('tense',target['grammar'])
        for row in curriculum():
            if row['scene_builder'].get('level')=='B1' and any(target['lemma'] in extended for target in row['vocabulary_refs']):
                self.assertGreater(len(row['scene_builder']['slots']),1,'B1 carrying should combine actions, not relabel an A2 introduction.')

    def test_motion_captions_and_visuals_establish_the_tested_contrasts(self):
        motion=[row for row in curriculum() if row['scene_builder']['family']=='motion']
        rows={row['id']:row for row in motion}
        for row in motion:
            scene=row['scene_builder']
            if scene['skill']=='routine':
                self.assertIn('и обратно',row['correct_sentence'])
                self.assertEqual(scene['motion_visual']['stage'],'habit')
                self.assertEqual({choice['text'] for choice in scene['slots'][0]['choices']},{'ходит','ездит'})
            elif scene['skill']=='now':
                self.assertEqual(scene['motion_visual']['stage'],'journey')
                self.assertEqual({choice['text'] for choice in scene['slots'][0]['choices']},{'идёт','едет'})
        arrival={choice['text'] for choice in rows['motion-clinic-arrival']['scene_builder']['slots'][0]['choices']}
        boundary={choice['text'] for choice in rows['motion-pharmacy-enter']['scene_builder']['slots'][0]['choices']}
        self.assertTrue(arrival.isdisjoint(boundary))
        for identity,detail,mode in (('parcel-hands','in her hands','carrying'),
                                     ('parcel-vehicle','back of his vehicle','transport'),
                                     ('child-walking','holding his hand','leading')):
            scene=rows['motion-'+identity]['scene_builder']
            self.assertIn(detail,scene['scenario'])
            self.assertEqual(scene['motion_visual']['mode'],mode)

    def test_motion_second_slot_scores_independently_and_rejects_other_levels_choices(self):
        rows=curriculum()
        challenge=next(row for row in rows if row['scene_builder']['family']=='motion' and len(row['scene_builder']['slots'])==2)
        for position in range(2):
            wrong=list(challenge['expected_answer'])
            wrong[position]=next(choice['id'] for choice in challenge['scene_builder']['slots'][position]['choices'] if choice['id']!=wrong[position])
            result=assess_answer(challenge,normalise_answer(challenge,wrong,'scene-builder'))
            self.assertEqual((result['correct'],result['score'],result['matched'],result['total']),(False,.5,1,2))
        foundation=next(row for row in rows if row['scene_builder']['family']=='motion' and row['scene_builder']['level']=='A1')
        foundation_choices={choice['id'] for choice in foundation['scene_builder']['slots'][0]['choices']}
        advanced_choice=next(choice['id'] for row in rows if row['scene_builder']['family']=='motion'
            for choice in row['scene_builder']['slots'][0]['choices'] if choice['id'] not in foundation_choices)
        with self.assertRaises(LearningError):
            normalise_answer(foundation,[advanced_choice],'scene-builder')


class SceneGameTests(unittest.TestCase):
    setUp=existing.JourneyGamesTests.setUp
    token=existing.JourneyGamesTests.token
    request=existing.JourneyGamesTests.request
    seed_lesson=existing.JourneyGamesTests.seed_lesson
    expected=existing.JourneyGamesTests.expected
    post=existing.JourneyGamesTests.post
    read=existing.JourneyGamesTests.read
    finish=existing.JourneyGamesTests.finish

    def start_scene(self,focus='location',request_id=None,*,motion_level=None,rounds=5,**kwargs):
        select_test_profile(self.client)
        settings={'grammar_focus':focus,'rounds':rounds}
        if motion_level is not None:
            settings['motion_level']=motion_level
        return self.request('/api/v1/games/scene-builder/start',{'request_id':request_id or identifier(),
            'options':settings,**kwargs})

    def saved_content(self,session_id):
        with transaction(self.db) as conn:
            return conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?',(session_id,)).fetchone()[0]

    def legacy_motion_session(self,version='scene-builder-v1'):
        """Freeze an old bank independently of future curriculum revisions."""
        state=self.start_scene('motion',request_id='legacy-motion-start-'+version)
        content=json.loads(self.saved_content(state['id']))
        verbs=slot('verb','Verb of motion','Глагол движения',[
            ('walk-now','идёт'),('walk-usual','ходит'),('ride-now','едет'),('ride-usual','ездит')])
        old_round=item('motion-ride-now','motion','taxi-moving',
            'John is in a moving taxi, halfway to the café right now.','Джон сейчас в такси на пути в кафе.',
            ['Джон сейчас ', ' в кафе на такси.'],[verbs],['ride-now'],
            'John is going to the café by taxi now.',
            [('Use «едет» for one journey by transport happening now.','«Едет» — одно направленное движение на транспорте сейчас.')],
            'Check how he travels and when it happens.','Учитывайте способ движения и время.')
        settings={'grammar_focus':'motion','rounds':5,'word_policy':'mixed-v1'}
        if version=='scene-builder-v2':
            old_round['scene_builder'].update(level='A2',skill='legacy-taxi')
            settings['motion_level']='A2'
        content.update(version=version,lesson_version='scene-builder-v1:motion',
            options=settings,
            rounds=[dict(deepcopy(old_round),id=f'legacy-motion-{index}') for index in range(5)],vocabulary_refs=[])
        saved=json.dumps(content,ensure_ascii=False)
        with transaction(self.db,write=True) as conn:
            conn.execute('UPDATE journey_game_sessions SET content_json=? WHERE id=?',(saved,state['id']))
        return self.read(state['id']),saved

    def test_starts_without_provider_or_vocabulary_and_hides_answer_until_check(self):
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        with patch('services.journey_vocabulary.select_examples',side_effect=AssertionError('must not sample vocabulary')):
            state=self.start_scene()
        self.assertEqual(state['phase'],'play')
        row=self.expected(state['id'])[0]
        for secret in ('expected_answer','answer_audio','correct_sentence','translation','slot_explanations','vocabulary'):
            self.assertNotIn(secret,state['round'])
        key=row['answer_audio'][0]['audio_key']
        self.assertEqual(self.client.get('/api/v1/games/media/'+key+'/status').status_code,404)
        checked=self.post(state['id'],'answer',{'round_id':row['id'],'answer':row['expected_answer']})
        self.assertEqual(checked['result']['correct_sentence'],row['correct_sentence'])
        self.assertTrue(all(slot['correct'] for slot in checked['result']['slot_results']))
        self.assertEqual(self.client.get('/api/v1/games/media/'+key+'/status').status_code,200)
        other=self.app.test_client()
        self.assertEqual(other.get('/api/v1/games/sessions/'+state['id']).status_code,404)

    def test_resume_idempotency_and_new_focus_preserve_prior_snapshot(self):
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        first=self.start_scene(request_id='scene-request-1')
        self.assertEqual(self.start_scene(request_id='scene-request-2')['id'],first['id'])
        second=self.start_scene('motion')
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(self.start_scene(request_id='scene-request-1')['id'],first['id'])
        self.assertEqual(self.read(first['id'])['round'],first['round'])
        self.request('/api/v1/games/scene-builder/start',{'request_id':'scene-request-1','options':{'grammar_focus':'roles'}},status=409)

    def test_level_changes_create_owned_snapshots_and_replays_do_not_rebuild(self):
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        first=self.start_scene('motion',request_id='motion-a1-start')
        first_saved=self.saved_content(first['id'])
        second=self.start_scene('motion',request_id='motion-b1-start',motion_level='B1')
        second_saved=self.saved_content(second['id'])
        self.assertNotEqual(first['id'],second['id'])
        for state,level in ((first,'A1'),(second,'B1')):
            content=json.loads(self.saved_content(state['id']))
            self.assertEqual(content['options']['motion_level'],level)
            self.assertEqual({row['scene_builder']['level'] for row in content['rounds']},{level})
            self.assertEqual(state['round']['scene_builder']['level'],level)
        with patch('services.scene_builder.build_content',side_effect=AssertionError('saved sessions must not rebuild')):
            self.assertEqual(self.start_scene('motion',request_id='motion-a1-start',motion_level='A1')['id'],first['id'])
            self.assertEqual(self.start_scene('motion',request_id='motion-b1-resume',motion_level='B1')['id'],second['id'])
            self.assertEqual(self.read(first['id'])['round'],first['round'])
            self.request('/api/v1/games/scene-builder/start',{
                'request_id':'motion-a1-start','options':{'grammar_focus':'motion','rounds':5,'motion_level':'B1'}},status=409)
        self.assertEqual(self.saved_content(first['id']),first_saved)
        self.assertEqual(self.saved_content(second['id']),second_saved)

    def test_legacy_motion_snapshot_resumes_and_grades_without_bank_rewriting(self):
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        legacy,saved=self.legacy_motion_session()
        self.assertNotIn('level',legacy['round']['scene_builder'])
        self.assertEqual(len(legacy['round']['scene_builder']['slots'][0]['choices']),4)
        with patch('services.scene_builder.build_content',side_effect=AssertionError('legacy snapshot must not rebuild')):
            self.assertEqual(self.start_scene('motion',request_id='legacy-motion-start-scene-builder-v1')['id'],legacy['id'])
            self.request('/api/v1/games/scene-builder/start',{
                'request_id':'legacy-motion-start-scene-builder-v1','options':{'grammar_focus':'motion','rounds':5,'motion_level':'A1'}},status=409)
            row=json.loads(saved)['rounds'][0]
            checked=self.post(legacy['id'],'answer',{'round_id':row['id'],'answer':row['expected_answer']})
            self.assertTrue(checked['result']['correct'])
            self.assertEqual(checked['result']['correct_sentence'],row['correct_sentence'])
        current=self.start_scene('motion')
        self.assertNotEqual(current['id'],legacy['id'])
        self.assertEqual(current['round']['scene_builder']['level'],'A1')
        self.assertEqual(json.loads(self.saved_content(current['id']))['version'],'scene-builder-v3')
        self.start_scene('motion',motion_level='A2')
        self.assertEqual(self.start_scene('motion',request_id='legacy-motion-start-scene-builder-v1')['id'],legacy['id'])
        self.assertEqual(self.read(legacy['id'])['result']['correct_sentence'],row['correct_sentence'])
        self.assertEqual(self.saved_content(legacy['id']),saved)

    def test_v2_snapshot_keeps_choices_replay_and_answer_audio_after_v3_starts(self):
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        legacy,saved=self.legacy_motion_session('scene-builder-v2')
        row=json.loads(saved)['rounds'][0]
        audio_url='/api/v1/games/media/'+row['answer_audio'][0]['audio_key']+'/status'
        self.assertEqual(self.client.get(audio_url).status_code,404)
        current=self.start_scene('motion',motion_level='A2')
        self.assertNotEqual(current['id'],legacy['id'])
        self.assertEqual(json.loads(self.saved_content(current['id']))['version'],'scene-builder-v3')
        with patch('services.scene_builder.build_content',side_effect=AssertionError('v2 snapshot must not rebuild')):
            replay=self.start_scene('motion',request_id='legacy-motion-start-scene-builder-v2',motion_level='A2')
            self.assertEqual(replay['id'],legacy['id'])
            self.assertEqual(replay['round'],legacy['round'])
            self.request('/api/v1/games/scene-builder/start',{
                'request_id':'legacy-motion-start-scene-builder-v2',
                'options':{'grammar_focus':'motion','rounds':5,'motion_level':'A1'}},status=409)
            checked=self.post(legacy['id'],'answer',{'round_id':row['id'],'answer':row['expected_answer']})
            self.assertTrue(checked['result']['correct'])
            self.assertEqual(checked['result']['correct_sentence'],row['correct_sentence'])
        self.assertEqual(self.client.get(audio_url).status_code,200)
        self.assertEqual(self.saved_content(legacy['id']),saved)

    def test_motion_level_cannot_mint_another_reward_for_the_same_focus(self):
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        legacy,_=self.legacy_motion_session()
        finished=[self.finish(legacy)]
        old_v2,_=self.legacy_motion_session('scene-builder-v2')
        finished.append(self.finish(old_v2))
        for level in ('A1','A2','B1'):
            finished.append(self.finish(self.start_scene('motion',motion_level=level)))
        self.assertEqual([state['reward']['amount'] for state in finished],[3,0,0,0,0])
        self.assertTrue(all(state['reward']['reason']=='already_rewarded' for state in finished[1:]))
        self.assertEqual(len({state['id'] for state in finished}),5)
        with transaction(self.db) as conn:
            events=conn.execute("SELECT content_key,target_level FROM progression_events WHERE activity='journey_game'").fetchall()
            self.assertEqual(len(events),5)
            self.assertEqual({row['content_key'] for row in events},{'journey-game:scene-builder:scene-builder-v1:motion'})
            self.assertTrue(all(row['target_level'] is None for row in events))

    def test_server_rejects_invalid_motion_levels_without_creating_a_session(self):
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        select_test_profile(self.client)
        for level in ('B2','a1','',None,True,1,[],{}):
            with self.subTest(level=level):
                self.request('/api/v1/games/scene-builder/start',{'request_id':identifier(),
                    'options':{'grammar_focus':'motion','motion_level':level}},status=400)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM journey_game_sessions WHERE game_id='scene-builder'").fetchone()[0],0)

    def test_server_filters_mixed_motion_rounds_and_keeps_answers_private(self):
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        secrets={'expected_answer','answer_audio','correct_sentence','translation','slot_explanations','vocabulary','vocabulary_refs','feedback'}
        for level in ('A1','A2','B1'):
            with self.subTest(level=level):
                state=self.start_scene('mixed',motion_level=level,rounds=10)
                for row in self.expected(state['id']):
                    public=self.read(state['id'])['round']
                    self.assertTrue(secrets.isdisjoint(public))
                    self.assertTrue(secrets.isdisjoint(public['scene_builder']))
                    if row['scene_builder']['family']=='motion':
                        self.assertEqual(row['scene_builder']['level'],level)
                        self.assertEqual(public['scene_builder']['level'],level)
                        self.assertTrue(public['scene_builder']['motion_visual'])
                    self.post(state['id'],'answer',{'round_id':row['id'],'answer':row['expected_answer']})
                    self.post(state['id'],'continue',{'round_id':row['id']})

    def test_hint_retry_review_and_reward_keep_the_first_attempt(self):
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        state=self.start_scene()
        sid=state['id']
        rounds=self.expected(sid)
        row=rounds[0]
        wrong=list(row['expected_answer'])
        wrong[-1]=next(c['id'] for c in row['scene_builder']['slots'][-1]['choices'] if c['id']!=wrong[-1])
        hinted=self.post(sid,'hint',{'round_id':row['id']})
        self.assertEqual(hinted['round']['hint_ru'],row['hint_ru'])
        checked=self.post(sid,'answer',{'round_id':row['id'],'answer':wrong})
        self.assertEqual([r['correct'] for r in checked['result']['slot_results']],[True,False])
        retry=self.post(sid,'retry',{'round_id':row['id']})
        self.assertIsNone(retry['result'])
        self.post(sid,'practice_answer',{'round_id':row['id'],'answer':row['expected_answer'],'request_id':'scene-correction-1'})
        self.post(sid,'practice_continue',{'round_id':row['id']})
        for row in rounds[1:]:
            self.post(sid,'answer',{'round_id':row['id'],'answer':row['expected_answer']})
            self.post(sid,'continue',{'round_id':row['id']})
        done=self.post(sid,'complete')
        self.assertEqual(done['summary']['missed_rounds'],1)
        self.assertEqual(done['reward']['amount'],3)
        self.assertTrue(done['study_available'])
        self.assertTrue(done['words'])
        self.assertEqual(self.post(sid,'complete')['reward']['amount'],3)
        self.assertEqual(self.post(sid,'review')['practice']['total'],1)
        with transaction(self.db) as conn:
            saved=conn.execute('SELECT answers_json FROM journey_game_sessions WHERE id=?',(sid,)).fetchone()[0]
            self.assertEqual(json.loads(saved)[rounds[0]['id']]['answer'],wrong)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='journey_game' AND source_key=?",(sid,)).fetchone()[0],1)

    def test_catalogue_replaces_pairs_without_breaking_legacy_urls(self):
        select_test_profile(self.client)
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        games=self.client.get('/api/v1/games').json['games']
        self.assertNotIn('pairs',{g['id'] for g in games})
        self.assertTrue(next(g for g in games if g['id']=='scene-builder')['unlocked'])
        legacy=self.request('/api/v1/games/pairs/start',{'request_id':'legacy-pairs-start','options':{'source':'first_steps'}})
        self.assertEqual(legacy['round']['mechanic'],'pairs')
        self.assertEqual(self.read(legacy['id'])['id'],legacy['id'])

    def test_authored_card_targets_resolve_to_the_lemma_and_exact_case(self):
        from services.first_steps_practice import _game_word
        with self.app.app_context(), transaction(self.db,write=True) as conn:
            for row in curriculum():
                for target in row.get('vocabulary_refs',[row['vocabulary']]):
                    with self.subTest(round=row['id'],form=target['form']):
                        word=_game_word(conn,target)
                        self.assertEqual(word['lemma'],target['lemma'])
                        self.assertEqual(word['form'],target['form'])
                        for key,value in target['grammar'].items():
                            self.assertEqual(word['tags'][key],value)
                        self.assertIn(target['form'].lower(),row['correct_sentence'].lower())


if __name__=='__main__':
    unittest.main()
