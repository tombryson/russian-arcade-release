-- Explicit course switches and optional follow-ups retain durable identities.
ALTER TABLE course_checkpoint_attempts ADD COLUMN draft_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE course_checkpoint_attempts ADD COLUMN draft_revision INTEGER NOT NULL DEFAULT 0;
CREATE TABLE course_release_switches (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 request_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
 from_release_id TEXT NOT NULL, to_release_id TEXT NOT NULL,
 created_at INTEGER NOT NULL, response_json TEXT NOT NULL,
 PRIMARY KEY(profile_id, request_id)
);
CREATE TABLE course_checkpoint_followups (
 attempt_id TEXT NOT NULL REFERENCES course_checkpoint_attempts(id),
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 kind TEXT NOT NULL CHECK(kind IN ('writing','word')),
 source_key TEXT NOT NULL, item_id INTEGER NOT NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY(attempt_id,profile_id,kind,source_key)
);
