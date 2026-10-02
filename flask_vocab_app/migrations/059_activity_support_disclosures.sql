-- Help is committed before its content is shown to a learner.
CREATE TABLE activity_support_disclosures (
 id TEXT PRIMARY KEY,
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 activity TEXT NOT NULL CHECK(activity='writing'),
 task_key TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind='model_answer'),
 contract_sha256 TEXT NOT NULL CHECK(length(contract_sha256)=64),
 content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
 created_at INTEGER NOT NULL,
 UNIQUE(profile_id,activity,task_key,kind)
);
CREATE TRIGGER activity_support_disclosure_immutable BEFORE UPDATE ON activity_support_disclosures
BEGIN SELECT RAISE(ABORT,'Saved help disclosures are immutable'); END;
