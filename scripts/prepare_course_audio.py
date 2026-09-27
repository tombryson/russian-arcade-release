"""Prepare reusable chapter listening recordings through the existing TTS provider.

Only an explicit maintenance run calls the provider. Learner requests play the
bundled clips without spending tokens. Existing matching clips are reused.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', action='append', type=Path, default=[])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--max-new', type=int, default=12)
    args = parser.parse_args()
    from dotenv import load_dotenv
    for path in args.env_file:
        if not path.is_file():
            raise SystemExit('The supplied configuration file does not exist.')
        load_dotenv(path, override=False)
    from config import app_config
    from services.speech_provider import SpeechProvider, audio_info
    from prepare_delivery_audio import _write_atomic, _save_manifest
    config = app_config()
    source = json.loads((ROOT / 'flask_vocab_app/data/course_chapters.json').read_text())
    clips = [variant for chapter in source['chapters'] for variant in chapter['variants']]
    directory = ROOT / 'flask_vocab_app/static/audio/course'
    manifest = directory / 'manifest.json'
    saved = json.loads(manifest.read_text()) if manifest.exists() else {'provider': 'elevenlabs', 'clips': {}}
    todo = []
    for clip in clips:
        digest = hashlib.sha256(clip['listening']['transcript'].encode()).hexdigest()
        previous = saved['clips'].get(clip['id'], {})
        # Saved attempts reference these URLs. A revised script needs a new
        # variant ID so it cannot change the audio of an existing assessment.
        if previous and previous.get('text_sha256') != digest:
            raise SystemExit(f'{clip["id"]} has a published recording. Use a new variant ID for revised speech.')
        path = directory / (clip['id'] + '.mp3')
        if path.is_file() and previous.get('audio_sha256') and hashlib.sha256(path.read_bytes()).hexdigest() != previous['audio_sha256']:
            raise SystemExit(f'{clip["id"]} does not match its recording manifest. Restore the published recording.')
        if previous and not path.is_file():
            raise SystemExit(f'{clip["id"]} is missing its published recording. Restore it from source control.')
        if not previous:
            todo.append((clip, digest))
    print(f'{len(todo)} new recordings; {sum(len(c["listening"]["transcript"]) for c, _ in todo)} Russian characters.', flush=True)
    if args.dry_run or not todo:
        return
    if len(todo) > args.max_new:
        raise SystemExit('Recording limit exceeded; no provider calls made.')
    voices = config.get('ELEVENLABS_VOICE_IDS') or ()
    if not voices or not config.get('ELEVENLABS_API_KEY'):
        raise SystemExit('Configured ElevenLabs credentials and voices are required.')
    directory.mkdir(parents=True, exist_ok=True)
    provider = SpeechProvider(config)
    for clip, digest in todo:
        old = saved['clips'].get(clip['id'], {})
        voice = old.get('voice_id') or random.choice(voices)
        try:
            data = provider.speak(clip['listening']['transcript'], voice)
            path = directory / (clip['id'] + '.mp3')
            _write_atomic(path, data)
            duration = audio_info(path)
        except Exception as error:
            raise SystemExit(f'Recording stopped ({type(error).__name__}); completed clips are preserved.') from None
        saved['clips'][clip['id']] = {'text_sha256': digest, 'audio_sha256': hashlib.sha256(data).hexdigest(), 'voice_id': voice,
                                     'model': config.get('ELEVENLABS_MODEL'), 'duration': duration}
        _save_manifest(manifest, saved)
        print(f'Saved {clip["id"]}: {duration:.1f}s', flush=True)


if __name__ == '__main__':
    main()
