#!/usr/bin/env python3
"""Opt-in language/scenario regression: recorded replies and synthetic live fixtures.

Uses the existing configured dialogue and speech models. No application database
is opened. Inspect replies against each fixture's expectation; the automatic
check verifies output language, not semantic correctness or human ASR accuracy.
Feed generated clips to test_live_conversation.py against an isolated test app.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'flask_vocab_app'))
from config import app_config
from services.conversation_ai import ConversationAI, SCENARIO
from services.conversation_policy import POLICY_VERSION, russian_speech
from services.speech_provider import SpeechProvider


def run(args):
    config=app_config()
    if args.config:
        config.update(json.loads(args.config.read_text()))
    cases=json.loads((ROOT/'flask_vocab_app/data/conversation_language_cases.json').read_text())
    args.output.mkdir(parents=True,exist_ok=True)
    history=[{'role':'assistant','text':SCENARIO['opening']}]
    ai=ConversationAI(config)
    speech=SpeechProvider(config)
    voice=random.choice(config['ELEVENLABS_VOICE_IDS'])

    def synthesise(case):
        path=args.output/(case['id']+'.mp3')
        path.write_bytes(speech.speak(case['text'],voice))
        return {**case,'audio':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'source':'synthetic','reference_verified':False,'voice_id':voice,'synthesis_model':config['ELEVENLABS_MODEL']}

    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        clips=[pool.submit(synthesise,case) for case in cases] if args.synthesise else []
        for case in cases:
            history.append({'role':'user','text':case['text']})
            reply=ai.reply(SCENARIO,history)
            history.append({'role':'assistant','text':reply['russian']})
            results.append({'case':case,'reply':reply})
            (args.output/'replies.json').write_text(json.dumps({'policy':POLICY_VERSION,'results':results},ensure_ascii=False,indent=2))
            print(case['id']+': '+reply['russian'],flush=True)
        if clips:
            (args.output/'fixtures.json').write_text(json.dumps([job.result() for job in clips],ensure_ascii=False,indent=2))
    if any(r['reply']['language_recovered'] or not russian_speech(r['reply']['russian']) for r in results):
        raise RuntimeError('A model reply needed language recovery. Inspect replies.json.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Make paid provider calls')
    parser.add_argument('--synthesise',action='store_true',help='Also generate audio fixtures for the live test')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,help='Optional existing application configuration JSON; read only')
    args=parser.parse_args()
    if not args.run:parser.error('Use --run to make paid provider calls.')
    if (args.output/'replies.json').exists():parser.error('Use a new output directory to preserve earlier results.')
    run(args)
