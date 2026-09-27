"""Full owned HTTP lifecycle for procedural delivery preparation and playback."""
from copy import deepcopy
import io
import json
import unittest
from tests.game_fixtures import grant_earned_game_access
import wave
from unittest.mock import patch

from repositories.learning_repository import encoded, transaction
from services.learning_assets import import_asset
from tests import test_route_town_delivery as towns
from tests.support import select_test_profile


class PreparationStub:
    """Only the paid preparation boundary is stubbed; map and missions are real."""
    calls = 0
    hook = None
    fail = False

    def plan(self, pack, *, scope):
        result = deepcopy(pack)
        result['_test_preparation'] = {'scope': scope, 'steps': 0}
        return result

    def status(self, pack):
        state = pack['_test_preparation']
        ready = state['steps'] >= 2
        return {'status': 'failed' if state.get('error') else 'ready' if ready else 'pending',
                'stage': 'ready' if ready else 'audio' if state['steps'] else 'dialogue',
                'ready': state['steps'], 'total': 2, 'message': 'Preparing the voices.',
                'error': state.get('error')}

    def advance(self, pack):
        self.calls += 1
        if self.hook:
            self.hook(pack)
        result = deepcopy(pack)
        result['_test_preparation'].pop('error', None)
        if self.fail:
            result['_test_preparation']['error'] = 'The recording could not be prepared.'
        else:
            result['_test_preparation']['steps'] += 1
        return result


