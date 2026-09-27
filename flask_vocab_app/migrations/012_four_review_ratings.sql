-- Widen the rating constraint without altering historical events or schedules.
-- The migration runner disables FKs before the transaction, then checks them.
CREATE TABLE review_events_next (
 attempt_id TEXT PRIMARY KEY REFERENCES activity_attempts(id),
 occurrence_id TEXT NOT NULL UNIQUE REFERENCES review_session_items(id),
 card_id TEXT NOT NULL REFERENCES card_definitions(id), card_version_id TEXT NOT NULL REFERENCES card_versions(id),
 rating TEXT NOT NULL CHECK (rating IN ('again','hard','good','easy')),
 before_state TEXT NOT NULL CHECK (json_valid(before_state)), after_state TEXT NOT NULL CHECK (json_valid(after_state)),
 before_session TEXT NOT NULL CHECK (json_valid(before_session)),
 scheduler_log TEXT NOT NULL CHECK (json_valid(scheduler_log)), scheduler_policy TEXT NOT NULL CHECK (json_valid(scheduler_policy)),
 study_day TEXT NOT NULL, study_timezone TEXT NOT NULL, created_at INTEGER NOT NULL
);
INSERT INTO review_events_next(rowid,attempt_id,occurrence_id,card_id,card_version_id,rating,before_state,after_state,before_session,scheduler_log,scheduler_policy,study_day,study_timezone,created_at)
 SELECT rowid,attempt_id,occurrence_id,card_id,card_version_id,rating,before_state,after_state,before_session,scheduler_log,scheduler_policy,study_day,study_timezone,created_at FROM review_events;
DROP TABLE review_events;
ALTER TABLE review_events_next RENAME TO review_events;
CREATE TRIGGER review_events_no_update BEFORE UPDATE ON review_events
BEGIN SELECT RAISE(ABORT,'Review history is append-only'); END;
CREATE TRIGGER review_events_no_delete BEFORE DELETE ON review_events
BEGIN SELECT RAISE(ABORT,'Review history is append-only'); END;
