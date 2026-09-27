-- Only the shipped preparation version has a known release/catalogue identity.
-- Refuse unknown history before adding defaults; never relabel it by guessing.
CREATE TABLE course_practice_identity_guard (valid INTEGER NOT NULL CHECK(valid=1));
INSERT INTO course_practice_identity_guard(valid)
 SELECT CASE WHEN content_version='a1-target-practice-v1'
   AND section_id IN ('home','postoffice','market','leavingtown')
   AND json_type(content_json)='array' AND json_array_length(content_json)>0
   THEN 1 ELSE 0 END FROM course_target_practice_attempts;
-- Unknown item-to-section references cannot inherit the known catalogue.
WITH known(section_id,target_id) AS (VALUES
 ('home','a1.greetings.exchange-names.read'),
 ('home','a1.family.identify-relatives.read'),
 ('home','a1.family.possessive-agreement.select'),
 ('home','a1.home.locate-object.read'),
 ('home','a1.home.identify-rooms-furniture.read'),
 ('home','a1.home.locate-object.listen'),
 ('home','a1.family.identify-relatives.listen'),
 ('home','a1.greetings.polite-greeting.read'),
 ('postoffice','a1.numbers.recognise-number.read'),
 ('postoffice','a1.numbers.event-time.read'),
 ('postoffice','a1.numbers.event-time.listen'),
 ('postoffice','a1.numbers.clock-hour-forms.select'),
 ('postoffice','a1.numbers.time-versus-duration.select'),
 ('postoffice','a1.daily_activities.describe-routine.read'),
 ('postoffice','a1.daily_activities.ask-current-activity.read'),
 ('postoffice','a1.daily_activities.irregular-present.select'),
 ('market','a1.food.identify-food-drink.read'),
 ('market','a1.food.make-request.read'),
 ('market','a1.food.polite-request.select'),
 ('market','a1.colors.identify-colour-size.read'),
 ('market','a1.colors.gender-agreement.select'),
 ('market','a1.clothing.identify-clothes.read'),
 ('market','a1.clothing.identify-clothing-description.listen'),
 ('market','a1.clothing.exceptional-nouns.select'),
 ('leavingtown','a1.places.ask-location.read'),
 ('leavingtown','a1.places.follow-directions.read'),
 ('leavingtown','a1.places.follow-directions.listen'),
 ('leavingtown','a1.places.location-versus-direction.select'),
 ('leavingtown','a1.places.direction-commands.select'),
 ('leavingtown','a1.weather.understand-weather.read'),
 ('leavingtown','a1.weather.choose-weather-plan.read'),
 ('leavingtown','a1.weather.impersonal-state.select')
)
INSERT INTO course_practice_identity_guard(valid)
 SELECT 0 FROM course_target_practice_attempts a,json_each(a.content_json) item
 WHERE NOT EXISTS (SELECT 1 FROM known k WHERE k.section_id=a.section_id
   AND k.target_id=json_extract(item.value,'$.target_id'));
DROP TABLE course_practice_identity_guard;

ALTER TABLE course_target_practice_attempts ADD COLUMN release_id TEXT NOT NULL DEFAULT 'a1-journey-v2';
ALTER TABLE course_target_practice_attempts ADD COLUMN target_catalogue_version TEXT NOT NULL DEFAULT 'a1-targets-v1';
-- Existing payloads remain byte-for-byte. Their retained versioned catalogue
-- supplies legacy metadata; new attempts also freeze their target definitions.
ALTER TABLE course_target_practice_attempts ADD COLUMN target_snapshot_json TEXT
 CHECK(target_snapshot_json IS NULL OR (json_valid(target_snapshot_json) AND json_type(target_snapshot_json)='object'));
DROP INDEX course_target_practice_active;
CREATE UNIQUE INDEX course_target_practice_active
 ON course_target_practice_attempts(profile_id,release_id,section_id) WHERE status='active';
