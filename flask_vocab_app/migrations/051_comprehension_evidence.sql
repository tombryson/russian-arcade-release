-- Additive history for newly issued Comprehension tasks. Existing story rows
-- and media remain the library; old feedback is not reclassified as evidence.
CREATE TABLE comprehension_tasks (
 id TEXT PRIMARY KEY,
 story_id INTEGER NOT NULL REFERENCES saved_stories(id),
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
 created_at INTEGER NOT NULL,
 checking_submission_id TEXT,
 checking_sha256 TEXT,
 checking_started_at INTEGER,
 checking_token TEXT,
 UNIQUE(id,profile_id)
);
CREATE INDEX comprehension_tasks_story ON comprehension_tasks(story_id,profile_id,created_at);
CREATE TABLE comprehension_attempts (
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL,
 profile_id TEXT NOT NULL,
 submission_id TEXT NOT NULL,
 request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64),
 answers_json TEXT NOT NULL CHECK(json_valid(answers_json)),
 assessment_json TEXT NOT NULL CHECK(json_valid(assessment_json)),
 support_json TEXT NOT NULL CHECK(json_valid(support_json)),
 created_at INTEGER NOT NULL,
 UNIQUE(task_id,submission_id),
 FOREIGN KEY(task_id,profile_id) REFERENCES comprehension_tasks(id,profile_id)
);
CREATE INDEX comprehension_attempts_task ON comprehension_attempts(task_id,created_at);
