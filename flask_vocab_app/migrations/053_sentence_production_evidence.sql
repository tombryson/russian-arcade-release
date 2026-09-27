-- Keep the exact assessed report and support alongside its original response.
-- Legacy and unscoped tasks retain NULL; shared reports are a validated index.
ALTER TABLE translation_attempts ADD COLUMN criterion_report_json TEXT;
ALTER TABLE translation_attempts ADD COLUMN criterion_support_json TEXT;
ALTER TABLE word_jumble_attempts ADD COLUMN criterion_report_json TEXT;
ALTER TABLE word_jumble_attempts ADD COLUMN criterion_support_json TEXT;

CREATE TABLE translation_reference_views (
    sentence_id INTEGER NOT NULL REFERENCES sentences(id),
    profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
    after_attempt_id INTEGER REFERENCES translation_attempts(id),
    PRIMARY KEY (sentence_id, profile_id)
);
