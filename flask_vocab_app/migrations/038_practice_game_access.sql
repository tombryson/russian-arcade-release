-- Keep historical tutorial snapshots and saved games. They no longer grant
-- new game access. This table records milestones from core practice receipts.
CREATE TABLE journey_game_access (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 game_id TEXT NOT NULL,
 required_coins INTEGER NOT NULL CHECK(required_coins>0),
 earned_coins INTEGER NOT NULL CHECK(earned_coins>=required_coins),
 unlocked_at INTEGER NOT NULL,
 first_started_at INTEGER,
 policy_version TEXT NOT NULL,
 PRIMARY KEY(profile_id,game_id)
);
