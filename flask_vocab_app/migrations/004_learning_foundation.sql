-- Additive household foundation. Legacy vocabulary, users and Anki rows are untouched.
CREATE TABLE IF NOT EXISTS household_settings (
 id INTEGER PRIMARY KEY CHECK (id = 1), name TEXT NOT NULL,
 pin_hash TEXT NOT NULL, failed_unlocks INTEGER NOT NULL DEFAULT 0,
 locked_until INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_profiles (
 id TEXT PRIMARY KEY, display_name TEXT NOT NULL, avatar TEXT NOT NULL,
 study_timezone TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
 legacy_user_id INTEGER UNIQUE REFERENCES users(user_id), created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS household_access (
 id TEXT PRIMARY KEY, profile_id TEXT REFERENCES learning_profiles(id),
 adult_until INTEGER NOT NULL, expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_assets (
 id TEXT PRIMARY KEY, storage_key TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
 byte_size INTEGER NOT NULL CHECK (byte_size > 0), media_type TEXT NOT NULL,
 source TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_content (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('deck','activity')),
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_content_versions (
 id TEXT PRIMARY KEY, content_id TEXT NOT NULL REFERENCES learning_content(id),
 version INTEGER NOT NULL CHECK (version > 0), title TEXT NOT NULL,
 payload TEXT NOT NULL CHECK (json_valid(payload)),
 status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','withdrawn')),
 source TEXT NOT NULL, created_at INTEGER NOT NULL,
 approved_by TEXT, approved_at INTEGER,
 UNIQUE(content_id, version),
 CHECK (status = 'draft' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE TRIGGER IF NOT EXISTS learning_content_immutable
BEFORE UPDATE ON learning_content_versions
WHEN NEW.payload != OLD.payload OR NEW.content_id != OLD.content_id
 OR NEW.version != OLD.version OR NEW.title != OLD.title OR NEW.source != OLD.source
 OR NEW.created_at != OLD.created_at
 OR (OLD.status != 'draft' AND (NEW.approved_by IS NOT OLD.approved_by OR NEW.approved_at IS NOT OLD.approved_at))
 OR (OLD.status = 'withdrawn' AND NEW.status != 'withdrawn')
 OR (OLD.status = 'published' AND NEW.status = 'draft')
BEGIN
 SELECT RAISE(ABORT, 'Content versions are immutable; create a new draft');
END;
CREATE TABLE IF NOT EXISTS learning_content_assets (
 version_id TEXT NOT NULL REFERENCES learning_content_versions(id),
 asset_id TEXT NOT NULL REFERENCES learning_assets(id), PRIMARY KEY(version_id, asset_id)
);
CREATE TABLE IF NOT EXISTS learning_content_words (
 version_id TEXT NOT NULL REFERENCES learning_content_versions(id), item_id TEXT NOT NULL,
 word_id INTEGER NOT NULL REFERENCES words(id), PRIMARY KEY(version_id, item_id)
);
CREATE TABLE IF NOT EXISTS learning_sessions (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 version_id TEXT NOT NULL REFERENCES learning_content_versions(id),
 kind TEXT NOT NULL, current_index INTEGER NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed')),
 help_used INTEGER NOT NULL DEFAULT 0 CHECK (help_used IN (0,1)),
 start_key TEXT NOT NULL, start_hash TEXT NOT NULL, start_result TEXT NOT NULL CHECK (json_valid(start_result)),
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
 UNIQUE(profile_id, start_key)
);
CREATE INDEX IF NOT EXISTS learning_sessions_profile ON learning_sessions(profile_id, updated_at);
CREATE TABLE IF NOT EXISTS learning_commands (
 session_id TEXT NOT NULL REFERENCES learning_sessions(id), submission_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL, result TEXT NOT NULL CHECK (json_valid(result)),
 created_at INTEGER NOT NULL, PRIMARY KEY(session_id, submission_id)
);
CREATE TABLE IF NOT EXISTS activity_attempts (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES learning_sessions(id),
 item_id TEXT NOT NULL, submission_id TEXT NOT NULL, answer TEXT NOT NULL CHECK (json_valid(answer)),
 assisted INTEGER NOT NULL CHECK (assisted IN (0,1)), outcome TEXT NOT NULL,
 policy_version TEXT NOT NULL, created_at INTEGER NOT NULL,
 UNIQUE(session_id, submission_id)
);
CREATE TABLE IF NOT EXISTS learner_word_evidence (
 attempt_id TEXT PRIMARY KEY REFERENCES activity_attempts(id),
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 word_id INTEGER NOT NULL REFERENCES words(id), evidence_type TEXT NOT NULL,
 outcome TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_reward_entries (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 attempt_id TEXT NOT NULL REFERENCES activity_attempts(id), eligibility_key TEXT NOT NULL,
 study_day TEXT NOT NULL, amount INTEGER NOT NULL CHECK (amount != 0),
 category TEXT NOT NULL CHECK (category IN ('activity','review')),
 policy_version TEXT NOT NULL, created_at INTEGER NOT NULL,
 UNIQUE(profile_id, eligibility_key)
);
CREATE INDEX IF NOT EXISTS learning_rewards_day ON learning_reward_entries(profile_id, study_day);
CREATE TRIGGER IF NOT EXISTS learning_rewards_no_update BEFORE UPDATE ON learning_reward_entries
BEGIN SELECT RAISE(ABORT, 'Reward history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS learning_rewards_no_delete BEFORE DELETE ON learning_reward_entries
BEGIN SELECT RAISE(ABORT, 'Reward history is append-only'); END;
