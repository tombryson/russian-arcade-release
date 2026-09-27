-- Rebuild only the shared session table to allow per-occurrence review content.
-- The migration runner disables FK enforcement outside this transaction and
-- verifies every reference before committing this particular table rebuild.
CREATE TABLE learning_sessions_next (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 version_id TEXT REFERENCES learning_content_versions(id), kind TEXT NOT NULL,
 current_index INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed')),
 help_used INTEGER NOT NULL DEFAULT 0 CHECK (help_used IN (0,1)),
 start_key TEXT NOT NULL, start_hash TEXT NOT NULL, start_result TEXT NOT NULL CHECK (json_valid(start_result)),
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
 UNIQUE(profile_id,start_key),
 CHECK ((kind='review' AND version_id IS NULL) OR (kind!='review' AND version_id IS NOT NULL))
);
INSERT INTO learning_sessions_next SELECT * FROM learning_sessions;
DROP TABLE learning_sessions;
ALTER TABLE learning_sessions_next RENAME TO learning_sessions;
CREATE INDEX IF NOT EXISTS learning_sessions_profile ON learning_sessions(profile_id,updated_at);

CREATE TABLE IF NOT EXISTS card_definitions (
 id TEXT PRIMARY KEY, word_id INTEGER REFERENCES words(id), form_id INTEGER REFERENCES forms(id),
 retrieval_mode TEXT NOT NULL CHECK (retrieval_mode IN ('ru-en','en-ru','ru-cloze')),
 sense_key TEXT NOT NULL, sibling_key TEXT NOT NULL, objective_hash TEXT NOT NULL,
 retired INTEGER NOT NULL DEFAULT 0 CHECK (retired IN (0,1)), created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS cards_word ON card_definitions(word_id,retired);
CREATE TABLE IF NOT EXISTS card_versions (
 id TEXT PRIMARY KEY, card_id TEXT NOT NULL REFERENCES card_definitions(id),
 content_version_id TEXT NOT NULL REFERENCES learning_content_versions(id), item_id TEXT NOT NULL,
 UNIQUE(content_version_id,item_id), UNIQUE(card_id,content_version_id)
);
CREATE TABLE IF NOT EXISTS learner_card_state (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), card_id TEXT NOT NULL REFERENCES card_definitions(id),
 scheduler_state TEXT CHECK (scheduler_state IS NULL OR json_valid(scheduler_state)),
 introduced_at INTEGER, due_at INTEGER, last_review_at INTEGER,
 reviews INTEGER NOT NULL DEFAULT 0 CHECK (reviews>=0), lapses INTEGER NOT NULL DEFAULT 0 CHECK (lapses>=0),
 suspended INTEGER NOT NULL DEFAULT 0 CHECK (suspended IN (0,1)),
 revision INTEGER NOT NULL DEFAULT 0, policy_version TEXT NOT NULL,
 PRIMARY KEY(profile_id,card_id)
);
CREATE INDEX IF NOT EXISTS native_due ON learner_card_state(profile_id,suspended,due_at);
CREATE TABLE IF NOT EXISTS review_introductions (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), card_id TEXT NOT NULL REFERENCES card_definitions(id),
 study_day TEXT NOT NULL, study_timezone TEXT NOT NULL, created_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,card_id)
);
CREATE INDEX IF NOT EXISTS review_introductions_day ON review_introductions(profile_id,study_day);
CREATE TABLE IF NOT EXISTS review_sessions (
 session_id TEXT PRIMARY KEY REFERENCES learning_sessions(id),
 scope TEXT NOT NULL CHECK (json_valid(scope)), target_size INTEGER NOT NULL CHECK (target_size BETWEEN 1 AND 20),
 current_occurrence_id TEXT, last_attempt_id TEXT REFERENCES activity_attempts(id),
 phase TEXT NOT NULL CHECK (phase IN ('front','revealed','feedback','completed'))
);
CREATE TABLE IF NOT EXISTS review_session_cards (
 session_id TEXT NOT NULL REFERENCES review_sessions(session_id), card_id TEXT NOT NULL REFERENCES card_definitions(id),
 card_version_id TEXT NOT NULL REFERENCES card_versions(id), position INTEGER NOT NULL,
 answered INTEGER NOT NULL DEFAULT 0 CHECK (answered IN (0,1)), skipped INTEGER NOT NULL DEFAULT 0 CHECK (skipped IN (0,1)),
 PRIMARY KEY(session_id,card_id)
);
CREATE TABLE IF NOT EXISTS review_session_items (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES review_sessions(session_id),
 card_id TEXT NOT NULL REFERENCES card_definitions(id), card_version_id TEXT NOT NULL REFERENCES card_versions(id),
 state_revision INTEGER NOT NULL, revealed INTEGER NOT NULL DEFAULT 0 CHECK (revealed IN (0,1)),
 assisted INTEGER NOT NULL DEFAULT 0 CHECK (assisted IN (0,1)), created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS review_events (
 attempt_id TEXT PRIMARY KEY REFERENCES activity_attempts(id),
 occurrence_id TEXT NOT NULL UNIQUE REFERENCES review_session_items(id),
 card_id TEXT NOT NULL REFERENCES card_definitions(id), card_version_id TEXT NOT NULL REFERENCES card_versions(id),
 rating TEXT NOT NULL CHECK (rating IN ('again','good')),
 before_state TEXT NOT NULL CHECK (json_valid(before_state)), after_state TEXT NOT NULL CHECK (json_valid(after_state)),
 before_session TEXT NOT NULL CHECK (json_valid(before_session)),
 scheduler_log TEXT NOT NULL CHECK (json_valid(scheduler_log)), scheduler_policy TEXT NOT NULL CHECK (json_valid(scheduler_policy)),
 study_day TEXT NOT NULL, study_timezone TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS review_reversals (
 id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE REFERENCES review_events(attempt_id),
 session_id TEXT NOT NULL REFERENCES review_sessions(session_id), created_at INTEGER NOT NULL
);
CREATE TRIGGER IF NOT EXISTS review_events_no_update BEFORE UPDATE ON review_events
BEGIN SELECT RAISE(ABORT,'Review history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_events_no_delete BEFORE DELETE ON review_events
BEGIN SELECT RAISE(ABORT,'Review history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_reversals_no_update BEFORE UPDATE ON review_reversals
BEGIN SELECT RAISE(ABORT,'Review reversals are append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_reversals_no_delete BEFORE DELETE ON review_reversals
BEGIN SELECT RAISE(ABORT,'Review reversals are append-only'); END;
CREATE TABLE IF NOT EXISTS review_start_commands (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), submission_id TEXT NOT NULL,
 session_id TEXT NOT NULL REFERENCES review_sessions(session_id), payload_hash TEXT NOT NULL,
 result TEXT NOT NULL CHECK (json_valid(result)), PRIMARY KEY(profile_id,submission_id)
);
CREATE TABLE IF NOT EXISTS card_reports (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 card_id TEXT NOT NULL REFERENCES card_definitions(id), card_version_id TEXT NOT NULL REFERENCES card_versions(id),
 reason TEXT NOT NULL, created_at INTEGER NOT NULL,
 UNIQUE(profile_id,card_version_id)
);
CREATE TABLE IF NOT EXISTS card_draft_archives (
 version_id TEXT PRIMARY KEY REFERENCES learning_content_versions(id), created_at INTEGER NOT NULL
);
