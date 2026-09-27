-- Additive lesson history. Original lessons/prompts/responses remain intact.
CREATE TABLE IF NOT EXISTS lesson_files (
 digest TEXT PRIMARY KEY, byte_size INTEGER NOT NULL CHECK(byte_size > 0),
 media_type TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS lesson_revisions (
 id TEXT PRIMARY KEY, lesson_id TEXT NOT NULL REFERENCES lessons(id),
 number INTEGER NOT NULL, parent_id TEXT REFERENCES lesson_revisions(id),
 fingerprint TEXT NOT NULL, materials TEXT NOT NULL CHECK(json_valid(materials)),
 state TEXT NOT NULL CHECK(state IN ('queued','processing','ready','failed')),
 stage TEXT NOT NULL DEFAULT 'queued', model TEXT NOT NULL,
 lease_token TEXT, lease_until INTEGER NOT NULL DEFAULT 0,
 error TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL,
 UNIQUE(lesson_id,number), UNIQUE(lesson_id,fingerprint)
);
CREATE TABLE IF NOT EXISTS lesson_pages (
 revision_id TEXT NOT NULL REFERENCES lesson_revisions(id), number INTEGER NOT NULL,
 source_digest TEXT NOT NULL REFERENCES lesson_files(digest), source_page INTEGER NOT NULL,
 image_digest TEXT NOT NULL REFERENCES lesson_files(digest), base_digest TEXT NOT NULL,
 extraction TEXT CHECK(extraction IS NULL OR json_valid(extraction)),
 PRIMARY KEY(revision_id,number)
);
CREATE TABLE IF NOT EXISTS lesson_extraction_cache (
 image_digest TEXT NOT NULL REFERENCES lesson_files(digest), policy TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)), PRIMARY KEY(image_digest,policy)
);
CREATE TABLE IF NOT EXISTS lesson_plans (
 id TEXT PRIMARY KEY, revision_id TEXT NOT NULL UNIQUE REFERENCES lesson_revisions(id),
 payload TEXT NOT NULL CHECK(json_valid(payload)), model TEXT NOT NULL,
 policy TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS lesson_tasks (
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES lesson_plans(id),
 position INTEGER NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)),
 UNIQUE(plan_id,position)
);
CREATE TABLE IF NOT EXISTS lesson_drafts (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), task_id TEXT NOT NULL REFERENCES lesson_tasks(id),
 answer TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,task_id)
);
CREATE TABLE IF NOT EXISTS lesson_attempts (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 task_id TEXT NOT NULL REFERENCES lesson_tasks(id), submission_key TEXT NOT NULL,
 answer TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('checking','checked','failed')),
 feedback TEXT CHECK(feedback IS NULL OR json_valid(feedback)), model TEXT NOT NULL,
 lease_until INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
 UNIQUE(profile_id,submission_key)
);
CREATE TABLE IF NOT EXISTS lesson_progress (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), lesson_id TEXT NOT NULL REFERENCES lessons(id),
 revision_id TEXT REFERENCES lesson_revisions(id), page INTEGER NOT NULL DEFAULT 1,
 base_digest TEXT, task_id TEXT REFERENCES lesson_tasks(id), updated_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,lesson_id)
);
CREATE INDEX IF NOT EXISTS lesson_attempts_task ON lesson_attempts(profile_id,task_id,created_at);
