-- Freeze what a saved task asks before any learner response is assessed.
-- Reports are diagnostic. Neither table awards a course pass or an entitlement.
CREATE TABLE activity_task_contracts (
 id TEXT PRIMARY KEY,
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 activity TEXT NOT NULL,
 task_key TEXT NOT NULL,
 contract_json TEXT NOT NULL CHECK(json_valid(contract_json)),
 contract_sha256 TEXT NOT NULL CHECK(length(contract_sha256)=64),
 created_at INTEGER NOT NULL,
 UNIQUE(profile_id,activity,task_key),
 UNIQUE(id,profile_id)
);
CREATE TABLE activity_criterion_reports (
 id TEXT PRIMARY KEY,
 contract_id TEXT NOT NULL,
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 source_key TEXT NOT NULL,
 response_sha256 TEXT NOT NULL CHECK(length(response_sha256)=64),
 report_json TEXT NOT NULL CHECK(json_valid(report_json)),
 support_json TEXT NOT NULL CHECK(json_valid(support_json)),
 created_at INTEGER NOT NULL,
 UNIQUE(contract_id,source_key),
 FOREIGN KEY(contract_id,profile_id) REFERENCES activity_task_contracts(id,profile_id)
);
CREATE INDEX activity_criterion_reports_profile ON activity_criterion_reports(profile_id,created_at);
