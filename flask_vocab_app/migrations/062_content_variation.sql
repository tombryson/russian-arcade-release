-- Recent generated material is private to its learner/workspace, including
-- encountered words which the learner has not chosen to save to vocabulary.
CREATE TABLE content_variation_exposures (
 id INTEGER PRIMARY KEY,
 owner_scope TEXT NOT NULL,
 identity TEXT NOT NULL,
 activity TEXT NOT NULL,
 content_hash TEXT NOT NULL,
 excerpt TEXT NOT NULL,
 situation_json TEXT NOT NULL CHECK(json_valid(situation_json)),
 lemmas_json TEXT NOT NULL CHECK(json_valid(lemmas_json)),
 created_at INTEGER NOT NULL,
 UNIQUE(owner_scope, identity)
);
CREATE INDEX content_variation_owner_recent ON content_variation_exposures(owner_scope, id DESC);
CREATE INDEX content_variation_owner_hash ON content_variation_exposures(owner_scope, content_hash);
