-- Titles shown by interface language; the original Russian title stays intact.
CREATE TABLE IF NOT EXISTS story_title_translations (
    story_id INTEGER NOT NULL REFERENCES saved_stories(id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 100),
    PRIMARY KEY (story_id, language)
);
