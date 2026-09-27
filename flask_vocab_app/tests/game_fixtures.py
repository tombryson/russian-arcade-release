"""Access fixtures for testing game mechanics independently of earning coins."""
from repositories.learning_repository import transaction
from services.game_access import LEGACY_THRESHOLDS


def grant_earned_game_access(db, *, profile='personal-learning', earned=96):
    """Restore durable milestones earned before this test's practice session.

    Policy tests should earn real ledger receipts. Mechanics tests use the
    persisted grant so their reward and daily-cap assertions stay independent.
    """
    with transaction(db, write=True) as conn:
        for game, required in LEGACY_THRESHOLDS.items():
            if earned >= required:
                conn.execute(
                    'INSERT OR IGNORE INTO journey_game_access '
                    '(profile_id,game_id,unlocked_at,policy_version) '
                    'VALUES (?,?,?,?)', (profile, game, 1, 'grandfathered-test-v1'))
