-- Games become available through completed lessons and keep their own replay
-- history. Frozen content and first answers survive later editorial changes.
CREATE TABLE journey_game_unlocks (
 id TEXT PRIMARY KEY,
 profile_id TEXT REFERENCES learning_profiles(id),
 guest_token TEXT,
 game_id TEXT NOT NULL CHECK(game_id IN ('pack-bag','directions')),
 lesson_id TEXT NOT NULL,
 lesson_version TEXT NOT NULL,
 lesson_json TEXT NOT NULL CHECK(json_valid(lesson_json)),
 unlocked_at INTEGER NOT NULL,
 first_started_at INTEGER,
 UNIQUE(profile_id,game_id),
 UNIQUE(guest_token,game_id),
 CHECK ((profile_id IS NOT NULL AND guest_token IS NULL) OR (profile_id IS NULL AND guest_token IS NOT NULL))
);

INSERT INTO journey_game_unlocks(id,profile_id,guest_token,game_id,lesson_id,lesson_version,lesson_json,unlocked_at)
 SELECT 'lesson-game:' || id,profile_id,guest_token,
 CASE lesson_id WHEN 'bag' THEN 'pack-bag' ELSE 'directions' END,
 lesson_id,version,content_json,completed_at FROM first_steps_attempts
 WHERE chapter_id='first-steps' AND lesson_id IN ('bag','directions') AND completed_at IS NOT NULL;

CREATE TABLE journey_game_sessions (
 id TEXT PRIMARY KEY,
 profile_id TEXT REFERENCES learning_profiles(id),
 guest_token TEXT,
 game_id TEXT NOT NULL CHECK(game_id IN ('pack-bag','directions')),
 seed TEXT NOT NULL,
 request_ids_json TEXT NOT NULL CHECK(json_valid(request_ids_json)),
 content_json TEXT NOT NULL CHECK(json_valid(content_json)),
 answers_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(answers_json)),
 hints_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(hints_json)),
 acknowledged_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(acknowledged_json)),
 completed_at INTEGER,
 reward_amount INTEGER CHECK(reward_amount IS NULL OR reward_amount>=0),
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 CHECK ((profile_id IS NOT NULL AND guest_token IS NULL) OR (profile_id IS NULL AND guest_token IS NOT NULL))
);
CREATE UNIQUE INDEX journey_game_active_profile ON journey_game_sessions(profile_id,game_id) WHERE completed_at IS NULL AND profile_id IS NOT NULL;
CREATE UNIQUE INDEX journey_game_active_guest ON journey_game_sessions(guest_token,game_id) WHERE completed_at IS NULL AND guest_token IS NOT NULL;
CREATE INDEX journey_game_history_profile ON journey_game_sessions(profile_id,created_at);
CREATE INDEX journey_game_history_guest ON journey_game_sessions(guest_token,created_at);
