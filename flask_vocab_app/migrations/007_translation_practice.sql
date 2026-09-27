-- Translation answers were not stored by the legacy activity. Do not invent history.
CREATE TABLE IF NOT EXISTS translation_drafts (
 sentence_id INTEGER PRIMARY KEY REFERENCES sentences(id),
 response TEXT NOT NULL, revision INTEGER NOT NULL CHECK (revision > 0), updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS translation_attempts (
 id INTEGER PRIMARY KEY, sentence_id INTEGER NOT NULL REFERENCES sentences(id),
 response TEXT NOT NULL, score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 4),
 score_max INTEGER NOT NULL DEFAULT 4 CHECK (score_max = 4),
 strength TEXT NOT NULL, next_step TEXT NOT NULL, example TEXT NOT NULL,
 ui_language TEXT NOT NULL CHECK (ui_language IN ('en','ru')),
 rubric TEXT NOT NULL DEFAULT 'translation-v1', created_at TEXT NOT NULL,
 coins_earned INTEGER NOT NULL, elo_change INTEGER NOT NULL,
 already_rewarded INTEGER NOT NULL CHECK (already_rewarded IN (0,1))
);
CREATE INDEX IF NOT EXISTS translation_attempts_sentence ON translation_attempts(sentence_id, id DESC);
