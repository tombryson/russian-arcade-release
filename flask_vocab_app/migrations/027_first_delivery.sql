CREATE TABLE first_delivery_attempts (
 id TEXT PRIMARY KEY,
 profile_id TEXT UNIQUE REFERENCES learning_profiles(id),
 guest_token TEXT UNIQUE,
 version TEXT NOT NULL,
 answers_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(answers_json)),
 hints_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(hints_json)),
 acknowledged_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(acknowledged_json)),
 completed_at INTEGER,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 CHECK ((profile_id IS NOT NULL AND guest_token IS NULL) OR (profile_id IS NULL AND guest_token IS NOT NULL))
);
