CREATE TABLE progression_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE progression_preferences (
 profile_id TEXT PRIMARY KEY REFERENCES learning_profiles(id),
 preferred_level TEXT NOT NULL DEFAULT 'A1' CHECK(preferred_level IN ('A1','A2','B1','B2'))
);
CREATE TABLE progression_events (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 activity TEXT NOT NULL, source_key TEXT NOT NULL, content_key TEXT NOT NULL,
 title TEXT NOT NULL, category TEXT NOT NULL CHECK(category IN ('activity','review')),
 target_level TEXT, evidence_json TEXT NOT NULL, created_at INTEGER NOT NULL,
 reversed_at INTEGER, UNIQUE(profile_id,activity,source_key)
);
CREATE TABLE progression_entries (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 event_id TEXT REFERENCES progression_events(id), operation_key TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(amount!=0), eligible INTEGER NOT NULL CHECK(eligible IN (0,1)),
 category TEXT NOT NULL CHECK(category IN ('activity','review','legacy')),
 study_day TEXT NOT NULL, title TEXT NOT NULL, policy_version TEXT NOT NULL,
 created_at INTEGER NOT NULL, UNIQUE(profile_id,operation_key)
);
CREATE TABLE progression_claims (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), category TEXT NOT NULL,
 content_key TEXT NOT NULL, study_day TEXT NOT NULL, event_id TEXT REFERENCES progression_events(id),
 amount INTEGER NOT NULL DEFAULT 0 CHECK(amount>=0),
 PRIMARY KEY(profile_id,category,content_key,study_day)
);
CREATE INDEX progression_entries_day ON progression_entries(profile_id,study_day,category);
CREATE TRIGGER progression_entries_no_update BEFORE UPDATE ON progression_entries
BEGIN SELECT RAISE(ABORT,'Reward history is append-only'); END;
CREATE TRIGGER progression_entries_no_delete BEFORE DELETE ON progression_entries
BEGIN SELECT RAISE(ABORT,'Reward history is append-only'); END;
CREATE TABLE journey_worlds (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, title_ru TEXT NOT NULL,
 threshold INTEGER NOT NULL CHECK(threshold>=0), sort_order INTEGER NOT NULL,
 prerequisite TEXT REFERENCES journey_worlds(id), scene_id TEXT NOT NULL, scene_json TEXT NOT NULL
);
CREATE TABLE journey_progress (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), world_id TEXT NOT NULL REFERENCES journey_worlds(id),
 unlocked_at INTEGER NOT NULL, visited_at INTEGER, completed_at INTEGER,
 PRIMARY KEY(profile_id,world_id)
);
CREATE TABLE journey_answers (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 world_id TEXT NOT NULL REFERENCES journey_worlds(id), submission_id TEXT NOT NULL,
 answer TEXT NOT NULL, correct INTEGER NOT NULL, scene_json TEXT NOT NULL,
 result_json TEXT NOT NULL, created_at INTEGER NOT NULL,
 UNIQUE(profile_id,submission_id)
);
