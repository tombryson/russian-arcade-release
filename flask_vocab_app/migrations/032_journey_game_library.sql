-- Keep the original two games and their row order while allowing the shared
-- registry to grow. Their frozen content, first answers and rewards are copied
-- byte for byte. New listening/transcript receipts are separate from hints.
CREATE TABLE journey_game_unlocks_next (
 id TEXT PRIMARY KEY,
 profile_id TEXT REFERENCES learning_profiles(id),
 guest_token TEXT,
 game_id TEXT NOT NULL CHECK(length(trim(game_id))>0),
 lesson_id TEXT NOT NULL,
 lesson_version TEXT NOT NULL,
 lesson_json TEXT NOT NULL CHECK(json_valid(lesson_json)),
 unlocked_at INTEGER NOT NULL,
 first_started_at INTEGER,
 UNIQUE(profile_id,game_id),
 UNIQUE(guest_token,game_id),
 CHECK ((profile_id IS NOT NULL AND guest_token IS NULL) OR (profile_id IS NULL AND guest_token IS NOT NULL))
);
INSERT INTO journey_game_unlocks_next(rowid,id,profile_id,guest_token,game_id,lesson_id,lesson_version,lesson_json,unlocked_at,first_started_at)
 SELECT rowid,id,profile_id,guest_token,game_id,lesson_id,lesson_version,lesson_json,unlocked_at,first_started_at FROM journey_game_unlocks;
DROP TABLE journey_game_unlocks;
ALTER TABLE journey_game_unlocks_next RENAME TO journey_game_unlocks;

CREATE TABLE journey_game_sessions_next (
 id TEXT PRIMARY KEY,
 profile_id TEXT REFERENCES learning_profiles(id),
 guest_token TEXT,
 game_id TEXT NOT NULL CHECK(length(trim(game_id))>0),
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
 support_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(support_json)),
 CHECK ((profile_id IS NOT NULL AND guest_token IS NULL) OR (profile_id IS NULL AND guest_token IS NOT NULL))
);
INSERT INTO journey_game_sessions_next(rowid,id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,answers_json,hints_json,acknowledged_json,completed_at,reward_amount,created_at,updated_at)
 SELECT rowid,id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,answers_json,hints_json,acknowledged_json,completed_at,reward_amount,created_at,updated_at FROM journey_game_sessions;
DROP TABLE journey_game_sessions;
ALTER TABLE journey_game_sessions_next RENAME TO journey_game_sessions;
CREATE UNIQUE INDEX journey_game_active_profile ON journey_game_sessions(profile_id,game_id) WHERE completed_at IS NULL AND profile_id IS NOT NULL;
CREATE UNIQUE INDEX journey_game_active_guest ON journey_game_sessions(guest_token,game_id) WHERE completed_at IS NULL AND guest_token IS NOT NULL;
CREATE INDEX journey_game_history_profile ON journey_game_sessions(profile_id,created_at);
CREATE INDEX journey_game_history_guest ON journey_game_sessions(guest_token,created_at);
