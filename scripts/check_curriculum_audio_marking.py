"""Bounded UnitExchange audio smoke check; dry run unless --execute is supplied.

No learner database or learner ASR is used. Three synthetic speech clips make
two original-audio cases. The shared first reply controls one source of variation.
Synthesis scripts are hypotheses, not independently verified audible ground truth.
Never retries: stop on the first unavailable provider or invalid assessment.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import random
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))
DEFAULT_VOICES = ('ymDCYd8puC7gYjxIamPt', 'gXMhWmiqsFkrcssqVb5k', 'sRk0zCqhS2Cmv0bzx5wA', '3EuKHIEZbSzrHGNmdYsx')
CLIPS = {'location': 'Я сейчас в школе.', 'destination-correct': 'Я иду в библиотеку.',
         'destination-wrong-ending': 'Я иду в библиотека.'}
CASES = (('correct', 'destination-correct', 'satisfied', 2),
         ('wrong-ending', 'destination-wrong-ending', 'not_satisfied', 0))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_config(path):
    # Avoid app_config(): importing it also searches other environment files.
    from dotenv import dotenv_values
    if not path.is_file():
        raise ValueError('ConfigurationUnavailable')
    values = dotenv_values(path, interpolate=False)
    config = {name: values.get(name) for name in ('OPENAI_API_KEY', 'ELEVENLABS_API_KEY')}
    config['ELEVENLABS_MODEL'] = values.get('ELEVENLABS_MODEL') or 'eleven_v4'
    config['SPEAKING_ASSESSMENT_MODEL'] = values.get('SPEAKING_ASSESSMENT_MODEL') or 'gpt-audio-1.5'
    config['ELEVENLABS_VOICE_IDS'] = tuple(v.strip() for v in (values.get('ELEVENLABS_VOICE_IDS') or ','.join(DEFAULT_VOICES)).split(',') if v.strip())
    if not all(config.get(name) for name in ('OPENAI_API_KEY', 'ELEVENLABS_API_KEY', 'ELEVENLABS_VOICE_IDS')):
        raise ValueError('ConfigurationUnavailable')
    return config


def assemble(directory, first, second):
    """Apply the same untrimmed PCM concatenation and timing as UnitExchange."""
    pcm, recordings, offset = bytearray(), [], 0
    for turn_id, clip in (('location', first), ('destination', second)):
        path = directory / clip['review_file']
        raw = path.read_bytes()
        if digest(raw) != clip['review_sha256']:
            raise ValueError('ChangedSyntheticRecording')
        with wave.open(io.BytesIO(raw), 'rb') as audio:
            if audio.getparams()[:3] != (1, 2, 16000):
                raise ValueError('UnsupportedSyntheticRecording')
            count = audio.getnframes()
            samples = audio.readframes(count)
            if len(samples) != count * 2:
                raise ValueError('IncompleteSyntheticRecording')
        pcm.extend(samples)
        recordings.append({'turn_id': turn_id, 'sha256': clip['original_sha256'],
                           'assessment_sha256': clip['review_sha256'],
                           'start_ms': offset * 1000 // 16000, 'end_ms': (offset + count) * 1000 // 16000})
        offset += count
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(pcm)
    waveform = output.getvalue()
    return waveform, {'sha256': digest(waveform), 'duration_ms': offset * 1000 // 16000, 'recordings': recordings}


def run_check(config, asset, directory, output, speech, assessor, convert):
    from services.curriculum_sequence_content import task_contract
    from services.unit_exchange import scenario_for_contract, turn_windows, validate_turn_evidence
    # Refuse accidental reruns of a paid batch, including partial failures.
    if len(CLIPS) > 4 or len(CASES) > 2 or any(not 1 <= len(text) <= 100 for text in CLIPS.values()):
        raise ValueError('SyntheticBatchExceedsCallBounds')
    if output.exists() or directory.exists() or directory.resolve().is_relative_to(ROOT):
        raise ValueError('UseFreshOutputAndExternalAudioDirectory')
    directory.mkdir(parents=True, mode=0o700)
    voice = random.choice(config['ELEVENLABS_VOICE_IDS'])
    result = {'kind': 'synthetic-original-audio-provider-smoke-check', 'at': datetime.now(timezone.utc).isoformat(),
              'asset': asset['id'], 'asset_sha256': digest(json.dumps(asset, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()),
              'synthesis': {'provider': 'elevenlabs', 'model': config['ELEVENLABS_MODEL'], 'voice_id': voice},
              'assessment_model': config['SPEAKING_ASSESSMENT_MODEL'],
              'maximum_calls': {'tts': 4, 'audio_assessment': 2}, 'calls': {'tts': 0, 'audio_assessment': 0},
              'automatic_retries': 0, 'learner_asr_supplied': False,
              'independent_audio_review': False, 'audible_ground_truth_verified': False,
              'proficiency_validated': False, 'state': 'running', 'clips': {}, 'cases': [],
              'limitation': 'TTS may pronounce or repair text differently. Script agreement cannot establish correctness of audible endings or ASR-repair resistance without independent listening.'}

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')

    save()
    phase = 'synthesis'
    try:
        for identity, text in CLIPS.items():
            result['calls']['tts'] += 1
            save()
            original = speech.speak(text, voice)
            original_path, review_path = directory / (identity + '.mp3'), directory / (identity + '.wav')
            original_path.write_bytes(original); original_path.chmod(0o600)
            convert(original_path, review_path); review_path.chmod(0o600)
            with wave.open(str(review_path), 'rb') as audio:
                duration = audio.getnframes() * 1000 // audio.getframerate()
            if not 200 <= duration <= 15000:
                raise ValueError('SyntheticReplyExceedsDurationBounds')
            result['clips'][identity] = {'synthesis_script': text, 'script_sha256': digest(text.encode()),
                'original_file': original_path.name, 'original_sha256': digest(original), 'original_size_bytes': len(original),
                'review_file': review_path.name, 'review_sha256': digest(review_path.read_bytes()), 'duration_ms': duration}
            save()
        phase = 'audio_assessment'
        for identity, destination, expected_outcome, expected_score in CASES:
            contract = task_contract(asset, 'synthetic-audio-' + identity, purpose='diagnostic')
            waveform, source = assemble(directory, result['clips']['location'], result['clips'][destination])
            path = directory / (identity + '-original-bundle.wav'); path.write_bytes(waveform); path.chmod(0o600)
            entry = {'id': identity, 'state': 'reviewing', 'contract_sha256': contract['contract_sha256'],
                     'original_bundle_file': path.name, 'original_audio': source,
                     'turn_windows': turn_windows(contract, source['recordings'], source['duration_ms']),
                     'expected_from_script_only': {'destination-form': {'outcome': expected_outcome, 'score': expected_score}}}
            result['cases'].append(entry)
            result['calls']['audio_assessment'] += 1
            save()
            checked = assessor.assess(path, scenario_for_contract(contract),
                [{'role': 'assistant', 'content': turn['prompt']} for turn in asset['content']['turns']],
                'en', curriculum_contract=contract, include_provenance=True, recording_turns=source['recordings'])
            validate_turn_evidence(contract, checked, source)
            rows = {row['criterion_id']: row for row in checked['criterion_report']['judgements']}
            matches = (rows['destination-form']['outcome'] == expected_outcome and rows['destination-form']['score'] == expected_score
                       and rows['location-form']['score'] == 2
                       and all(rows[key]['outcome'] == 'satisfied' for key in ('current-place', 'next-place')))
            entry.update(state='matches_script_expectation_unverified' if matches else 'disagreement_with_script_expectation',
                         script_expectations_met=matches, assessment=checked)
            save()
        result['state'] = 'complete'
    except Exception as error:
        # Never persist provider exception bodies or environment contents.
        result.update(state='unavailable', stopped_phase=phase, error_type=type(error).__name__)
        if result['cases'] and result['cases'][-1]['state'] == 'reviewing':
            result['cases'][-1].update(state='unavailable', error_type=type(error).__name__)
    result['script_expectations_met'] = (result['state'] == 'complete' and all(c['script_expectations_met'] for c in result['cases']))
    save()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--env-file', type=Path, help='Read only this dotenv file; no environment-file discovery.')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--audio-dir', type=Path)
    args = parser.parse_args(argv)
    from services.curriculum_sequence_content import load_asset
    asset = load_asset('location-exchange-v1')
    if not args.execute:
        print(json.dumps({'execute': False, 'asset': asset['id'], 'tts_calls': len(CLIPS),
                          'audio_assessment_calls': len(CASES), 'automatic_retries': 0,
                          'cases': [case[0] for case in CASES], 'learner_asr_supplied': False}))
        return 0
    if args.output is None or args.audio_dir is None or args.env_file is None:
        parser.error('--execute requires --env-file, --output and a fresh --audio-dir outside the repository.')
    try:
        config = load_config(args.env_file)
        from services.speech_provider import SpeechProvider, wav_copy
        from services.speaking_assessment import SpeakingAssessment
        result = run_check(config, asset, args.audio_dir, args.output, SpeechProvider(config), SpeakingAssessment(config), wav_copy)
    except Exception as error:
        print(json.dumps({'state': 'unavailable', 'error_type': type(error).__name__}))
        return 1
    print(json.dumps({'state': result['state'], 'calls': result['calls'], 'script_expectations_met': result['script_expectations_met'],
                      'cases': [{'id': case['id'], 'state': case['state']} for case in result['cases']],
                      **({'error_type': result['error_type']} if 'error_type' in result else {})}))
    return 0 if result['state'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
