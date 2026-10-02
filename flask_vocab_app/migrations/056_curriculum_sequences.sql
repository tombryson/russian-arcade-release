-- Lesson navigation owns references, never a second score or reward ledger.
CREATE TABLE curriculum_unit_runs (
 id TEXT PRIMARY KEY,
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 sequence_id TEXT NOT NULL,
 unit_id TEXT NOT NULL,
 manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
 manifest_sha256 TEXT NOT NULL,
 completion_path TEXT NOT NULL,
 last_step_id TEXT,
 revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),
 completed_at INTEGER,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 UNIQUE(id,profile_id)
);
CREATE UNIQUE INDEX curriculum_run_active ON curriculum_unit_runs(profile_id,sequence_id) WHERE completed_at IS NULL;
CREATE TABLE curriculum_unit_bindings (
 id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL,
 profile_id TEXT NOT NULL,
 step_id TEXT NOT NULL,
 ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 activity TEXT NOT NULL,
 task_key TEXT NOT NULL,
 effects_policy TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 UNIQUE(run_id,step_id,ordinal),
 UNIQUE(profile_id,activity,task_key),
 FOREIGN KEY(run_id,profile_id) REFERENCES curriculum_unit_runs(id,profile_id)
);
CREATE TABLE curriculum_unit_requests (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 request_id TEXT NOT NULL,
 operation TEXT NOT NULL,
 request_sha256 TEXT NOT NULL,
 response_json TEXT NOT NULL CHECK(json_valid(response_json)),
 created_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,request_id)
);
CREATE TABLE curriculum_transfer_exposure (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 family_id TEXT NOT NULL,
 run_id TEXT NOT NULL,
 exposed_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,family_id),
 FOREIGN KEY(run_id,profile_id) REFERENCES curriculum_unit_runs(id,profile_id)
);
CREATE TABLE learning_session_drafts (
 session_id TEXT NOT NULL REFERENCES learning_sessions(id),
 item_id TEXT NOT NULL,
 response_json TEXT NOT NULL CHECK(json_valid(response_json)),
 revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),
 updated_at INTEGER NOT NULL,
 PRIMARY KEY(session_id,item_id)
);
CREATE INDEX curriculum_run_owner ON curriculum_unit_runs(profile_id,updated_at);
CREATE TABLE learning_prior_feedback (
 session_id TEXT NOT NULL REFERENCES learning_sessions(id),
 item_id TEXT NOT NULL,
 source_attempt_id TEXT NOT NULL REFERENCES activity_attempts(id),
 PRIMARY KEY(session_id,item_id)
);
CREATE TABLE learning_hint_usage (
 session_id TEXT NOT NULL REFERENCES learning_sessions(id),
 item_id TEXT NOT NULL,
 PRIMARY KEY(session_id,item_id)
);
