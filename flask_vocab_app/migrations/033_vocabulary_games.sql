-- An unlock introduces a mechanic; it is not the mechanic's word list.
-- Keep previous attempts and their answers intact when starting a new selection.
ALTER TABLE journey_game_sessions ADD COLUMN superseded_at INTEGER;
DROP INDEX journey_game_active_profile;
DROP INDEX journey_game_active_guest;
CREATE UNIQUE INDEX journey_game_active_profile ON journey_game_sessions(profile_id,game_id) WHERE completed_at IS NULL AND superseded_at IS NULL AND profile_id IS NOT NULL;
CREATE UNIQUE INDEX journey_game_active_guest ON journey_game_sessions(guest_token,game_id) WHERE completed_at IS NULL AND superseded_at IS NULL AND guest_token IS NOT NULL;

CREATE TABLE journey_game_examples (
 id TEXT PRIMARY KEY,
 profile_id TEXT REFERENCES learning_profiles(id),
 guest_token TEXT,
 identity TEXT NOT NULL,
 word_id INTEGER REFERENCES words(id),
 form_id INTEGER REFERENCES forms(id),
 content_json TEXT NOT NULL CHECK(json_valid(content_json)),
 created_at INTEGER NOT NULL,
 CHECK ((profile_id IS NOT NULL AND guest_token IS NULL) OR (profile_id IS NULL AND guest_token IS NOT NULL))
);
CREATE UNIQUE INDEX journey_example_profile ON journey_game_examples(profile_id,identity) WHERE profile_id IS NOT NULL;
CREATE UNIQUE INDEX journey_example_guest ON journey_game_examples(guest_token,identity) WHERE guest_token IS NOT NULL;

CREATE TABLE journey_game_preparations (
 session_id TEXT PRIMARY KEY REFERENCES journey_game_sessions(id),
 items_json TEXT NOT NULL CHECK(json_valid(items_json)),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','ready','failed')),
 error TEXT,
 claim_id TEXT,
 lease_until INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
