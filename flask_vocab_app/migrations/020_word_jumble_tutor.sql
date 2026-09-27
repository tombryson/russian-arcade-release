-- Add richer feedback without rewriting previous answers, grades or comments.
ALTER TABLE word_jumble_attempts ADD COLUMN tutor_feedback TEXT
 CHECK (tutor_feedback IS NULL OR (json_valid(tutor_feedback) AND json_type(tutor_feedback) = 'object'));
