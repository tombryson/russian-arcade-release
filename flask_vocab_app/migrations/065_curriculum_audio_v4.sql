-- Only unrecorded speech can move to v4. Saved media and its original spec
-- remain immutable; the transcript, provider and chosen voice never change.
DROP TRIGGER curriculum_situation_voice_immutable;
CREATE TRIGGER curriculum_situation_voice_immutable BEFORE UPDATE OF voice_json ON curriculum_situations
WHEN OLD.voice_json IS NOT NULL AND NEW.voice_json IS NOT OLD.voice_json
 AND NOT COALESCE(
  OLD.audio_json IS NULL AND NEW.audio_json IS NULL
  AND OLD.stage='audio' AND NEW.stage='audio'
  AND OLD.state='running' AND NEW.state='running'
  AND json_extract(OLD.voice_json,'$.model') != 'eleven_v4'
  AND json_extract(NEW.voice_json,'$.model') = 'eleven_v4'
  AND json_remove(OLD.voice_json,'$.model','$.voice_settings') = json_remove(NEW.voice_json,'$.model','$.voice_settings')
  AND json_extract(NEW.voice_json,'$.voice_settings.stability') = 0.8
  AND json_extract(NEW.voice_json,'$.voice_settings.similarity_boost') = 0.85
  AND (SELECT COUNT(*) FROM json_each(NEW.voice_json,'$.voice_settings')) = 2,
  0)
BEGIN SELECT RAISE(ABORT,'Selected voice is immutable'); END;
