"""Prepare bounded, reusable speech for the draft location/destination sequence.

Uses the existing SpeechProvider and configured random voices. It never runs in
a learner request, retries paid calls, or regenerates a saved recording. A dry
run checks the complete manifest before reporting any new work. Completed clips
survive a failed batch; rerunning associates them without spending twice.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))
from services.curriculum_requirement_map import content_digest
from services.curriculum_sequence_content import DATA_DIR, SEQUENCE_ID, load_manifest, load_asset
from prepare_curriculum_unit_audio import _atomic_write, _manifest_bytes

MAX_NEW, MAX_CHARACTERS = 20, 3000
AUDIO_DIR = ROOT / 'flask_vocab_app/static/audio/course/curriculum' / SEQUENCE_ID


def audio_nodes(asset):
    content = asset['content']
    nodes = content.get('items', []) + content.get('turns', [])
    nodes += [e for group in content.get('groups', []) for e in group.get('examples', [])]
    if content.get('closing'):
        nodes.append(content['closing'])
    return [n for n in nodes if n.get('audio_key')]


def sequence_assets():
    manifest = load_manifest()
    identities = {s['content_id'] for s in manifest['steps']}
    identities.update(i for f in manifest['transfer_families'] for i in f['task_ids'])
    return {i: load_asset(i) for i in sorted(identities)}


def plan_recordings(assets, directory, probe):
    directory = Path(directory)
    manifest_path = directory / 'manifest.json'
    if directory.is_symlink() or manifest_path.is_symlink():
        raise ValueError('Recording directories cannot be symbolic links.')
    saved = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {
        'version': 'curriculum-sequence-audio-v1', 'sequence_id': SEQUENCE_ID,
        'provider': 'elevenlabs', 'clips': {}, 'keys': {}}
    if (saved.get('version') != 'curriculum-sequence-audio-v1' or saved.get('sequence_id') != SEQUENCE_ID
            or saved.get('provider') != 'elevenlabs' or not isinstance(saved.get('clips'), dict)
            or not isinstance(saved.get('keys'), dict)):
        raise ValueError('Unknown sequence recording manifest.')
    texts, keys = {}, {}
    for asset in assets.values():
        for node in audio_nodes(asset):
            key = node['audio_key']
            text = node.get('transcript', node.get('prompt', node.get('text', node.get('ru', ''))))
            if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,99}', key) or not isinstance(text, str) or not text.strip():
                raise ValueError('Every recording needs a safe identity and authored text.')
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            if key in keys and keys[key] != digest:
                raise ValueError('A recording identity cannot contain two scripts.')
            if key in saved['keys'] and saved['keys'][key] != digest:
                raise ValueError('A saved script changed; publish a new content version.')
            keys[key] = digest
            texts[digest] = text
            if asset['status'] != 'draft' and not node.get('audio'):
                raise ValueError('Do not amend published content during recording preparation.')
    if set(saved['keys']) - set(keys) or set(saved['clips']) - set(texts):
        raise ValueError('A saved recording is no longer represented by authored content.')
    todo = []
    for digest, text in texts.items():
        path = directory / (digest + '.mp3')
        if path.is_symlink():
            raise ValueError('Recording files cannot be symbolic links.')
        clip = saved['clips'].get(digest)
        if clip is None:
            if path.exists():
                raise ValueError('Untracked audio exists; restore its manifest before continuing.')
            todo.append((digest, text))
        else:
            if (not path.is_file() or clip.get('text_sha256') != digest
                    or clip.get('audio_sha256') != hashlib.sha256(path.read_bytes()).hexdigest()
                    or clip.get('size_bytes') != path.stat().st_size):
                raise ValueError('Saved audio is missing or changed; restore the original recording.')
            duration = clip.get('duration')
            if (type(duration) not in (int, float) or not math.isfinite(duration)
                    or not 0.2 <= duration <= 90 or abs(probe(path) - duration) > 0.01
                    or not clip.get('voice_id') or not clip.get('model')):
                raise ValueError('Saved recording metadata is invalid.')
    return saved, keys, todo


def associate_recordings(assets, saved):
    """Update only draft audio pointers, then refresh both authored catalogues."""
    assets = deepcopy(assets)
    for identity, asset in assets.items():
        for node in audio_nodes(asset):
            digest = saved['keys'][node['audio_key']]
            clip = saved['clips'][digest]
            audio = {'url': f'/static/audio/course/curriculum/{SEQUENCE_ID}/{digest}.mp3',
                     'sha256': clip['audio_sha256'], 'duration_ms': round(clip['duration'] * 1000),
                     'text_sha256': digest, 'size_bytes': clip['size_bytes']}
            if asset['kind'] == 'listening':
                audio = {key: audio[key] for key in ('url', 'sha256', 'duration_ms')}
            if asset['status'] != 'draft' and node.get('audio') != audio:
                raise ValueError('Published audio associations cannot be replaced.')
            node['audio'] = audio
        _atomic_write(DATA_DIR / 'curriculum_sequence_assets' / (identity + '.json'), _manifest_bytes(asset))
    manifest_path = DATA_DIR / 'curriculum_sequences' / (SEQUENCE_ID + '.json')
    manifest = json.loads(manifest_path.read_text())
    for step in manifest['steps']:
        step['content_sha256'] = content_digest(assets[step['content_id']])
    for family in manifest['transfer_families']:
        for identity in family['task_ids']:
            family['content_hashes'][identity] = content_digest(assets[identity])
    _atomic_write(manifest_path, _manifest_bytes(manifest))
    coverage_path = DATA_DIR / 'curriculum_coverage/curriculum-delivery-coverage-v1.json'
    coverage = json.loads(coverage_path.read_text())
    for row in coverage['requirements']:
        for stage in ('teaching', 'recognition', 'production', 'assessment'):
            for entry in row[stage]:
                if entry['content_id'] in assets:
                    entry['content_sha256'] = content_digest(assets[entry['content_id']])
    _atomic_write(coverage_path, _manifest_bytes(coverage))


def prepare_recordings(assets, directory, config, provider_factory, probe, *, dry_run=False,
                       max_new=MAX_NEW, max_characters=MAX_CHARACTERS):
    if (type(max_new) is not int or not 0 <= max_new <= MAX_NEW
            or type(max_characters) is not int or not 0 <= max_characters <= MAX_CHARACTERS):
        raise ValueError('Use recording limits within the authored batch bounds.')
    saved, keys, todo = plan_recordings(assets, directory, probe)
    characters = sum(len(text) for _, text in todo)
    print(f'{len(todo)} distinct new recordings; {characters} Russian characters; {len(keys)} recording identities.', flush=True)
    if len(todo) > max_new or characters > max_characters:
        raise ValueError('Batch exceeds the selected limits; no provider calls made.')
    if dry_run:
        return saved
    voices = config.get('ELEVENLABS_VOICE_IDS') or ()
    if todo and (not voices or not config.get('ELEVENLABS_API_KEY') or not config.get('ELEVENLABS_MODEL')):
        raise ValueError('Configured ElevenLabs credentials, model and voices are required.')
    provider = provider_factory(config) if todo else None
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for digest, text in todo:
        voice = random.choice(voices)
        try:
            audio = provider.speak(text, voice)
            import tempfile
            with tempfile.TemporaryDirectory(dir=directory) as temporary:
                path = Path(temporary) / 'clip.mp3'
                path.write_bytes(audio)
                duration = probe(path)
            if not math.isfinite(duration) or not 0.2 <= duration <= 90:
                raise ValueError('Recording duration is invalid.')
        except Exception as error:
            raise ValueError(f'Recording stopped ({type(error).__name__}); completed clips are preserved.') from None
        _atomic_write(directory / (digest + '.mp3'), audio)
        saved['clips'][digest] = {'text_sha256': digest, 'audio_sha256': hashlib.sha256(audio).hexdigest(),
                                  'duration': duration, 'size_bytes': len(audio),
                                  'voice_id': voice, 'model': config['ELEVENLABS_MODEL']}
        saved['keys'].update({k: d for k, d in keys.items() if d in saved['clips']})
        _atomic_write(directory / 'manifest.json', _manifest_bytes(saved))
        print(f'Saved clip {len(saved["clips"])}: {duration:.1f}s', flush=True)
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', action='append', type=Path, default=[])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--max-new', type=int, default=MAX_NEW)
    parser.add_argument('--max-characters', type=int, default=MAX_CHARACTERS)
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    for path in args.env_file:
        if not path.is_file():
            raise SystemExit('The selected environment file is missing.')
        load_dotenv(path, override=False)
    from config import app_config
    from services.speech_provider import SpeechProvider, audio_info
    assets = sequence_assets()
    try:
        saved = prepare_recordings(assets, AUDIO_DIR, app_config(), SpeechProvider, audio_info,
                                   dry_run=args.dry_run, max_new=args.max_new, max_characters=args.max_characters)
        if not args.dry_run:
            associate_recordings(assets, saved)
            load_manifest()
            from services.curriculum_coverage import load_coverage
            load_coverage()
    except ValueError as error:
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
