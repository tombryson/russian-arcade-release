-- Per-item support receipts for audio practice. A playback-ended receipt is
-- browser-reported, not proof of attention. Existing attempts remain unchanged.
CREATE TABLE learning_item_support (
 session_id TEXT NOT NULL REFERENCES learning_sessions(id),
 item_id TEXT NOT NULL,
 audio_sha256 TEXT NOT NULL CHECK(length(audio_sha256)=64),
 listened_at INTEGER,
 transcript_at INTEGER,
 hint_at INTEGER,
 PRIMARY KEY(session_id,item_id)
);
