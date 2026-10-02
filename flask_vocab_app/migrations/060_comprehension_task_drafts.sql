-- Saving unfinished answers is separate from submitting them for feedback.
CREATE TABLE comprehension_task_drafts (
 task_id TEXT PRIMARY KEY REFERENCES comprehension_tasks(id),
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 task_revision INTEGER NOT NULL CHECK(task_revision>=0),
 revision INTEGER NOT NULL CHECK(revision>=1),
 answers_json TEXT NOT NULL CHECK(json_valid(answers_json)),
 updated_at INTEGER NOT NULL
);
