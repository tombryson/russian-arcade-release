-- Lessons reference native cards; they never own a second review schedule.
CREATE TABLE IF NOT EXISTS lesson_card_requests (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
 lesson_id TEXT NOT NULL REFERENCES lessons(id),
 revision_id TEXT NOT NULL REFERENCES lesson_revisions(id),
 first_page INTEGER NOT NULL, last_page INTEGER NOT NULL, quantity INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','processing','ready','failed')),
 lease_token TEXT, lease_until INTEGER NOT NULL DEFAULT 0,
 response TEXT CHECK(response IS NULL OR json_valid(response)),
 report TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(report)), error TEXT,
 batch_id TEXT REFERENCES native_card_batches(id), created_at INTEGER NOT NULL,
 UNIQUE(owner_id,revision_id,first_page,last_page,quantity)
);
CREATE TABLE IF NOT EXISTS lesson_card_targets (
 owner_id TEXT NOT NULL, lesson_id TEXT NOT NULL REFERENCES lessons(id),
 identity TEXT NOT NULL,
 item_id TEXT NOT NULL REFERENCES native_card_generation_items(id),
 PRIMARY KEY(owner_id,lesson_id,identity)
);
CREATE TABLE IF NOT EXISTS lesson_card_sources (
 request_id TEXT NOT NULL REFERENCES lesson_card_requests(id),
 item_id TEXT NOT NULL REFERENCES native_card_generation_items(id),
 revision_id TEXT NOT NULL, page INTEGER NOT NULL,
 PRIMARY KEY(request_id,item_id),
 FOREIGN KEY(revision_id,page) REFERENCES lesson_pages(revision_id,number)
);
CREATE INDEX IF NOT EXISTS lesson_card_source_item ON lesson_card_sources(item_id);
