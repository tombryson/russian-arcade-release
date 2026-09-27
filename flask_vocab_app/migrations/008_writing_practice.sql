-- Preserve original tasks and saved writing; add metadata separately.
CREATE TABLE IF NOT EXISTS writing_details (
 exercise_id INTEGER PRIMARY KEY REFERENCES writing_exercises(id),
 title TEXT NOT NULL, title_en TEXT NOT NULL, task_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS writing_drafts (
 exercise_id INTEGER PRIMARY KEY REFERENCES writing_exercises(id),
 response TEXT NOT NULL, revision INTEGER NOT NULL CHECK (revision > 0), updated_at TEXT
);
CREATE TABLE IF NOT EXISTS writing_attempts (
 id INTEGER PRIMARY KEY, exercise_id INTEGER NOT NULL REFERENCES writing_exercises(id),
 response TEXT NOT NULL, score INTEGER, score_max INTEGER,
 feedback TEXT NOT NULL DEFAULT '', strength TEXT, next_step TEXT, example TEXT,
 ui_language TEXT, created_at TEXT, source TEXT NOT NULL CHECK (source IN ('legacy','writing-v1')),
 CHECK (source = 'legacy' OR (score IS NOT NULL AND score BETWEEN 0 AND 10 AND score_max IS NOT NULL AND score_max = 10))
);
CREATE INDEX IF NOT EXISTS writing_attempts_exercise ON writing_attempts(exercise_id,id DESC);
-- Old creation time is not a draft/check timestamp. Leave unknown dates empty.
INSERT OR IGNORE INTO writing_drafts(exercise_id,response,revision,updated_at)
 SELECT id,user_response,1,NULL FROM writing_exercises WHERE user_response IS NOT NULL;
INSERT INTO writing_attempts(exercise_id,response,score,score_max,feedback,source)
 SELECT id,COALESCE(user_response,''),score,CASE WHEN score BETWEEN 0 AND 10 THEN 10 ELSE NULL END,
 COALESCE(feedback,''),'legacy' FROM writing_exercises e
 WHERE (score IS NOT NULL OR feedback IS NOT NULL)
 AND NOT EXISTS (SELECT 1 FROM writing_attempts a WHERE a.exercise_id=e.id);
