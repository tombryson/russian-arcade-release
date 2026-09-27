-- Introduction milestones are explicit actions, never inferred from old rewards.
CREATE TABLE profile_onboarding (
 profile_id TEXT PRIMARY KEY REFERENCES learning_profiles(id),
 coins_introduced_at INTEGER,
 progress_introduced_at INTEGER,
 CHECK (progress_introduced_at IS NULL OR coins_introduced_at IS NOT NULL)
);
INSERT INTO profile_onboarding(profile_id) SELECT id FROM learning_profiles;
