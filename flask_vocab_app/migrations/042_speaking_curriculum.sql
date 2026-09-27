-- Authored category/level relationships. Topic IDs refer to the versioned
-- curriculum catalogue and are validated by the transactional seed compiler.
CREATE TABLE IF NOT EXISTS speaking_scenario_levels (
    scenario_id TEXT NOT NULL REFERENCES speaking_scenarios(id),
    target_level TEXT NOT NULL CHECK (target_level IN ('A1','A2','B1','B2')),
    topic_id TEXT NOT NULL,
    title TEXT NOT NULL,
    title_ru TEXT NOT NULL,
    description TEXT NOT NULL,
    description_ru TEXT NOT NULL,
    PRIMARY KEY (scenario_id,target_level)
);
