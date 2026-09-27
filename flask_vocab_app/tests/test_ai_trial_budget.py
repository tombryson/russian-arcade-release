from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services.ai_trial_budget import (
    AITrialBudget, TrialDenied, ACCOUNT_OPERATIONS_PER_DAY,
    ACCOUNT_OPERATIONS_PER_MINUTE, ACCOUNT_DAILY_LIMIT, ACCOUNT_TOTAL_LIMIT,
    TOTAL_LIMIT,
)


class AITrialBudgetTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.path = Path(root.name) / 'spending.db'
        self.now = 1789516800  # UTC September 16, 2026.
        self.ledger = AITrialBudget(self.path, enabled=True, clock=lambda: self.now)
        self.ledger.initialize()
        for identity in ('a', 'b', 'c'):
            self.ledger.authorize_identity(identity)

    def reserve(self, identity='a', request='first', cost=400000):
        return self.ledger.reserve(identity, request, 'a' * 64, cost)

    def test_default_disabled_unknown_account_and_missing_storage_fail_closed(self):
        with self.assertRaises(TrialDenied):
            AITrialBudget(self.path).reserve('a', 'first', 'a' * 64, 1)
        with self.assertRaises(TrialDenied):
            self.reserve(identity='unverified')
        self.path.unlink()
        with self.assertRaises(TrialDenied):
            self.reserve()
        self.assertFalse(self.path.exists())

    @patch('services.ai_trial_budget.ACCOUNT_DAILY_LIMIT', 1000000)
    def test_concurrency_reserves_before_shared_daily_spend(self):
        def reserve(identity):
            try:
                return self.reserve(identity, cost=600000)['created']
            except TrialDenied:
                return False
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertEqual(sum(pool.map(reserve, ('a', 'b', 'c'))), 1)
        self.now += 86400
        self.ledger.authorize_identity('d')
        with self.assertRaisesRegex(TrialDenied, 'shared AI budget'):
            self.reserve('d', 'new-day', cost=600000)  # Old pending spend still counts.

    def test_retries_and_conflicting_payloads_do_not_make_new_reservations(self):
        self.assertTrue(self.reserve()['created'])
        self.assertFalse(self.reserve()['created'])
        with self.assertRaises(TrialDenied):
            self.ledger.reserve('a', 'first', 'b' * 64, 400000)
        self.ledger.uncertain('a', 'first')
        restarted = AITrialBudget(self.path, enabled=True, clock=lambda: self.now)
        self.assertEqual(restarted.reserve('a', 'first', 'a' * 64, 400000)['state'], 'uncertain')
        with self.assertRaises(TrialDenied):
            self.reserve('a', 'different-request')

    def test_account_and_global_concurrency_limits_apply_even_to_cheap_calls(self):
        self.reserve('a', cost=1)
        with self.assertRaises(TrialDenied):
            self.reserve('a', 'second', cost=1)
        self.reserve('b', cost=1)
        with self.assertRaises(TrialDenied):
            self.reserve('c', cost=1)
        self.ledger.settle('b', 'first', 0)
        self.assertTrue(self.reserve('c', cost=1)['created'])

    def test_same_request_race_admits_work_once(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.reserve(cost=1), range(16)))
        self.assertEqual(sum(row['created'] for row in results), 1)

    def test_daily_spend_and_per_account_allowance(self):
        for i in range(3):
            self.reserve(request=str(i), cost=100000)
            self.ledger.settle('a', str(i), 100000)
        self.reserve('b', cost=500000)
        self.ledger.settle('b', 'first', 500000)
        self.reserve('c', cost=200000)
        self.ledger.settle('c', 'first', 200000)
        with self.assertRaises(TrialDenied):
            self.reserve('c', 'exhausted', cost=1)
        self.now += 86400
        self.assertTrue(self.reserve('c', 'tomorrow', cost=1)['created'])

    def test_provider_operation_cap_allows_workflows_but_stops_abuse(self):
        for index in range(ACCOUNT_OPERATIONS_PER_DAY):
            self.reserve(request=str(index), cost=1)
            self.ledger.settle('a', str(index), 1)
            self.now += 3  # Isolate the daily cap from the rolling burst cap.
        with self.assertRaises(TrialDenied):
            self.reserve(request='one-more', cost=1)

    def test_unknown_usage_charges_reservation_without_locking_account(self):
        self.reserve(cost=10000)
        self.ledger.charge_reservation('a', 'first')
        self.assertTrue(self.reserve(request='next', cost=1)['created'])

    def test_voice_hold_allows_one_metered_delegate_but_no_second_voice(self):
        self.ledger.reserve('a', 'voice', 'b' * 64, 100000, lane='voice')
        self.assertTrue(self.reserve(request='delegate', cost=1000)['created'])
        with self.assertRaises(TrialDenied):
            self.reserve(request='parallel', cost=1)
        self.ledger.settle('a', 'delegate', 1000)
        with self.assertRaises(TrialDenied):
            self.ledger.reserve('a', 'voice2', 'b' * 64, 100000, lane='voice')
        self.assertTrue(self.reserve(request='next-delegate', cost=1000)['created'])

    @patch('services.ai_trial_budget.ACCOUNT_DAILY_LIMIT', 1000000)
    @patch('services.ai_trial_budget.ACCOUNT_TOTAL_LIMIT', 30000000)
    @patch('services.ai_trial_budget.TOTAL_LIMIT', 30000000)
    def test_monthly_spend_survives_day_rollover_and_process_restart(self):
        # Start early enough for twenty days in one calendar month.
        self.now -= 15 * 86400
        for day in range(20):
            self.reserve(request=str(day), cost=1000000)
            self.ledger.settle('a', str(day), 1000000)
            self.now += 86400
        self.ledger = AITrialBudget(self.path, enabled=True, clock=lambda: self.now)
        with self.assertRaises(TrialDenied):
            self.reserve('b', cost=1)

    def test_underestimated_usage_halts_new_work_and_cannot_be_refunded_by_retry(self):
        self.reserve(cost=100000)
        self.ledger.settle('a', 'first', 100001)
        with self.assertRaises(TrialDenied):
            self.reserve('b', cost=1)
        with self.assertRaises(TrialDenied):
            self.ledger.settle('a', 'first', 0)

    def test_daily_account_allowance_includes_settled_usage_and_voice_hold(self):
        self.reserve(cost=600000)
        self.ledger.settle('a', 'first', 600000)
        self.ledger.reserve('a', 'voice', 'b' * 64, 400000, lane='voice')
        # A delegate normally runs alongside its voice hold, but cannot exceed
        # their account's combined allowance.
        with self.assertRaisesRegex(TrialDenied, 'today’s AI allowance'):
            self.reserve(request='delegate', cost=1)
        self.now += 86400
        self.assertTrue(self.reserve('b', cost=1)['created'])

    def test_account_pending_holds_survive_month_rollover_and_reinitialization(self):
        self.ledger.reserve('a', 'voice', 'b' * 64, 900000, lane='voice')
        self.ledger.uncertain('a', 'voice')
        self.now += 40 * 86400
        self.ledger = AITrialBudget(self.path, enabled=True, clock=lambda: self.now)
        self.ledger.initialize()
        self.ledger.authorize_identity('a')
        with self.assertRaisesRegex(TrialDenied, 'today’s AI allowance'):
            self.reserve(request='too-much', cost=100001)
        self.assertTrue(self.reserve(request='within-remaining', cost=100000)['created'])

    def test_account_lifetime_limit_survives_day_month_restart_and_authorization(self):
        for index in range(ACCOUNT_TOTAL_LIMIT // ACCOUNT_DAILY_LIMIT):
            request = f'day-{index}'
            self.reserve(request=request, cost=ACCOUNT_DAILY_LIMIT)
            self.ledger.settle('a', request, ACCOUNT_DAILY_LIMIT)
            self.now += 86400
        self.now += 40 * 86400
        self.ledger = AITrialBudget(self.path, enabled=True, clock=lambda: self.now)
        self.ledger.initialize()
        self.ledger.authorize_identity('a')
        with self.assertRaisesRegex(TrialDenied, 'your AI demo allowance'):
            self.reserve(request='fresh-browser', cost=1)
        # Retrying already-settled work does not consume the allowance again.
        self.assertFalse(self.reserve(request='day-0', cost=ACCOUNT_DAILY_LIMIT)['created'])
        self.assertTrue(self.reserve('b', cost=1)['created'])

    @patch('services.ai_trial_budget.ACCOUNT_TOTAL_LIMIT', 500000)
    def test_account_lifetime_limit_includes_previous_period_uncertain_hold(self):
        self.reserve(cost=300000)
        self.ledger.settle('a', 'first', 300000)
        self.ledger.reserve('a', 'voice', 'b' * 64, 200000, lane='voice')
        self.ledger.uncertain('a', 'voice')
        self.now += 40 * 86400
        with self.assertRaisesRegex(TrialDenied, 'your AI demo allowance'):
            self.reserve(request='delegate', cost=1)

    def test_shared_lifetime_limit_survives_month_rollover_and_new_account(self):
        for index in range(TOTAL_LIMIT // ACCOUNT_DAILY_LIMIT):
            identity = f'learner-{index // (ACCOUNT_TOTAL_LIMIT // ACCOUNT_DAILY_LIMIT)}'
            self.ledger.authorize_identity(identity)
            request = f'day-{index}'
            self.reserve(identity, request, cost=ACCOUNT_DAILY_LIMIT)
            self.ledger.settle(identity, request, ACCOUNT_DAILY_LIMIT)
            self.now += 86400
        self.now += 40 * 86400
        self.ledger = AITrialBudget(self.path, enabled=True, clock=lambda: self.now)
        self.ledger.initialize()
        with self.assertRaisesRegex(TrialDenied, 'shared AI demo allowance'):
            self.reserve('c', 'new-month', cost=1)

    @patch('services.ai_trial_budget.TOTAL_LIMIT', 600000)
    def test_shared_lifetime_admission_is_atomic_across_accounts(self):
        def reserve(identity):
            try:
                return self.reserve(identity)['created']
            except TrialDenied:
                return False
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertEqual(sum(pool.map(reserve, ('a', 'b', 'c'))), 1)
        # No calendar reset releases an unresolved provider charge.
        self.now += 40 * 86400
        self.ledger.authorize_identity('d')
        with self.assertRaisesRegex(TrialDenied, 'shared AI demo allowance'):
            self.reserve('d', cost=200001)

    def test_rolling_burst_counts_all_lanes_and_zero_cost_results(self):
        for index in range(ACCOUNT_OPERATIONS_PER_MINUTE):
            self.ledger.reserve('a', str(index), 'a' * 64, 1,
                                lane='voice' if index % 2 else 'operation')
            self.ledger.settle('a', str(index), 0)
        with self.assertRaisesRegex(TrialDenied, 'wait a minute'):
            self.reserve(request='over-burst', cost=1)
        # An exact retry succeeds, but never creates another provider request.
        self.assertFalse(self.reserve(request='0', cost=1)['created'])
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM trial_requests').fetchone()[0],
                             ACCOUNT_OPERATIONS_PER_MINUTE)
        self.now += 59
        restarted = AITrialBudget(self.path, enabled=True, clock=lambda: self.now)
        with self.assertRaisesRegex(TrialDenied, 'wait a minute'):
            restarted.reserve('a', 'after-restart', 'a' * 64, 1)
        self.now += 1
        self.assertTrue(restarted.reserve('a', 'after-minute', 'a' * 64, 1)['created'])

    def test_burst_allowance_is_per_account_and_denials_are_not_new_requests(self):
        for index in range(ACCOUNT_OPERATIONS_PER_MINUTE):
            self.reserve(request=str(index), cost=1)
            self.ledger.charge_reservation('a', str(index))
        for _ in range(3):
            with self.assertRaisesRegex(TrialDenied, 'wait a minute'):
                self.reserve(request='repeated-click', cost=1)
        self.assertTrue(self.reserve('b', cost=1)['created'])
        self.now += 60
        self.assertTrue(self.reserve(request='repeated-click', cost=1)['created'])
