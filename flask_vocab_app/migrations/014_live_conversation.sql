CREATE TABLE IF NOT EXISTS live_conversation_sessions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
    start_key TEXT NOT NULL,
    scenario_json TEXT NOT NULL,
    language TEXT NOT NULL,
    model TEXT NOT NULL,
    backend_model TEXT NOT NULL,
    voice TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'new',
    provider_id TEXT,
    offer_hash TEXT,
    answer_sdp TEXT,
    created_at INTEGER NOT NULL,
    started_at INTEGER,
    ended_at INTEGER,
    heartbeat_at INTEGER NOT NULL,
    final_usage_json TEXT,
    error TEXT,
    UNIQUE(profile_id, start_key)
);
CREATE TABLE IF NOT EXISTS live_conversation_events (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES live_conversation_sessions(id) ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    UNIQUE(session_id, event_key)
);
CREATE TABLE IF NOT EXISTS live_conversation_recordings (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES live_conversation_sessions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    filename TEXT NOT NULL,
    start_sample INTEGER NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    sample_rate INTEGER NOT NULL DEFAULT 24000,
    state TEXT NOT NULL DEFAULT 'capturing',
    transcript_json TEXT,
    assessment_json TEXT,
    lease_until INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at INTEGER NOT NULL,
    UNIQUE(session_id, ordinal)
);
CREATE INDEX IF NOT EXISTS live_conversations_profile ON live_conversation_sessions(profile_id, created_at);
CREATE INDEX IF NOT EXISTS live_events_session ON live_conversation_events(session_id, id);
