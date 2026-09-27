import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from migrations import upgrade_database
from repositories.learning_repository import LearningError, transaction
from services.demo_limits import DemoLimits
from services.personal_learning import PersonalSessions


class DemoLimitsTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.database = str(Path(root.name) / 'demo.db')
        upgrade_database(self.database, backup=False)
        self.now = 120
        self.limits = DemoLimits(self.database, clock=lambda: self.now)

    def test_concurrent_requests_cannot_exceed_shared_allowance(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            waits = list(pool.map(lambda _: self.limits.consume([('global', 60, 5)]), range(20)))
        self.assertEqual(waits.count(0), 5)
        self.assertEqual(waits.count(60), 15)

    def test_rejected_requests_do_not_consume_other_limits_and_expiry_is_bounded(self):
        self.assertEqual(self.limits.consume([('global', 60, 1)]), 0)
        self.assertEqual(self.limits.consume([('visitor', 60, 2), ('global', 60, 1)]), 60)
        with transaction(self.database) as conn:
            self.assertIsNone(conn.execute("SELECT * FROM demo_limits WHERE scope='visitor'").fetchone())
        self.now = 181
        self.assertEqual(self.limits.consume([('global', 60, 1)]), 0)
        with transaction(self.database) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM demo_limits').fetchone()[0], 1)

    def test_new_limiter_instance_preserves_counters(self):
        self.limits.consume([('writes', 86400, 1)])
        restarted = DemoLimits(self.database, clock=lambda: self.now)
        self.assertGreater(restarted.consume([('writes', 86400, 1)]), 0)

    def test_profile_limit_is_atomic(self):
        sessions = PersonalSessions(self.database)
        with transaction(self.database) as conn:
            initial = conn.execute('SELECT COUNT(*) FROM learning_profiles').fetchone()[0]

        def create(_):
            try:
                sessions.create('Demo visitor', max_profiles=initial + 2)
                return True
            except LearningError as error:
                self.assertEqual(error.code, 'demo_full')
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(create, range(12)))
        self.assertEqual(sum(accepted), 2)
