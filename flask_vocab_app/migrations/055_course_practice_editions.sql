-- Keep saved questions, answers and receipts intact when teaching is revised.
-- A learner may resume the old lesson or begin the new edition separately.
DROP INDEX course_target_practice_active;
CREATE UNIQUE INDEX course_target_practice_active
 ON course_target_practice_attempts(profile_id,release_id,section_id,content_version)
 WHERE status='active';
