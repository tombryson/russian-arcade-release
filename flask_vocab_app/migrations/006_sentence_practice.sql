-- Keep unfinished writing separate from checked answers. Legacy rows remain intact.
CREATE TABLE IF NOT EXISTS word_jumble_drafts (
 game_id TEXT PRIMARY KEY REFERENCES word_jumble_games(id),
 response TEXT NOT NULL, revision INTEGER NOT NULL CHECK (revision > 0),
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS word_jumble_attempts (
 id INTEGER PRIMARY KEY, game_id TEXT NOT NULL REFERENCES word_jumble_games(id),
 response TEXT NOT NULL, score INTEGER, score_max INTEGER,
 feedback TEXT NOT NULL, strength TEXT, next_step TEXT, example TEXT,
 ui_language TEXT, created_at TEXT,
 source TEXT NOT NULL CHECK (source IN ('legacy', 'sentence-v1')),
 CHECK (source = 'legacy' OR (score BETWEEN 0 AND 4 AND score_max = 4
   AND score IS NOT NULL AND score_max IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS word_jumble_attempts_game ON word_jumble_attempts(game_id, id DESC);
-- Old check dates and some old score scales were never stored. Do not invent them.
INSERT INTO word_jumble_attempts(game_id, response, score, score_max, feedback, source)
 SELECT id, COALESCE(user_response, ''), score,
 CASE WHEN score BETWEEN 0 AND 4 THEN 4 ELSE NULL END,
 COALESCE(feedback, ''), 'legacy'
 FROM word_jumble_games g WHERE user_response IS NOT NULL AND (feedback IS NOT NULL OR score IS NOT NULL)
 AND NOT EXISTS (SELECT 1 FROM word_jumble_attempts a WHERE a.game_id=g.id);
