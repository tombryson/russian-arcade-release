-- Audio for frozen lesson clues. The shared cache contains server-authored
-- instruction text only; private native-card assets remain owner-scoped.
CREATE TABLE IF NOT EXISTS journey_game_media (
 id TEXT PRIMARY KEY,
 text_hash TEXT NOT NULL,
 text TEXT NOT NULL,
 policy_hash TEXT NOT NULL,
 spec_json TEXT NOT NULL CHECK(json_valid(spec_json)),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','ready','failed')),
 asset_id TEXT REFERENCES learning_assets(id),
 claim_id TEXT,
 lease_until INTEGER NOT NULL DEFAULT 0,
 error TEXT,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 UNIQUE(text_hash,policy_hash)
);
