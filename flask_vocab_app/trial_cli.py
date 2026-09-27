"""Explicit administration of the shared, persistent demo spending ledger."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from services.ai_trial_budget import (AITrialBudget, DAILY_LIMIT, MONTHLY_LIMIT, TOTAL_LIMIT,
    ACCOUNT_DAILY_LIMIT, ACCOUNT_TOTAL_LIMIT, ACCOUNT_OPERATIONS_PER_DAY, ACCOUNT_OPERATIONS_PER_MINUTE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'status', 'pause'))
    parser.add_argument('--root', default=os.environ.get('HOSTED_TRIAL_ROOT'))
    args = parser.parse_args()
    if not args.root:
        parser.error('Set HOSTED_TRIAL_ROOT or pass --root for the persistent workspace.')
    budget = AITrialBudget(Path(args.root) / 'ai-budget.sqlite3')
    if args.command == 'init':
        budget.initialize()
        print('Ledger initialized or upgraded. Existing spending is preserved; AI activation is unchanged.')
        return
    with budget._transaction() as conn:
        if args.command == 'pause':
            conn.execute('UPDATE trial_control SET halted=1 WHERE id=1')
        counts = dict(conn.execute('SELECT state,COUNT(*) FROM trial_requests GROUP BY state').fetchall())
        held = conn.execute("SELECT COALESCE(SUM(reserved),0) FROM trial_requests WHERE state!='settled'").fetchone()[0]
        now = datetime.fromtimestamp(budget.clock(), timezone.utc)
        day = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        month = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        remaining = {}
        for name, start, limit in (('shared_daily', day, DAILY_LIMIT), ('shared_monthly', month, MONTHLY_LIMIT), ('shared_total', 0, TOTAL_LIMIT)):
            spent = conn.execute("SELECT COALESCE(SUM(actual),0) FROM trial_requests WHERE state='settled' AND settled_at>=?", (start,)).fetchone()[0]
            remaining[name] = max(0, limit - spent - held) / 1_000_000
        print(json.dumps({'paused': bool(conn.execute('SELECT halted FROM trial_control WHERE id=1').fetchone()[0]),
            'operations': counts,
            'reserved_usd': held / 1_000_000,
            'limits_usd': {'account_daily': ACCOUNT_DAILY_LIMIT / 1_000_000, 'account_total': ACCOUNT_TOTAL_LIMIT / 1_000_000,
                'shared_daily': DAILY_LIMIT / 1_000_000, 'shared_monthly': MONTHLY_LIMIT / 1_000_000, 'shared_total': TOTAL_LIMIT / 1_000_000},
            'remaining_usd': remaining,
            'provider_operations_per_account': {'rolling_minute': ACCOUNT_OPERATIONS_PER_MINUTE, 'utc_day': ACCOUNT_OPERATIONS_PER_DAY},
            'accounted_usd': conn.execute('SELECT COALESCE(SUM(actual),0)/1000000.0 FROM trial_requests').fetchone()[0]}))


if __name__ == '__main__':
    main()
