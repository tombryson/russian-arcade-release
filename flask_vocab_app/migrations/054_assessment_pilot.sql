-- Diagnostic evidence grouping only: no rewards, passes or access rights.
CREATE TABLE assessment_pilot_sessions (
 id TEXT PRIMARY KEY,
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 blueprint_id TEXT NOT NULL,
 blueprint_json TEXT NOT NULL CHECK(json_valid(blueprint_json)),
 blueprint_sha256 TEXT NOT NULL,
 start_key TEXT NOT NULL,
 language TEXT NOT NULL CHECK(language IN ('en','ru')),
 created_at INTEGER NOT NULL,
 UNIQUE(id,profile_id), UNIQUE(profile_id,start_key)
);
CREATE TABLE assessment_pilot_components (
 id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL,
 profile_id TEXT NOT NULL,
 domain TEXT NOT NULL CHECK(domain IN ('language_use','reading','listening','writing','speaking')),
 ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 task_json TEXT NOT NULL CHECK(json_valid(task_json)),
 task_sha256 TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),
 draft_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(draft_json)),
 repeated INTEGER NOT NULL DEFAULT 0 CHECK(repeated IN (0,1)),
 prior_feedback INTEGER NOT NULL DEFAULT 0 CHECK(prior_feedback IN (0,1)),
 created_at INTEGER NOT NULL,
 UNIQUE(id,profile_id), UNIQUE(session_id,domain,ordinal),
 FOREIGN KEY(session_id,profile_id) REFERENCES assessment_pilot_sessions(id,profile_id)
);
CREATE TABLE assessment_pilot_support (
 id TEXT PRIMARY KEY,
 component_id TEXT NOT NULL,
 profile_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('listened','transcript','hint')),
 detail_json TEXT NOT NULL CHECK(json_valid(detail_json)),
 revision INTEGER NOT NULL CHECK(revision>=0),
 created_at INTEGER NOT NULL,
 FOREIGN KEY(component_id,profile_id) REFERENCES assessment_pilot_components(id,profile_id)
);
CREATE TABLE assessment_pilot_submissions (
 id TEXT PRIMARY KEY,
 component_id TEXT NOT NULL UNIQUE,
 profile_id TEXT NOT NULL,
 submission_key TEXT NOT NULL,
 request_sha256 TEXT NOT NULL,
 response_json TEXT NOT NULL CHECK(json_valid(response_json)),
 support_json TEXT NOT NULL CHECK(json_valid(support_json)),
 receipt_ids_json TEXT NOT NULL CHECK(json_valid(receipt_ids_json)),
 audio_json TEXT CHECK(audio_json IS NULL OR json_valid(audio_json)),
 submitted_revision INTEGER NOT NULL,
 created_at INTEGER NOT NULL,
 UNIQUE(id,profile_id),
 FOREIGN KEY(component_id,profile_id) REFERENCES assessment_pilot_components(id,profile_id)
);
CREATE TABLE assessment_pilot_reviews (
 submission_id TEXT PRIMARY KEY REFERENCES assessment_pilot_submissions(id),
 state TEXT NOT NULL CHECK(state IN ('pending','running','ready','failed')),
 claim_token TEXT,
 lease_until INTEGER NOT NULL DEFAULT 0,
 report_json TEXT CHECK(report_json IS NULL OR json_valid(report_json)),
 error TEXT,
 updated_at INTEGER NOT NULL
);
CREATE TABLE assessment_pilot_requests (
 session_id TEXT NOT NULL REFERENCES assessment_pilot_sessions(id),
 request_key TEXT NOT NULL,
 operation TEXT NOT NULL,
 request_sha256 TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY(session_id,request_key)
);
CREATE INDEX assessment_pilot_owned ON assessment_pilot_sessions(profile_id,created_at);
CREATE INDEX assessment_pilot_current ON assessment_pilot_components(session_id,domain,ordinal);
