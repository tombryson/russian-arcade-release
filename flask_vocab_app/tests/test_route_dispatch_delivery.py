"""Generated delivery dispatch, persistence and disclosure through the HTTP API."""
import json
import unittest
from tests.game_fixtures import grant_earned_game_access
from unittest.mock import patch

from repositories.learning_repository import transaction
from tests import test_route_town_delivery as towns
from tests.support import select_test_profile


class DispatchDeliveryTests(unittest.TestCase):
    setUp = towns.TownDeliveryTests.setUp
    token = towns.TownDeliveryTests.token
    request = towns.TownDeliveryTests.request
    seed_lesson = towns.TownDeliveryTests.seed_lesson
    hello = towns.TownDeliveryTests.hello
    create_profile = towns.TownDeliveryTests.create_profile
    act = towns.TownDeliveryTests.act
    paths = towns.TownDeliveryTests.paths
    pack = towns.TownDeliveryTests.pack
    finish_leg = towns.TownDeliveryTests.finish_leg

    def start_generated(self, *, request_id=None, new=True, mode='reading'):
        if not getattr(self, 'ready', False):
            select_test_profile(self.client)
            self.seed_lesson('directions')
            grant_earned_game_access(self.db)
            self.ready = True
        self.number = getattr(self, 'number', 0) + 1
        return self.request('/api/v1/games/directions/start', {
            'request_id': request_id or f'dispatch-start-{self.number:06d}',
            'new_game': new, 'options': {'delivery_id': 'town-generated', 'delivery_mode': mode},
        })

    def reload(self, state, *, client=None, status=200):
        response = (client or self.client).get('/api/v1/games/sessions/' + state['id'])
        self.assertEqual(response.status_code, status, response.text)
        return response.json

    def frozen_content(self, state):
        with transaction(self.db) as conn:
            return conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?',
                                (state['id'],)).fetchone()[0]

    def assert_unrevealed(self, state, pack):
        delivery, index = state['delivery'], state['delivery']['leg']
        self.assertEqual(state['title'], 'A delivery for Barsik')
        self.assertEqual(delivery['objective'], 'Follow the directions')
        self.assertNotIn('guided_path', delivery)
        self.assertNotIn('target', delivery)
        self.assertNotIn('mission_facts', delivery)
        self.assertNotIn('ending', delivery)
        self.assertFalse(delivery['arrival_speaker']['name'])
        self.assertFalse(delivery['arrival_speaker']['name_en'])
        for i, stage in enumerate(delivery['stages']):
            self.assertEqual(stage['title'], '')
            self.assertEqual(stage['title_ru'], '')
            if i >= index and i < len(pack['legs']) - 1:
                self.assertEqual(stage['name'], f'Stop {i + 1}')
        for line in delivery['lines']:
            self.assertNotIn('english', line)
        for entry in delivery['notebook']:
            for line in entry['lines']:
                self.assertNotIn('english', line)
        received_ids = {line['id'] for entry in delivery['notebook'] for line in entry['lines']}
        future_ids = {line['id'] for leg in pack['legs'][index + 1:] for line in leg['lines']}
        # A composer may reuse a phrase; only genuinely future dialogue is secret.
        current_ids = {line['id'] for leg in pack['legs'][:index + 1] for line in leg['lines']}
        self.assertFalse(received_ids & (future_ids - current_ids))
        self.assertLessEqual(len(delivery['notebook']), index + 1)
        self.assertTrue(all(closure.get('from_leg', 0) <= index
                            for closure in delivery['map'].get('closures', [])))
        known_contacts = {pack['legs'][0]['start']}
        known_contacts.update(leg['target'] for leg in pack['legs'][:index])
        known_contacts.update(contact['position'] for leg in pack['legs'][:index + 1]
                              for contact in leg.get('visible_contacts', []))
        self.assertTrue(all(contact['position'] in known_contacts for contact in delivery['encounters']))

    def test_previous_composer_start_resume_and_retry_keep_the_frozen_delivery_without_network(self):
        from services.route_dispatch import MISSION_ID
        with patch('socket.socket.connect', side_effect=AssertionError('Delivery preparation must be offline')):
            state = self.start_generated(request_id='default-dispatch-request')
            pack = self.pack(state)
            original = self.frozen_content(state)
            self.assertEqual(pack['mission_id'], MISSION_ID)
            self.assertEqual(MISSION_ID, 'town-generated')
            self.assertGreaterEqual(len(pack['legs']), 2)
            self.assertLessEqual(len(pack['legs']), 4)
            self.assertTrue(pack['mission_facts']['fingerprint'])
            self.assert_unrevealed(state, pack)
            with patch('services.route_dispatch.build_mission', side_effect=AssertionError('Do not regenerate saved content')):
                retried = self.start_generated(request_id='default-dispatch-request')
                resumed = self.start_generated(new=False)
                reloaded = self.reload(state)
            self.assertEqual(retried['id'], state['id'])
            self.assertEqual(resumed['id'], state['id'])
            self.assertEqual(retried['delivery'], state['delivery'])
            self.assertEqual(resumed['delivery'], state['delivery'])
            self.assertEqual(reloaded['delivery'], state['delivery'])
            self.assertEqual(self.frozen_content(state), original)
        self.reload(state, client=self.app.test_client(), status=404)

    def test_new_deliveries_reuse_town_but_exclude_the_last_twenty_mission_fingerprints(self):
        from services.route_dispatch import build_mission
        fingerprints, seeds, states, original = [], [], [], None
        with patch('services.route_dispatch.build_mission', wraps=build_mission) as compose:
            for index in range(23):
                state = self.start_generated()
                pack = self.pack(state)
                call = compose.call_args
                self.assertEqual(call.kwargs['exclude_fingerprints'], fingerprints[-20:])
                seed = call.args[1]
                self.assertNotIn(seed, seeds)
                self.assertEqual(pack['mission_seed'], seed)
                self.assertNotIn(pack['mission_facts']['fingerprint'], fingerprints[-20:])
                seeds.append(seed)
                fingerprints.append(pack['mission_facts']['fingerprint'])
                states.append(state)
                if index == 0:
                    original = self.frozen_content(state)
                    town = pack['town']
                self.assertEqual(pack['town'], town)
        self.assertEqual(compose.call_count, 23)
        self.assertEqual(self.frozen_content(states[0]), original)
        self.act(states[0], 'begin', status=409)

    def test_generated_routes_finish_with_one_reward_and_keep_received_clues_separate(self):
        from services.route_dispatch import build_mission
        for run in range(5):
            with self.subTest(run=run), patch('socket.socket.connect', side_effect=AssertionError('No live generation')):
                def compose(world, seed, **kwargs):
                    return build_mission(world, f'http-finish-{run}', **kwargs)
                with patch('services.route_dispatch.build_mission', side_effect=compose):
                    state = self.start_generated()
                pack, original = self.pack(state), self.frozen_content(state)
                self.assertGreaterEqual(len(pack['legs']), 2)
                self.assertLessEqual(len(pack['legs']), 4)
                for index, leg in enumerate(pack['legs']):
                    self.assert_unrevealed(state, pack)
                    self.assertEqual(self.reload(state)['delivery'], state['delivery'])
                    state = self.finish_leg(state, leg)
                    self.assertTrue(state['delivery']['feedback']['correct'])
                    before = state
                    operation = 'deliver' if index == len(pack['legs']) - 1 else 'talk'
                    state = self.act(state, operation)
                self.assertEqual(state['phase'], 'completed')
                self.assertEqual(state['reward']['amount'], 3 if run < 4 else 0)
                self.assertEqual(len(state['delivery']['first_checks']), len(pack['legs']))
                self.assertEqual(state['title'], pack['title'])
                self.assertEqual(self.act(before, 'deliver')['delivery'], state['delivery'])
                self.assertEqual(self.frozen_content(state), original)
        with transaction(self.db) as conn:
            events = conn.execute("SELECT evidence_json FROM progression_events WHERE activity='journey_game'").fetchall()
            self.assertEqual(len(events), 5)
            self.assertTrue(all('_skill' not in json.loads(event[0]) for event in events))
            self.assertEqual(conn.execute("SELECT SUM(amount) FROM progression_entries WHERE category='activity'").fetchone()[0], 12)

    def test_english_translation_is_explicit_help_and_does_not_reveal_later_stops(self):
        state = self.start_generated()
        pack = self.pack(state)
        self.assert_unrevealed(state, pack)
        state = self.act(state, 'help', {'kind': 'english'})
        self.assertTrue(state['delivery']['support']['english'])
        self.assertEqual(state['delivery']['objective'], pack['legs'][0]['objective'])
        self.assertEqual([line['english'] for line in state['delivery']['lines']],
                         [line['english'] for line in pack['legs'][0]['lines']])
        self.assertEqual(len(state['delivery']['notebook']), 1)
        self.assertFalse(state['delivery']['arrival_speaker']['name_en'])
        for index, stage in enumerate(state['delivery']['stages'][:-1]):
            self.assertEqual(stage['name'], f'Stop {index + 1}')
        self.assertEqual(self.reload(state)['delivery'], state['delivery'])
        state = self.finish_leg(state, pack['legs'][0])
        self.assertTrue(state['delivery']['first_checks'][0]['assisted'])

    def test_replaying_identical_mission_content_does_not_award_coins_again(self):
        state = self.start_generated()
        pack = self.pack(state)
        for run in range(2):
            if run:
                with patch('services.route_dispatch.build_mission', return_value=pack):
                    state = self.start_generated()
            for index, leg in enumerate(pack['legs']):
                state = self.finish_leg(state, leg)
                state = self.act(state, 'deliver' if index == len(pack['legs']) - 1 else 'talk')
            self.assertEqual(state['phase'], 'completed')
            self.assertEqual(state['reward']['amount'], 0 if run else 3)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='journey_game'").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT SUM(amount) FROM progression_entries WHERE category='activity'").fetchone()[0], 3)

    def test_listening_delivery_requires_hearing_the_required_question_reply(self):
        from services.route_dispatch import build_mission
        from services.route_town import build_world
        world = build_world('dispatch-listening-world')
        pack = None
        for index in range(64):
            candidate = build_mission(world, f'listening-question-{index}')
            if any(leg.get('required_question') for leg in candidate['legs']):
                pack = candidate
                break
        self.assertIsNotNone(pack, 'The composer must include conversations needing clarification')
        with patch('services.route_town.build_world', return_value=world), \
                patch('services.route_dispatch.build_mission', return_value=pack), \
                patch('socket.socket.connect', side_effect=AssertionError('Listening preparation must be offline')):
            state = self.start_generated(mode='listening')
        required_questions = 0
        for index, leg in enumerate(pack['legs']):
            self.assertFalse(state['delivery']['can_go'])
            self.assertFalse(state['delivery']['text_visible'])
            for line in state['delivery']['lines']:
                self.assertNotIn('text', line)
                self.assertNotIn('english', line)
                self.assertTrue(line['audio_url'].startswith('/static/audio/deliveries/'))
            if leg.get('required_question'):
                required_questions += 1
                question = next(question for question in leg['questions']
                                if question['id'] == leg['required_question'])
                self.act(state, 'listen', {'leg': index, 'line_id': question['reply']['id']}, status=400)
                for line in leg['lines']:
                    state = self.act(state, 'listen', {'leg': index, 'line_id': line['id']})
                self.assertFalse(state['delivery']['can_go'], 'The original statement still lacks the missing information')
                state = self.act(state, 'ask', {'question_id': question['id']})
                self.assertFalse(state['delivery']['can_go'], 'Asking does not mean the reply has been heard')
                self.assertNotIn('text', state['delivery']['lines'][-1])
            for line in state['delivery']['lines']:
                if line['id'] not in state['delivery']['heard']:
                    state = self.act(state, 'listen', {'leg': index, 'line_id': line['id']})
            self.assertTrue(state['delivery']['can_go'])
            state = self.reload(state)
            self.assertTrue(state['delivery']['can_go'])
            state = self.finish_leg(state, leg)
            self.assertEqual(state['delivery']['first_checks'][-1]['presentation'], 'listening')
            self.assertFalse(state['delivery']['first_checks'][-1]['assisted'])
            state = self.act(state, 'deliver' if index == len(pack['legs']) - 1 else 'talk')
        self.assertGreater(required_questions, 0)
        self.assertEqual(state['phase'], 'completed')
        self.assertEqual(state['reward']['amount'], 3)

    def test_catalogue_offers_one_generic_delivery_instead_of_scenario_answers(self):
        self.start_generated()
        response = self.client.get('/api/v1/games')
        self.assertEqual(response.status_code, 200)
        catalogue = response.json['deliveries']
        self.assertEqual(len(catalogue), 1)
        self.assertEqual(catalogue[0]['mission_id'], 'town-procedural')
        for hidden in ('mission_facts', 'legs', 'target', 'rules', 'route', 'fingerprint'):
            self.assertNotIn(hidden, catalogue[0])

    def test_repeat_help_does_not_answer_an_unasked_address_question(self):
        from services.route_dispatch import build_mission
        from services.route_town import build_world
        world = build_world('repeat-without-spoilers')
        candidates = (build_mission(world, seed) for seed in range(64))
        pack = next(candidate for candidate in candidates
                    if any(leg.get('required_question') for leg in candidate['legs']))
        with patch('services.route_dispatch.build_mission', return_value=pack):
            state = self.start_generated()
        for leg in pack['legs']:
            if not leg.get('required_question'):
                state = self.act(self.finish_leg(state, leg), 'talk')
                continue
            question = leg['questions'][0]
            state = self.act(state, 'help', {'kind': 'clarify'})
            self.assertNotEqual(state['delivery']['clarification']['id'], question['reply']['id'])
            self.assertNotIn(question['reply']['text'], json.dumps(state, ensure_ascii=False))
            self.assertFalse(state['delivery']['can_go'])
            state = self.act(state, 'ask', {'question_id': question['id']})
            self.assertIn(question['reply']['text'], [line['text'] for line in state['delivery']['lines']])
            self.assertTrue(state['delivery']['can_go'])
            break


if __name__ == '__main__':
    unittest.main()
