CREATE TABLE IF NOT EXISTS learning_activity_types (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    title_ru TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS speaking_scenarios (
    id TEXT PRIMARY KEY,
    activity_type_id TEXT NOT NULL REFERENCES learning_activity_types(id),
    title TEXT NOT NULL,
    title_ru TEXT NOT NULL,
    description TEXT NOT NULL,
    description_ru TEXT NOT NULL,
    role TEXT NOT NULL,
    role_ru TEXT NOT NULL,
    icon TEXT NOT NULL,
    sign TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
CREATE TABLE IF NOT EXISTS speaking_scenario_variants (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL REFERENCES speaking_scenarios(id),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
CREATE INDEX IF NOT EXISTS speaking_variants_scenario ON speaking_scenario_variants(scenario_id,enabled);
ALTER TABLE live_conversation_sessions ADD COLUMN scenario_id TEXT REFERENCES speaking_scenarios(id);
ALTER TABLE live_conversation_sessions ADD COLUMN variant_id TEXT REFERENCES speaking_scenario_variants(id);
CREATE INDEX IF NOT EXISTS live_sessions_scenario ON live_conversation_sessions(profile_id,scenario_id,created_at);
