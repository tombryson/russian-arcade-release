"""Real HTTP flows over an isolated database; no provider calls."""
import json
from pathlib import Path
import unittest
from tests.game_fixtures import grant_earned_game_access
from unittest.mock import patch

from repositories.learning_repository import transaction
from services.route_content import build_mission,all_audio,validate_pack,MISSION_IDS
from copy import deepcopy
from services.route_delivery import assess,validate_path
from tests import test_journey_games as games
from tests.support import select_test_profile


class DeliveryTests(unittest.TestCase):
    setUp=games.JourneyGamesTests.setUp
    token=games.JourneyGamesTests.token
    request=games.JourneyGamesTests.request
    seed_lesson=games.JourneyGamesTests.seed_lesson
    hello=games.JourneyGamesTests.hello
    create_profile=games.JourneyGamesTests.create_profile

    def start_delivery(self,new=False,options=None):
        if not getattr(self,'ready',False):
            select_test_profile(self.client)
            self.seed_lesson('directions')
            grant_earned_game_access(self.db)
            self.ready=True
        # This suite preserves compatibility with the original authored routes.
        # New generated-delivery defaults have their own HTTP integration tests.
        selected = {'delivery_id': MISSION_IDS[getattr(self, 'number', 0) % len(MISSION_IDS)], **(options or {})}
        return self.request('/api/v1/games/directions/start',{'request_id':f'delivery-start-{getattr(self,"number",0)}','new_game':new,'options':selected})

    def act(self,state,action,payload=None,**kwargs):
        return self.request('/api/v1/games/sessions/'+state['id']+'/route-command',
                            {'request_id':f'action-{state["delivery"]["revision"]:08d}-{action}',
                             'revision':state['delivery']['revision'],'action':action,'payload':payload or {}},**kwargs)

    def paths(self,sid):
        with transaction(self.db) as conn:
            return json.loads(conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?',(sid,)).fetchone()[0])['legs']

    def finish(self,state):
        for leg in self.paths(state['id']):
            state=self.act(state,'begin')
            state=self.act(state,'go',{'path':leg['route']})
            self.assertEqual(state['delivery']['phase'],'arrived')
            state=self.act(state,'deliver' if state['delivery']['leg']==2 else 'talk')
        return state

    def test_complete_delivery_preserves_position_first_attempts_and_single_reward(self):
        with patch('socket.socket.connect',side_effect=AssertionError('No generation in authored game')):
            state=self.start_delivery()
            self.assertEqual(state['delivery']['position'],'post')
            self.assertEqual(state['delivery']['phase'],'dialogue')
            self.assertEqual([entry['position'] for entry in state['delivery']['encounters']],['post'])
            self.assertNotIn('target',json.dumps(state))
            self.assertNotIn('Дом Анны',json.dumps(state,ensure_ascii=False))
            done=self.finish(state)
        self.assertEqual(done['phase'],'completed')
        self.assertEqual(done['delivery']['position'],'house-two')
        self.assertEqual(done['reward']['amount'],3)
        self.assertEqual(len(done['delivery']['first_checks']),3)
        self.assertEqual([entry['position'] for entry in done['delivery']['encounters']],['post','fountain','bakery','house-two'])
        with transaction(self.db) as conn:
            events=conn.execute("SELECT evidence_json FROM progression_events WHERE activity='journey_game'").fetchall()
            self.assertEqual(len(events),1)
            self.assertNotIn('_skill',json.loads(events[0][0]))
        self.assertEqual(self.client.get('/api/v1/games/sessions/'+state['id']).json['phase'],'completed')

    def test_wrong_bridge_turn_can_be_corrected_without_overwriting_first_check(self):
        state=self.start_delivery();legs=self.paths(state['id'])
        state=self.act(state,'begin');state=self.act(state,'go',{'path':legs[0]['route']});state=self.act(state,'talk')
        self.assertEqual(state['delivery']['position'],'fountain')
        state=self.act(state,'begin')
        wrong=['fountain','approach','bridge','bank']
        state=self.act(state,'go',{'path':wrong})
        self.assertEqual(state['delivery']['feedback']['code'],'bridge')
        state=self.client.get('/api/v1/games/sessions/'+state['id']).json
        self.assertEqual(state['delivery']['phase'],'feedback')
        state=self.act(state,'retry');state=self.act(state,'go',{'path':legs[1]['route']})
        checks=state['delivery']['first_checks']
        self.assertFalse(checks[1]['correct'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM journey_route_actions WHERE session_id=? AND attempt_kind='correction'",(state['id'],)).fetchone()[0],1)
        self.assertEqual(state['delivery']['phase'],'arrived')

    def test_request_retry_conflict_and_stale_tab_do_not_duplicate_actions(self):
        state=self.start_delivery()
        begun=self.act(state,'begin')
        self.assertEqual(self.act(state,'begin')['delivery']['revision'],begun['delivery']['revision'])
        self.act(state,'help',{'kind':'english'},status=409)
        body={'request_id':'action-00000000-begin','revision':0,'action':'help','payload':{'kind':'english'}}
        response=self.request('/api/v1/games/sessions/'+state['id']+'/route-command',body,status=409)
        self.assertEqual(response['error']['code'],'idempotency_conflict')

    def test_illegal_paths_and_premature_completion_are_rejected(self):
        state=self.start_delivery()
        self.act(state,'deliver',status=409)
        state=self.act(state,'begin')
        self.act(state,'go',{'path':['post','fountain']},status=400)
        self.act(state,'go',{'path':['post','corner']},status=400)
        self.act(state,'go',{'path':['post']},status=400)
        self.request('/api/v1/games/sessions/'+state['id']+'/complete',{},status=409)
        other=self.app.test_client()
        self.assertEqual(other.get('/api/v1/games/sessions/'+state['id']).status_code,404)

    def test_saved_plan_and_help_survive_refresh_without_future_dialogue(self):
        state=self.act(self.start_delivery(),'begin')
        state=self.act(state,'plan',{'path':['post','corner']})
        state=self.act(state,'help',{'kind':'english'})
        read=self.client.get('/api/v1/games/sessions/'+state['id']).json
        self.assertEqual(read['delivery']['draft'],['post','corner'])
        self.assertIn('english',read['delivery']['lines'][0])
        self.assertNotIn('Дом Анны',json.dumps(read,ensure_ascii=False))
        self.act(state,'help',{'kind':'word:парк'},status=400)
        guided=self.act(state,'help',{'kind':'route'})
        self.assertEqual(guided['delivery']['guided_path'],self.paths(state['id'])[0]['route'])

    def test_new_deliveries_vary_the_actual_address_and_keep_old_history(self):
        state=self.start_delivery()
        self.finish(state)
        self.number=1
        next_state=self.start_delivery(new=True)
        self.assertIn('Nikolai',next_state['title'])
        self.assertEqual(self.paths(next_state['id'])[2]['target'],'house-one')
        self.number=2
        third=self.start_delivery(new=True)
        self.assertIn('Vera',third['title'])
        self.assertEqual(self.paths(third['id'])[2]['target'],'house-three')
        self.assertEqual(self.client.get('/api/v1/games/sessions/'+state['id']).json['phase'],'completed')
        self.act(next_state,'begin',status=409)

    def test_route_writes_require_csrf_and_the_current_owner(self):
        state=self.start_delivery()
        other=self.app.test_client()
        self.create_profile('Another learner',client=other)
        self.act(state,'begin',client=other,status=404)
        url='/api/v1/games/sessions/'+state['id']+'/route-command'
        body={'request_id':'unauthorised-write','revision':0,'action':'begin','payload':{}}
        self.assertEqual(self.client.post(url,json=body).status_code,403)
        self.assertEqual(self.client.post(url,json=body,headers={'X-CSRF-Token':self.token(),'X-Profile-ID':'another-profile'}).status_code,409)
        self.assertEqual(self.client.get('/api/v1/games/sessions/'+state['id']).json['delivery']['revision'],0)

    def test_legacy_guest_delivery_attaches_to_a_new_profile_with_the_same_route_and_reward(self):
        self.hello(profile=False)
        with self.client.session_transaction() as session:
            guest=session[games.GUEST_ATTEMPT_KEY]
        self.seed_lesson('directions',profile=None,guest=guest)
        self.ready=True
        # Historical saved guest deliveries remain claimable after the gate changes.
        with patch('services.game_access.require_access'):
            state=self.start_delivery()
        done=self.finish(state)
        self.assertEqual(done['reward']['status'],'pending')
        profile=self.create_profile()
        read=self.client.get('/api/v1/games/sessions/'+done['id']).json
        self.assertEqual(read['profile_id'],profile)
        self.assertEqual(read['delivery'],done['delivery'])
        self.assertEqual(read['reward']['amount'],3)
        self.assertEqual(read['reward']['status'],'credited')

    def test_feature_switch_preserves_saved_deliveries_and_allows_legacy_starts(self):
        state=self.start_delivery()
        self.finish(state)
        self.app.config['DIRECTIONS_DELIVERIES_ENABLED']=False
        self.assertEqual(self.client.get('/api/v1/games/sessions/'+state['id']).json['delivery']['phase'],'completed')
        # The fallback keeps old mechanics readable without interpreting their
        # arrow arrays as the new spatial constraints.
        legacy=self.request('/api/v1/games/directions/start',{'request_id':'explicit-legacy-start','new_game':True,'options':{'source':'first_steps'}})
        self.assertNotIn('delivery',legacy)

    def test_choose_riverside_delivery_and_catalogue_does_not_reveal_routes(self):
        state = self.start_delivery(options={'delivery_id': 'irina'})
        self.assertEqual(state['title'], 'A letter for Irina')
        self.assertEqual(state['delivery']['map']['scene'], 'riverside')
        self.assertEqual([s['name'] for s in state['delivery']['stages']], ['Boris', 'Lena', 'The letter'])
        catalogue = self.client.get('/api/v1/games').json['deliveries']
        self.assertEqual({item['mission_id'] for item in catalogue}, {'town-procedural'})
        self.assertTrue(all({'mission_id', 'title', 'title_ru', 'summary', 'summary_ru', 'area'} <= set(item) for item in catalogue))
        self.assertTrue(all('route' not in item and 'target' not in item for item in catalogue))
        done = self.finish(state)
        self.assertEqual(done['delivery']['position'], 'station-house')
        station = next(w for w in done['words'] if w['lemma'] == 'вокзал')
        self.assertEqual(station['form'], 'вокзалом')
        self.assertEqual(station['grammar']['case'], 'ablt')

    def test_listening_hides_text_and_waits_for_current_recordings_or_transcript(self):
        state = self.start_delivery(options={'delivery_id': 'dima', 'delivery_mode': 'listening'})
        leg = self.paths(state['id'])[0]
        self.assertFalse(state['delivery']['can_go'])
        self.assertEqual(state['delivery']['glossary'], [])
        self.assertTrue(all(not stage['title'] and not stage['title_ru'] for stage in state['delivery']['stages']))
        self.assertEqual(state['delivery']['arrival_speaker']['role_en'], '')
        for line in state['delivery']['lines'] + state['delivery']['notebook'][0]['lines']:
            self.assertNotIn('text', line)
            self.assertNotIn('english', line)
        state = self.act(state, 'begin')
        self.act(state, 'go', {'path': leg['route']}, status=409)
        self.act(state, 'listen', {'line_id': 'other-recording', 'leg': 0}, status=400)
        self.act(state, 'listen', {'line_id': leg['lines'][0]['id'], 'leg': 1}, status=400)
        for line in leg['lines']:
            state = self.act(state, 'listen', {'line_id': line['id'], 'leg': 0})
        state = self.client.get('/api/v1/games/sessions/'+state['id']).json
        self.assertTrue(state['delivery']['can_go'])
        state = self.act(state, 'go', {'path': leg['route']})
        check = state['delivery']['first_checks'][0]
        self.assertEqual(check['presentation'], 'listening')
        self.assertFalse(check['assisted'])
        state = self.act(state, 'talk')
        self.assertFalse(state['delivery']['can_go'])
        state = self.act(state, 'help', {'kind': 'transcript'})
        self.assertTrue(state['delivery']['text_visible'])
        state = self.act(state, 'begin')
        state = self.act(state, 'go', {'path': self.paths(state['id'])[1]['route']})
        self.assertEqual(state['delivery']['first_checks'][1]['presentation'], 'reading')
        self.assertTrue(state['delivery']['first_checks'][1]['assisted'])

    def test_reading_then_switching_to_listening_cannot_erase_text_exposure(self):
        state = self.start_delivery()
        state = self.act(state, 'mode', {'mode': 'listening'})
        leg = self.paths(state['id'])[0]
        for line in leg['lines']:
            state = self.act(state, 'listen', {'line_id': line['id'], 'leg': 0})
        state = self.act(state, 'begin')
        state = self.act(state, 'go', {'path': leg['route']})
        self.assertEqual(state['delivery']['first_checks'][0]['presentation'], 'reading')

    def test_clarification_audio_allows_listening_with_help(self):
        state = self.start_delivery(options={'delivery_mode': 'listening'})
        state = self.act(state, 'help', {'kind': 'clarify'})
        self.assertNotIn('text', state['delivery']['clarification'])
        state = self.act(state, 'listen', {'line_id': state['delivery']['clarification']['id'], 'leg': 0})
        state = self.act(state, 'begin')
        state = self.act(state, 'go', {'path': self.paths(state['id'])[0]['route']})
        self.assertTrue(state['delivery']['first_checks'][0]['assisted'])
        self.assertEqual(state['delivery']['first_checks'][0]['presentation'], 'listening')

    def test_section_practice_survives_refresh_and_preserves_original_outcome(self):
        state = self.start_delivery(options={'delivery_id': 'dima'})
        self.act(state, 'review_start', {'leg': 0}, status=409)
        state = self.act(state, 'help', {'kind': 'english'})
        done = self.finish(state)
        self.assertTrue(done['delivery']['practice_sections'][0]['needs_practice'])
        checks = done['delivery']['first_checks']
        replay = self.act(done, 'review_start', {'leg': 1})
        self.assertEqual(replay['phase'], 'practice')
        self.assertEqual(self.act(done, 'review_start', {'leg': 1}), replay)  # Lost response retry.
        self.assertEqual(replay['delivery']['position'], 'market')
        self.assertIsNone(replay['reward'])
        self.assertEqual(len(replay['delivery']['notebook']), 1)
        replay = self.act(replay, 'begin')
        replay = self.act(replay, 'plan', {'path': ['market', 'square']})
        replay = self.client.get('/api/v1/games/sessions/'+done['id']).json
        self.assertEqual(replay['delivery']['draft'], ['market', 'square'])
        replay = self.act(replay, 'go', {'path': self.paths(done['id'])[1]['route']})
        self.act(replay, 'talk', status=409)
        self.act(replay, 'deliver', status=409)
        restored = self.act(replay, 'review_exit')
        self.assertEqual(restored['phase'], 'completed')
        self.assertEqual(restored['delivery']['first_checks'], checks)
        self.assertEqual(restored['delivery']['position'], done['delivery']['position'])
        self.assertEqual(restored['reward']['amount'], done['reward']['amount'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='journey_game'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM journey_route_actions WHERE attempt_kind='first'").fetchone()[0], 3)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM journey_route_actions WHERE attempt_kind='review'").fetchone()[0], 1)
        self.act(restored, 'review_start', {'leg': True}, status=400)
        self.act(restored, 'review_start', {'leg': 3}, status=400)

    def test_old_frozen_v2_pack_keeps_its_original_content(self):
        state = self.start_delivery()
        with transaction(self.db, write=True) as conn:
            pack = json.loads(conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?', (state['id'],)).fetchone()[0])
            for key in ('area', 'recipient_id', 'summary', 'summary_ru'):
                pack.pop(key)
            for key in ('scene', 'name_ru', 'name_en'):
                pack['map'].pop(key)
            for leg in pack['legs']:
                for key in ('rules', 'arrival_speaker', 'review_title', 'review_title_ru', 'clarify_prompt'):
                    leg.pop(key)
            for word in pack['vocabulary_refs']:
                word.pop('leg')
            frozen = json.dumps(pack)
            conn.execute('UPDATE journey_game_sessions SET content_json=? WHERE id=?', (frozen, state['id']))
            runtime = json.loads(conn.execute('SELECT state_json FROM journey_route_state WHERE session_id=?', (state['id'],)).fetchone()[0])
            for key in ('mode', 'heard', 'text_seen'):
                runtime.pop(key)
            conn.execute('UPDATE journey_route_state SET state_json=? WHERE session_id=?', (json.dumps(runtime), state['id']))
        state = self.client.get('/api/v1/games/sessions/'+state['id']).json
        self.assertEqual(state['delivery']['mode'], 'reading')
        self.finish(state)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?', (state['id'],)).fetchone()[0], frozen)


class RouteContentTests(unittest.TestCase):
    def test_semantic_routes_and_equivalent_detours(self):
        for i in range(len(MISSION_IDS)):
            pack=build_mission(i)
            for index,leg in enumerate(pack['legs']):
                validate_path(pack,leg,leg['route'],arrival=True)
                self.assertTrue(assess(pack,index,leg['route'])['correct'])
        anna=build_mission()
        self.assertFalse(assess(anna,0,['post','corner','street','fountain','approach','fountain'])['correct'])
        self.assertTrue(assess(anna,1,['fountain','approach','fountain','approach','bakery'])['correct'])
        self.assertFalse(assess(anna,1,['fountain','approach','bridge','approach','bakery'])['correct'])
        self.assertFalse(assess(anna,2,['bakery','house-one-turn','house-two-turn','park','house-two-turn','house-two'])['correct'])
        self.assertFalse(assess(anna,2,['bakery','house-one-turn','house-one'])['correct'])

    def test_recordings_are_unique_by_speaker_and_text(self):
        clips=all_audio()
        self.assertEqual(len(clips),len({x['id'] for x in clips}))
        self.assertTrue(all(c['audio_url'].startswith('/static/audio/deliveries/') for c in clips))
        root=Path(__file__).resolve().parents[1]
        for clip in clips:
            path=root/clip['audio_url'].lstrip('/')
            self.assertTrue(path.is_file(),f'Missing authored recording: {path.name}')
            self.assertGreater(path.stat().st_size,1024)

    def test_riverside_before_after_and_viewpoint_constraints(self):
        pack = build_mission(mission_id='dima')
        # Stopping before the bridge cannot satisfy the river-crossing task.
        self.assertFalse(assess(pack, 1, ['market', 'square', 'cafe'])['correct'])
        self.assertFalse(assess(pack, 1, ['market', 'square', 'south-bank', 'bridge'])['correct'])
        self.assertTrue(assess(pack, 1, ['market', 'square', 'south-bank', 'bridge', 'north-bank', 'library'])['correct'])
        # The first house and a reversed approach to the second are distinct errors.
        self.assertFalse(assess(pack, 2, ['library', 'school', 'house-first'])['correct'])
        irina = build_mission(mission_id='irina')
        self.assertFalse(assess(irina, 2, ['library', 'house-opposite'])['correct'])
        self.assertTrue(assess(irina, 2, ['library', 'north-bank', 'station', 'station-house'])['correct'])

    def test_authoring_rejects_missing_context_and_discontinuous_encounters(self):
        pack = deepcopy(build_mission(mission_id='dima'))
        pack['vocabulary_refs'][0]['form'] = 'рынками'
        with self.assertRaisesRegex(ValueError, 'absent'):
            validate_pack(pack)
        pack = deepcopy(build_mission(mission_id='dima'))
        pack['legs'][1]['start'] = 'post'
        with self.assertRaises(ValueError):
            validate_pack(pack)
