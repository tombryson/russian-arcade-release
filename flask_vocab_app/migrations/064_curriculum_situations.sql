-- One owned preparation keeps its facts, text and recording across retries.
CREATE TABLE curriculum_situations (
 id TEXT PRIMARY KEY,
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 unit_id TEXT NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('reading','listening')),
 request_json TEXT NOT NULL,
 document_json TEXT,
 voice_json TEXT,
 audio_json TEXT,
 state TEXT NOT NULL CHECK(state IN ('pending','running','failed','ready')),
 stage TEXT NOT NULL CHECK(stage IN ('text','audio','publish','ready')),
 text_attempts INTEGER NOT NULL DEFAULT 0,
 audio_attempts INTEGER NOT NULL DEFAULT 0,
 claim_id TEXT,
 lease_until INTEGER NOT NULL DEFAULT 0,
 error_code TEXT,
 session_id TEXT REFERENCES learning_sessions(id),
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE INDEX curriculum_situations_owner ON curriculum_situations(profile_id,unit_id,mode,created_at);
CREATE TABLE curriculum_situation_requests (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 request_id TEXT NOT NULL,
 request_sha256 TEXT NOT NULL,
 situation_id TEXT NOT NULL REFERENCES curriculum_situations(id),
 PRIMARY KEY(profile_id,request_id)
);
CREATE TRIGGER curriculum_situation_input_immutable BEFORE UPDATE OF profile_id,unit_id,mode,request_json ON curriculum_situations
BEGIN SELECT RAISE(ABORT,'Situation inputs are immutable'); END;
CREATE TRIGGER curriculum_situation_text_immutable BEFORE UPDATE OF document_json ON curriculum_situations
WHEN OLD.document_json IS NOT NULL AND NEW.document_json IS NOT OLD.document_json
BEGIN SELECT RAISE(ABORT,'Accepted situation text is immutable'); END;
CREATE TRIGGER curriculum_situation_voice_immutable BEFORE UPDATE OF voice_json ON curriculum_situations
WHEN OLD.voice_json IS NOT NULL AND NEW.voice_json IS NOT OLD.voice_json
BEGIN SELECT RAISE(ABORT,'Selected voice is immutable'); END;
CREATE TRIGGER curriculum_situation_audio_immutable BEFORE UPDATE OF audio_json ON curriculum_situations
WHEN OLD.audio_json IS NOT NULL AND NEW.audio_json IS NOT OLD.audio_json
BEGIN SELECT RAISE(ABORT,'Accepted recording is immutable'); END;
