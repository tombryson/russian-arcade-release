"""Game outcomes, replay identity and rewards use frozen owned lessons."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import sqlite3
import unittest
from unittest.mock import patch

from repositories.learning_repository import encoded, identifier, timestamp, transaction
from migrations import MIGRATION_DIR, upgrade_database
from services.first_delivery import GUEST_ATTEMPT_KEY
from services.first_steps import chapter_content
from services.journey_games import GAMES, _content, assess_answer, movement_path, sync_unlocks, _snapshot_legacy_unlocks
from services.progression import award, snapshot
from tests.support import isolated_app, select_test_profile, latest_schema_version, strip_course_progression
from tests import test_first_steps as first_steps_tests
from tests.game_fixtures import grant_earned_game_access


class JourneyGamesTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, signed_in=False)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.content = chapter_content()

    # Real first-delivery/profile flows for the guest-transfer boundary.
    token = first_steps_tests.FirstStepsTests.token
    request = first_steps_tests.FirstStepsTests.request
    hello = first_steps_tests.FirstStepsTests.hello
    create_profile = first_steps_tests.FirstStepsTests.create_profile

    def seed_lesson(self, lesson_id, *, profile='personal-learning', guest=None, sync=True):
        lesson = deepcopy(next(lesson for lesson in self.content['lessons'] if lesson['id'] == lesson_id))
        lesson.update(chapter_id='first-steps', version=self.content['version'])
        now = timestamp()
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO first_steps_attempts(id,profile_id,guest_token,chapter_id,lesson_id,version,content_json,completed_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (identifier(), profile, guest, 'first-steps', lesson_id, lesson['version'], encoded(lesson), now, now, now))
            if sync:
                sync_unlocks(conn, profile, guest, now=now)
        return lesson

    def post(self, session_id, operation, data=None, *, client=None, status=200):
        return self.request(f'/api/v1/games/sessions/{session_id}/{operation}', data, client=client, status=status)

    def start(self, game='pack-bag', request_id=None, *, client=None, status=200):
        options = {'grammar_focus': 'location'} if game == 'scene-builder' else {'source': 'first_steps'}
        return self.request(f'/api/v1/games/{game}/start', {'request_id': request_id or identifier(), 'options': options}, client=client, status=status)

    def read(self, session_id, *, client=None):
        response = (client or self.client).get('/api/v1/games/sessions/' + session_id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.json

    def expected(self, session_id):
        with transaction(self.db) as conn:
            row = conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?', (session_id,)).fetchone()
            return json.loads(row['content_json'])['rounds']

    def finish(self, state, *, hints=(), wrong=(), client=None):
        session_id = state['id']
        for item in self.expected(session_id):
            if item.get('mechanic') == 'radio':
                self.post(session_id, 'transcript', {'round_id': item['id']}, client=client)
            if item['id'] in hints:
                self.post(session_id, 'hint', {'round_id': item['id']}, client=client)
            answer = item['expected_answer']
            if item['id'] in wrong:
                answer = ['apple'] if state['game_id'] == 'pack-bag' else ['right' if answer != ['right'] else 'left']
            self.post(session_id, 'answer', {'round_id': item['id'], 'answer': answer}, client=client)
            self.post(session_id, 'continue', {'round_id': item['id']}, client=client)
        return self.post(session_id, 'complete', client=client)

    def counts(self):
        with transaction(self.db) as conn:
            return tuple(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                         for table in ('journey_game_unlocks', 'journey_game_sessions', 'progression_events', 'progression_entries'))

    def test_catalogue_is_read_only_and_tutorial_completion_does_not_unlock_games(self):
        select_test_profile(self.client)
        before = self.counts()
        catalogue = self.client.get('/api/v1/games')
        self.assertEqual(catalogue.status_code, 200)
        self.assertEqual(catalogue.headers['Cache-Control'], 'no-store')
        self.assertTrue(all(not game['unlocked'] for game in catalogue.json['games']))
        self.start(status=409)
        self.assertEqual(self.counts(), before)
        self.seed_lesson('bag', sync=False)
        before = self.counts()
        for _ in range(2):
            games = self.client.get('/api/v1/games').json['games']
            self.assertTrue(all(not game['unlocked'] for game in games))
        self.assertEqual(self.counts(), before)
        self.start(status=409)
        with transaction(self.db, write=True) as conn:
            for index in range(9):
                award(conn, 'personal-learning', activity='reading',
                      content_key=f'read-{index}', source_key=f'read-{index}',
                      title='Completed reading practice', now=946684800 + (index // 4) * 86400)
        before = self.counts()
        for _ in range(2):
            games = self.client.get('/api/v1/games').json['games']
            self.assertTrue(all(not game['unlocked'] for game in games))
            self.assertTrue(all(game['purchase']['can_purchase'] for game in games))
        self.assertEqual(self.counts(), before)
        self.start('directions', status=409)
        self.request('/api/v1/games/pack-bag/purchase', {'request_id': identifier(), 'expected_price': 25})
        self.assertTrue(self.client.get('/api/v1/games').json['games'][0]['new'])
        started = self.start()
        game = self.client.get('/api/v1/games').json['games'][0]
        self.assertFalse(game['new'])
        self.assertIsNone(game['active_session_id'])  # Introduction does not replace standalone library practice.

    def test_start_resumes_active_and_every_request_alias_retries_original_session(self):
        select_test_profile(self.client)
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        first = self.start(request_id='request-1111')
        self.assertEqual(self.start(request_id='request-2222')['id'], first['id'])
        self.assertEqual(self.start(request_id='request-1111')['id'], first['id'])
        self.finish(first)
        for request_id in ('request-1111', 'request-2222'):
            self.assertEqual(self.start(request_id=request_id)['phase'], 'completed')
        next_state = self.start(request_id='request-3333')
        self.assertNotEqual(first['id'], next_state['id'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_sessions WHERE completed_at IS NULL').fetchone()[0], 1)
            seeds = [row[0] for row in conn.execute('SELECT seed FROM journey_game_sessions')]
            self.assertEqual(len(set(seeds)), 2)

    def test_first_answer_and_hint_are_saved_without_leaking_hidden_answer(self):
        select_test_profile(self.client)
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        state = self.start()
        sid, item = state['id'], self.expected(state['id'])[0]
        self.assertIsNone(state['result'])
        self.assertNotIn('hint', state['round'])
        self.assertNotIn('expected_answer', state['round'])
        self.assertNotIn('translation', state['round']['clues'][0])
        self.post(sid, 'complete', status=409)
        self.post(sid, 'continue', {'round_id': item['id']}, status=409)
        hinted = self.post(sid, 'hint', {'round_id': item['id']})
        self.assertEqual(hinted['round']['hint'], item['hint'])
        feedback = self.post(sid, 'answer', {'round_id': item['id'], 'answer': ['apple']})
        self.assertEqual(feedback['phase'], 'feedback')
        self.assertFalse(feedback['result']['correct'])
        self.assertEqual(feedback['result']['expected_answer'], item['expected_answer'])
        self.assertEqual(self.read(sid), feedback)
        self.post(sid, 'answer', {'round_id': item['id'], 'answer': item['expected_answer']}, status=409)
        self.assertEqual(self.post(sid, 'answer', {'round_id': item['id'], 'answer': ['apple']}), feedback)
        with transaction(self.db) as conn:
            saved = json.loads(conn.execute('SELECT answers_json FROM journey_game_sessions WHERE id=?', (sid,)).fetchone()[0])
            self.assertTrue(saved[item['id']]['hint_used'])
        self.post(sid, 'answer', {'round_id': item['id'], 'answer': []}, status=400)
        self.post(sid, 'answer', {'round_id': item['id'], 'answer': ['letter'], 'correct': True}, status=400)

    def test_frozen_unlock_survives_source_retirement_and_game_source_changes(self):
        select_test_profile(self.client)
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        with transaction(self.db, write=True) as conn:
            _snapshot_legacy_unlocks(conn, 'personal-learning', None)
            frozen = json.loads(conn.execute('SELECT lesson_json FROM journey_game_unlocks').fetchone()[0])
            frozen['vocabulary'][0]['sentence'] = 'Вот письмо.'
            conn.execute('UPDATE journey_game_unlocks SET lesson_json=?', (encoded(frozen),))
            conn.execute('DELETE FROM first_steps_attempts')
        game = self.client.get('/api/v1/games').json['games'][0]
        self.assertTrue(game['unlocked'])
        state = self.start()
        frozen_rounds = self.expected(state['id'])
        self.assertTrue(any(clue['text'] == 'Вот письмо.' for item in frozen_rounds for clue in item['clues']))
        for item in frozen_rounds:
            for clue in item['clues']:
                self.assertEqual(clue['audio_key'], hashlib.sha256(clue['text'].encode()).hexdigest())
        with patch('services.journey_games._content', side_effect=AssertionError('Existing session must remain frozen')):
            self.assertEqual(self.start()['id'], state['id'])
            self.assertEqual(self.read(state['id'])['round'], state['round'])

    def test_completed_game_awards_participation_once_per_game_per_day_and_skill_once(self):
        select_test_profile(self.client)
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        first = self.finish(self.start())
        self.assertEqual(first['reward']['amount'], 3)
        self.assertEqual(first['reward']['reason'], 'awarded')
        self.assertTrue(first['reward']['awarded_now'])
        reading = next(skill for skill in first['progression']['skill']['skills'] if skill['id'] == 'reading')
        self.assertEqual(reading['observations'], 1)
        self.assertEqual(reading['rating'], 1009)
        repeated = self.post(first['id'], 'complete')
        self.assertFalse(repeated['reward']['awarded_now'])
        self.assertEqual(repeated['reward']['amount'], 3)
        second = self.finish(self.start())
        self.assertEqual(second['reward']['amount'], 0)
        self.assertEqual(second['reward']['reason'], 'already_rewarded')
        self.assertEqual(second['progression']['balance'], first['progression']['balance'])
        # A fresh random seed cannot become another content claim or Elo sample.
        self.assertEqual(second['progression']['skill'], first['progression']['skill'])
        self.seed_lesson('directions')
        grant_earned_game_access(self.db)
        with transaction(self.db, write=True) as conn:
            for i in range(3):
                award(conn, 'personal-learning', activity='test', content_key=str(i), source_key=str(i), title='Cap fixture')
        capped = self.finish(self.start('directions'))
        self.assertEqual(capped['reward']['amount'], 0)
        self.assertEqual(capped['reward']['reason'], 'daily_cap')

    def test_hints_exclude_assisted_rounds_from_skill_without_removing_participation(self):
        select_test_profile(self.client)
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        state = self.start()
        rounds = self.expected(state['id'])
        result = self.finish(state, hints=[item['id'] for item in rounds])
        self.assertEqual(result['reward']['amount'], 3)
        reading = next(skill for skill in result['progression']['skill']['skills'] if skill['id'] == 'reading')
        self.assertEqual(reading['observations'], 0)
        self.assertIsNone(reading['rating'])
        # A replay after seeing translations cannot manufacture a first sample.
        replay = self.finish(self.start())
        self.assertEqual(replay['progression']['skill'], result['progression']['skill'])

    def test_migration_backfills_existing_completed_lessons_without_rewarding_or_rewriting(self):
        self.seed_lesson('bag', sync=False)
        self.seed_lesson('directions', profile=None, guest='fixture-guest', sync=False)
        with transaction(self.db, write=True) as conn:
            before = [tuple(row) for row in conn.execute('SELECT * FROM first_steps_attempts ORDER BY id')]
            ledger = [tuple(row) for row in conn.execute('SELECT * FROM progression_events')]
            strip_course_progression(conn)
            for table in ('step_conversation_answers', 'step_conversation_sessions', 'journey_game_purchases', 'journey_game_access', 'journey_route_audio_cache', 'journey_route_preparations', 'journey_route_actions', 'journey_route_state', 'journey_game_corrections', 'journey_game_preparations', 'journey_game_examples', 'journey_game_media', 'journey_game_sessions', 'journey_game_unlocks'):
                conn.execute('DROP TABLE ' + table)
            conn.execute('ALTER TABLE word_jumble_games DROP COLUMN task_json')
            conn.execute('DELETE FROM schema_migrations WHERE version>=30')
        self.assertEqual(upgrade_database(self.db, backup=False)[0], latest_schema_version())
        with transaction(self.db) as conn:
            self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM first_steps_attempts ORDER BY id')], before)
            self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM progression_events')], ledger)
            unlocks = conn.execute('SELECT * FROM journey_game_unlocks').fetchall()
            self.assertEqual(len(unlocks), 6)
            self.assertEqual({row['game_id'] for row in unlocks}, {'pack-bag', 'directions', 'pairs', 'missing-stamp', 'radio', 'scene-builder'})
            self.assertTrue(all(row['first_started_at'] is None for row in unlocks))
            self.assertTrue(all(json.loads(row['lesson_json'])['version'] == self.content['version'] for row in unlocks))
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertIsNone(conn.execute('PRAGMA foreign_key_check').fetchone())

    def test_direction_rounds_are_relative_ordered_in_bounds_and_cover_all_three_words(self):
        lesson = next(lesson for lesson in self.content['lessons'] if lesson['id'] == 'directions') | {'version': self.content['version']}
        game = GAMES[1]
        varieties = set()
        for i in range(30):
            content = _content(game, lesson, str(i))
            varieties.add(encoded(content))
            first_commands = []
            for item in content['rounds']:
                path = movement_path(item['board'], item['expected_answer'])
                self.assertEqual(len(path), len(item['expected_answer']) + 1)
                first_commands.append(item['expected_answer'][0])
            self.assertEqual(set(first_commands), {'left', 'right', 'straight'})
        self.assertGreater(len(varieties), 10)
        board = content['rounds'][0]['board']
        path = movement_path(board, ['left', 'straight'])
        self.assertEqual(path[-1], {'x': 0, 'y': 3, 'heading': 'west'})

    def test_other_profiles_and_stale_tabs_cannot_read_or_write_games_or_audio(self):
        select_test_profile(self.client)
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        state = self.start()
        key = state['round']['clues'][0]['audio_key']
        other = self.app.test_client()
        other_id = self.create_profile('Someone else', client=other)
        self.assertNotEqual(other_id, 'personal-learning')
        self.assertEqual(other.get('/api/v1/games/sessions/' + state['id']).status_code, 404)
        self.post(state['id'], 'hint', {'round_id': state['round']['id']}, client=other, status=404)
        self.assertEqual(other.get('/api/v1/games/media/' + key + '/status').status_code, 404)
        self.start(client=other, status=409)
        self.assertEqual(other.get('/api/v1/games', headers={'X-Profile-ID': 'personal-learning'}).status_code, 409)
        self.assertEqual(other.get('/api/v1/games/sessions/' + state['id'], headers={'X-Profile-ID': 'personal-learning'}).status_code, 409)
        self.assertEqual(self.client.post('/api/v1/games/pack-bag/start', json={'request_id': identifier()}).status_code, 403)

    def test_legacy_guest_progress_is_claimed_only_by_new_profile_and_keeps_saved_session(self):
        self.hello(profile=False)
        with self.client.session_transaction() as session:
            guest_token = session[GUEST_ATTEMPT_KEY]
        self.seed_lesson('bag', profile=None, guest=guest_token)
        # Recreate a session saved under the retired introduction-unlock policy.
        with patch('services.journey_games.require_access'):
            state = self.start()
        first = self.finish(state)
        self.assertIsNone(first['profile_id'])
        self.assertEqual(first['reward']['status'], 'pending')
        new_id = self.create_profile()
        claimed = self.read(first['id'])
        self.assertEqual(claimed['profile_id'], new_id)
        self.assertEqual(claimed['reward']['status'], 'credited')
        self.assertFalse(self.client.get('/api/v1/games').json['games'][0]['new'])
        self.assertTrue(self.client.get('/api/v1/games').json['games'][0]['unlocked'])
        self.start()
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_sessions WHERE guest_token=?', (guest_token,)).fetchone()[0], 0)
        untouched = self.app.test_client()
        self.hello(profile=False, client=untouched)
        with untouched.session_transaction() as session:
            guest_token = session[GUEST_ATTEMPT_KEY]
        self.seed_lesson('bag', profile=None, guest=guest_token)
        with patch('services.journey_games.require_access'):
            guest = self.start(client=untouched)
        select_test_profile(untouched)
        self.assertEqual(untouched.get('/api/v1/games/sessions/' + guest['id']).status_code, 404)

    def test_concurrent_starts_share_one_active_session(self):
        select_test_profile(self.client)
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        token = self.token()
        cookie = self.client.get_cookie(self.app.config['SESSION_COOKIE_NAME'])
        def start(index):
            client = self.app.test_client()
            client.set_cookie(self.app.config['SESSION_COOKIE_NAME'], cookie.value)
            response = client.post('/api/v1/games/pack-bag/start', json={'request_id': 'parallel-' + str(index), 'options': {'source': 'first_steps'}}, headers={'X-CSRF-Token': token})
            self.assertEqual(response.status_code, 200, response.text)
            return response.json['id']
        with ThreadPoolExecutor(max_workers=3) as pool:
            sessions = list(pool.map(start, range(3)))
        self.assertEqual(len(set(sessions)), 1)

    def test_guest_pending_receipt_matches_claim_caps_and_never_promises_replay_coins(self):
        self.hello(profile=False)
        with self.client.session_transaction() as session:
            guest_token = session[GUEST_ATTEMPT_KEY]
        self.seed_lesson('bag', profile=None, guest=guest_token)
        with patch('services.journey_games.require_access'):
            state = self.start()
        first = self.finish(state)
        self.assertEqual(first['reward']['amount'], 3)
        with patch('services.journey_games.require_access'):
            state = self.start()
        replay = self.finish(state)
        self.assertEqual(replay['reward']['amount'], 0)
        for lesson_id in ('directions', 'help', 'set-off'):
            self.seed_lesson(lesson_id, profile=None, guest=guest_token)
        estimate = self.read(first['id'])
        self.assertEqual(estimate['reward']['amount'], 0)
        self.assertEqual(estimate['reward']['reason'], 'profile_needed')
        self.create_profile()
        claimed = self.read(first['id'])
        self.assertEqual(claimed['reward']['amount'], estimate['reward']['amount'])
        self.assertEqual(claimed['reward']['reason'], 'daily_cap')

    def seed_chapter(self):
        self.hello()
        for lesson_id in ('bag', 'directions', 'help', 'set-off'):
            self.seed_lesson(lesson_id)
        grant_earned_game_access(self.db)

    def test_all_six_new_games_have_complete_owned_replayable_flows(self):
        self.seed_chapter()
        games = self.client.get('/api/v1/games').json['games']
        self.assertEqual(len(games), 8)
        self.assertTrue(all(game['unlocked'] for game in games))
        for game in (game for game in games if game['id'] not in ('pack-bag', 'directions')):
            with self.subTest(game=game['id']):
                request_id = identifier()
                state = self.start(game['id'], request_id)
                self.assertEqual(state['round']['mechanic'], game['id'])
                self.assertEqual(state['source']['lesson_id'], 'scene-builder' if game['id']=='scene-builder' else game['lesson_id'])
                self.assertNotIn('expected_answer', state['round'])
                self.assertNotIn('answer_audio', state['round'])
                self.assertNotIn('vocabulary_refs', state)
                self.assertEqual(self.start(game['id'])['id'], state['id'])
                complete = self.finish(state)
                self.assertEqual(complete['phase'], 'completed')
                self.assertEqual(complete['summary']['correct_rounds'], 5 if game['id']=='scene-builder' else 3)
                self.assertTrue(complete['study_available'])
                self.assertEqual(self.start(game['id'], request_id)['id'], state['id'])
                self.assertEqual(self.read(state['id'])['phase'], 'completed')
                replay = self.finish(self.start(game['id']))
                self.assertEqual(replay['reward']['amount'], 0)
                self.assertEqual(replay['progression']['skill'], complete['progression']['skill'])

    def test_assignments_are_validated_by_mechanic_and_partial_accuracy_is_retained(self):
        self.seed_chapter()
        pairs = self.start('pairs')
        sid, item = pairs['id'], self.expected(pairs['id'])[0]
        answer = list(item['expected_answer'])
        self.post(sid, 'answer', {'round_id': item['id'], 'answer': answer[:1]}, status=400)
        self.post(sid, 'answer', {'round_id': item['id'], 'answer': [answer[0], answer[0]]}, status=400)
        duplicate_picture = [token.split(':')[0] + ':' + answer[0].split(':')[1] for token in answer]
        self.post(sid, 'answer', {'round_id': item['id'], 'answer': duplicate_picture}, status=400)
        self.post(sid, 'answer', {'round_id': item['id'], 'answer': ['other:picture-0', answer[1]]}, status=400)
        # Reordering the same completed matching is an idempotent answer.
        first = self.post(sid, 'answer', {'round_id': item['id'], 'answer': list(reversed(answer))})
        self.assertTrue(first['result']['correct'])
        self.assertEqual(self.post(sid, 'answer', {'round_id': item['id'], 'answer': answer}), first)
        sorting = self.start('mailbox-sort')
        item = self.expected(sorting['id'])[0]
        answer = list(item['expected_answer'])
        wrong_bin = next(entry['id'] for entry in item['bins'] if entry['id'] != answer[0].split(':')[1])
        answer[0] = answer[0].split(':')[0] + ':' + wrong_bin
        feedback = self.post(sorting['id'], 'answer', {'round_id': item['id'], 'answer': answer})
        self.assertFalse(feedback['result']['correct'])
        self.assertEqual((feedback['result']['matched'], feedback['result']['total']), (2, 3))
        self.assertAlmostEqual(feedback['result']['score'], 2 / 3)
        self.assertEqual(assess_answer(item, answer), {key: feedback['result'][key] for key in ('correct', 'score', 'matched', 'total')})
        letter = self.start('letter-back')
        item = self.expected(letter['id'])[0]
        answer = item['expected_answer']
        self.post(letter['id'], 'answer', {'round_id': item['id'], 'answer': [answer[0], answer[0]]}, status=400)
        self.post(letter['id'], 'answer', {'round_id': item['id'], 'answer': answer[:1]}, status=400)
        reversed_reply = self.post(letter['id'], 'answer', {'round_id': item['id'], 'answer': list(reversed(answer))})
        self.assertFalse(reversed_reply['result']['correct'])

    def test_cloze_and_reply_audio_are_revealed_only_with_saved_feedback(self):
        self.seed_chapter()
        for game_id in ('missing-stamp', 'letter-back'):
            state = self.start(game_id)
            item = self.expected(state['id'])[0]
            self.assertEqual(state['round']['clues'], [])
            self.assertNotIn('answer_audio', state['round'])
            if game_id == 'missing-stamp':
                self.assertIn('[[blank]]', state['round']['sentence'])
                self.assertTrue(state['round']['translation'])
                self.assertNotEqual(state['round']['sentence'], item['answer_audio'][0]['text'])
            feedback = self.post(state['id'], 'answer', {'round_id': item['id'], 'answer': item['expected_answer']})
            self.assertEqual(feedback['result']['answer_audio'], item['answer_audio'])
            self.assertNotIn('answer_audio', feedback['round'])
            for clue in feedback['result']['answer_audio']:
                response = self.client.get('/api/v1/games/media/' + clue['audio_key'] + '/status')
                self.assertEqual(response.status_code, 200, response.text)

    def test_completed_game_hides_native_study_when_flashcards_are_disabled(self):
        self.seed_chapter()
        completed = self.finish(self.start('missing-stamp'))
        self.assertTrue(completed['study_available'])
        self.app.config['NATIVE_FLASHCARDS_ENABLED'] = False
        self.assertFalse(self.read(completed['id'])['study_available'])
        self.assertTrue(self.client.get('/api/v1/games').json['games'][0]['unlocked'])

    def test_radio_requires_listening_or_transcript_and_keeps_support_receipts_separate(self):
        self.seed_chapter()
        state = self.start('radio')
        sid, rounds = state['id'], self.expected(state['id'])
        item, key = rounds[0], rounds[0]['clues'][0]['audio_key']
        self.assertEqual(state['round']['clues'], [{'audio_key': key}])
        self.post(sid, 'answer', {'round_id': item['id'], 'answer': item['expected_answer']}, status=409)
        self.post(sid, 'listen', {'round_id': item['id'], 'audio_key': key}, status=409)
        self.post(sid, 'listen', {'round_id': item['id'], 'audio_key': 'f' * 64}, status=400)
        media = self.app.extensions['learning']['journey_game_media']
        with patch.object(media, 'status', return_value={'status': 'ready', 'url': '/fixture-audio'}):
            heard = self.post(sid, 'listen', {'round_id': item['id'], 'audio_key': key})
        self.assertEqual(heard['round']['clues'], [{'audio_key': key}])
        self.assertEqual(heard['round']['support'], {'listened_audio_keys': [key], 'transcript': False})
        self.assertEqual(self.post(sid, 'listen', {'round_id': item['id'], 'audio_key': key}), heard)
        feedback = self.post(sid, 'answer', {'round_id': item['id'], 'answer': item['expected_answer']})
        self.assertEqual(feedback['round']['clues'], item['clues'])
        self.post(sid, 'continue', {'round_id': item['id']})
        next_item = rounds[1]
        transcript = self.post(sid, 'transcript', {'round_id': next_item['id']})
        self.assertEqual(transcript['round']['clues'], next_item['clues'])
        self.assertNotIn('hint', transcript['round'])
        self.assertTrue(transcript['round']['support']['transcript'])
        self.post(sid, 'answer', {'round_id': next_item['id'], 'answer': next_item['expected_answer']})
        self.post(sid, 'continue', {'round_id': next_item['id']})
        final_item = rounds[2]
        self.post(sid, 'hint', {'round_id': final_item['id']})
        self.post(sid, 'answer', {'round_id': final_item['id'], 'answer': final_item['expected_answer']}, status=409)
        self.post(sid, 'transcript', {'round_id': final_item['id']})
        self.post(sid, 'answer', {'round_id': final_item['id'], 'answer': final_item['expected_answer']})
        self.post(sid, 'continue', {'round_id': final_item['id']})
        self.post(sid, 'complete')
        with transaction(self.db) as conn:
            answers = json.loads(conn.execute('SELECT answers_json FROM journey_game_sessions WHERE id=?', (sid,)).fetchone()[0])
            self.assertEqual(answers[item['id']]['listened_audio_keys'], [key])
            self.assertFalse(answers[item['id']]['transcript_used'])
            self.assertFalse(answers[item['id']]['hint_used'])
            self.assertTrue(answers[next_item['id']]['transcript_used'])
            self.assertFalse(answers[next_item['id']]['hint_used'])
            self.assertTrue(answers[final_item['id']]['hint_used'])

    def test_related_lesson_language_remains_available_after_original_lessons_are_removed(self):
        self.seed_chapter()
        with transaction(self.db, write=True) as conn:
            _snapshot_legacy_unlocks(conn, 'personal-learning', None)
            frozen = json.loads(conn.execute("SELECT lesson_json FROM journey_game_unlocks WHERE game_id='letter-back'").fetchone()[0])
            self.assertTrue({'hello', 'bag', 'directions', 'help'}.issubset({item['id'] for item in frozen['related_lessons']}))
            conn.execute('DELETE FROM first_steps_attempts')
            conn.execute('DELETE FROM first_delivery_attempts')
        self.assertTrue(all(game['unlocked'] for game in self.client.get('/api/v1/games').json['games']))
        for game in GAMES[2:]:
            state = self.start(game['id'])
            self.assertEqual(state['phase'], 'play')
            self.assertEqual(state['source']['lesson_id'], 'scene-builder' if game['id']=='scene-builder' else game['lesson_id'])

    def test_schema_32_preserves_original_game_sessions_and_backfills_six_unlocks(self):
        self.seed_chapter()
        with transaction(self.db, write=True) as conn:
            _snapshot_legacy_unlocks(conn, 'personal-learning', None)
        finished = self.finish(self.start())
        active = self.start('directions')
        with sqlite3.connect(self.db) as conn:
            columns = [row[1] for row in conn.execute('PRAGMA table_info(journey_game_sessions)') if row[1] not in ('support_json', 'superseded_at')]
            sessions = conn.execute('SELECT rowid,' + ','.join(columns) + ' FROM journey_game_sessions ORDER BY rowid').fetchall()
            unlock_columns = [row[1] for row in conn.execute('PRAGMA table_info(journey_game_unlocks)')]
            unlocks = conn.execute("SELECT rowid," + ','.join(unlock_columns) + " FROM journey_game_unlocks WHERE game_id IN ('pack-bag','directions') ORDER BY rowid").fetchall()
            events = conn.execute('SELECT * FROM progression_events ORDER BY rowid').fetchall()
            strip_course_progression(conn)
            conn.execute('DROP TABLE step_conversation_answers')
            conn.execute('DROP TABLE step_conversation_sessions')
            conn.executescript('DROP TABLE journey_game_purchases; DROP TABLE journey_game_access; DROP TABLE journey_route_audio_cache; DROP TABLE journey_route_preparations; DROP TABLE journey_route_actions; DROP TABLE journey_route_state; DROP TABLE journey_game_corrections; DROP TABLE journey_game_preparations; DROP TABLE journey_game_examples; DROP TABLE journey_game_sessions; DROP TABLE journey_game_unlocks;')
            conn.executescript((MIGRATION_DIR / '030_journey_games.sql').read_text())
            conn.execute('DELETE FROM journey_game_unlocks')
            conn.executemany('INSERT INTO journey_game_unlocks(rowid,' + ','.join(unlock_columns) + ') VALUES (' + ','.join('?' for _ in range(len(unlock_columns) + 1)) + ')', unlocks)
            conn.executemany('INSERT INTO journey_game_sessions(rowid,' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in range(len(columns) + 1)) + ')', sessions)
            conn.execute('ALTER TABLE word_jumble_games DROP COLUMN task_json')
            conn.execute('DELETE FROM schema_migrations WHERE version>=32')
            self.assertNotIn('support_json', {row[1] for row in conn.execute('PRAGMA table_info(journey_game_sessions)')})
        self.assertEqual(upgrade_database(self.db, backup=False)[0], latest_schema_version())
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT rowid,' + ','.join(columns) + ' FROM journey_game_sessions ORDER BY rowid').fetchall(), sessions)
            self.assertEqual(conn.execute("SELECT rowid," + ','.join(unlock_columns) + " FROM journey_game_unlocks WHERE game_id IN ('pack-bag','directions') ORDER BY rowid").fetchall(), unlocks)
            self.assertEqual(conn.execute('SELECT * FROM progression_events ORDER BY rowid').fetchall(), events)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_unlocks').fetchone()[0], 9)
            self.assertEqual({row[0] for row in conn.execute('SELECT support_json FROM journey_game_sessions')}, {'{}'})
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.read(finished['id'])['phase'], 'completed')
        self.assertEqual(self.read(active['id'])['phase'], 'play')
        self.start('unregistered-game', status=404)


if __name__ == '__main__':
    unittest.main()
