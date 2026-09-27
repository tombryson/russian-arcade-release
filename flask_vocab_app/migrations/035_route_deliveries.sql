-- Connected deliveries keep their own runtime and immutable request receipts.
CREATE TABLE journey_route_state (
 session_id TEXT PRIMARY KEY REFERENCES journey_game_sessions(id),
 revision INTEGER NOT NULL DEFAULT 0,
 state_json TEXT NOT NULL CHECK(json_valid(state_json))
);
CREATE TABLE journey_route_actions (
 id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES journey_game_sessions(id),
 request_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 operation TEXT NOT NULL,
 leg INTEGER NOT NULL,
 attempt_kind TEXT,
 submitted_json TEXT NOT NULL CHECK(json_valid(submitted_json)),
 result_json TEXT NOT NULL CHECK(json_valid(result_json)),
 created_at INTEGER NOT NULL,
 UNIQUE(session_id,request_id)
);
CREATE UNIQUE INDEX journey_route_first_check ON journey_route_actions(session_id,leg)
 WHERE attempt_kind='first';
