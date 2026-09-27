-- Preparation has a durable lease; provider requests run outside transactions.
CREATE TABLE journey_route_preparations (
 session_id TEXT PRIMARY KEY REFERENCES journey_game_sessions(id),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','ready','failed')),
 error TEXT,
 claim_id TEXT,
 lease_until INTEGER NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
