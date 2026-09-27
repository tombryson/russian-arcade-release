-- Existing practice belongs to the original learner. Keep IDs, content, media,
-- answers, grades and reward history intact; no personal table is rebuilt.
INSERT OR IGNORE INTO learning_profiles(id,display_name,avatar,study_timezone,created_at)
 VALUES ('personal-learning','Me','cat','UTC',CAST(strftime('%s','now') AS INTEGER));
ALTER TABLE saved_stories ADD COLUMN owner_profile_id TEXT REFERENCES learning_profiles(id);
ALTER TABLE writing_exercises ADD COLUMN owner_profile_id TEXT REFERENCES learning_profiles(id);
ALTER TABLE word_jumble_games ADD COLUMN owner_profile_id TEXT REFERENCES learning_profiles(id);
ALTER TABLE sentences ADD COLUMN owner_profile_id TEXT REFERENCES learning_profiles(id);
UPDATE saved_stories SET owner_profile_id='personal-learning' WHERE owner_profile_id IS NULL;
UPDATE writing_exercises SET owner_profile_id='personal-learning' WHERE owner_profile_id IS NULL;
UPDATE word_jumble_games SET owner_profile_id='personal-learning' WHERE owner_profile_id IS NULL;
UPDATE sentences SET owner_profile_id='personal-learning' WHERE owner_profile_id IS NULL;
CREATE INDEX saved_stories_owner ON saved_stories(owner_profile_id,id);
CREATE INDEX writing_exercises_owner ON writing_exercises(owner_profile_id,id);
CREATE INDEX word_jumble_games_owner ON word_jumble_games(owner_profile_id,id);
CREATE INDEX sentences_owner ON sentences(owner_profile_id,id);
