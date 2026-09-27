-- Course evidence begins here; existing rewards are deliberately not backfilled.
CREATE TABLE course_evidence (
 event_id TEXT PRIMARY KEY REFERENCES progression_events(id),
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 topic_id TEXT NOT NULL, activity TEXT NOT NULL, content_key TEXT NOT NULL,
 target_level TEXT NOT NULL CHECK(target_level='A1'),
 score REAL NOT NULL CHECK(score>=0.7 AND score<=1),
 policy_version TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE INDEX course_evidence_profile_topic ON course_evidence(profile_id,topic_id);
CREATE TABLE course_checkpoint_attempts (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 chapter_id TEXT NOT NULL, chapter_number INTEGER NOT NULL,
 variant_id TEXT NOT NULL, content_version INTEGER NOT NULL, rubric_version TEXT NOT NULL,
 frozen_json TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','passed','retry')),
 support_json TEXT NOT NULL DEFAULT '[]', listened_at INTEGER,
 answers_json TEXT, result_json TEXT, created_at INTEGER NOT NULL, completed_at INTEGER
);
CREATE UNIQUE INDEX course_checkpoint_active ON course_checkpoint_attempts(profile_id,chapter_id) WHERE status='active';
CREATE INDEX course_checkpoint_history ON course_checkpoint_attempts(profile_id,chapter_id,created_at);
CREATE TABLE course_checkpoint_requests (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), request_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL, attempt_id TEXT NOT NULL REFERENCES course_checkpoint_attempts(id),
 response_json TEXT NOT NULL, PRIMARY KEY(profile_id,request_id)
);
CREATE TABLE course_checkpoint_submissions (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), submission_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL, attempt_id TEXT NOT NULL REFERENCES course_checkpoint_attempts(id),
 response_json TEXT NOT NULL, PRIMARY KEY(profile_id,submission_id)
);
CREATE TABLE course_chapter_passes (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), chapter_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL REFERENCES course_checkpoint_attempts(id), passed_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,chapter_id)
);
