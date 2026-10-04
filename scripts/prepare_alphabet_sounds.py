"""Build packaged Russian pronunciation examples from fixed v4 recordings.

Default is a read-only plan. --execute copies vowel recordings and complete
consonant-vowel practice syllables, with authored durations for sound excerpts.
Authored source hashes are checked. No credentials or provider calls are used.
--verify checks source provenance and output hashes.
Waveform inspection and automatic checks are not native-listener certification.
"""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('_alphabet_audio_preparation', ROOT / 'scripts/prepare_alphabet_audio.py')
audio = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audio)
DATA = audio.DATA
SOURCES = ROOT
SOURCE_PREFIX = 'flask_vocab_app/static/audio/alphabet-v1/'
RECORDED_PREFIX = 'scripts/audio-sources/alphabet/syllables-v1/'
DIRECTORY = audio.DIRECTORY / 'sounds'
RECIPES = ROOT / 'scripts/data/alphabet-sound-crops.json'
MODEL = audio.MODEL
VERSION = 'alphabet-sounds-v9'
RECIPE_VERSION = 'alphabet-sound-crops-v8'
MAX_CLIPS = 31
MIN_SPEECH_MS = 160
# Explicit listening adjustments; all other isolated sounds keep the default.
MIN_SPEECH_MS_BY_LETTER = {
    've': 150, 'en': 150, 'o': 130, 'shcha': 130, 'ef': 130, 'che': 130, 'tse': 150, 'pe': 130,
    'sha': 110, 'short-i': 150, 'zhe': 150,
}
# Preserve natural low-energy portions inside the measured speech span.
# Moving past them would remove releases or extend cuts into adjacent vowels.
MAX_INTERNAL_QUIET_MS = {'che': 5, 'en': 3, 'tse': 12}
RECORDED_CROP_TEXT = {'short-i': 'йо.'}
CROPPED_SYLLABLE_IDS = frozenset(('pe',))
SPEECH_THRESHOLD_DBFS = -45
SPEECH_FRAME_MS = 1
VOWELS = frozenset(('a', 'ye', 'yo', 'i', 'o', 'u', 'yery', 'e', 'yu', 'ya'))
VOICE_IDS = {'female': 'ymDCYd8puC7gYjxIamPt', 'male': 'sRk0zCqhS2Cmv0bzx5wA'}
PROCESSING = {'normalization_dbfs': -20, 'max_peak_dbfs': -3, 'leading_ms': 60,
              'trailing_ms': 100, 'max_gain_db': 3, 'minimum_speech_ms': MIN_SPEECH_MS,
              'minimum_speech_ms_by_letter': MIN_SPEECH_MS_BY_LETTER,
              'max_internal_quiet_ms_by_letter': MAX_INTERNAL_QUIET_MS,
              'cropped_syllable_ids': sorted(CROPPED_SYLLABLE_IDS),
              'speech_frame_ms': SPEECH_FRAME_MS, 'speech_threshold_dbfs': SPEECH_THRESHOLD_DBFS}


def load_clips(path=DATA):
    audio.load_clips(path)
    clips = {}
    for item in json.loads(Path(path).read_text()):
        ipa, urls = item['soundIpa'], item['soundAudio']
        if item['kind'] == 'sign':
            if ipa is not None or urls is not None:
                raise ValueError('Hard and soft signs have no independent sound recording.')
            continue
        filename = item['id'] + '-sound.mp3'
        expected = {voice: '/static/audio/alphabet-v1/sounds/' + voice + '/' + filename for voice in VOICE_IDS}
        if not isinstance(ipa, str) or not re.fullmatch(r'[a-zɡɨɫʂʐɕɛʲː͡]{1,12}', ipa) or urls != expected:
            raise ValueError('Every sounding letter needs IPA and both exact sound recording URLs.')
        clips[filename] = {'letter_id': item['id'], 'kind': 'syllable' if item['practiceSyllable'] else 'sound',
                           'display_text': item['practiceSyllable'] or item['lower'], 'ipa': ipa}
        if item.get('soundByVoice'):
            clips[filename]['voice_overrides'] = {
                voice: {'kind': 'syllable' if value['practiceSyllable'] else 'sound',
                        'display_text': value['practiceSyllable'] or item['lower'], 'ipa': value['soundIpa']}
                for voice, value in item['soundByVoice'].items()
            }
    if len(clips) != MAX_CLIPS:
        raise ValueError('The alphabet needs exactly 31 sounding letters.')
    return clips


def for_voice(item, voice):
    """Resolve the label used to validate and package this voice's recording."""
    return {**{key: value for key, value in item.items() if key != 'voice_overrides'},
            **item.get('voice_overrides', {}).get(voice, {})}


