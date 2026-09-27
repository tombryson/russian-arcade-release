from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.ai_trial_budget import AITrialBudget
from trial_cli import main


class TrialCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.now = 1789516800
        self.budget = AITrialBudget(self.root / 'ai-budget.sqlite3', enabled=True, clock=lambda: self.now)
        self.budget.initialize()
        self.budget.authorize_identity('private-test-account')
        self.budget.reserve('private-test-account', 'yesterday', 'a' * 64, 10_000)
        self.budget.settle('private-test-account', 'yesterday', 10_000)
        self.now += 86400
        self.budget.reserve('private-test-account', 'pending', 'b' * 64, 20_000)

    def command(self, command):
        output = StringIO()
        with patch('sys.argv', ['trial_cli.py', command, '--root', str(self.root)]), patch('trial_cli.AITrialBudget', return_value=self.budget), redirect_stdout(output):
            main()
        self.assertNotIn('private-test-account', output.getvalue())
        return json.loads(output.getvalue())

    def test_status_reports_limits_and_remaining_money_including_holds(self):
        status = self.command('status')
        self.assertEqual(status['limits_usd'], {'account_daily': 1, 'account_total': 2,
            'shared_daily': 1, 'shared_monthly': 20, 'shared_total': 10})
        self.assertEqual(status['remaining_usd'], {'shared_daily': .98, 'shared_monthly': 19.97, 'shared_total': 9.97})
        self.assertEqual(status['provider_operations_per_account'], {'rolling_minute': 30, 'utc_day': 120})
        self.assertEqual(status['operations'], {'reserved': 1, 'settled': 1})

    def test_pause_keeps_usage_and_pending_reservations(self):
        before = self.command('status')
        after = self.command('pause')
        self.assertFalse(before['paused'])
        self.assertTrue(after['paused'])
        for key in ('operations', 'reserved_usd', 'accounted_usd', 'remaining_usd'):
            self.assertEqual(after[key], before[key])
