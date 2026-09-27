"""Record authored milestone audio once; never regenerate published clips.

Use --env-file to select existing operator configuration. Random voice choice
is persisted before requesting speech, so an interrupted run keeps its cast.
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', action='append', type=Path, default=[])
    parser.add_argument('--practice-only', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--max-new', type=int, default=17)
    args = parser.parse_args()
    from dotenv import load_dotenv
    for path in args.env_file:
        if not path.is_file():
            raise SystemExit('Configuration file not found.')
        load_dotenv(path, override=False)
    from config import app_config
    from services.speech_provider import SpeechProvider, audio_info
    from prepare_delivery_audio import _write_atomic, _save_manifest
    clips = []
    for item in json.loads((APP / 'data/course_target_practice.json').read_text())['items']:
        question = item['question']
        if question.get('audio_url'):
            clips.append((question['audio_url'], question['transcript']))
    if not args.practice_only:
        course = json.loads((APP / 'data/course_drafts/a1-journey-v2.json').read_text())
        for chapter in course['chapters']:
            for variant in chapter['variants']:
                clip = variant['listening']
                clips.append((f"/static/audio/course/{course['release_id']}/{clip['id']}.mp3", clip['transcript']))
    manifest = APP / 'static/audio/course/milestones-manifest.json'
    saved = json.loads(manifest.read_text()) if manifest.exists() else {'provider': 'elevenlabs', 'clips': {}}
    pending = []
    for url, transcript in clips:
        path = APP / 'static' / url.removeprefix('/static/')
        digest = hashlib.sha256(transcript.encode()).hexdigest()
        previous = saved['clips'].get(url, {})
        if previous and previous['text_sha256'] != digest:
            raise SystemExit(f'Transcript changed for {path.name}. Publish a new clip identity.')
        if previous.get('audio_sha256'):
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != previous['audio_sha256']:
                raise SystemExit(f'Restore the published recording for {path.name}.')
            continue
        pending.append((url, path, transcript, digest))
    print(f'{len(pending)} new clips; {sum(len(item[2]) for item in pending)} Russian characters.', flush=True)
    if args.dry_run or not pending:
        return
    if len(pending) > args.max_new:
        raise SystemExit('Recording limit exceeded; no provider calls made.')
    config = app_config()
    voices = config.get('ELEVENLABS_VOICE_IDS') or ()
    if not voices or not config.get('ELEVENLABS_API_KEY'):
        raise SystemExit('Configured ElevenLabs credentials and voices are required.')
    provider = SpeechProvider(config)
    for url, path, transcript, digest in pending:
        previous = saved['clips'].get(url, {})
        voice = previous.get('voice_id') or random.choice(voices)
        record = {'text_sha256': digest, 'voice_id': voice, 'model': config.get('ELEVENLABS_MODEL')}
        saved['clips'][url] = record
        manifest.parent.mkdir(parents=True, exist_ok=True)
        _save_manifest(manifest, saved)
        try:
            data = provider.speak(transcript, voice)
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_atomic(path, data)
            duration = audio_info(path)
            minimum = 0.2 if '/a1-targets-v1/' in url else 3
            if not minimum < duration < 30:
                raise ValueError('Course clip outside authored duration limit')
        except Exception as error:
            raise SystemExit(f'Recording stopped ({type(error).__name__}); completed clips are preserved.') from None
        record.update(audio_sha256=hashlib.sha256(data).hexdigest(), duration=duration)
        _save_manifest(manifest, saved)
        print(f'Saved {path.name}: {duration:.1f}s', flush=True)


if __name__ == '__main__':
    main()
