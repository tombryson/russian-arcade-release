"""Build packaged Russian sound examples from fixed, inspected v4 recordings.

Default is a read-only plan. --execute copies vowel recordings and extracts
consonants using the authored source hashes and boundaries. No credentials or
provider calls are used. --verify checks source provenance and output hashes.
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
RECORDED_PREFIX = 'scripts/audio-sources/alphabet/'
DIRECTORY = audio.DIRECTORY / 'sounds'
RECIPES = ROOT / 'scripts/data/alphabet-sound-crops.json'
MODEL = audio.MODEL
VERSION = 'alphabet-sounds-v2'
RECIPE_VERSION = 'alphabet-sound-crops-v1'
MAX_CLIPS = 31
VOWELS = frozenset(('a', 'ye', 'yo', 'i', 'o', 'u', 'yery', 'e', 'yu', 'ya'))
VOICE_IDS = {'female': 'ymDCYd8puC7gYjxIamPt', 'male': 'sRk0zCqhS2Cmv0bzx5wA'}
PROCESSING = {'normalization_dbfs': -20, 'max_peak_dbfs': -3, 'leading_ms': 60,
              'trailing_ms': 100, 'repeat_gap_ms': 180}


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
        clips[filename] = {'letter_id': item['id'], 'kind': 'sound', 'display_text': item['lower'], 'ipa': ipa}
    if len(clips) != MAX_CLIPS:
        raise ValueError('The alphabet needs exactly 31 sounding letters.')
    return clips


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
            recipe = data['clips'][voice + '-' + item['letter_id']]
            prefix = SOURCE_PREFIX + ('male/' if voice == 'male' else '')
            allowed = {prefix + item['letter_id'] + '-' + kind + '.mp3' for kind in ('name', 'word')}
            allowed.add(RECORDED_PREFIX + voice + '-' + item['letter_id'] + '.mp3')
            if (not isinstance(recipe, dict) or set(recipe) != fields or recipe['source'] not in allowed
                    or not isinstance(recipe['source_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', recipe['source_sha256'])
                    or type(recipe['repetitions']) is not int or recipe['repetitions'] not in (1, 3)
                    or recipe['mode'] not in ('copy', 'crop')):
                raise ValueError('A sound recipe needs its exact same-voice source and processing instructions.')
            if recipe['mode'] == 'copy':
                if (item['letter_id'] not in VOWELS or recipe['source'] != prefix + item['letter_id'] + '-name.mp3'
                        or any(recipe[key] is not None for key in ('start_ms', 'end_ms'))
                        or recipe['repetitions'] != 1 or recipe['fade_in_ms'] != 0 or recipe['fade_out_ms'] != 0):
                    raise ValueError('Copied vowel recordings must stay byte-for-byte unchanged.')
            else:
                if (any(type(recipe[key]) not in (int, float) or not math.isfinite(recipe[key]) for key in ('start_ms', 'end_ms', 'fade_in_ms', 'fade_out_ms'))
                        or not 0 <= recipe['start_ms'] < recipe['end_ms'] <= 15000
                        or not 0 <= recipe['fade_in_ms'] <= 10 or not 0 <= recipe['fade_out_ms'] <= 10
                        or recipe['fade_in_ms'] + recipe['fade_out_ms'] >= recipe['end_ms'] - recipe['start_ms']):
                    raise ValueError('A consonant crop needs bounded, nonempty source intervals and small edge fades.')
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
        recipe = recipes[voice + '-' + item['letter_id']]
        source = source_dir / recipe['source']
        if recipe['source'].startswith(RECORDED_PREFIX):
            generated = json.loads(source.with_suffix('.json').read_text())
            payload = generated.get('payload', {})
            if (payload.get('model_id') != MODEL or payload.get('language_code') != 'ru'
                    or payload.get('voice_settings') != audio.SETTINGS or generated.get('voice_id') != VOICE_IDS[voice]
                    or not isinstance(payload.get('text'), str) or not 1 <= len(payload['text']) <= 500):
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


def render(source, destination, recipe):
    from pydub import AudioSegment
    if recipe['mode'] == 'copy':
        destination.write_bytes(source.read_bytes())
        return {'gain_db': 0, 'processing_applied': 'byte-for-byte copy'}
    original = AudioSegment.from_file(source, format='mp3')
    crop = original[recipe['start_ms']:recipe['end_ms']]
    if not math.isfinite(crop.dBFS):
        raise ValueError('The authored crop contains no audible signal.')
    crop = crop.fade_in(recipe['fade_in_ms']).fade_out(recipe['fade_out_ms'])
    gain = min(PROCESSING['normalization_dbfs'] - crop.dBFS, PROCESSING['max_peak_dbfs'] - crop.max_dBFS)
    crop = crop.apply_gain(gain)
    gap = AudioSegment.silent(duration=PROCESSING['repeat_gap_ms'], frame_rate=crop.frame_rate)
    body = crop
    for _ in range(recipe['repetitions'] - 1):
        body += gap + crop
    result = (AudioSegment.silent(duration=PROCESSING['leading_ms'], frame_rate=crop.frame_rate) + body
              + AudioSegment.silent(duration=PROCESSING['trailing_ms'], frame_rate=crop.frame_rate))
    with result.export(destination, format='mp3', bitrate='128k'):
        pass
    return {'gain_db': gain, 'processing_applied': 'crop, edge fades, bounded gain, repetition and padding'}


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
        saved = {'version': VERSION, 'method': 'extract-existing-v4-alphabet-recordings',
                 'voice': voice, 'voice_id': VOICE_IDS[voice], 'processing': PROCESSING,
                 'review': 'Source boundaries inspected with waveforms and spectrograms; automatic checks are not native-listener certification.',
                 'clips': {}}
    for filename in todo:
        spec = specs[filename]
        with tempfile.TemporaryDirectory(prefix='.alphabet-sound-', dir=directory) as temporary:
            candidate = Path(temporary) / filename
            details = render(source_dir / spec['recipe']['source'], candidate, spec['recipe'])
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
