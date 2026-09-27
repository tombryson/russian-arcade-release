ALTER TABLE speaking_scenario_variants ADD COLUMN target_level TEXT
    CHECK(target_level IS NULL OR target_level IN ('A1','A2','B1','B2'));
ALTER TABLE live_conversation_sessions ADD COLUMN target_level TEXT
    CHECK(target_level IS NULL OR target_level IN ('A1','A2','B1','B2'));
CREATE INDEX speaking_variants_level ON speaking_scenario_variants(scenario_id,target_level,enabled);
CREATE INDEX live_sessions_level ON live_conversation_sessions(profile_id,scenario_id,target_level,created_at);