def selection(clips, letters=None):
    if letters is None:
        return set(clips)
    ids = letters.split(',')
    selected = {letter.strip() + '-sound.mp3' for letter in ids}
    if not ids or len(selected) != len(ids) or not selected <= set(clips):
        raise ValueError('Choose distinct sounding letter IDs, separated by commas.')
    return selected


def load_recipes(path=RECIPES, clips=None):
    clips = load_clips() if clips is None else clips
    data = json.loads(Path(path).read_text())
    expected = {voice + '-' + item['letter_id'] for voice in VOICE_IDS for item in clips.values()}
    if (not isinstance(data, dict) or data.get('version') != RECIPE_VERSION
            or data.get('processing') != PROCESSING or not isinstance(data.get('clips'), dict)
            or set(data['clips']) != expected):
        raise ValueError('The authored sound recipe must cover both complete recording sets.')
    fields = {'source', 'source_sha256', 'mode', 'start_ms', 'end_ms', 'repetitions', 'fade_in_ms', 'fade_out_ms'}
    for voice in VOICE_IDS:
        for item in clips.values():
            item = for_voice(item, voice)
            recipe = data['clips'][voice + '-' + item['letter_id']]
            prefix = SOURCE_PREFIX + ('male/' if voice == 'male' else '')
            allowed = {prefix + item['letter_id'] + '-' + kind + '.mp3' for kind in ('name', 'word')}
            allowed.add(RECORDED_PREFIX + voice + '-' + item['letter_id'] + '.mp3')
            if (not isinstance(recipe, dict) or set(recipe) != fields or recipe['source'] not in allowed
                    or not isinstance(recipe['source_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', recipe['source_sha256'])
                    or type(recipe['repetitions']) is not int or recipe['repetitions'] != 1
                    or recipe['mode'] not in ('copy', 'crop')):
                raise ValueError('A sound recipe needs its exact same-voice source and processing instructions.')
            if recipe['mode'] == 'copy':
                expected_source = (prefix + item['letter_id'] + '-name.mp3' if item['letter_id'] in VOWELS
                                   else RECORDED_PREFIX + voice + '-' + item['letter_id'] + '.mp3')
                if (recipe['source'] != expected_source or (item['letter_id'] not in VOWELS and item['kind'] != 'syllable')
                        or any(recipe[key] is not None for key in ('start_ms', 'end_ms'))
                        or recipe['fade_in_ms'] != 0 or recipe['fade_out_ms'] != 0):
                    raise ValueError('Copy only an unchanged vowel recording or an explicitly labelled practice syllable.')
            else:
                minimum = MIN_SPEECH_MS_BY_LETTER.get(item['letter_id'], MIN_SPEECH_MS)
                if (any(type(recipe[key]) not in (int, float) or not math.isfinite(recipe[key]) for key in ('start_ms', 'end_ms', 'fade_in_ms', 'fade_out_ms'))
                        or not 0 <= recipe['start_ms'] < recipe['end_ms'] <= 15000
                        or recipe['end_ms'] - recipe['start_ms'] < minimum
                        or (item['kind'] == 'syllable' and
                            (item['letter_id'] not in CROPPED_SYLLABLE_IDS or
                             recipe['source'] != RECORDED_PREFIX + voice + '-' + item['letter_id'] + '.mp3'))
                        or not 0 <= recipe['fade_in_ms'] <= 10 or not 0 <= recipe['fade_out_ms'] <= 10
                        or recipe['fade_in_ms'] + recipe['fade_out_ms'] >= recipe['end_ms'] - recipe['start_ms']):
                    raise ValueError(f'An excerpt needs at least {minimum} ms of source audio; unlisted practice syllables must remain whole.')
    return data['clips']


def source_specs(clips, recipes, voice, source_dir=SOURCES):
    if voice not in VOICE_IDS:
        raise ValueError('Choose the female or male recording set.')
    manifest_dir = source_dir / SOURCE_PREFIX / ('male' if voice == 'male' else '')
    source_manifest = json.loads((manifest_dir / 'manifest.json').read_text())
    if (source_manifest.get('provider') != 'elevenlabs' or source_manifest.get('model') != MODEL
            or source_manifest.get('version') != audio.VERSION or source_manifest.get('voice', 'female') != voice
            or source_manifest.get('voice_id') != VOICE_IDS[voice]):
        raise ValueError('The source recording manifest must match the pinned v4 voice.')
    specs = {}
    for filename, item in clips.items():
        item = for_voice(item, voice)
        recipe = recipes[voice + '-' + item['letter_id']]
        source = source_dir / recipe['source']
        if recipe['source'].startswith(RECORDED_PREFIX):
            generated = json.loads(source.with_suffix('.json').read_text())
            payload = generated.get('payload', {})
            expected_text = (item['display_text'] + '.' if item['kind'] == 'syllable'
                             else RECORDED_CROP_TEXT.get(item['letter_id']) if recipe['mode'] == 'crop' else None)
            if (payload.get('model_id') != MODEL or payload.get('language_code') != 'ru'
                    or payload.get('voice_settings') != audio.SETTINGS or generated.get('voice_id') != VOICE_IDS[voice]
                    or expected_text is None or payload.get('text') != expected_text):
                raise ValueError('An authored source needs its exact Russian v4 request provenance.')
            record = {'model': MODEL, 'voice_id': generated['voice_id'], 'text': payload['text'],
                      'text_sha256': audio.digest(payload['text'].encode()), 'audio_sha256': generated.get('sha256'),
                      'duration_ms': generated.get('duration_ms'), 'request': payload}
        else:
            record = source_manifest.get('clips', {}).get(source.name, {})
        if (record.get('audio_sha256') != recipe['source_sha256'] or record.get('model') != MODEL
                or record.get('voice_id') != VOICE_IDS[voice]
                or not source.is_file() or audio.digest(source.read_bytes()) != recipe['source_sha256']):
            raise ValueError('A sound source changed or does not have verified v4 provenance.')
        if recipe['mode'] == 'crop' and recipe['end_ms'] > record.get('duration_ms', 0):
            raise ValueError('A sound crop exceeds its source recording.')
        if item['kind'] == 'syllable':
            from pydub import AudioSegment
            require_speech(AudioSegment.from_file(source, format='mp3'))
        provenance = {key: record[key] for key in ('model', 'voice_id', 'text', 'text_sha256', 'audio_sha256')}
        if 'request' in record:
            provenance['request'] = record['request']
        specs[filename] = {**item, 'recipe': recipe, 'source_generation': provenance,
                           'model': MODEL, 'voice_id': VOICE_IDS[voice]}
    return specs


def plan(directory, specs, voice):
    manifest_path = directory / 'manifest.json'
    saved = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    if saved and (saved.get('version') != VERSION or saved.get('voice') != voice
                  or saved.get('voice_id') != VOICE_IDS[voice] or saved.get('processing') != PROCESSING
                  or not isinstance(saved.get('clips'), dict) or set(saved['clips']) - set(specs)):
        raise ValueError('The saved sounds do not match this extraction version; preserve earlier candidates separately.')
    todo = []
    for filename, spec in specs.items():
        record = saved['clips'].get(filename) if saved else None
        path = directory / filename
        if record:
            if any(record.get(key) != value for key, value in spec.items()):
                raise ValueError('An authored sound recipe changed; preserve the earlier version before rebuilding.')
            checked = audio.audio_metadata(path)
            if any(record.get(key) != value for key, value in checked.items()):
                raise ValueError('A packaged sound recording changed; restore its verified bytes.')
        elif path.exists():
            raise ValueError('An unverified sound recording exists; preserve it before rebuilding.')
        else:
            todo.append(filename)
    return saved, todo


def require_speech(recording, *, letter_id=None):
    # Measure the source signal, not MP3/container duration or added padding.
    # This detects undersized/quiet clips; it cannot certify pronunciation.
    active_frames = [(start, len(recording[start:start + SPEECH_FRAME_MS]))
                     for start in range(0, len(recording), SPEECH_FRAME_MS)
                     if recording[start:start + SPEECH_FRAME_MS].dBFS > SPEECH_THRESHOLD_DBFS]
    active_ms = sum(length for _, length in active_frames)
    span_ms = active_frames[-1][0] + active_frames[-1][1] - active_frames[0][0] if active_frames else 0
    minimum = MIN_SPEECH_MS_BY_LETTER.get(letter_id, MIN_SPEECH_MS)
    if span_ms < minimum or active_ms < minimum - MAX_INTERNAL_QUIET_MS.get(letter_id, 0):
        raise ValueError(f'A pronunciation example needs at least {minimum} ms of audible source speech; silence does not count.')
    return active_ms


def render(source, destination, recipe, *, letter_id=None):
    if recipe['repetitions'] != 1:
        raise ValueError('Each recording must contain one pronunciation, without repeats.')
    from pydub import AudioSegment
    original = AudioSegment.from_file(source, format='mp3')
    if recipe['mode'] == 'copy':
        active_ms = require_speech(original)
        destination.write_bytes(source.read_bytes())
        return {'gain_db': 0, 'source_active_ms': active_ms, 'processing_applied': 'byte-for-byte copy'}
    minimum = MIN_SPEECH_MS_BY_LETTER.get(letter_id, MIN_SPEECH_MS)
    if recipe['end_ms'] - recipe['start_ms'] < minimum:
        raise ValueError(f'A pronunciation crop needs at least {minimum} ms of source audio.')
    crop = original[recipe['start_ms']:recipe['end_ms']]
    active_ms = require_speech(crop, letter_id=letter_id)
    crop = crop.fade_in(recipe['fade_in_ms']).fade_out(recipe['fade_out_ms'])
    gain = min(PROCESSING['max_gain_db'], PROCESSING['normalization_dbfs'] - crop.dBFS,
               PROCESSING['max_peak_dbfs'] - crop.max_dBFS)
    crop = crop.apply_gain(gain)
    result = (AudioSegment.silent(duration=PROCESSING['leading_ms'], frame_rate=crop.frame_rate) + crop
              + AudioSegment.silent(duration=PROCESSING['trailing_ms'], frame_rate=crop.frame_rate))
    with result.export(destination, format='mp3', bitrate='128k'):
        pass
    return {'gain_db': gain, 'source_active_ms': active_ms, 'processing_applied': 'single crop, edge fades, bounded gain and padding'}


def prepare(directory, specs, *, voice, selected=None, max_new=MAX_CLIPS, source_dir=SOURCES):
    if voice not in VOICE_IDS or type(max_new) is not int or not 0 <= max_new <= MAX_CLIPS or len(specs) > MAX_CLIPS:
        raise ValueError('Choose one voice and at most 31 sound recordings.')
    selected = set(specs) if selected is None else selected
    if not isinstance(selected, (set, frozenset)) or not selected <= set(specs):
        raise ValueError('Choose only known sound recordings.')
    saved, todo = plan(directory, specs, voice)
    todo = [filename for filename in todo if filename in selected]
    if len(todo) > max_new:
        raise ValueError('The requested batch exceeds the recording limit.')
    # Check every selected source before making any output writes.
    for filename in selected:
        recipe = specs[filename]['recipe']
        if audio.digest((source_dir / recipe['source']).read_bytes()) != recipe['source_sha256']:
            raise ValueError('A sound source changed before extraction.')
    if not todo:
        return saved
    directory.mkdir(parents=True, exist_ok=True)
    if saved is None:
        saved = {'version': VERSION, 'method': 'v4-pronunciation-examples-with-explicit-sound-crops',
                 'voice': voice, 'voice_id': VOICE_IDS[voice], 'processing': PROCESSING,
                 'review': 'Excerpts use authored per-letter durations. Uncropped examples preserve whole source recordings. Signal-duration checks are not a pronunciation review.',
                 'clips': {}}
    for filename in todo:
        spec = specs[filename]
        with tempfile.TemporaryDirectory(prefix='.alphabet-sound-', dir=directory) as temporary:
            candidate = Path(temporary) / filename
            details = render(source_dir / spec['recipe']['source'], candidate, spec['recipe'], letter_id=spec['letter_id'])
            metadata = audio.audio_metadata(candidate)
            audio.atomic_write(directory / filename, candidate.read_bytes())
        saved['clips'][filename] = {**spec, **details, **metadata}
        audio.save_manifest(directory, saved)
        print('Saved ' + filename, flush=True)
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--verify', action='store_true')
    parser.add_argument('--voice', choices=tuple(VOICE_IDS), default='female')
    parser.add_argument('--letters', help='Optional comma-separated letter IDs for a limited extraction batch.')
    parser.add_argument('--max-new', type=int, default=MAX_CLIPS)
    args = parser.parse_args(argv)
    try:
        clips = load_clips()
        selected = selection(clips, args.letters)
        specs = source_specs(clips, load_recipes(clips=clips), args.voice)
        directory = DIRECTORY / args.voice
        _, todo = plan(directory, specs, args.voice)
        missing = [filename for filename in todo if filename in selected]
        if args.verify and missing:
            raise ValueError('The selected sounds still have missing recordings.')
        if args.execute and missing:
            prepare(directory, specs, voice=args.voice, selected=selected, max_new=args.max_new)
            _, todo = plan(directory, specs, args.voice)
            missing = [filename for filename in todo if filename in selected]
        print(json.dumps({'model': MODEL, 'voice': args.voice, 'selected': len(selected),
                          'verified': len(selected) - len(missing), 'missing': len(missing),
                          'provider_calls': 0, 'complete': not missing,
                          'total_clips': len(clips), 'total_missing': len(todo)}))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
