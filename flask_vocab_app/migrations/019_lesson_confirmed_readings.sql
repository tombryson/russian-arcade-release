-- A previous tap is not evidence that the learner checked the OCR spelling.
ALTER TABLE lesson_word_picks ADD COLUMN reading_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(reading_confirmed IN (0,1));
