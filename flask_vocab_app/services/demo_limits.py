"""Atomic limits for the anonymous, provider-free demo.

Counters belong to the disposable demo database. They are not a paid-AI budget
ledger: that must survive deployments and use verified account identities.
"""
import time

from repositories.learning_repository import transaction


class DemoLimits:
    def __init__(self, database, clock=time.time):
        self.database, self.clock = database, clock
        with transaction(database, write=True) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS demo_limits (
                scope TEXT NOT NULL, window INTEGER NOT NULL, duration INTEGER NOT NULL,
                used INTEGER NOT NULL CHECK(used >= 0),
                PRIMARY KEY(scope, window, duration))''')

    def consume(self, limits):
        """Consume all (scope, duration seconds, capacity) limits or none.

        Return the longest required wait in seconds, or zero on admission.
        BEGIN IMMEDIATE serializes checks across threads and processes.
        """
        now = int(self.clock())
        with transaction(self.database, write=True) as conn:
            conn.execute('DELETE FROM demo_limits WHERE window + duration <= ?', (now,))
            buckets, retry_after = [], 0
            for scope, duration, capacity in limits:
                window = now // duration * duration
                row = conn.execute('SELECT used FROM demo_limits WHERE scope=? AND window=? AND duration=?',
                                   (scope, window, duration)).fetchone()
                if row and row['used'] >= capacity:
                    retry_after = max(retry_after, window + duration - now)
                buckets.append((scope, window, duration))
            if retry_after:
                return retry_after
            for bucket in buckets:
                conn.execute('''INSERT INTO demo_limits(scope,window,duration,used) VALUES (?,?,?,1)
                    ON CONFLICT(scope,window,duration) DO UPDATE SET used=used+1''', bucket)
        return 0
