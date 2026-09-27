ALTER TABLE live_conversation_sessions ADD COLUMN end_reason TEXT;
CREATE TABLE speaking_reviews (
    session_id TEXT PRIMARY KEY REFERENCES live_conversation_sessions(id) ON DELETE CASCADE,
    state TEXT NOT NULL DEFAULT 'queued',
    report_json TEXT,
    error TEXT,
    lease_until INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
