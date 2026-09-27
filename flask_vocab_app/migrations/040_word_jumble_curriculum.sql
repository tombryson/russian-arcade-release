-- Freeze the displayed curriculum task for new Word Jumble sessions.
-- Existing games keep NULL and their original free-sentence instructions.
ALTER TABLE word_jumble_games ADD COLUMN task_json TEXT
 CHECK(task_json IS NULL OR (json_valid(task_json) AND json_type(task_json)='object'));
