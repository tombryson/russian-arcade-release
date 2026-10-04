"""Add four standard MAI samples to a completed comparison without regenerating it."""
import argparse
import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

import compare_tts as base

MODEL = 'microsoft/mai-voice-2.1'
VOICE = 'ru-RU-Masha:MAI-Voice-2.1'
RATE = 22  # Published USD per million input characters, checked 4 October 2026.
SOURCE = 'https://openrouter.ai/microsoft/mai-voice-2.1'


def inspect_existing(directory):
    if directory.resolve().is_relative_to(base.ROOT):
        raise base.ComparisonError('UseExternalOutputDirectory')
    if any((directory / name).exists() for name in (
            'mai-standard-extension.json', 'manifest.three-model.json', 'listen.three-model.html')):
        raise base.ComparisonError('ExtensionAlreadyAttempted')
    result = json.loads((directory / 'manifest.json').read_text())
    expected = [dict(s, sha256=base.digest(s['text'].encode())) for s in base.load_samples()]
    if (result.get('version') != 'russian-tts-comparison-v1'
            or result.get('state') != 'complete' or result.get('calls') != 12
            or result.get('samples') != expected or len(result.get('results', [])) != 12):
        raise base.ComparisonError('OriginalComparisonMismatch')
    pairs = set()
    for sample in expected:
        rows = [r for r in result['results'] if r['sample_id'] == sample['id']]
        if len(rows) != 3 or {r['blind_label'] for r in rows} != set('ABC'):
            raise base.ComparisonError('OriginalComparisonMismatch')
        for row in rows:
            pair = (sample['id'], row['model'])
            if (pair in pairs or row['model'] not in base.MODELS or row['state'] != 'complete'
                    or row['text_sha256'] != sample['sha256']):
                raise base.ComparisonError('OriginalComparisonMismatch')
            pairs.add(pair)
            for kind in ('raw', 'listen'):
                name = row['audio'][kind + '_file']
                path = directory / name
                if (Path(name).name != name or path.is_symlink()
                        or base.digest(path.read_bytes()) != row['audio'][kind + '_sha256']):
                    raise base.ComparisonError('OriginalAudioMismatch')
        if any(directory.glob(sample['id'] + '-D.*')):
            raise base.ComparisonError('ExtensionAudioAlreadyExists')
    estimate = len(''.join(s['text'] for s in expected)) * RATE / 1_000_000
    if estimate > 0.10:
        raise base.ComparisonError('ExtensionBudgetExceeded')
    return result, round(estimate, 6)


def preflight(client, key):
    response = base.checked(client.get('https://openrouter.ai/api/v1/models?output_modalities=speech', timeout=(10, 30)))
    try:
        model = next((m for m in response.json().get('data', []) if m.get('id') == MODEL), None)
    finally:
        response.close()
    if not model or VOICE not in model.get('supported_voices', []):
        raise base.ComparisonError('MAIStandardVoiceUnavailable')
    rate = float(model.get('pricing', {}).get('prompt', 'nan'))
    if not math.isfinite(rate) or not 0 <= rate <= RATE / 1_000_000:
        raise base.ComparisonError('MAIStandardPriceExceedsEstimate')
    response = base.checked(client.get('https://openrouter.ai/api/v1/key',
                                       headers={'Authorization': 'Bearer ' + key}, timeout=(10, 30)))
    try:
        if not isinstance(response.json().get('data'), dict):
            raise base.ComparisonError('OpenRouterCredentialUnavailable')
    finally:
        response.close()


