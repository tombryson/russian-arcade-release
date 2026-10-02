"""The opt-in smoke batch stays bounded and never supplies learner ASR."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from services.curriculum_sequence_content import load_asset

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/check_curriculum_audio_marking.py'
spec = importlib.util.spec_from_file_location('curriculum_audio_smoke', SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\x01\x00' * 8000)
    return output.getvalue()


class CurriculumAudioSmokeTests(unittest.TestCase):
    def test_dry_run_does_not_load_credentials_or_make_calls(self):
        with patch.object(smoke, 'load_config', side_effect=AssertionError('Dry runs do not need credentials')), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(smoke.main([]), 0)
        plan = json.loads(output.getvalue())
        self.assertFalse(plan['execute'])
        self.assertEqual((plan['tts_calls'], plan['audio_assessment_calls']), (3, 2))

    def test_failure_stops_batch_and_preserves_redacted_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            directory, output = Path(root) / 'audio', Path(root) / 'result.json'
            speech, assessor = Mock(), Mock()
            speech.speak.side_effect = RuntimeError('provider secret detail must never be copied')
            result = smoke.run_check({'ELEVENLABS_VOICE_IDS': ['test'], 'ELEVENLABS_MODEL': 'test',
                'SPEAKING_ASSESSMENT_MODEL': 'test'}, load_asset('location-exchange-v1'), directory, output,
                speech, assessor, lambda *_: None)
            self.assertEqual(result['state'], 'unavailable')
            self.assertEqual(result['calls'], {'tts': 1, 'audio_assessment': 0})
            self.assertEqual(result['error_type'], 'RuntimeError')
            self.assertNotIn('provider secret', output.read_text())
            assessor.assess.assert_not_called()
            with self.assertRaises(ValueError):
                smoke.run_check({'ELEVENLABS_VOICE_IDS': ['test']}, load_asset('location-exchange-v1'), directory, output,
                                speech, assessor, lambda *_: None)
            speech.speak.assert_called_once()

    def test_bounded_batch_reviews_only_exact_original_waveforms_with_turn_windows(self):
        with tempfile.TemporaryDirectory() as root:
            directory, output = Path(root) / 'audio', Path(root) / 'result.json'
            speech, assessor = Mock(), Mock()
            speech.speak.return_value = wav_bytes()
            def assess(path, scenario, dialogue, language, *, curriculum_contract, include_provenance, recording_turns):
                self.assertTrue(include_provenance)
                self.assertTrue(all(turn['role'] == 'assistant' for turn in dialogue))
                self.assertEqual([turn['content'] for turn in dialogue], [turn['prompt'] for turn in curriculum_contract['content']['turns']])
                self.assertEqual(recording_turns[0]['end_ms'], recording_turns[1]['start_ms'])
                with wave.open(str(path), 'rb') as audio:
                    self.assertEqual(audio.readframes(audio.getnframes()), b'\x01\x00' * 16000)
                spans = {turn['turn_id']: {'start_ms': turn['start_ms'], 'end_ms': turn['end_ms']} for turn in recording_turns}
                wrong = path.name.startswith('wrong-ending')
                return {'assessment_provenance': {'model': 'test', 'prompt_sha256': 'a' * 64},
                    'criterion_report': {'contract_sha256': curriculum_contract['contract_sha256'], 'judgements': [
                        {'criterion_id': c['id'], 'score': 0 if wrong and c['id'] == 'destination-form' else c['max_score'],
                         'outcome': 'not_satisfied' if wrong and c['id'] == 'destination-form' else 'satisfied', 'reason_code': None,
                         'feedback': 'Synthetic fixture only.', 'evidence': [spans[t] for t in curriculum_contract['content']['criterion_turns'][c['id']]]}
                        for c in curriculum_contract['criteria']]}}
            assessor.assess.side_effect = assess
            result = smoke.run_check({'ELEVENLABS_VOICE_IDS': ['test'], 'ELEVENLABS_MODEL': 'test',
                'SPEAKING_ASSESSMENT_MODEL': 'test'}, load_asset('location-exchange-v1'), directory, output,
                speech, assessor, lambda source, target: target.write_bytes(source.read_bytes()))
            self.assertEqual(result['state'], 'complete')
            self.assertEqual(result['calls'], {'tts': 3, 'audio_assessment': 2})
            self.assertTrue(result['script_expectations_met'])
            self.assertFalse(result['audible_ground_truth_verified'])
            self.assertFalse(result['learner_asr_supplied'])
            self.assertEqual(result['cases'][0]['original_audio']['recordings'][0], result['cases'][1]['original_audio']['recordings'][0])
            self.assertEqual(speech.speak.call_count, 3)
            self.assertEqual(assessor.assess.call_count, 2)


if __name__ == '__main__':
    unittest.main()
