-- Exact owned originals survive provider outages and review retries.
CREATE TABLE activity_review_submissions (
 id TEXT PRIMARY KEY,
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 activity TEXT NOT NULL CHECK(activity IN ('writing','comprehension','unit_exchange')),
 task_key TEXT NOT NULL,
 submission_id TEXT NOT NULL,
 request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64),
 task_revision INTEGER NOT NULL CHECK(task_revision>=0),
 original_json TEXT NOT NULL CHECK(json_valid(original_json)),
 task_json TEXT NOT NULL CHECK(json_valid(task_json)),
 contract_json TEXT NOT NULL CHECK(json_valid(contract_json)),
 support_json TEXT NOT NULL CHECK(json_valid(support_json)),
 support_receipts_json TEXT NOT NULL CHECK(json_valid(support_receipts_json)),
 effects_policy TEXT NOT NULL CHECK(effects_policy IN ('existing-activity-effects-v1','unit-transfer-no-effects-v1')),
 review_status TEXT NOT NULL DEFAULT 'submitted' CHECK(review_status IN ('submitted','reviewing','reviewed','review_unavailable')),
 review_token TEXT,
 review_started_at INTEGER,
 review_error TEXT,
 attempt_ref_json TEXT CHECK(attempt_ref_json IS NULL OR json_valid(attempt_ref_json)),
 result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)),
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 UNIQUE(profile_id,submission_id),
 UNIQUE(profile_id,activity,task_key,task_revision),
 UNIQUE(id,profile_id)
);
CREATE INDEX activity_review_submissions_task ON activity_review_submissions(profile_id,activity,task_key,created_at);
CREATE TRIGGER activity_review_original_immutable BEFORE UPDATE OF profile_id,activity,task_key,submission_id,request_sha256,task_revision,original_json,task_json,contract_json,support_json,support_receipts_json,effects_policy,created_at ON activity_review_submissions
BEGIN SELECT RAISE(ABORT,'Saved activity originals are immutable'); END;
