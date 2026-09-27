-- Keep earlier activity answers untouched until the learner explicitly restarts.
ALTER TABLE first_delivery_attempts ADD COLUMN learned_json TEXT NOT NULL
 DEFAULT '[]' CHECK(json_valid(learned_json));
ALTER TABLE first_delivery_attempts ADD COLUMN previous_attempt_json TEXT
 CHECK(previous_attempt_json IS NULL OR json_valid(previous_attempt_json));
