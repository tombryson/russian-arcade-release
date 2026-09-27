-- A generation batch can resume after navigation or restart, without rebuilding
-- cards that were already saved. Native schedules and Anki counters are separate.
CREATE TABLE IF NOT EXISTS native_card_batches (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, request_key TEXT NOT NULL,
 request_hash TEXT NOT NULL, options TEXT NOT NULL CHECK(json_valid(options)),
 created_at INTEGER NOT NULL, UNIQUE(owner_id,request_key)
);
CREATE TABLE IF NOT EXISTS native_card_generation_items (
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES native_card_batches(id),
 position INTEGER NOT NULL, selection TEXT NOT NULL CHECK(json_valid(selection)),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','generated','saved','failed')),
 response TEXT CHECK(response IS NULL OR json_valid(response)),
 version_id TEXT REFERENCES learning_content_versions(id), error TEXT,
 claim_id TEXT, lease_until INTEGER NOT NULL DEFAULT 0,
 UNIQUE(batch_id,position)
);
CREATE INDEX IF NOT EXISTS native_generation_batch ON native_card_generation_items(batch_id,position);
