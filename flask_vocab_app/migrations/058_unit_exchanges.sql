CREATE TABLE curriculum_unit_exchanges (
 id TEXT PRIMARY KEY,
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 asset_json TEXT NOT NULL CHECK(json_valid(asset_json)),
 contract_json TEXT NOT NULL CHECK(json_valid(contract_json)),
 revision INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL,
 UNIQUE(id,profile_id)
);
CREATE TABLE curriculum_unit_exchange_turns (
 exchange_id TEXT NOT NULL,
 profile_id TEXT NOT NULL,
 turn_id TEXT NOT NULL,
 request_id TEXT NOT NULL,
 request_sha256 TEXT NOT NULL,
 audio_json TEXT NOT NULL CHECK(json_valid(audio_json)),
 created_at INTEGER NOT NULL,
 PRIMARY KEY(exchange_id,turn_id),
 UNIQUE(profile_id,request_id),
 FOREIGN KEY(exchange_id,profile_id) REFERENCES curriculum_unit_exchanges(id,profile_id)
);
CREATE TABLE curriculum_unit_exchange_playback (
 exchange_id TEXT NOT NULL,
 profile_id TEXT NOT NULL,
 turn_id TEXT NOT NULL,
 request_id TEXT NOT NULL,
 request_sha256 TEXT NOT NULL,
 audio_sha256 TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,request_id),
 FOREIGN KEY(exchange_id,profile_id) REFERENCES curriculum_unit_exchanges(id,profile_id)
);
CREATE TRIGGER unit_exchange_turn_immutable BEFORE UPDATE ON curriculum_unit_exchange_turns
BEGIN SELECT RAISE(ABORT,'Saved original recordings are immutable'); END;
CREATE TRIGGER unit_exchange_task_immutable BEFORE UPDATE OF id,profile_id,asset_json,contract_json,created_at ON curriculum_unit_exchanges
BEGIN SELECT RAISE(ABORT,'Saved Speaking prompts and criteria are immutable'); END;
CREATE TRIGGER unit_exchange_playback_immutable BEFORE UPDATE ON curriculum_unit_exchange_playback
BEGIN SELECT RAISE(ABORT,'Saved prompt playback receipts are immutable'); END;
