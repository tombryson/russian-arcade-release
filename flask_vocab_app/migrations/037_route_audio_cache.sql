-- Multiple speech specifications may produce the same deduplicated asset.
-- The specification hash includes learner scope, voice, model and exact text.
CREATE TABLE journey_route_audio_cache (
 spec_hash TEXT PRIMARY KEY CHECK(length(spec_hash)=64),
 asset_id TEXT NOT NULL REFERENCES learning_assets(id),
 created_at INTEGER NOT NULL
);
