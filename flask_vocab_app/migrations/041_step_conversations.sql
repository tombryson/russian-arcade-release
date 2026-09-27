-- Guided reply-choice practice is separate from recorded/live speaking evidence.
CREATE TABLE step_conversation_sessions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
    start_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    scenario_id TEXT NOT NULL REFERENCES speaking_scenarios(id),
    variant_id TEXT NOT NULL REFERENCES speaking_scenario_variants(id),
    scenario_json TEXT NOT NULL CHECK(json_valid(scenario_json)),
    target_level TEXT CHECK(target_level IS NULL OR target_level IN ('A1','A2','B1','B2')),
    language TEXT NOT NULL CHECK(language IN ('en','ru')),
    voice_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('preparing','active','completed','failed')),
    dialogue_json TEXT CHECK(dialogue_json IS NULL OR json_valid(dialogue_json)),
    progress_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(progress_json)),
    current_index INTEGER NOT NULL DEFAULT 0 CHECK(current_index>=0),
    lease_until INTEGER NOT NULL DEFAULT 0,
    preparation_id TEXT,
    error TEXT,
    reward_amount INTEGER NOT NULL DEFAULT 0 CHECK(reward_amount>=0),
    created_at INTEGER NOT NULL,
    completed_at INTEGER,
    UNIQUE(profile_id,start_key)
);
CREATE INDEX step_conversations_profile ON step_conversation_sessions(profile_id,created_at);
CREATE TABLE step_conversation_answers (
    session_id TEXT NOT NULL REFERENCES step_conversation_sessions(id) ON DELETE CASCADE,
    submission_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    option_id TEXT NOT NULL,
    correct INTEGER NOT NULL CHECK(correct IN (0,1)),
    created_at INTEGER NOT NULL,
    PRIMARY KEY(session_id,submission_id)
);
