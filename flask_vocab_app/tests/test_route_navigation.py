"""Arrival fairness through saved, owned delivery sessions."""
import json
import unittest

from repositories.learning_repository import transaction
from services.route_delivery import assess
from services.route_town import shortest_path
from tests import test_route_town_delivery as towns


class RouteNavigationTests(unittest.TestCase):
    # Reuse isolated HTTP fixtures without inheriting the existing test suite.
    setUp = towns.TownDeliveryTests.setUp
    token = towns.TownDeliveryTests.token
    request = towns.TownDeliveryTests.request
    seed_lesson = towns.TownDeliveryTests.seed_lesson
    hello = towns.TownDeliveryTests.hello
    create_profile = towns.TownDeliveryTests.create_profile
    start_delivery = towns.TownDeliveryTests.start_delivery
    act = towns.TownDeliveryTests.act
    paths = towns.TownDeliveryTests.paths
    start_town = towns.TownDeliveryTests.start_town
    pack = towns.TownDeliveryTests.pack
    finish_leg = towns.TownDeliveryTests.finish_leg

    def detour_at_worker(self):
        state = self.start_town()
        pack = self.pack(state)
        state = self.finish_leg(state, pack['legs'][0])
        state = self.act(state, 'talk')
        return self.act(state, 'begin'), pack

    def get_saved(self, state):
        response = self.client.get('/api/v1/games/sessions/' + state['id'])
        self.assertEqual(response.status_code, 200)
        return response.json

    def receipts(self, state):
        with transaction(self.db) as conn:
            return [dict(row) for row in conn.execute(
                'SELECT * FROM journey_route_actions WHERE session_id=? ORDER BY rowid',
                (state['id'],))]

    def make_historic_failure(self, state, code):
        """Model an old binary result without altering its submitted path."""
        old_result = {'correct': False, 'code': code, 'en': 'Original ambiguous failure',
                      'ru': 'Старая ошибка', 'assisted': False, 'presentation': 'reading',
                      'recordings': []}
        with transaction(self.db, write=True) as conn:
            row = conn.execute('SELECT state_json FROM journey_route_state WHERE session_id=?',
                               (state['id'],)).fetchone()
            runtime = json.loads(row[0])
            runtime.update(phase='feedback', feedback=old_result)
            runtime.pop('walked', None)
            conn.execute('UPDATE journey_route_state SET state_json=? WHERE session_id=?',
                         (json.dumps(runtime, ensure_ascii=False), state['id']))
            receipt = conn.execute(
                "SELECT id FROM journey_route_actions WHERE session_id=? AND operation='go' ORDER BY rowid DESC LIMIT 1",
                (state['id'],)).fetchone()
            conn.execute("UPDATE journey_route_actions SET attempt_kind='first',result_json=? WHERE id=?",
                         (json.dumps(old_result, ensure_ascii=False), receipt[0]))
        return self.receipts(state)

    def test_clicking_closed_bridge_meets_worker_without_crossing_or_failed_first_check(self):
        state = self.start_town()
        pack = self.pack(state)
        leg = pack['legs'][0]
        bridge = pack['town']['bridges'][pack['mission_facts']['closed_bridge']]
        submitted = [*leg['route'], bridge]
        state = self.act(self.act(state, 'begin'), 'go', {'path': submitted})
        delivery = state['delivery']
        self.assertEqual(delivery['phase'], 'arrived')
        self.assertEqual(delivery['position'], leg['target'])
        self.assertEqual(delivery['walked'], leg['route'])
        self.assertNotIn(bridge, delivery['last_path'])
        self.assertTrue(delivery['first_checks'][0]['correct'])
        self.assertEqual(json.loads(self.receipts(state)[-1]['submitted_json'])['path'], submitted)
        self.assertEqual(self.get_saved(state)['delivery'], delivery)

    def test_wrong_bank_does_not_count_as_meeting_worker(self):
        state = self.start_town()
        pack = self.pack(state)
        leg, world = pack['legs'][0], pack['town']
        bridge = world['bridges'][pack['mission_facts']['closed_bridge']]
        opposite = next(b if a == bridge else a for a, b in pack['map']['edges']
                        if bridge in (a, b) and leg['target'] not in (a, b))
        submitted = [*shortest_path(world, leg['start'], opposite, avoid=[bridge]), bridge]
        state = self.act(self.act(state, 'begin'), 'go', {'path': submitted})
        self.assertEqual(state['delivery']['phase'], 'feedback')
        self.assertEqual(state['delivery']['position'], opposite)
        self.assertFalse(state['delivery']['feedback']['correct'])
        self.assertFalse(state['delivery']['feedback']['navigation'])
        self.assertFalse(state['delivery']['first_checks'][0]['correct'])

    def test_library_frontage_preserves_crossing_and_continues_without_first_attempt_penalty(self):
        state, pack = self.detour_at_worker()
        leg = pack['legs'][1]
        frontage = leg['route'][:-1]
        state = self.act(state, 'go', {'path': frontage})
        delivery = state['delivery']
        self.assertEqual(delivery['feedback']['code'], 'nearby')
        self.assertTrue(delivery['feedback']['navigation'])
        self.assertEqual({check['id']: check['complete'] for check in delivery['feedback']['checks']},
                         {'crossing': True, 'destination': False})
        self.assertEqual([check['leg'] for check in delivery['first_checks']], [0])
        self.assertEqual(self.receipts(state)[-1]['attempt_kind'], 'navigation')
        state = self.act(self.get_saved(state), 'continue')
        self.assertEqual(state['delivery']['position'], frontage[-1])
        self.assertEqual(state['delivery']['draft'], frontage)
        self.assertEqual(state['delivery']['walked'], frontage)
        state = self.act(state, 'go', {'path': leg['route']})
        self.assertEqual(state['delivery']['phase'], 'arrived')
        self.assertEqual(state['delivery']['last_path'], leg['route'][-2:])
        self.assertTrue(state['delivery']['first_checks'][1]['correct'])
        self.assertFalse(state['delivery']['first_checks'][1]['assisted'])
        done = self.act(state, 'deliver')
        self.assertEqual(done['reward']['amount'], 3)
        self.assertEqual(len(done['delivery']['first_checks']), 2)

    def test_continuation_cannot_discard_walked_prefix_or_recheck_without_moving(self):
        state, pack = self.detour_at_worker()
        leg = pack['legs'][1]
        frontage = leg['route'][:-1]
        state = self.act(state, 'go', {'path': frontage})
        state = self.act(state, 'continue')
        for action, path in [('plan', [leg['start']]), ('go', frontage),
                             ('go', [frontage[-1], leg['target']])]:
            with self.subTest(action=action, path=path):
                self.act(state, action, {'path': path}, status=400)
                self.assertEqual(self.get_saved(state)['delivery'], state['delivery'])
        arrived = self.act(state, 'go', {'path': leg['route']})
        self.assertEqual(arrived['delivery']['phase'], 'arrived')

    def test_stopping_on_open_bridge_is_unfinished_navigation_not_a_wrong_destination(self):
        state, pack = self.detour_at_worker()
        leg = pack['legs'][1]
        bridge = pack['town']['bridges'][pack['mission_facts']['open_bridge']]
        bridge_path = leg['route'][:leg['route'].index(bridge) + 1]
        state = self.act(state, 'go', {'path': bridge_path})
        self.assertTrue(state['delivery']['feedback']['navigation'])
        self.assertFalse(next(check['complete'] for check in state['delivery']['feedback']['checks']
                              if check['id'] == 'crossing'), 'Standing on a bridge is not yet reaching the far bank')
        self.assertEqual([check['leg'] for check in state['delivery']['first_checks']], [0])
        self.assertEqual(state['delivery']['position'], bridge)
        state = self.act(state, 'continue')
        state = self.act(state, 'go', {'path': leg['route'][:-1]})
        self.assertTrue(next(check['complete'] for check in state['delivery']['feedback']['checks']
                             if check['id'] == 'crossing'))
        self.assertTrue(state['delivery']['feedback']['navigation'])
        state = self.act(self.act(state, 'continue'), 'go', {'path': leg['route']})
        self.assertEqual(state['delivery']['phase'], 'arrived')
        self.assertTrue(state['delivery']['first_checks'][1]['correct'])

    def test_walking_back_to_worker_can_continue_without_erasing_the_walk(self):
        state, pack = self.detour_at_worker()
        leg = pack['legs'][1]
        returned = [leg['start'], leg['route'][1], leg['start']]
        state = self.act(state, 'go', {'path': returned})
        self.assertTrue(state['delivery']['feedback']['navigation'])
        self.assertEqual(state['delivery']['position'], leg['start'])
        self.assertEqual(state['delivery']['walked'], returned)
        self.assertEqual([check['leg'] for check in state['delivery']['first_checks']], [0])
        state = self.act(state, 'continue')
        self.assertEqual(state['delivery']['draft'], returned)
        state = self.act(state, 'go', {'path': [*returned, *leg['route'][1:]]})
        self.assertEqual(state['delivery']['phase'], 'arrived')
        self.assertTrue(state['delivery']['first_checks'][1]['correct'])

    def test_different_house_remains_an_assessed_language_choice(self):
        state = self.start_town('town-address')
        pack = self.pack(state)
        state = self.act(self.finish_leg(state, pack['legs'][0]), 'talk')
        state = self.act(state, 'begin')
        leg, world = pack['legs'][1], pack['town']
        colour = 'blue' if pack['mission_facts']['house_colour'] == 'yellow' else 'yellow'
        wrong_path = shortest_path(world, leg['start'], world['places'][colour + '-house'])
        state = self.act(state, 'go', {'path': wrong_path})
        self.assertFalse(state['delivery']['feedback']['correct'])
        self.assertFalse(state['delivery']['feedback']['navigation'])
        self.assertEqual(state['delivery']['feedback']['code'], 'place')
        self.assertFalse(state['delivery']['first_checks'][1]['correct'])
        state = self.act(self.act(state, 'retry'), 'go', {'path': leg['route']})
        self.assertEqual(state['delivery']['phase'], 'arrived')
        self.assertFalse(state['delivery']['first_checks'][1]['correct'])

    def test_wrong_entrance_to_same_building_is_not_nearby_credit(self):
        state = self.start_town('town-courtyard')
        pack = self.pack(state)
        front, rear = pack['legs']
        wrong = shortest_path(pack['town'], front['start'], rear['target'])
        state = self.act(self.act(state, 'begin'), 'go', {'path': wrong})
        self.assertEqual(state['delivery']['feedback']['code'], 'place')
        self.assertFalse(state['delivery']['feedback']['navigation'])
        # The later instruction explicitly asks for the rear entrance. Standing
        # at its front door is not an accepted alternative to that distinction.
        result = assess(pack, 1, [rear['start']])
        self.assertFalse(result['correct'])
        self.assertFalse(result['navigation'])

    def test_historic_bridge_failure_is_repaired_in_view_without_rewriting_receipts(self):
        state = self.start_town()
        frozen = self.pack(state)
        leg = frozen['legs'][0]
        bridge = frozen['town']['bridges'][frozen['mission_facts']['closed_bridge']]
        state = self.act(self.act(state, 'begin'), 'go', {'path': [*leg['route'], bridge]})
        original_receipts = self.make_historic_failure(state, 'closed_bridge')
        restored = self.get_saved(state)
        self.assertEqual(restored['delivery']['phase'], 'arrived')
        self.assertEqual(restored['delivery']['position'], leg['target'])
        self.assertTrue(restored['delivery']['first_checks'][0]['correct'])
        self.assertEqual(self.receipts(state), original_receipts)
        self.assertEqual(self.pack(state), frozen)
        next_leg = self.act(restored, 'talk')
        self.assertEqual(next_leg['delivery']['leg'], 1)
        self.assertEqual(self.receipts(state)[:-1], original_receipts)

    def test_historic_frontage_failure_does_not_consume_effective_first_check(self):
        state, pack = self.detour_at_worker()
        leg = pack['legs'][1]
        state = self.act(state, 'go', {'path': leg['route'][:-1]})
        original_receipts = self.make_historic_failure(state, 'place')
        restored = self.get_saved(state)
        self.assertTrue(restored['delivery']['feedback']['navigation'])
        self.assertEqual([check['leg'] for check in restored['delivery']['first_checks']], [0])
        self.assertEqual(self.receipts(state), original_receipts)
        state = self.act(self.act(restored, 'continue'), 'go', {'path': leg['route']})
        self.assertEqual(state['delivery']['phase'], 'arrived')
        self.assertTrue(state['delivery']['first_checks'][1]['correct'])
        self.assertEqual(self.receipts(state)[:-2], original_receipts)


if __name__ == '__main__':
    unittest.main()
