"""Permanent purchases, shared wallet accounting and migration guarantees."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
import threading
import unittest

from migrations import MIGRATION_DIR, upgrade_database
from repositories.learning_repository import LearningError, encoded, identifier, timestamp, transaction
from services.first_steps import chapter_content
from services.game_access import access_state, purchase, wallet_balance
from services.progression import award, reverse, snapshot
from services.scene_builder import build_content, options as scene_options
from tests.support import isolated_app, select_test_profile, latest_schema_version, strip_course_progression
from tests import test_first_steps


class GameAccessTests(unittest.TestCase):
    token = test_first_steps.FirstStepsTests.token
    request = test_first_steps.FirstStepsTests.request
    post = test_first_steps.FirstStepsTests.post
    hello = test_first_steps.FirstStepsTests.hello
    definition = test_first_steps.FirstStepsTests.definition
    prepare = test_first_steps.FirstStepsTests.prepare
    finish = test_first_steps.FirstStepsTests.finish

    def setUp(self):
        self.app = isolated_app(self, signed_in=False)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.content = chapter_content()
        select_test_profile(self.client)

    def receipt(self, conn, amount, activity='reading', profile='personal-learning', *, eligible=1, event=True):
        receipt_id, now = identifier(), timestamp()
        category = 'legacy' if not event and not eligible else ('review' if activity == 'flashcards' else 'activity')
        if event:
            conn.execute('INSERT INTO progression_events VALUES (?,?,?,?,?,?,?,?,?,?,NULL)',
                         (receipt_id, profile, activity, receipt_id, receipt_id, 'Saved practice', category, None, '{}', now))
        conn.execute('INSERT INTO progression_entries VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                     (identifier(), profile, receipt_id if event else None, receipt_id, amount, eligible,
                      category, '2000-01-01', 'Saved practice', 'fixture-v1', now))
        return receipt_id

    def fund(self, amount=100, **kwargs):
        with transaction(self.db, write=True) as conn:
            return self.receipt(conn, amount, **kwargs)

    def legacy_unlock(self, conn, game='scene-builder'):
        lesson = deepcopy(self.definition('bag')) | {'version': self.content['version']}
        conn.execute('INSERT INTO journey_game_unlocks(id,profile_id,game_id,lesson_id,lesson_version,lesson_json,unlocked_at) VALUES (?,?,?,?,?,?,?)',
                     (identifier(), 'personal-learning', game, 'bag', lesson['version'], encoded(lesson), timestamp()))

    def saved_scene(self, conn, *, sample=False):
        session_id, now = identifier(), timestamp()
        content = build_content('saved-before-access-change', scene_options({'grammar_focus': 'location'}))
        if sample:
            content['sample'] = True
        conn.execute('INSERT INTO journey_game_sessions(id,profile_id,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                     (session_id, 'personal-learning', 'scene-builder', 'old-seed', '["old-scene-request"]', encoded(content), now, now))
        return session_id, encoded(content)

    def catalogue(self):
        response = self.client.get('/api/v1/games')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json, {game['id']: game for game in response.json['games']}

    def buy(self, game='scene-builder', request_id='first-purchase', price=25, status=200):
        return self.request('/api/v1/games/' + game + '/purchase',
                            {'request_id': request_id, 'expected_price': price}, status=status)

    def test_all_intro_lessons_keep_rewards_but_unlock_no_games(self):
        self.hello()
        for lesson in self.content['lessons']:
            self.finish(lesson['id'])
        with transaction(self.db) as conn:
            self.assertGreater(wallet_balance(conn, 'personal-learning'), 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_access').fetchone()[0], 0)
        self.assertTrue(all(not game['unlocked'] for game in self.catalogue()[1].values()))

    def test_large_wallet_and_core_rewards_never_automatically_unlock(self):
        self.fund(1000)
        with transaction(self.db, write=True) as conn:
            award(conn, 'personal-learning', activity='reading', content_key='new-reading',
                  source_key='new-reading', title='Reading')
        for _ in range(2):
            state, games = self.catalogue()
            self.assertEqual(state['shop'], {'balance': 1003, 'first_purchase': True, 'price': 25, 'enabled': True})
            self.assertTrue(all(not game['unlocked'] and game['purchase']['can_purchase'] for game in games.values()))
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_access').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_purchases').fetchone()[0], 0)

    def test_first_choice_costs_25_then_any_other_costs_50(self):
        self.fund(100)
        first = self.buy('directions')
        self.assertEqual({k: first[k] for k in ('game_id', 'charged', 'balance', 'owned', 'already_owned')},
                         {'game_id': 'directions', 'charged': 25, 'balance': 75, 'owned': True, 'already_owned': False})
        state, games = self.catalogue()
        self.assertFalse(state['shop']['first_purchase'])
        self.assertEqual(state['shop']['price'], 50)
        self.assertTrue(games['directions']['purchase']['owned'])
        self.assertFalse(games['directions']['purchase']['can_purchase'])
        second = self.buy('scene-builder', 'second-purchase', 50)
        self.assertEqual((second['charged'], second['balance']), (50, 25))
        state, games = self.catalogue()
        self.assertTrue(games['scene-builder']['unlocked'])
        self.assertFalse(games['radio']['purchase']['can_purchase'])

    def test_old_wallet_and_intro_coins_are_spendable(self):
        self.fund(10, event=False, eligible=0)
        self.fund(15, activity='first_steps')
        self.assertEqual(self.buy()['balance'], 0)
        with transaction(self.db) as conn:
            self.assertEqual(wallet_balance(conn, 'personal-learning'), 0)
            row = conn.execute("SELECT * FROM progression_entries WHERE category='purchase'").fetchone()
            self.assertEqual((row['amount'], row['eligible'], row['event_id']), (-25, 0, None))

    def test_retry_is_identical_and_owned_click_never_charges_again(self):
        self.fund(100)
        first = self.buy()
        self.assertEqual(first, self.buy())
        owned = self.buy(request_id='another-request', price=25)
        self.assertEqual((owned['charged'], owned['balance'], owned['already_owned']), (0, 75, True))
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_entries WHERE category='purchase'").fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_access').fetchone()[0], 1)

    def test_reusing_purchase_request_for_other_choice_is_conflict(self):
        self.fund(100)
        self.buy()
        for game, price in (('directions', 25), ('scene-builder', 50)):
            result = self.buy(game, price=price, status=409)
            self.assertEqual(result['error']['code'], 'idempotency_conflict')

    def test_failed_receipt_rolls_back_debit_and_ownership_together(self):
        self.fund(100)
        with transaction(self.db, write=True) as conn:
            conn.execute("CREATE TRIGGER test_purchase_failure BEFORE INSERT ON journey_game_purchases "
                         "BEGIN SELECT RAISE(ABORT,'Simulated storage failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.buy()
        with transaction(self.db) as conn:
            self.assertEqual(wallet_balance(conn, 'personal-learning'), 100)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_access').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_purchases').fetchone()[0], 0)

    def test_stale_price_never_silently_charges_higher_amount(self):
        self.fund(100)
        self.buy()
        stale = self.buy('directions', 'stale-price', 25, status=409)
        self.assertEqual(stale['error']['code'], 'price_changed')
        self.assertEqual(stale['error']['price'], 50)
        with transaction(self.db) as conn:
            self.assertEqual(wallet_balance(conn, 'personal-learning'), 75)
            self.assertFalse(access_state(conn, 'personal-learning')['directions']['unlocked'])
        self.assertEqual(self.buy('directions', 'stale-price', 50)['charged'], 50)

    def test_insufficient_balance_changes_nothing(self):
        self.fund(24)
        result = self.buy(status=409)
        self.assertEqual(result['error']['code'], 'insufficient_coins')
        with transaction(self.db) as conn:
            self.assertEqual(wallet_balance(conn, 'personal-learning'), 24)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_purchases').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_access').fetchone()[0], 0)
        self.fund(1)
        self.assertEqual(self.buy()['charged'], 25)

    def test_profile_required_and_other_profile_cannot_spend_or_inherit_access(self):
        self.fund(100)
        self.buy()
        guest = self.app.test_client()
        token = guest.get('/api/v1/games').json['csrf_token']
        response = guest.post('/api/v1/games/directions/purchase',
                              json={'request_id': 'guest-purchase', 'expected_price': 25}, headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json['error']['code'], 'profile_required')
        self.assertIsNone(guest.get('/api/v1/games').json['shop']['balance'])
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)", (timestamp(),))
        select_test_profile(self.client, 'other')
        self.assertFalse(self.catalogue()[1]['scene-builder']['unlocked'])
        self.assertTrue(self.catalogue()[0]['shop']['first_purchase'])
        self.assertEqual(self.buy(status=409)['error']['code'], 'insufficient_coins')

    def test_post_requires_csrf_and_strict_price(self):
        self.fund(100)
        response = self.client.post('/api/v1/games/scene-builder/purchase', json={'request_id': 'no-csrf', 'expected_price': 25})
        self.assertEqual(response.status_code, 403)
        for price in (True, '25', -1, 25.0):
            self.assertEqual(self.buy(price=price, status=400)['error']['code'], 'invalid_price')
        self.assertEqual(self.buy('unknown', status=404)['error']['code'], 'not_found')
        self.assertEqual(self.buy('pairs', status=404)['error']['code'], 'not_found')

    def test_purchase_does_not_change_skill_earned_total_daily_allowance_or_journey(self):
        self.fund(100)
        with transaction(self.db, write=True) as conn:
            award(conn, 'personal-learning', activity='reading', content_key='before', source_key='before', title='Reading')
            before = snapshot(conn, 'personal-learning')
            tables = {name: [tuple(row) for row in conn.execute('SELECT * FROM ' + name)]
                      for name in ('progression_events', 'progression_claims', 'journey_progress')}
        self.buy()
        with transaction(self.db, write=True) as conn:
            after = snapshot(conn, 'personal-learning')
            self.assertEqual(after['balance'], before['balance'] - 25)
            for field in ('earned_total', 'legacy_balance', 'skill', 'journey'):
                self.assertEqual(after[field], before[field], field)
            for name, rows in tables.items():
                self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM ' + name)], rows, name)
            rewards = [award(conn, 'personal-learning', activity='reading', content_key=str(i), source_key=str(i), title='Reading') for i in range(4)]
            self.assertEqual(rewards, [3, 3, 3, 0])

    def test_undo_after_spending_keeps_right_and_append_only_history(self):
        self.fund(22)
        with transaction(self.db, write=True) as conn:
            award(conn, 'personal-learning', activity='reading', content_key='undoable', source_key='undoable', title='Reading')
        self.buy()
        with transaction(self.db, write=True) as conn:
            self.assertEqual(reverse(conn, 'personal-learning', 'reading', 'undoable'), -3)
            self.assertEqual(wallet_balance(conn, 'personal-learning'), -3)
            self.assertTrue(access_state(conn, 'personal-learning')['scene-builder']['unlocked'])
            self.assertFalse(access_state(conn, 'personal-learning')['directions']['purchase']['can_purchase'])
        self.assertEqual(self.catalogue()[0]['shop']['balance'], -3)
        for table in ('progression_entries', 'journey_game_purchases'):
            with self.assertRaises(sqlite3.IntegrityError):
                with transaction(self.db, write=True) as conn:
                    conn.execute('DELETE FROM ' + table)

    def test_paid_purchase_opens_game_without_introduction(self):
        self.fund(25)
        self.buy()
        self.assertTrue(self.catalogue()[1]['scene-builder']['new'])
        state = self.request('/api/v1/games/scene-builder/start',
                             {'request_id': 'purchased-scene', 'options': {'grammar_focus': 'location'}})
        self.assertEqual(state['phase'], 'play')
        self.assertFalse(self.catalogue()[1]['scene-builder']['new'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_steps_attempts').fetchone()[0], 0)

    def test_legacy_intro_unlock_cannot_bypass_any_game_start(self):
        with transaction(self.db, write=True) as conn:
            for game in ('pack-bag', 'scene-builder', 'directions'):
                self.legacy_unlock(conn, game)
        for game, options in (('pack-bag', {}), ('pack-bag', {'source': 'first_steps'}),
                              ('scene-builder', {'grammar_focus': 'location'}), ('directions', {})):
            with self.subTest(game=game, options=options):
                response = self.request(f'/api/v1/games/{game}/start',
                                        {'request_id': identifier(), 'options': options}, status=409)
                self.assertEqual(response['error']['code'], 'game_locked')

    def migrate_from_38(self, *, sample=False):
        with transaction(self.db, write=True) as conn:
            self.legacy_unlock(conn, 'radio')
            session_id, saved_content = self.saved_scene(conn, sample=sample)
            self.receipt(conn, 100, 'first_steps')
            before_ledger = [tuple(row) for row in conn.execute('SELECT rowid,* FROM progression_entries')]
            strip_course_progression(conn)
            conn.execute('DROP TABLE journey_game_purchases')
            conn.execute('DROP TABLE journey_game_access')
            conn.execute('DROP TABLE step_conversation_answers')
            conn.execute('DROP TABLE step_conversation_sessions')
            conn.execute((MIGRATION_DIR / '038_practice_game_access.sql').read_text())
            conn.execute('INSERT INTO journey_game_access VALUES (?,?,?,?,?,?,?)',
                         ('personal-learning', 'pack-bag', 12, 12, 123, None, 'practice-coins-v1'))
            conn.execute('ALTER TABLE word_jumble_games DROP COLUMN task_json')
            conn.execute('DELETE FROM schema_migrations WHERE version>=39')
        self.assertEqual(upgrade_database(self.db, backup=False)[0], latest_schema_version())
        with transaction(self.db) as conn:
            self.assertEqual([tuple(row) for row in conn.execute('SELECT rowid,* FROM progression_entries')], before_ledger)
            self.assertEqual(conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?', (session_id,)).fetchone()[0], saved_content)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_unlocks').fetchone()[0], 1)
        return session_id

    def test_migration_keeps_rights_and_real_sessions_but_not_unused_intro_unlocks(self):
        session_id = self.migrate_from_38()
        state, games = self.catalogue()
        self.assertTrue(games['pack-bag']['unlocked'])
        self.assertTrue(games['scene-builder']['unlocked'])
        self.assertFalse(games['radio']['unlocked'])
        self.assertEqual(games['scene-builder']['active_session_id'], session_id)
        self.assertTrue(state['shop']['first_purchase'])
        self.assertEqual(self.client.get('/api/v1/games/sessions/' + session_id).status_code, 200)
        self.assertEqual(self.buy('radio')['charged'], 25)
        self.assertEqual(upgrade_database(self.db, backup=False)[0], latest_schema_version())
        other = self.app.test_client()
        self.assertEqual(other.get('/api/v1/games/sessions/' + session_id).status_code, 404)

    def test_demo_sessions_never_become_owned_on_migration(self):
        self.migrate_from_38(sample=True)
        self.assertFalse(self.catalogue()[1]['scene-builder']['unlocked'])

    def test_grandfathered_right_does_not_consume_discount(self):
        self.fund(100)
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO journey_game_access VALUES (?,?,?,?,?)',
                         ('personal-learning', 'scene-builder', 1, 1, 'practice-coins-v1'))
        self.assertEqual(self.buy('scene-builder')['charged'], 0)
        self.assertTrue(self.catalogue()[0]['shop']['first_purchase'])
        self.assertEqual(self.buy('directions', 'first-paid')['charged'], 25)

    def concurrent(self, choices):
        barrier = threading.Barrier(len(choices))
        def attempt(args):
            barrier.wait(timeout=5)
            try:
                with transaction(self.db, write=True) as conn:
                    return purchase(conn, 'personal-learning', *args)
            except LearningError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=len(choices)) as pool:
            return list(pool.map(attempt, choices))

    def test_concurrent_same_game_charges_once(self):
        self.fund(100)
        results = self.concurrent([('scene-builder', 'parallel-one', 25), ('scene-builder', 'parallel-two', 25)])
        self.assertEqual(sorted(row['charged'] for row in results), [0, 25])
        with transaction(self.db) as conn:
            self.assertEqual(wallet_balance(conn, 'personal-learning'), 75)

    def test_concurrent_same_request_returns_same_receipt(self):
        self.fund(100)
        results = self.concurrent([('scene-builder', 'same-request', 25)] * 2)
        self.assertEqual(results[0], results[1])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_purchases').fetchone()[0], 1)

    def test_concurrent_different_games_cannot_both_claim_first_discount(self):
        self.fund(100)
        results = self.concurrent([('scene-builder', 'parallel-one', 25), ('directions', 'parallel-two', 25)])
        self.assertEqual(sum(isinstance(row, dict) for row in results), 1)
        self.assertIn('price_changed', results)
        with transaction(self.db) as conn:
            self.assertEqual(wallet_balance(conn, 'personal-learning'), 75)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_access').fetchone()[0], 1)

    def test_concurrent_full_price_purchases_cannot_overspend(self):
        self.fund(75)
        self.buy('pack-bag')
        results = self.concurrent([('scene-builder', 'parallel-one', 50), ('directions', 'parallel-two', 50)])
        self.assertEqual(sum(isinstance(row, dict) for row in results), 1)
        self.assertIn('insufficient_coins', results)
        with transaction(self.db) as conn:
            self.assertEqual(wallet_balance(conn, 'personal-learning'), 0)

    def test_demo_samples_remain_available_but_shop_is_disabled(self):
        self.app.config['PUBLIC_DEMO'] = True
        self.fund(100)
        state, games = self.catalogue()
        self.assertFalse(state['shop']['enabled'])
        for game in ('pack-bag', 'scene-builder', 'directions', 'missing-stamp'):
            self.assertTrue(games[game]['unlocked'])
            self.assertFalse(games[game]['purchase']['can_purchase'])
            self.assertEqual(games[game]['availability'], 'sample')
        self.assertFalse(games['radio']['unlocked'])
        self.assertEqual(self.buy(status=403)['error']['code'], 'demo_unavailable')
        with transaction(self.db) as conn:
            self.assertEqual(wallet_balance(conn, 'personal-learning'), 100)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_access').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
