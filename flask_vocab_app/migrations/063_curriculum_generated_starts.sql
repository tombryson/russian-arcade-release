-- Resume requests remain bound to their original generated set after completion.
CREATE TABLE curriculum_generated_starts (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 request_id TEXT NOT NULL,
 request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64),
 session_id TEXT NOT NULL REFERENCES learning_sessions(id),
 created_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,request_id)
);
