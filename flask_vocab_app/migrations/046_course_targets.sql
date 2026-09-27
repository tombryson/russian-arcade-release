-- Target evidence records individual responses. Existing topic scores are not copied.
CREATE TABLE course_target_practice_attempts (
 id TEXT PRIMARY KEY,
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 section_id TEXT NOT NULL,
 content_version TEXT NOT NULL,
 content_json TEXT NOT NULL CHECK(json_valid(content_json)),
 state_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(state_json)),
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed')),
 current_index INTEGER NOT NULL DEFAULT 0 CHECK(current_index>=0),
 created_at INTEGER NOT NULL,
 completed_at INTEGER,
 UNIQUE(id,profile_id)
);
CREATE UNIQUE INDEX course_target_practice_active ON course_target_practice_attempts(profile_id,section_id) WHERE status='active';
CREATE TABLE course_target_practice_requests (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 request_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 attempt_id TEXT NOT NULL,
 PRIMARY KEY(profile_id,request_id),
 FOREIGN KEY(attempt_id,profile_id) REFERENCES course_target_practice_attempts(id,profile_id)
);
CREATE TABLE course_target_practice_receipts (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 request_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 result_json TEXT NOT NULL CHECK(json_valid(result_json)),
 created_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,request_id),
 FOREIGN KEY(attempt_id,profile_id) REFERENCES course_target_practice_attempts(id,profile_id)
);
CREATE TABLE course_target_observations (
 id TEXT PRIMARY KEY,
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 target_id TEXT NOT NULL,
 catalogue_version TEXT NOT NULL,
 target_version INTEGER NOT NULL CHECK(target_version>0),
 response_mode TEXT NOT NULL,
 activity TEXT NOT NULL,
 source_key TEXT NOT NULL,
 item_id TEXT NOT NULL,
 content_hash TEXT NOT NULL,
 rubric_version TEXT NOT NULL,
 introduced INTEGER NOT NULL CHECK(introduced IN (0,1)),
 practised INTEGER NOT NULL CHECK(practised IN (0,1)),
 demonstrated INTEGER NOT NULL CHECK(demonstrated IN (0,1)),
 needs_practice INTEGER NOT NULL CHECK(needs_practice IN (0,1)),
 score REAL CHECK(score IS NULL OR (score>=0 AND score<=1)),
 first_response_json TEXT CHECK(first_response_json IS NULL OR json_valid(first_response_json)),
 response_json TEXT CHECK(response_json IS NULL OR json_valid(response_json)),
 support_json TEXT NOT NULL CHECK(json_valid(support_json)),
 event_id TEXT REFERENCES progression_events(id),
 checkpoint_id TEXT REFERENCES course_checkpoint_attempts(id),
 practice_id TEXT,
 created_at INTEGER NOT NULL,
 UNIQUE(profile_id,activity,source_key,item_id,target_id),
 FOREIGN KEY(practice_id,profile_id) REFERENCES course_target_practice_attempts(id,profile_id),
 CHECK(demonstrated=0 OR (practised=1 AND score=1)),
 CHECK(needs_practice=0 OR practised=1)
);
CREATE INDEX course_target_observations_profile ON course_target_observations(profile_id,target_id,created_at);
