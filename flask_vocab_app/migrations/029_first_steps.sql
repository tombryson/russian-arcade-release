-- Optional first-chapter lessons keep their authored content and first answers.
CREATE TABLE first_steps_attempts (
 id TEXT PRIMARY KEY,
 profile_id TEXT REFERENCES learning_profiles(id),
 guest_token TEXT,
 chapter_id TEXT NOT NULL,
 lesson_id TEXT NOT NULL,
 version TEXT NOT NULL,
 content_json TEXT NOT NULL CHECK(json_valid(content_json)),
 learned_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(learned_json)),
 answers_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(answers_json)),
 hints_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(hints_json)),
 acknowledged_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(acknowledged_json)),
 completed_at INTEGER,
 reward_amount INTEGER CHECK(reward_amount IS NULL OR reward_amount>=0),
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 UNIQUE(profile_id,chapter_id,lesson_id),
 UNIQUE(guest_token,chapter_id,lesson_id),
 CHECK ((profile_id IS NOT NULL AND guest_token IS NULL) OR (profile_id IS NULL AND guest_token IS NOT NULL))
);
