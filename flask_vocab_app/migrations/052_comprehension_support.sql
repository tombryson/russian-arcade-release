-- New generated tasks record what was disclosed before each answer check.
-- Old payloads and reports remain reading evidence under their original policy.
CREATE TABLE comprehension_support_receipts (
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL,
 profile_id TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision >= 0),
 request_key TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('listened','transcript','translation','hint')),
 detail_json TEXT NOT NULL CHECK(json_valid(detail_json)),
 created_at INTEGER NOT NULL,
 inherited_from TEXT REFERENCES comprehension_support_receipts(id),
 UNIQUE(task_id,request_key),
 FOREIGN KEY(task_id,profile_id) REFERENCES comprehension_tasks(id,profile_id)
);
CREATE INDEX comprehension_support_task ON comprehension_support_receipts(task_id,revision);
ALTER TABLE comprehension_attempts ADD COLUMN support_receipts_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(support_receipts_json));
