-- Preserve existing batches, adding an explicit selection to request identity.
CREATE TABLE lesson_card_requests_new (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
 lesson_id TEXT NOT NULL REFERENCES lessons(id), revision_id TEXT NOT NULL REFERENCES lesson_revisions(id),
 first_page INTEGER NOT NULL, last_page INTEGER NOT NULL, quantity INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','processing','ready','failed')),
 lease_token TEXT, lease_until INTEGER NOT NULL DEFAULT 0,
 response TEXT CHECK(response IS NULL OR json_valid(response)),
 report TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(report)), error TEXT,
 batch_id TEXT REFERENCES native_card_batches(id), created_at INTEGER NOT NULL,
 selection_key TEXT NOT NULL DEFAULT 'pages', selection TEXT CHECK(selection IS NULL OR json_valid(selection)),
 UNIQUE(owner_id,revision_id,first_page,last_page,quantity,selection_key)
);
INSERT INTO lesson_card_requests_new(id,owner_id,lesson_id,revision_id,first_page,last_page,quantity,state,lease_token,lease_until,response,report,error,batch_id,created_at)
 SELECT id,owner_id,lesson_id,revision_id,first_page,last_page,quantity,state,lease_token,lease_until,response,report,error,batch_id,created_at FROM lesson_card_requests;
DROP TABLE lesson_card_requests;
ALTER TABLE lesson_card_requests_new RENAME TO lesson_card_requests;

CREATE TABLE IF NOT EXISTS lesson_ocr_pages (
 image_digest TEXT NOT NULL REFERENCES lesson_files(digest), policy TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)), created_at INTEGER NOT NULL,
 PRIMARY KEY(image_digest,policy)
);
CREATE TABLE IF NOT EXISTS lesson_word_picks (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, lesson_id TEXT NOT NULL REFERENCES lessons(id),
 revision_id TEXT NOT NULL, page INTEGER NOT NULL, token_key TEXT NOT NULL,
 surface TEXT NOT NULL, context TEXT NOT NULL, original TEXT NOT NULL,
 selected INTEGER NOT NULL DEFAULT 1 CHECK(selected IN (0,1)),
 request_id TEXT REFERENCES lesson_card_requests(id), item_id TEXT REFERENCES native_card_generation_items(id),
 error TEXT, created_at INTEGER NOT NULL,
 FOREIGN KEY(revision_id,page) REFERENCES lesson_pages(revision_id,number),
 UNIQUE(owner_id,revision_id,page,token_key)
);
CREATE INDEX IF NOT EXISTS lesson_pending_words ON lesson_word_picks(owner_id,lesson_id,revision_id,selected);
