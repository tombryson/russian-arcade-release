"""Prepare introductory recordings once through the existing speech provider.

The finite authored catalogue, recording limit and character limit bound the
run. Published audio is immutable; a rerun verifies and reuses completed files.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'flask_vocab_app'
sys.path.insert(0, str(APP))


def validate_authored_speech(path):
    """Require audible signal in packaged speech, beyond a valid audio container."""
    from services.speech_provider import audio_info
    duration = audio_info(path)
    try:
        result = subprocess.run(
            ['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-t', '91',
             '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', 'pipe:1'],
            capture_output=True, timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError('The authored recording could not be decoded.') from None
    samples = array('h')
    samples.frombytes(result.stdout)
    if sys.byteorder != 'little':
        samples.byteswap()
    # At least 0.10 seconds of samples above -45 dBFS. This deliberately low
    # threshold rejects empty/near-silent responses without normalizing voices.
    if sum(abs(sample) >= 185 for sample in samples) < 1600:
        raise ValueError('The authored recording is silent or too quiet.')
    return duration


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--provider', choices=('elevenlabs', 'openai'), default='elevenlabs',
                        help='Explicit provider for these packaged recordings only.')
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
    from services.speech_provider import SpeechProvider
    from prepare_delivery_audio import _write_atomic, _save_manifest
    directory = APP / 'static/audio/first-steps-v2'
    manifest = directory / 'manifest.json'
    saved = json.loads(manifest.read_text()) if manifest.exists() else {'provider': args.provider, 'clips': {}}
    if saved['provider'] != args.provider:
        raise SystemExit('Use the provider recorded in the existing manifest; published clips are immutable.')
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
            try:
                validate_authored_speech(path)
            except ValueError as error:
                raise SystemExit(f'{path.name}: {error} Use a new recording URL to replace it.') from None
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
    if args.provider == 'elevenlabs':
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
        model = config.get('ELEVENLABS_MODEL')
        provider = SpeechProvider(config)
        speak = provider.speak
    else:
        if not config.get('OPENAI_API_KEY'):
            raise SystemExit('Configured OpenAI credentials are required.')
        from openai import OpenAI
        client = OpenAI(api_key=config['OPENAI_API_KEY'], timeout=60, max_retries=0)
        voices, model = ('marin', 'cedar'), 'gpt-4o-mini-tts'
        def speak(text, voice):
            return client.audio.speech.create(model=model, voice=voice, input=text,
                response_format='mp3', instructions='Read only the supplied Russian text. Use natural standard Russian pronunciation, clear word stress and a calm, friendly pace for a beginner. Do not translate, explain or add words.').content
    directory.mkdir(parents=True, exist_ok=True)
    for url, text, digest, path in pending:
        clip = saved['clips'].setdefault(url, {'text_sha256': digest, 'voice_id': random.choice(voices),
                                              'model': model})
        _save_manifest(manifest, saved)
        try:
            data = speak(text, clip['voice_id'])
            with tempfile.TemporaryDirectory() as tmp:
                candidate = Path(tmp) / path.name
                candidate.write_bytes(data)
                duration = validate_authored_speech(candidate)
            _write_atomic(path, data)
        except Exception as error:
            raise SystemExit(f'Recording stopped ({type(error).__name__}); completed clips are preserved.') from None
        clip.update(audio_sha256=hashlib.sha256(data).hexdigest(), duration=duration, bytes=len(data))
        _save_manifest(manifest, saved)
        print(f'Saved {path.name}: {duration:.1f}s', flush=True)


if __name__ == '__main__':
    main()