def run(directory, key, client=None, audio_processor=base.prepare_audio):
    import requests
    original, cost = inspect_existing(directory)
    original_bytes = (directory / 'manifest.json').read_bytes()
    original_page = (directory / 'listen.html').read_bytes()
    client = client or requests.Session()
    client.trust_env = False
    if isinstance(client, requests.Session):
        client.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))
    receipt = directory / 'mai-standard-extension.json'
    extension = {'model': MODEL, 'voice': VOICE, 'at': datetime.now(timezone.utc).isoformat(),
                 'state': 'preflight', 'maximum_calls': 4, 'calls': 0, 'automatic_retries': 0,
                 'estimated_usd': cost, 'actual_charge_usd': None, 'pricing_source': SOURCE,
                 'original_manifest_sha256': base.digest(original_bytes), 'results': []}
    claimed = False
    try:
        preflight(client, key)
        # Exclusive receipt prevents a second process from paying for the same addition.
        with receipt.open('x') as handle:
            claimed = True
            receipt.chmod(0o600)
            json.dump(extension, handle, ensure_ascii=False, indent=2)
        (directory / 'manifest.three-model.json').write_bytes(original_bytes)
        (directory / 'listen.three-model.html').write_bytes(original_page)
        extension['state'] = 'generating'
        for sample in original['samples']:
            body = {'model': MODEL, 'input': sample['text'], 'voice': VOICE, 'response_format': 'mp3'}
            row = {'sample_id': sample['id'], 'text_sha256': sample['sha256'], 'model': MODEL,
                   'voice': VOICE, 'blind_label': 'D', 'state': 'requesting', 'request': body,
                   'at': datetime.now(timezone.utc).isoformat(), 'actual_charge_usd': None}
            extension['results'].append(row)
            extension['calls'] += 1
            base.save(receipt, extension)
            raw, row['timing'] = base.synthesize(client, ('https://openrouter.ai/api/v1/audio/speech',
                {'Authorization': 'Bearer ' + key}, body))
            started = time.monotonic()
            row['audio'] = audio_processor(raw, directory, sample['id'] + '-D')
            row['timing']['normalization_ms'] = round((time.monotonic() - started) * 1000)
            row['state'] = 'complete'
            base.save(receipt, extension)
        extension['state'] = 'complete'
        base.save(receipt, extension)
        combined = copy.deepcopy(original)
        combined['version'] = 'russian-tts-comparison-v2'
        combined['results'].extend(extension['results'])
        combined['calls'] += extension['calls']
        combined['extensions'] = [{k: v for k, v in extension.items() if k != 'results'}]
        combined['original_budget'] = copy.deepcopy(original['budget'])
        budget = combined['budget']
        budget['maximum_synthesis_calls'] = 16
        for field in ('published_estimate_usd', 'conservative_estimate_usd'):
            budget[field] = round(budget[field] + cost, 6)
        for field in ('published_usd_per_million_characters', 'reserved_usd_per_million_characters'):
            budget[field][MODEL] = RATE
        budget['sources'].append(SOURCE)
        try:
            base.render_html(combined, directory)
            base.save(directory / 'manifest.json', combined)
        except Exception:
            # Publication failure must leave the original listening comparison usable.
            temporary = directory / 'listen.html.tmp'
            temporary.write_bytes(original_page)
            temporary.replace(directory / 'listen.html')
            raise
        return extension
    except Exception as error:
        extension.update(state='stopped', error_type=type(error).__name__,
                         error_code=str(error) if isinstance(error, base.ComparisonError) else None)
        if extension['results'] and extension['results'][-1]['state'] != 'complete':
            extension['results'][-1]['state'] = 'failed'
        if claimed:
            base.save(receipt, extension)
        return extension
    finally:
        client.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args(argv)
    try:
        _, cost = inspect_existing(args.directory)
        if not args.live:
            print(json.dumps({'live': False, 'model': MODEL, 'voice': VOICE,
                              'maximum_new_calls': 4, 'estimated_additional_usd': cost}))
            return 0
        if args.env_file is None:
            parser.error('--live requires --env-file.')
        keys = base.load_credentials(args.env_file, names=('OPENROUTER_API_KEY',))
        result = run(args.directory, keys['OPENROUTER_API_KEY'])
        print(json.dumps({k: result[k] for k in ('state', 'calls', 'estimated_usd')}))
        return 0 if result['state'] == 'complete' else 1
    except Exception as error:
        print(json.dumps({'state': 'unavailable', 'error_type': type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
