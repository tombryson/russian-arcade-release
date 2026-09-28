"""Prepare introductory recordings once through the existing speech provider.

The finite authored catalogue, recording limit and character limit bound the
run. Published audio is immutable; a rerun verifies and reuses completed files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'flask_vocab_app'
sys.path.insert(0, str(APP))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--max-new', type=int, default=40)
    parser.add_argument('--max-characters', type=int, default=2000)
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    for path in args.env_file:
        if not path.is_file():
            raise SystemExit('Configuration file not found.')
        load_dotenv(path, override=False)
    from config import app_config
    from services.first_steps_audio import authored_clips
    from services.speech_provider import SpeechProvider, audio_info
    from prepare_delivery_audio import _write_atomic, _save_manifest
    directory = APP / 'static/audio/first-steps-v2'
    manifest = directory / 'manifest.json'
    saved = json.loads(manifest.read_text()) if manifest.exists() else {'provider': 'elevenlabs', 'clips': {}}
    pending = []
    for url, text in authored_clips().items():
        path = APP / 'static' / url.removeprefix('/static/')
        digest = hashlib.sha256(text.encode()).hexdigest()
        previous = saved['clips'].get(url, {})
        if previous and previous['text_sha256'] != digest:
            raise SystemExit(f'Text changed for {path.name}; use a new recording URL.')
        if previous.get('audio_sha256'):
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != previous['audio_sha256']:
                raise SystemExit(f'Restore the published recording for {path.name}.')
        else:
            if path.exists():
                raise SystemExit(f'Unverified recording exists for {path.name}; check it before continuing.')
            pending.append((url, text, digest, path))
    characters = sum(len(text) for _, text, _, _ in pending)
    print(f'{len(pending)} new recordings; {characters} Russian characters.', flush=True)
    if args.dry_run or not pending:
        return
    if len(pending) > args.max_new or characters > args.max_characters:
        raise SystemExit('Preparation limit exceeded; no speech calls made.')
    config = app_config()
    voices = config.get('ELEVENLABS_VOICE_IDS') or ()
    if not voices or not config.get('ELEVENLABS_API_KEY'):
        raise SystemExit('Configured ElevenLabs credentials and voices are required.')
    import requests
    response = requests.get('https://api.elevenlabs.io/v1/user/subscription',
                            headers={'xi-api-key': config['ELEVENLABS_API_KEY']}, timeout=(10, 20))
    if not response.ok:
        raise SystemExit('Could not verify the speech allowance; no speech calls made.')
    account = response.json()
    remaining = account.get('character_limit', 0) - account.get('character_count', 0)
    if characters > remaining:
        raise SystemExit(f'Recordings need {characters} characters; {remaining} remain. No speech calls made.')
    directory.mkdir(parents=True, exist_ok=True)
    provider = SpeechProvider(config)
    for url, text, digest, path in pending:
        clip = saved['clips'].setdefault(url, {'text_sha256': digest, 'voice_id': random.choice(voices),
                                              'model': config.get('ELEVENLABS_MODEL')})
        _save_manifest(manifest, saved)
        try:
            data = provider.speak(text, clip['voice_id'])
            _write_atomic(path, data)
            duration = audio_info(path)
        except Exception as error:
            raise SystemExit(f'Recording stopped ({type(error).__name__}); completed clips are preserved.') from None
        clip.update(audio_sha256=hashlib.sha256(data).hexdigest(), duration=duration, bytes=len(data))
        _save_manifest(manifest, saved)
        print(f'Saved {path.name}: {duration:.1f}s', flush=True)


if __name__ == '__main__':
    main()
