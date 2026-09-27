-- Retryable native media stages. Card identities and review history are unchanged.
CREATE TABLE IF NOT EXISTS native_card_media_jobs (
 id TEXT PRIMARY KEY,
 card_id TEXT NOT NULL REFERENCES card_definitions(id),
 kind TEXT NOT NULL CHECK(kind IN ('image','word_audio','sentence_audio')),
 spec TEXT NOT NULL CHECK(json_valid(spec)),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','saved','failed')),
 asset_id TEXT REFERENCES learning_assets(id),
 error TEXT, claim_id TEXT, lease_until INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL,
 UNIQUE(card_id,kind)
);
CREATE INDEX IF NOT EXISTS native_media_work ON native_card_media_jobs(status,lease_until);
