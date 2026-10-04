"""Prepare the 66 packaged Russian alphabet clips with ElevenLabs v4.

Default is a provider-free dry run. --execute uses the selected dotenv
file's credentials, chooses one configured voice for the whole set, and
preserves verified recordings on every rerun. --verify checks all shipped bytes
and decodes every clip without credentials or provider calls.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import logging
import math
from pathlib import Path
import random
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'flask_vocab_app'
DATA = APP / 'ui/src/alphabet-data.json'
DIRECTORY = APP / 'static/audio/alphabet-v1'
MODEL = 'eleven_v4'
VERSION = 'alphabet-audio-v1'
MAX_CLIPS, MAX_CHARACTERS, MAX_BYTES = 66, 1500, 1024 * 1024
SETTINGS = {'stability': 0.8, 'similarity_boost': 0.85}
SILENCE_THRESHOLD_DBFS, EDGE_PADDING_MS = -50, 80
SOURCES = [
    'https://orfo.ruslang.ru/alphabet',
    'https://russian.cornell.edu/russian.web/courses/305/letters_sounds_1.htm',
    'https://russian.cornell.edu/grammar/html/paired_cons.htm',
]
# Conventional names are written же and це; their names have э, not the
# unstressed vowel in the particle же. These are pronunciation spellings only.
NAME_SPEECH = {'zhe': 'жэ', 'tse': 'цэ'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.alphabet-', delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(data)
            output.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def save_manifest(directory, manifest):
    atomic_write(directory / 'manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode())


def load_clips(path=DATA):
    data = json.loads(Path(path).read_text())
    alphabet = 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'
    fields = {'id', 'upper', 'lower', 'name', 'nameAudio', 'example', 'exampleMeaning', 'exampleAudio', 'kind', 'note'}
    if (not isinstance(data, list) or len(data) != 33
            or ''.join(item.get('upper', '') for item in data) != alphabet):
        raise ValueError('The catalogue must contain all 33 letters in alphabetical order.')
    clips = {}
    for item in data:
        if (set(item) != fields or not all(isinstance(value, str) and value for value in item.values())
                or not re.fullmatch('[a-z][a-z0-9-]*', item['id']) or item['lower'] != item['upper'].lower()
                or item['kind'] != ('vowel' if item['upper'] in 'АЕЁИОУЫЭЮЯ' else 'sign' if item['upper'] in 'ЪЬ' else 'consonant')):
            raise ValueError('The alphabet catalogue has an invalid letter.')
        for kind, field, url_field in (('name', 'name', 'nameAudio'), ('word', 'example', 'exampleAudio')):
            filename = item['id'] + '-' + kind + '.mp3'
            if item[url_field] != '/static/audio/alphabet-v1/' + filename or filename in clips:
                raise ValueError('Alphabet audio URLs must have unique, fixed filenames.')
            spoken = (NAME_SPEECH.get(item['id'], item[field]) if kind == 'name' else item[field]).replace('\u0301', '')
            if not re.fullmatch('[А-Яа-яЁё ]{1,40}', spoken):
                raise ValueError('Alphabet speech must be a short Russian name or word.')
            text = spoken + '.'
            clips[filename] = {'letter_id': item['id'], 'kind': kind, 'display_text': item[field],
                               'text': text, 'text_sha256': digest(text.encode())}
    if len(clips) != MAX_CLIPS or sum(len(clip['text']) for clip in clips.values()) > MAX_CHARACTERS:
        raise ValueError('The alphabet exceeds its recording bounds.')
    return clips


def audio_metadata(path):
    from pydub import AudioSegment
    from pydub.silence import detect_leading_silence
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError('An alphabet recording is missing or too large.')
    audio = AudioSegment.from_file(path, format='mp3')
    if not 150 <= len(audio) <= 15000 or audio.channels not in (1, 2) or audio.frame_rate < 16000 or not math.isfinite(audio.dBFS):
        raise ValueError('An alphabet recording must contain short, audible speech.')
    data = path.read_bytes()
    return {'audio_sha256': digest(data), 'duration_ms': len(audio), 'size_bytes': len(data),
            'leading_silence_ms': detect_leading_silence(audio, silence_threshold=SILENCE_THRESHOLD_DBFS, chunk_size=5),
            'trailing_silence_ms': detect_leading_silence(audio.reverse(), silence_threshold=SILENCE_THRESHOLD_DBFS, chunk_size=5)}


def trim_padding(path):
    """Remove excessive provider silence, keeping quiet onsets and 80ms edges."""
    from pydub import AudioSegment
    before = audio_metadata(path)
    leading, trailing = before['leading_silence_ms'], before['trailing_silence_ms']
    start = leading - EDGE_PADDING_MS if leading > 150 else 0
    end = trailing - EDGE_PADDING_MS if trailing > 200 else 0
    if start or end:
        audio = AudioSegment.from_file(path, format='mp3')
        with audio[start:len(audio) - end].export(path, format='mp3'):
            pass
    return {**audio_metadata(path), 'source_duration_ms': before['duration_ms'],
            'trimmed_leading_ms': start, 'trimmed_trailing_ms': end}


def plan(directory, clips):
    manifest_path = directory / 'manifest.json'
    saved = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    if saved and (saved.get('version') != VERSION or saved.get('provider') != 'elevenlabs'
                  or saved.get('model') != MODEL or saved.get('voice_settings') != SETTINGS
                  or not isinstance(saved.get('clips'), dict) or set(saved['clips']) - set(clips)):
        raise ValueError('The saved alphabet manifest does not match this recording set.')
    todo = []
    for filename, spec in clips.items():
        record = saved['clips'].get(filename) if saved else None
        path = directory / filename
        if record:
            if (any(record.get(key) != value for key, value in spec.items())
                    or record.get('model') != MODEL or record.get('voice_id') != saved['voice_id']):
                raise ValueError('Published alphabet speech changed; use a new recording version.')
            if record.get('audio_sha256'):
                checked = audio_metadata(path)
                if any(record.get(key) != value for key, value in checked.items()):
                    raise ValueError('A published alphabet recording changed; restore the original file.')
                continue
        if path.exists():
            raise ValueError('An unverified alphabet recording exists; review it before continuing.')
        todo.append(filename)
    return saved, todo


def load_config(path):
    from dotenv import dotenv_values
    if not path.is_file():
        raise ValueError('The selected configuration file is missing.')
    values = dotenv_values(path, interpolate=False)
    key = values.get('ELEVENLABS_API_KEY')
    if not key:
        raise ValueError('The selected configuration needs an ElevenLabs API key.')
    sys.path.insert(0, str(APP))
    from config import ELEVENLABS_VOICE_IDS
    voices = tuple(voice.strip() for voice in (values.get('ELEVENLABS_VOICE_IDS') or '').split(',') if voice.strip()) or ELEVENLABS_VOICE_IDS
    if not voices or any(not re.fullmatch('[A-Za-z0-9]{1,100}', voice) for voice in voices):
        raise ValueError('Configured Russian voices are required.')
    return {'ELEVENLABS_API_KEY': key, 'ELEVENLABS_MODEL': MODEL, 'ELEVENLABS_VOICE_IDS': voices}


def prepare(directory, clips, config, *, max_new=MAX_CLIPS, workers=3, service_factory=None):
    saved, todo = plan(directory, clips)
    if not 0 <= max_new <= MAX_CLIPS or len(todo) > max_new or workers not in (1, 2, 3):
        raise ValueError('The requested batch exceeds the recording limits.')
    if not todo:
        return saved
    if config.get('ELEVENLABS_MODEL') != MODEL or not config.get('ELEVENLABS_API_KEY') or not config.get('ELEVENLABS_VOICE_IDS'):
        raise ValueError('Alphabet speech requires v4 and configured credentials and voices.')
    directory.mkdir(parents=True, exist_ok=True)
    if saved is None:
        saved = {'version': VERSION, 'provider': 'elevenlabs', 'model': MODEL,
                 'voice_id': random.choice(config['ELEVENLABS_VOICE_IDS']), 'voice_settings': SETTINGS,
                 'normalization_dbfs': -20, 'edge_padding_ms': EDGE_PADDING_MS,
                 'silence_threshold_dbfs': SILENCE_THRESHOLD_DBFS, 'sources': SOURCES, 'clips': {}}
    save_manifest(directory, saved)
    if service_factory is None:
        sys.path.insert(0, str(APP))
        from services.elevenlabs_service import ElevenLabsService
        service_factory = ElevenLabsService
        # The command reports fixed failures, never provider exception bodies.
        logging.getLogger('services.elevenlabs_service').disabled = True

    def generate(filename):
        with tempfile.TemporaryDirectory(prefix='.alphabet-', dir=directory) as temporary:
            provider = service_factory(config['ELEVENLABS_API_KEY'], temporary,
                voice_ids=(saved['voice_id'],), model=MODEL, config=config)
            result = provider.generate_audio(clips[filename]['text'], filename)
            candidate = Path(temporary) / filename
            if result != filename:
                raise ValueError('The speech provider did not return a recording.')
            metadata = trim_padding(candidate)
            return candidate.read_bytes(), metadata

    # A failed batch stops after its at-most-three in-flight calls. All
    # successful siblings are saved; a rerun never pays for them again.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for start in range(0, len(todo), workers):
            batch = todo[start:start + workers]
            for filename in batch:
                attempts = saved['clips'].get(filename, {}).get('attempts', 0)
                if attempts >= 3:
                    raise ValueError('This alphabet recording reached its attempt limit.')
                saved['clips'][filename] = {**clips[filename], 'model': MODEL,
                                            'voice_id': saved['voice_id'], 'attempts': attempts + 1}
            save_manifest(directory, saved)
            pending = {executor.submit(generate, filename): filename for filename in batch}
            failed = False
            for future in as_completed(pending):
                filename = pending[future]
                try:
                    data, metadata = future.result()
                except Exception:
                    failed = True
                    continue
                atomic_write(directory / filename, data)
                saved['clips'][filename].update(metadata)
                save_manifest(directory, saved)
                print('Saved ' + filename, flush=True)
            if failed:
                raise ValueError('Recording stopped; completed clips are preserved. Rerun to retry missing clips.')
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--verify', action='store_true')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--max-new', type=int, default=MAX_CLIPS)
    parser.add_argument('--workers', type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args(argv)
    try:
        clips = load_clips()
        saved, todo = plan(DIRECTORY, clips)
        provider_calls = 0
        if args.verify and todo:
            raise ValueError('The alphabet still has missing recordings.')
        if args.execute and todo:
            if args.env_file is None:
                parser.error('--execute requires --env-file when recordings are missing.')
            provider_calls = len(todo)
            saved = prepare(DIRECTORY, clips, load_config(args.env_file), max_new=args.max_new, workers=args.workers)
            _, todo = plan(DIRECTORY, clips)
        print(json.dumps({'model': MODEL, 'clips': len(clips), 'verified': len(clips) - len(todo),
                          'missing': len(todo), 'new_characters': sum(len(clips[name]['text']) for name in todo),
                          'provider_calls': provider_calls, 'complete': not todo}))
        return 0
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
