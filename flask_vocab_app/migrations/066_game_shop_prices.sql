-- Prices belong to the current shop policy, while saved receipts retain their
-- original charge. Preserve receipt rows, ordering and append-only guarantees.
CREATE TABLE journey_game_purchases_next (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 request_id TEXT NOT NULL,
 game_id TEXT NOT NULL,
 expected_price INTEGER NOT NULL CHECK(expected_price>=0),
 charged INTEGER NOT NULL CHECK(typeof(charged)='integer' AND charged>=0),
 entry_id TEXT UNIQUE REFERENCES progression_entries(id),
 result_json TEXT NOT NULL CHECK(json_valid(result_json)),
 created_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,request_id),
 CHECK((charged=0 AND entry_id IS NULL) OR (charged>0 AND entry_id IS NOT NULL))
);
INSERT INTO journey_game_purchases_next(rowid,profile_id,request_id,game_id,expected_price,charged,entry_id,result_json,created_at)
 SELECT rowid,profile_id,request_id,game_id,expected_price,charged,entry_id,result_json,created_at FROM journey_game_purchases;
DROP TABLE journey_game_purchases;
ALTER TABLE journey_game_purchases_next RENAME TO journey_game_purchases;
CREATE UNIQUE INDEX journey_game_purchase_once ON journey_game_purchases(profile_id,game_id) WHERE charged>0;
CREATE TRIGGER journey_game_purchases_no_update BEFORE UPDATE ON journey_game_purchases
BEGIN SELECT RAISE(ABORT,'Purchase history is append-only'); END;
CREATE TRIGGER journey_game_purchases_no_delete BEFORE DELETE ON journey_game_purchases
BEGIN SELECT RAISE(ABORT,'Purchase history is append-only'); END;