class ProceduralDeliveryHTTPTests(unittest.TestCase):
    token = towns.TownDeliveryTests.token
    request = towns.TownDeliveryTests.request
    seed_lesson = towns.TownDeliveryTests.seed_lesson
    pack = towns.TownDeliveryTests.pack
    act = towns.TownDeliveryTests.act
    finish_leg = towns.TownDeliveryTests.finish_leg

    def setUp(self):
        towns.TownDeliveryTests.setUp(self)
        select_test_profile(self.client)
        self.seed_lesson('directions')
        grant_earned_game_access(self.db)
        self.preparation = PreparationStub()
        self.app.extensions['learning']['route_preparation'] = self.preparation

    def start(self, key='procedural-start-0001', **options):
        return self.request('/api/v1/games/directions/start',
                            {'request_id': key, 'new_game': True, 'options': options})

    def advance(self, state, retry=False, **kwargs):
        return self.request('/api/v1/games/sessions/' + state['id'] + '/prepare', {'retry': retry}, **kwargs)

    def ready(self, state):
        state = self.advance(state)
        state = self.advance(state)
        self.assertEqual(state['phase'], 'play')
        return state

    def test_default_creates_frozen_procedural_map_and_idempotent_preparation_without_network(self):
        with patch('socket.socket.connect', side_effect=AssertionError('Start must not call providers')):
            state = self.start()
            original = self.pack(state)
            self.assertEqual(original['mission_id'], 'town-procedural')
            self.assertEqual(state['phase'], 'preparing')
            self.assertNotIn('delivery', state)
            self.assertNotIn('mission_facts', json.dumps(state))
            again = self.start()
            self.assertEqual(state['id'], again['id'])
            self.assertEqual(self.pack(again), original)
            second = self.start('procedural-start-0002')
            self.assertEqual(self.pack(second)['town'], original['town'])
            self.assertNotEqual(self.pack(second)['mission_facts']['fingerprint'], original['mission_facts']['fingerprint'])
            self.advance(state, status=409)
        self.assertEqual(self.preparation.calls, 0)

    def test_new_town_is_explicit_changes_family_and_keeps_saved_snapshots(self):
        with patch('socket.socket.connect', side_effect=AssertionError('Start must not call providers')):
            first = self.start('saved-first-town')
            original = self.pack(first)
            fresh_request = {'request_id': 'explicit-new-town', 'new_game': False,
                             'options': {'delivery_new_town': True}}
            second = self.request('/api/v1/games/directions/start', fresh_request)
            replacement = self.pack(second)
            self.assertNotEqual(first['id'], second['id'])
            self.assertNotEqual(original['town']['seed'], replacement['town']['seed'])
            self.assertNotEqual(original['town']['layout_family'], replacement['town']['layout_family'])
            self.assertEqual(self.pack(first), original)
            same_request = self.request('/api/v1/games/directions/start', fresh_request)
            self.assertEqual(second['id'], same_request['id'])
            self.assertEqual(self.pack(same_request), replacement)
            reused = self.start('reuse-new-town-default')
            self.assertEqual(self.pack(reused)['town'], replacement['town'])
            self.assertEqual(self.pack(first), original)
        self.assertEqual(self.preparation.calls, 0)

    def test_new_town_option_rejects_non_boolean_values_without_creating_sessions(self):
        for index, value in enumerate(('false', 'true', 0, 1, None, [], {})):
            with self.subTest(value=value):
                result = self.request('/api/v1/games/directions/start',
                                      {'request_id': f'invalid-town-option-{index}', 'options': {'delivery_new_town': value}},
                                      status=400)
                self.assertEqual(result['error']['code'], 'invalid_options')
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM journey_game_sessions WHERE game_id='directions'").fetchone()[0], 0)
        self.assertEqual(self.preparation.calls, 0)

    def test_exploring_after_completion_preserves_the_previous_delivery_and_route(self):
        completed = self.ready(self.start('finish-before-new-town'))
        frozen = self.pack(completed)
        for index, leg in enumerate(frozen['legs']):
            completed = self.finish_leg(completed, leg)
            completed = self.act(completed, 'deliver' if index == len(frozen['legs']) - 1 else 'talk')
        with transaction(self.db) as conn:
            original_route = dict(conn.execute('SELECT * FROM journey_route_state WHERE session_id=?', (completed['id'],)).fetchone())
            reward_count = conn.execute('SELECT count(*) FROM progression_events').fetchone()[0]
        new_town = self.start('new-town-after-completion', delivery_new_town=True)
        self.assertNotEqual(self.pack(new_town)['town']['layout_family'], frozen['town']['layout_family'])
        self.assertEqual(self.pack(completed), frozen)
        self.assertEqual(self.client.get('/api/v1/games/sessions/' + completed['id']).json['phase'], 'completed')
        with transaction(self.db) as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM journey_route_state WHERE session_id=?', (completed['id'],)).fetchone()), original_route)
            self.assertEqual(conn.execute('SELECT count(*) FROM progression_events').fetchone()[0], reward_count)

    def test_false_new_town_option_resumes_existing_assignment(self):
        state = self.start('original-town-choice')
        original = self.pack(state)
        resumed = self.request('/api/v1/games/directions/start',
                               {'request_id': 'false-new-town-choice', 'options': {'delivery_new_town': False}})
        self.assertEqual(state['id'], resumed['id'])
        self.assertEqual(self.pack(resumed), original)

    def test_new_town_flag_does_not_regenerate_legacy_deliveries(self):
        state = self.start('legacy-town-choice', delivery_id='town-generated')
        original = self.pack(state)
        resumed = self.request('/api/v1/games/directions/start',
                               {'request_id': 'legacy-new-town-ignored',
                                'options': {'delivery_id': 'town-generated', 'delivery_new_town': True}})
        self.assertEqual(state['id'], resumed['id'])
        self.assertEqual(self.pack(resumed), original)
        self.assertEqual(self.preparation.calls, 0)

    def test_provider_work_holds_no_write_transaction_and_all_encounters_finish(self):
        state = self.start()
        def check_no_write_lock(pack):
            with transaction(self.db, write=True) as conn:
                conn.execute('UPDATE journey_game_sessions SET updated_at=updated_at WHERE id=?', (state['id'],))
        self.preparation.hook = check_no_write_lock
        state = self.ready(state)
        frozen = self.pack(state)
        for index, leg in enumerate(frozen['legs']):
            self.assertFalse(state['delivery']['arrival_speaker']['name'])
            state = self.finish_leg(state, leg)
            state = self.act(state, 'deliver' if index == len(frozen['legs']) - 1 else 'talk')
        self.assertEqual(state['phase'], 'completed')
        self.assertEqual(state['reward']['amount'], 3)
        self.assertEqual(self.pack(state), frozen)
        self.assertEqual(self.preparation.calls, 2)
        self.advance(state)
        self.assertEqual(self.preparation.calls, 2)

    def test_preparing_game_cannot_be_played_or_read_by_another_owner(self):
        state = self.start()
        self.request('/api/v1/games/sessions/' + state['id'] + '/route-command',
                     {'request_id': 'early-route-command', 'revision': 0, 'action': 'begin', 'payload': {}}, status=409)
        self.assertEqual(self.client.get('/api/v1/games/sessions/' + state['id']).json['phase'], 'preparing')
        other = self.app.test_client()
        self.assertEqual(other.get('/api/v1/games/sessions/' + state['id']).status_code, 404)
        self.advance(state, client=other, status=404)
        self.assertEqual(self.preparation.calls, 0)

    def test_listening_deliveries_finish_with_hidden_text_and_heard_clarifications(self):
        for number in range(3):
            with self.subTest(delivery=number):
                state = self.ready(self.start(f'listening-delivery-{number}', delivery_mode='listening'))
                frozen = self.pack(state)
                for index, leg in enumerate(frozen['legs']):
                    self.assertFalse(state['delivery']['text_visible'])
                    self.assertFalse(state['delivery']['can_go'])
                    self.assertTrue(all('text' not in line for line in state['delivery']['lines']))
                    for line in leg['lines']:
                        state = self.act(state, 'listen', {'leg': index, 'line_id': line['id']})
                    if leg.get('required_question'):
                        self.assertFalse(state['delivery']['can_go'])
                        state = self.act(state, 'ask', {'question_id': leg['required_question']})
                        self.assertFalse(state['delivery']['can_go'])
                        question = next(item for item in leg['questions'] if item['id'] == leg['required_question'])
                        state = self.act(state, 'listen', {'leg': index, 'line_id': question['reply']['id']})
                    self.assertTrue(state['delivery']['can_go'])
                    state = self.act(state, 'begin')
                    state = self.act(state, 'go', {'path': leg['route']})
                    self.assertEqual(state['delivery']['phase'], 'arrived')
                    self.assertEqual(state['delivery']['first_checks'][-1]['presentation'], 'listening')
                    self.assertFalse(state['delivery']['first_checks'][-1]['assisted'])
                    state = self.act(state, 'deliver' if index == len(frozen['legs']) - 1 else 'talk')
                self.assertEqual(state['phase'], 'completed')
                self.assertEqual(state['reward']['amount'], 3)
                self.assertEqual(self.pack(state), frozen)

    def test_failure_requires_explicit_retry_and_keeps_completed_stage(self):
        state = self.advance(self.start())
        original = self.pack(state)
        self.preparation.fail = True
        failed = self.advance(state)
        self.assertEqual(failed['preparation']['status'], 'failed')
        self.assertEqual(self.pack(state)['_test_preparation']['steps'], 1)
        self.advance(state)
        self.assertEqual(self.preparation.calls, 2)
        self.preparation.fail = False
        ready = self.advance(state, retry=True)
        self.assertEqual(ready['phase'], 'play')
        self.assertEqual(self.pack(state)['town'], original['town'])
        self.assertEqual(self.pack(state)['legs'], original['legs'])

    def test_missing_recording_after_ready_requires_explicit_repair_not_paid_read(self):
        state = self.ready(self.start())
        original = self.pack(state)
        missing = deepcopy(original)
        missing['_test_preparation']['steps'] = 1
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE journey_game_sessions SET content_json=? WHERE id=?', (encoded(missing), state['id']))
        paused = self.client.get('/api/v1/games/sessions/' + state['id']).json
        self.assertEqual(paused['phase'], 'preparing')
        self.assertEqual(paused['preparation']['status'], 'failed')
        self.advance(state)
        self.assertEqual(self.preparation.calls, 2)
        self.act(state, 'begin', status=409)
        restored = self.advance(state, retry=True)
        self.assertEqual(restored['phase'], 'play')
        self.assertEqual(self.pack(state), original)

    def test_active_and_expired_leases_do_not_automatically_duplicate_provider_work(self):
        state = self.start()
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE journey_route_preparations SET status='running',claim_id='in-flight',lease_until=9999999999 WHERE session_id=?", (state['id'],))
        running = self.advance(state, retry=True)
        self.assertEqual(running['preparation']['status'], 'running')
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE journey_route_preparations SET lease_until=0 WHERE session_id=?', (state['id'],))
        failed = self.advance(state)
        self.assertEqual(failed['preparation']['status'], 'failed')
        self.assertEqual(self.preparation.calls, 0)
        self.advance(state, retry=True)
        self.assertEqual(self.preparation.calls, 1)

    def test_stale_worker_cannot_overwrite_a_new_claim(self):
        state = self.start()
        original = self.pack(state)
        def take_over(pack):
            with transaction(self.db, write=True) as conn:
                conn.execute("UPDATE journey_route_preparations SET claim_id='newer-claim' WHERE session_id=?", (state['id'],))
        self.preparation.hook = take_over
        self.advance(state, status=409)
        self.assertEqual(self.pack(state), original)

    def test_starting_replacement_invalidates_the_in_flight_worker(self):
        state = self.start()
        original = self.pack(state)
        def replace(pack):
            replacement = self.start('replacement-during-provider')
            self.assertNotEqual(replacement['id'], state['id'])
        self.preparation.hook = replace
        self.advance(state, status=409)
        self.assertEqual(self.pack(state), original)
        with transaction(self.db) as conn:
            record = conn.execute('SELECT * FROM journey_route_preparations WHERE session_id=?', (state['id'],)).fetchone()
            self.assertIsNone(record['claim_id'])

    @staticmethod
    def audio(frames):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as writer:
            writer.setparams((1, 2, 8000, frames, 'NONE', 'not compressed'))
            writer.writeframes(b'\0\0' * frames)
        return buffer.getvalue()

    def test_audio_is_owned_and_future_dialogue_cannot_be_fetched(self):
        state = self.ready(self.start())
        pack = self.pack(state)
        store = self.app.extensions['learning']['assets']
        current_asset = import_asset(self.db, store, self.audio(1600), 'test current dialogue')
        future_asset = import_asset(self.db, store, self.audio(1800), 'test future dialogue')
        pack['legs'][0]['lines'][0]['asset_id'] = current_asset
        pack['legs'][1]['lines'][0]['asset_id'] = future_asset
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE journey_game_sessions SET content_json=? WHERE id=?', (encoded(pack), state['id']))
        prefix = '/api/v1/games/sessions/' + state['id'] + '/assets/'
        response = self.client.get(prefix + current_asset)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content_type.startswith('audio/'))
        response.close()
        self.assertEqual(self.client.get(prefix + future_asset).status_code, 404)
        self.assertEqual(self.app.test_client().get(prefix + current_asset).status_code, 404)
        public = self.client.get('/api/v1/games/sessions/' + state['id']).json
        self.assertEqual(public['delivery']['lines'][0]['audio_url'], prefix + current_asset)
        self.assertNotIn('encounter_contract', json.dumps(public))

    def test_public_demo_cannot_prepare_paid_missions(self):
        state = self.start()
        self.app.config['PUBLIC_DEMO'] = True
        self.advance(state, status=403)
        self.assertEqual(self.preparation.calls, 0)


if __name__ == '__main__':
    unittest.main()
