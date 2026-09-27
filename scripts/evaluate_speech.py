#!/usr/bin/env python3
"""Paid, opt-in speech preservation experiment; synthetic input is NOT ground truth.

python scripts/evaluate_speech.py --output instance/speech-eval --synthesise --run
To use listened-to human recordings instead, supply --manifest with rows containing
id, text, audio (absolute path), reference_verified=true, target, correction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))
from config import app_config
from services.speech_provider import SpeechProvider, SpeechError


def tokens(text):
    return re.findall(r'[а-яё]+', text.lower().replace('ё', 'е'))


def compare(case, transcript):
    words = tokens(transcript)
    if not case.get('target'):
        return 'unchanged' if tokens(case['text']) == words else 'changed_control'
    target, correction = tokens(case['target']), tokens(case.get('correction', ''))
    def contains(needle):
        return bool(needle) and any(words[i:i+len(needle)] == needle for i in range(len(words)))
    if contains(target):
        return 'target_preserved'
    return 'correction_substituted' if contains(correction) else 'target_missing'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--synthesise', action='store_true')
    parser.add_argument('--segmented', action='store_true', help='Speak the target word separately, then join audio segments; still needs a human reference check')
    parser.add_argument('--run', action='store_true', help='Make paid provider calls')
    parser.add_argument('--limit', type=int, default=8)
    parser.add_argument('--assess', action='store_true', help='Also test grammar feedback on the supplied reference text')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = json.loads((args.manifest or ROOT / 'flask_vocab_app/data/speech_cases.json').read_text())[:args.limit]
    config = app_config()
    provider = SpeechProvider(config)
    voice = config['ELEVENLABS_VOICE_IDS'][0]
    results = []
    for original in cases:
        case = dict(original)
        path = Path(case.get('audio', args.output / (case['id'] + '.mp3')))
        if args.synthesise and not path.exists():
            if not args.run:
                raise SystemExit('Add --run to authorise the requested provider calls.')
            if args.segmented and case.get('target'):
                from pydub import AudioSegment
                import io
                before, after = case['text'].split(case['target'], 1)
                pieces = [part.strip(' .?!') for part in (before,case['target'],after) if part.strip(' .?!')]
                combined = AudioSegment.empty()
                for index, piece in enumerate(pieces):
                    part = args.output / f'{case["id"]}-segment-{index}.mp3'
                    if not part.exists(): part.write_bytes(provider.speak(piece, voice))
                    combined += AudioSegment.from_file(part,format='mp3') + AudioSegment.silent(duration=80)
                combined.export(path, format='mp3')
            else:
                path.write_bytes(provider.speak(case['text'], voice))
        if not path.exists():
            raise SystemExit(f'Missing fixture for {case["id"]}; supply audio or use --synthesise --run.')
        case.update(audio=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    source=case.get('source', 'human' if args.manifest and not args.synthesise else 'synthetic'),
                    reference_verified=bool(case.get('reference_verified', False)))
        if args.synthesise:
            case.update(voice_id=voice, synthesis_model=config['ELEVENLABS_MODEL'], reference_verified=False,
                        source='synthetic-segments' if args.segmented else 'synthetic')
        for name, style in [('mai', 'verbatim'), ('mai', 'clean'), ('openai', 'verbatim')]:
            output = args.output / f'{case["id"]}-{name}-{style}.json'
            if output.exists():
                result = json.loads(output.read_text())
                if result['case']['sha256'] != case['sha256'] or result['case']['text'] != case['text']:
                    raise SystemExit('Cached fixture differs from this input. Use a new output directory.')
                expected_model = config['CONVERSATION_TRANSCRIPTION_MODEL' if name=='mai' else 'CONVERSATION_COMPARISON_MODEL']
                if 'transcription' in result and result['transcription']['model'] != expected_model:
                    raise SystemExit('Cached model differs from this configuration. Use a new output directory.')
                if args.synthesise and any(result['case'].get(k) != case.get(k) for k in ('voice_id','synthesis_model','source')):
                    raise SystemExit('Cached synthesis settings differ. Use a new output directory.')
            else:
                if not args.run:
                    continue
                try:
                    result = {'case': case, 'transcription': provider.transcribe(path, provider=name, style=style)}
                    result['comparison'] = compare(case, result['transcription']['text'])
                except SpeechError as error:
                    result = {'case': case, 'provider': name, 'style': style, 'error': str(error)}
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            results.append(result)
            print(case['id'], name, style, result.get('comparison', result.get('error')),
                  result.get('transcription', {}).get('text', ''), flush=True)
        if args.assess:
            from services.conversation_ai import ConversationAI
            output = args.output / f'{case["id"]}-grammar.json'
            if not output.exists() and args.run:
                context = 'Что вы хотите заказать?' if case['id'] in ('genitive','correct_control','self_repair') else 'Вам чай с сахаром?' if case['id']=='short_control' else 'Расскажите, что происходит.'
                try:
                    assessment = ConversationAI(config).assess(case['text'], context)
                    output.write_text(json.dumps({'reference_text':case['text'],'assessment':assessment},ensure_ascii=False,indent=2))
                    print('Grammar',case['id'],assessment['corrections'],flush=True)
                except SpeechError as error:
                    print('Grammar',case['id'],str(error),flush=True)
    (args.output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print('Synthetic comparisons are against the script, not verified speech. Listen before attributing changes to ASR.')


if __name__ == '__main__':
    main()
