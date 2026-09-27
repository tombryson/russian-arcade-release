"""Prepare delivery dialogue recordings; never called by a visiting learner.

Uses existing ElevenLabs configuration. Saves speaker assignments before calls
so interrupted runs preserve voices and reuse already prepared recordings.
"""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'flask_vocab_app'))
from config import app_config
from services.route_content import all_audio,SPEAKERS
from services.speech_provider import SpeechProvider


def _write_atomic(path, data):
    """A stopped process must not leave a partial clip that a rerun skips."""
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary=Path(handle.name)
        try:
            handle.write(data)
            handle.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _save_manifest(manifest, saved):
    _write_atomic(manifest,(json.dumps(saved,ensure_ascii=False,indent=2)+'\n').encode())


def _prepare_clips(provider, todo, saved, root, manifest, workers):
    """Only the main thread saves results; at most three calls can be in flight."""
    remaining=iter(todo)
    completed=0
    failures=[]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending={}
        def schedule():
            clip=next(remaining,None)
            if clip is not None:
                future=executor.submit(provider.speak,clip['text'],saved['speakers'][clip['speaker']])
                pending[future]=clip
        for _ in range(workers):
            schedule()
        while pending:
            done,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in done:
                clip=pending.pop(future)
                try:
                    data=future.result()
                except Exception as error:
                    failures.append(type(error).__name__)
                    continue
                _write_atomic(root/(clip['id']+'.mp3'),data)
                saved['clips'][clip['id']]={'text':clip['text'],'speaker':clip['speaker'],'bytes':len(data)}
                _save_manifest(manifest,saved)
                completed+=1
                print(f'Saved {completed}/{len(todo)}',flush=True)
            # On failure, finish and save in-flight calls without starting more.
            if not failures:
                for _ in done:
                    schedule()
    if failures:
        raise SystemExit(f'Recording could not finish ({failures[0]}). Completed clips are saved.') from None


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings',type=Path)
    parser.add_argument('--max-new',type=int,default=40)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--town',action='store_true',help='Include the finite tile-town scenario dialogue.')
    parser.add_argument('--generated',action='store_true',help='Include reusable dialogue for generated deliveries.')
    parser.add_argument('--workers',type=int,choices=range(1,4),default=1,help='Concurrent speech requests (1–3; default: 1).')
    args=parser.parse_args(argv)
    config=app_config()
    if args.settings:
        config.update(json.loads(args.settings.read_text()))
    root=ROOT/'flask_vocab_app/static/audio/deliveries'
    manifest=root/'manifest.json'
    voices=list(config.get('ELEVENLABS_VOICE_IDS') or ())
    if not voices:
        raise SystemExit('No configured Russian voices; configuration was not changed.')
    saved=json.loads(manifest.read_text()) if manifest.exists() else {
        'provider':'elevenlabs','model':config.get('ELEVENLABS_MODEL'),
        'speakers':{name:voices[i%len(voices)] for i,name in enumerate(SPEAKERS)},'clips':{}}
    clips=all_audio()
    if args.town:
        from services.route_town import all_audio as town_audio
        clips += town_audio()
    if args.generated:
        from services.route_dispatch import all_audio as generated_audio
        clips += generated_audio()
    speakers=list(dict.fromkeys([*SPEAKERS,*(clip['speaker'] for clip in clips)]))
    for i,name in enumerate(speakers):
        saved['speakers'].setdefault(name,voices[i%len(voices)])
    clips=list({clip['id']:clip for clip in clips}.values())
    todo=[clip for clip in clips if not (root/(clip['id']+'.mp3')).is_file()]
    print(f'{len(todo)} new recordings; {sum(len(c["text"]) for c in todo)} Russian characters.',flush=True)
    if args.dry_run:
        return
    if len(todo)>args.max_new:
        raise SystemExit('Recording limit exceeded; no provider calls made.')
    if not config.get('ELEVENLABS_API_KEY'):
        raise SystemExit('ELEVENLABS_API_KEY is not configured; no files or settings changed.')
    root.mkdir(parents=True,exist_ok=True)
    _save_manifest(manifest,saved)
    provider=SpeechProvider(config)
    _prepare_clips(provider,todo,saved,root,manifest,args.workers)


if __name__=='__main__':
    main()
