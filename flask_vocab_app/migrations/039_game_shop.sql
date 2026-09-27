-- Permanent rights replace automatic coin milestones. Keep every granted right.
CREATE TABLE journey_game_access_next (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 game_id TEXT NOT NULL,
 unlocked_at INTEGER NOT NULL,
 first_started_at INTEGER,
 policy_version TEXT NOT NULL,
 PRIMARY KEY(profile_id,game_id)
);
INSERT INTO journey_game_access_next
 SELECT profile_id,game_id,unlocked_at,first_started_at,policy_version FROM journey_game_access;
DROP TABLE journey_game_access;
ALTER TABLE journey_game_access_next RENAME TO journey_game_access;

-- Add a purchase category while preserving ledger rows, ordering and immutability.
CREATE TABLE progression_entries_next (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 event_id TEXT REFERENCES progression_events(id), operation_key TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(amount!=0), eligible INTEGER NOT NULL CHECK(eligible IN (0,1)),
 category TEXT NOT NULL CHECK(category IN ('activity','review','legacy','purchase')),
 study_day TEXT NOT NULL, title TEXT NOT NULL, policy_version TEXT NOT NULL,
 created_at INTEGER NOT NULL, UNIQUE(profile_id,operation_key),
 CHECK(category!='purchase' OR (amount<0 AND eligible=0 AND event_id IS NULL))
);
INSERT INTO progression_entries_next(rowid,id,profile_id,event_id,operation_key,amount,eligible,category,study_day,title,policy_version,created_at)
 SELECT rowid,id,profile_id,event_id,operation_key,amount,eligible,category,study_day,title,policy_version,created_at FROM progression_entries;
DROP TABLE progression_entries;
ALTER TABLE progression_entries_next RENAME TO progression_entries;
CREATE INDEX progression_entries_day ON progression_entries(profile_id,study_day,category);
CREATE TRIGGER progression_entries_no_update BEFORE UPDATE ON progression_entries
BEGIN SELECT RAISE(ABORT,'Reward history is append-only'); END;
CREATE TRIGGER progression_entries_no_delete BEFORE DELETE ON progression_entries
BEGIN SELECT RAISE(ABORT,'Reward history is append-only'); END;

CREATE TABLE journey_game_purchases (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 request_id TEXT NOT NULL,
 game_id TEXT NOT NULL,
 expected_price INTEGER NOT NULL CHECK(expected_price>=0),
 charged INTEGER NOT NULL CHECK(charged IN (0,25,50)),
 entry_id TEXT UNIQUE REFERENCES progression_entries(id),
 result_json TEXT NOT NULL CHECK(json_valid(result_json)),
 created_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,request_id),
 CHECK((charged=0 AND entry_id IS NULL) OR (charged>0 AND entry_id IS NOT NULL))
);
CREATE UNIQUE INDEX journey_game_purchase_once ON journey_game_purchases(profile_id,game_id) WHERE charged>0;
CREATE TRIGGER journey_game_purchases_no_update BEFORE UPDATE ON journey_game_purchases
BEGIN SELECT RAISE(ABORT,'Purchase history is append-only'); END;
CREATE TRIGGER journey_game_purchases_no_delete BEFORE DELETE ON journey_game_purchases
BEGIN SELECT RAISE(ABORT,'Purchase history is append-only'); END;
