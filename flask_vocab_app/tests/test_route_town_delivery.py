"""Exercise generated deliveries through owned HTTP commands and saved state."""
import json
import unittest
from unittest.mock import patch

from repositories.learning_repository import LearningError, transaction
from services.route_delivery import _transport_path
from services.route_town import GENERATOR_VERSION, TOWN_MISSION_IDS, build_world
from tests import test_route_delivery as legacy


class TownTransportGeometryTests(unittest.TestCase):
    def test_bus_uses_roads_instead_of_shorter_pedestrian_shortcut(self):
        edges = [['post', 'court'], ['court', 'square'], ['post', 'west'],
                 ['west', 'north'], ['north', 'square']]
        pack = {'map': {'edges': edges, 'street_segments': [
            {'from': a, 'to': b, 'kind': 'path' if 'court' in (a, b) else 'main'}
            for a, b in edges
        ]}}
        self.assertEqual(_transport_path(pack, ['post', 'square']),
                         ['post', 'west', 'north', 'square'])
        del pack['map']['street_segments']
        self.assertEqual(_transport_path(pack, ['post', 'square']),
                         ['post', 'court', 'square'])

    def test_disconnected_bus_route_cannot_fall_back_to_a_footpath(self):
        pack = {'map': {'edges': [['post', 'square']], 'street_segments': [
            {'from': 'post', 'to': 'square', 'kind': 'path'}
        ]}}
        with self.assertRaises(LearningError):
            _transport_path(pack, ['post', 'square'])


