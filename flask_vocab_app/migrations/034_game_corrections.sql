-- First answers remain immutable. Supported practice has its own history.
CREATE TABLE journey_game_corrections (
 id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES journey_game_sessions(id),
 round_id TEXT NOT NULL,
 request_id TEXT NOT NULL,
 answer_json TEXT NOT NULL CHECK(json_valid(answer_json)),
 created_at INTEGER NOT NULL,
 UNIQUE(session_id, request_id)
);
CREATE INDEX journey_game_corrections_session ON journey_game_corrections(session_id, created_at);
