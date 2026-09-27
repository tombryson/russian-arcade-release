-- Keep every v1 attempt and receipt byte-for-byte. Only identity is added.
ALTER TABLE course_checkpoint_attempts ADD COLUMN release_id TEXT NOT NULL DEFAULT 'a1-v1';
ALTER TABLE course_checkpoint_attempts ADD COLUMN band TEXT NOT NULL DEFAULT 'A1' CHECK(band IN ('A1','A2','B1','B2','C1','C2'));
DROP INDEX course_checkpoint_active;
DROP INDEX course_checkpoint_history;
CREATE UNIQUE INDEX course_checkpoint_active ON course_checkpoint_attempts(profile_id,release_id,chapter_id) WHERE status='active';
CREATE INDEX course_checkpoint_history ON course_checkpoint_attempts(profile_id,release_id,chapter_id,created_at);
CREATE UNIQUE INDEX course_checkpoint_owned_release ON course_checkpoint_attempts(id,profile_id,release_id,chapter_id);

CREATE TABLE course_enrolments (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 band TEXT NOT NULL CHECK(band IN ('A1','A2','B1','B2','C1','C2')),
 release_id TEXT NOT NULL,
 started_at INTEGER NOT NULL, migration_source TEXT,
 PRIMARY KEY(profile_id,band)
);
INSERT INTO course_enrolments(profile_id,band,release_id,started_at,migration_source)
 SELECT p.id,'A1','a1-v1',COALESCE((SELECT MIN(a.created_at) FROM course_checkpoint_attempts a WHERE a.profile_id=p.id),p.created_at),'schema-044'
 FROM learning_profiles p;

CREATE TABLE course_chapter_passes_v45 (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id), chapter_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL REFERENCES course_checkpoint_attempts(id), passed_at INTEGER NOT NULL,
 release_id TEXT NOT NULL DEFAULT 'a1-v1', requirement_version TEXT NOT NULL,
 PRIMARY KEY(profile_id,release_id,chapter_id),
 FOREIGN KEY(attempt_id,profile_id,release_id,chapter_id) REFERENCES course_checkpoint_attempts(id,profile_id,release_id,chapter_id)
);
INSERT INTO course_chapter_passes_v45(profile_id,chapter_id,attempt_id,passed_at,release_id,requirement_version)
 SELECT p.profile_id,p.chapter_id,p.attempt_id,p.passed_at,'a1-v1',
        (SELECT a.rubric_version FROM course_checkpoint_attempts a WHERE a.id=p.attempt_id)
 FROM course_chapter_passes p;
DROP TABLE course_chapter_passes;
ALTER TABLE course_chapter_passes_v45 RENAME TO course_chapter_passes;

-- Access already earned is durable, even if an enrolment later changes.
CREATE TABLE course_continuation_entitlements (
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 target_level TEXT NOT NULL CHECK(target_level IN ('A2','B1','B2','C1','C2')),
 source_release_id TEXT NOT NULL, source TEXT NOT NULL,
 earned_at INTEGER NOT NULL,
 PRIMARY KEY(profile_id,target_level)
);
INSERT INTO course_continuation_entitlements(profile_id,target_level,source_release_id,source,earned_at)
 SELECT profile_id,'A2','a1-v1','legacy-course-completion',MAX(passed_at)
 FROM course_chapter_passes
 WHERE release_id='a1-v1' AND chapter_id IN ('a1-post-office','a1-home','a1-market','a1-delivery')
 GROUP BY profile_id HAVING COUNT(DISTINCT chapter_id)=4;

-- Widen storage only; later levels still require published content/adapters.
CREATE TABLE course_evidence_v45 (
 event_id TEXT PRIMARY KEY REFERENCES progression_events(id),
 profile_id TEXT NOT NULL REFERENCES learning_profiles(id),
 topic_id TEXT NOT NULL, activity TEXT NOT NULL, content_key TEXT NOT NULL,
 target_level TEXT NOT NULL CHECK(target_level IN ('A1','A2','B1','B2','C1','C2')),
 score REAL NOT NULL CHECK(score>=0.7 AND score<=1),
 policy_version TEXT NOT NULL, created_at INTEGER NOT NULL
);
INSERT INTO course_evidence_v45 SELECT * FROM course_evidence;
DROP TABLE course_evidence;
ALTER TABLE course_evidence_v45 RENAME TO course_evidence;
CREATE INDEX course_evidence_profile_topic ON course_evidence(profile_id,topic_id);