class TownDeliveryTests(unittest.TestCase):
    setUp = legacy.DeliveryTests.setUp
    token = legacy.DeliveryTests.token
    request = legacy.DeliveryTests.request
    seed_lesson = legacy.DeliveryTests.seed_lesson
    hello = legacy.DeliveryTests.hello
    create_profile = legacy.DeliveryTests.create_profile
    start_delivery = legacy.DeliveryTests.start_delivery
    act = legacy.DeliveryTests.act
    paths = legacy.DeliveryTests.paths

    def start_town(self, mission='town-detour', *, mode='reading'):
        self.number = getattr(self, 'number', 0) + 1
        return self.start_delivery(new=True, options={'delivery_id': mission, 'delivery_mode': mode})

    def pack(self, state):
        with transaction(self.db) as conn:
            return json.loads(conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?', (state['id'],)).fetchone()[0])

    def finish_leg(self, state, leg):
        if leg.get('required_question'):
            state = self.act(state, 'ask', {'question_id': leg['required_question']})
        state = self.act(state, 'begin')
        if leg.get('transport'):
            state = self.act(state, 'board', {'transport_id': leg['transport']['id']})
            state = self.act(state, 'ride', {'stop_id': leg['target']})
            drivable = {frozenset((segment['from'], segment['to']))
                        for segment in state['delivery']['map'].get('street_segments', [])
                        if segment['kind'] in ('main', 'residential')}
            if drivable:
                travelled = state['delivery']['last_path']
                self.assertTrue(travelled)
                self.assertTrue(all(frozenset(edge) in drivable
                                    for edge in zip(travelled, travelled[1:])))
            state = self.act(state, 'alight')
        else:
            state = self.act(state, 'go', {'path': leg['route']})
        self.assertEqual(state['delivery']['phase'], 'arrived', state['delivery']['feedback'])
        return state

    def finish_town(self, state):
        legs = self.paths(state['id'])
        for index, leg in enumerate(legs):
            state = self.finish_leg(state, leg)
            state = self.act(state, 'deliver' if index == len(legs)-1 else 'talk')
        return state

    def test_all_scenario_types_finish_offline_with_one_receipt_each(self):
        with patch('socket.socket.connect', side_effect=AssertionError('No runtime generation')):
            for mission in TOWN_MISSION_IDS:
                with self.subTest(mission=mission):
                    state = self.start_town(mission)
                    self.assertEqual(state['delivery']['map']['scene'], 'town')
                    self.assertNotIn('expected_answer', json.dumps(state))
                    self.assertNotIn('required_question', json.dumps(state))
                    done = self.finish_town(state)
                    self.assertEqual(done['phase'], 'completed')
                    self.assertEqual(len(done['delivery']['first_checks']), done['total_rounds'])
                    again = self.client.get('/api/v1/games/sessions/'+state['id']).json
                    self.assertEqual(again['delivery'], done['delivery'])
        with transaction(self.db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='journey_game'").fetchone()[0]
            self.assertEqual(count, len(TOWN_MISSION_IDS))
            earned = conn.execute("SELECT SUM(amount) FROM progression_entries WHERE category='activity'").fetchone()[0]
            self.assertEqual(earned, 12)

    def test_town_persists_across_missions_and_original_session_is_frozen(self):
        first = self.start_town()
        original = self.pack(first)
        second = self.start_town('town-address')
        self.assertEqual(original['town'], self.pack(second)['town'])
        self.assertEqual(self.pack(first), original)
        self.assertEqual(first['title'], second['title'], 'Unfinished mission headings must not reveal their scenario')
        self.act(first, 'begin', status=409)

    def test_repeat_missions_cycle_through_facts_before_repeating(self):
        for mission, count in [('town-detour', 2), ('town-address', 2), ('town-parcel', 4), ('town-recipient', 2)]:
            with self.subTest(mission=mission):
                packs = [self.pack(self.start_town(mission)) for _ in range(count + 1)]
                facts = [json.dumps(pack['mission_facts'], sort_keys=True) for pack in packs]
                self.assertEqual(len(set(facts[:count])), count)
                self.assertEqual(facts[0], facts[-1])
                self.assertTrue(all(pack['town'] == packs[0]['town'] for pack in packs))

    def test_old_world_version_is_preserved_and_new_current_world_is_reused(self):
        old_state = self.start_town('town-address')
        old_pack = self.pack(old_state)
        old_pack['generator_version'] = 'delivery-town-v1'
        old_pack['town']['generator_version'] = 'delivery-town-v1'
        # The earlier town format did not have these semantic encounter IDs.
        old_pack['town']['places'].pop('north-approach')
        old_pack['town']['places'].pop('south-approach')
        frozen_json = json.dumps(old_pack, ensure_ascii=False)
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE journey_game_sessions SET content_json=? WHERE id=?', (frozen_json, old_state['id']))
        old_view = self.client.get('/api/v1/games/sessions/' + old_state['id']).json
        replacement_world = build_world('current-world-after-upgrade')
        with patch('services.route_town.build_world', return_value=replacement_world) as generate:
            current = self.start_town('town-detour')
            generate.assert_called_once()
        self.assertEqual(self.pack(current)['town'], replacement_world)
        self.assertEqual(self.pack(current)['town']['generator_version'], GENERATOR_VERSION)
        self.assertNotEqual(old_pack['town'], self.pack(current)['town'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?', (old_state['id'],)).fetchone()[0], frozen_json)
        self.assertEqual(self.client.get('/api/v1/games/sessions/' + old_state['id']).json['delivery'], old_view['delivery'])
        with patch('services.route_town.build_world', side_effect=AssertionError('Current town must be reused')):
            another = self.start_town('town-parcel')
        self.assertEqual(self.pack(another)['town'], replacement_world)
        self.assertEqual(self.pack(old_state), old_pack)

    def test_required_question_is_saved_without_becoming_a_hint(self):
        state = self.start_town('town-clarify')
        for leg in self.paths(state['id']):
            if not leg.get('required_question'):
                state = self.finish_leg(state, leg)
                state = self.act(state, 'talk')
                continue
            self.assertTrue(state['delivery']['question_required'])
            self.assertFalse(state['delivery']['can_go'])
            hidden = leg['questions'][0]['reply']['text']
            self.assertNotIn(hidden, [line.get('text') for line in state['delivery']['lines']])
            state = self.act(state, 'ask', {'question_id': leg['required_question']})
            self.assertFalse(state['delivery']['question_required'])
            self.assertEqual(state['delivery']['support'], {})
            restored = self.client.get('/api/v1/games/sessions/'+state['id']).json
            self.assertEqual(restored['delivery']['lines'], state['delivery']['lines'])
            state = self.act(state, 'begin')
            state = self.act(state, 'go', {'path': leg['route']})
            self.assertFalse(state['delivery']['first_checks'][-1]['assisted'])
            return
        self.fail('Clarification scenario has no required conversation')

    def test_listening_requires_the_question_reply_before_travel(self):
        state = self.start_town('town-clarify', mode='listening')
        leg = self.paths(state['id'])[0]
        reply = leg['questions'][0]['reply']
        self.assertFalse(state['delivery']['text_visible'])
        self.assertFalse(state['delivery']['can_go'])
        self.act(state, 'listen', {'leg': 0, 'line_id': reply['id']}, status=400)
        for line in leg['lines']:
            state = self.act(state, 'listen', {'leg': 0, 'line_id': line['id']})
        self.assertFalse(state['delivery']['can_go'], 'Hearing an ambiguous address does not supply the missing detail')
        state = self.act(state, 'ask', {'question_id': leg['required_question']})
        self.assertFalse(state['delivery']['question_required'])
        self.assertFalse(state['delivery']['can_go'], 'Asking is not the same as hearing the answer')
        self.assertNotIn('text', state['delivery']['lines'][-1])
        state = self.act(state, 'begin')
        denied = self.act(state, 'go', {'path': leg['route']}, status=409)
        self.assertEqual(denied['error']['code'], 'listen_first')
        state = self.act(state, 'listen', {'leg': 0, 'line_id': reply['id']})
        self.assertTrue(state['delivery']['can_go'])
        self.assertEqual(state['delivery']['support'], {})
        restored = self.client.get('/api/v1/games/sessions/' + state['id']).json
        self.assertTrue(restored['delivery']['can_go'])
        self.assertIn(reply['id'], restored['delivery']['heard'])
        state = self.act(restored, 'go', {'path': leg['route']})
        self.assertEqual(state['delivery']['phase'], 'arrived')
        self.assertFalse(state['delivery']['first_checks'][0]['assisted'])
        self.assertEqual(state['delivery']['first_checks'][0]['presentation'], 'listening')

    def test_replaying_initial_clarification_does_not_replace_required_reply(self):
        state = self.start_town('town-clarify', mode='listening')
        leg = self.paths(state['id'])[0]
        state = self.act(state, 'ask', {'question_id': leg['required_question']})
        state = self.act(state, 'help', {'kind': 'clarify'})
        state = self.act(state, 'listen', {'leg': 0, 'line_id': leg['clarify']['id']})
        self.assertFalse(state['delivery']['can_go'], 'The replay repeats the original address; the necessary reply is still unheard')
        reply = leg['questions'][0]['reply']
        state = self.act(state, 'listen', {'leg': 0, 'line_id': reply['id']})
        self.assertTrue(state['delivery']['can_go'])

    def test_parcel_is_collected_and_consumed_and_review_restores_inventory(self):
        state = self.start_town('town-parcel')
        legs = self.paths(state['id'])
        for index, leg in enumerate(legs):
            state = self.finish_leg(state, leg)
            if leg.get('arrival_item'):
                self.assertIn(leg['arrival_item'], state['delivery']['inventory'])
            if leg.get('arrival_remove_item'):
                self.assertNotIn(leg['arrival_remove_item'], [item['id'] for item in state['delivery']['inventory']])
            state = self.act(state, 'deliver' if index == len(legs)-1 else 'talk')
        required_index = next(i for i, leg in enumerate(legs) if leg.get('requires_item'))
        review = self.act(state, 'review_start', {'leg': required_index})
        self.assertIn(legs[required_index]['requires_item'], [item['id'] for item in review['delivery']['inventory']])
        self.assertEqual(review['delivery']['first_checks'], state['delivery']['first_checks'])

    def test_bus_requires_boarding_and_records_wrong_stop_then_correction(self):
        state = self.start_town('town-bus')
        for leg in self.paths(state['id']):
            if not leg.get('transport'):
                state = self.finish_leg(state, leg)
                state = self.act(state, 'talk')
                continue
            state = self.act(state, 'begin')
            self.act(state, 'go', {'path': leg['route']}, status=409)
            self.act(state, 'ride', {'stop_id': leg['target']}, status=409)
            state = self.act(state, 'board', {'transport_id': leg['transport']['id']})
            self.assertNotIn('alight', state['delivery']['transport'])
            wrong = next(stop for stop in leg['transport']['stops'][1:] if stop != leg['target'])
            state = self.act(state, 'ride', {'stop_id': wrong})
            state = self.act(state, 'alight')
            self.assertEqual(state['delivery']['phase'], 'feedback')
            state = self.act(state, 'retry')
            state = self.act(state, 'board', {'transport_id': leg['transport']['id']})
            state = self.act(state, 'ride', {'stop_id': leg['target']})
            state = self.act(state, 'alight')
            self.assertEqual(state['delivery']['phase'], 'arrived')
            self.assertFalse(state['delivery']['first_checks'][-1]['correct'])
            return
        self.fail('Bus scenario has no transport leg')

    def test_bus_route_help_resets_transport_position_and_draft_together(self):
        for phase in ('aboard', 'feedback'):
            with self.subTest(from_phase=phase):
                state = self.start_town('town-bus')
                legs = self.paths(state['id'])
                for leg in legs:
                    if not leg.get('transport'):
                        state = self.finish_leg(state, leg)
                        state = self.act(state, 'talk')
                        continue
                    bus = leg['transport']
                    state = self.act(state, 'begin')
                    state = self.act(state, 'board', {'transport_id': bus['id']})
                    wrong = next(stop for stop in bus['stops'][1:] if stop != leg['target'])
                    state = self.act(state, 'ride', {'stop_id': wrong})
                    self.assertEqual(state['delivery']['position'], wrong)
                    if phase == 'feedback':
                        state = self.act(state, 'alight')
                        self.assertEqual(state['delivery']['phase'], 'feedback')
                    first_checks = state['delivery']['first_checks']
                    state = self.act(state, 'help', {'kind': 'route'})
                    delivery = state['delivery']
                    self.assertEqual(delivery['phase'], 'planning')
                    self.assertEqual(delivery['transport']['status'], 'waiting')
                    self.assertEqual(delivery['transport']['stop_id'], bus['board'])
                    self.assertEqual(delivery['position'], bus['board'])
                    self.assertEqual(delivery['draft'], [bus['board']])
                    self.assertEqual(delivery['last_path'], [])
                    self.assertIsNone(delivery['feedback'])
                    self.assertEqual(delivery['guided_path'], leg['route'])
                    self.assertEqual(delivery['first_checks'], first_checks)
                    restored = self.client.get('/api/v1/games/sessions/' + state['id']).json
                    self.assertEqual(restored['delivery'], delivery)
                    self.act(restored, 'ride', {'stop_id': leg['target']}, status=409)
                    self.act(restored, 'alight', status=409)
                    state = self.act(restored, 'board', {'transport_id': bus['id']})
                    state = self.act(state, 'ride', {'stop_id': leg['target']})
                    state = self.act(state, 'alight')
                    self.assertEqual(state['delivery']['phase'], 'arrived')
                    self.assertTrue(state['delivery']['feedback']['assisted'])
                    break
                else:
                    self.fail('Bus scenario has no transport leg')

    def test_new_actions_keep_csrf_owner_revision_and_question_boundaries(self):
        state = self.start_town('town-clarify')
        self.act(state, 'ask', {'question_id': 'invented'}, status=400)
        self.act(state, 'board', {'transport_id': 'invented'}, status=409)
        other = self.app.test_client()
        self.assertEqual(other.get('/api/v1/games/sessions/'+state['id']).status_code, 404)
        url = '/api/v1/games/sessions/'+state['id']+'/route-command'
        self.assertEqual(self.client.post(url, json={'request_id':'forged-request', 'revision':0, 'action':'begin', 'payload':{}}).status_code, 403)
