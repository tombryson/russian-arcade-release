CREATE TABLE IF NOT EXISTS conversation_sessions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
    mode TEXT NOT NULL CHECK(mode IN ('conversation','lab')),
    scenario_json TEXT NOT NULL,
    voice_id TEXT NOT NULL,
    ui_language TEXT NOT NULL,
    start_key TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','completed')),
    created_at INTEGER NOT NULL,
    UNIQUE(profile_id,start_key)
);
CREATE TABLE IF NOT EXISTS conversation_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    submission_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    audio_filename TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    case_id TEXT,
    state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','ready','failed')),
    lease_until INTEGER NOT NULL DEFAULT 0,
    transcript_json TEXT,
    comparisons_json TEXT,
    reply_json TEXT,
    assessment_json TEXT,
    assessment_state TEXT NOT NULL DEFAULT 'pending',
    reply_audio_filename TEXT,
    audio_state TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    assessment_error TEXT,
    audio_error TEXT,
    created_at INTEGER NOT NULL,
    UNIQUE(session_id,ordinal),
    UNIQUE(session_id,submission_id)
);
CREATE INDEX IF NOT EXISTS conversation_sessions_profile ON conversation_sessions(profile_id,created_at);
