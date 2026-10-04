"""Local three-model Russian TTS comparison; dry-run unless --live.

Preserves production settings and data. Twelve synthesis calls maximum, no retries,
no resume and a conservative $1 estimated ceiling. Prices are estimates, not bills.
"""
import argparse
from datetime import date, datetime, timezone
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import random
import time

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = Path(__file__).with_name('tts_comparison_samples.json')
MODEL_MAI = 'microsoft/mai-voice-2.1-flash'
VOICE_MAI = 'ru-RU-Masha:MAI-Voice-2.1-Flash'
MODELS = ('eleven_multilingual_v2', MODEL_MAI, 'eleven_v4')
RATES = {'eleven_multilingual_v2': 80, MODEL_MAI: 15, 'eleven_v4': 80}
MAX_USD, MAX_CALLS, MAX_CHARS, MAX_BYTES = 1.0, 12, 2500, 8 * 1024 * 1024
HOSTED_FLAGS = ('AI_TRIAL_ENABLED', 'HOSTED_AI_TRIAL', 'PUBLIC_DEMO',
                'HOSTED_ACCOUNTS_ENABLED', 'HOSTED_GUEST_DEMO_ENABLED', 'FLY_APP_NAME', 'FLY_MACHINE_ID')
PRICING_SOURCES = ['https://elevenlabs.io/pricing/api',
                   'https://openrouter.ai/microsoft/mai-voice-2.1-flash']


class ComparisonError(ValueError):
    """Only fixed internal messages; never provider bodies or exception text."""


def digest(value):
    return hashlib.sha256(value).hexdigest()


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def load_samples(path=SAMPLES):
    samples = json.loads(path.read_text())
    if (not isinstance(samples, list) or len(samples) != 4
            or any(not isinstance(s, dict) or set(s) != {'id', 'title', 'purpose', 'text'} for s in samples)
            or any(not all(isinstance(v, str) and v.strip() for v in s.values()) for s in samples)
            or any(not s['id'].isascii() or not s['id'].replace('-', '').isalnum() for s in samples)
            or len({s['id'] for s in samples}) != 4
            or any(len(s['text']) > 1000 or '\x00' in s['text'] for s in samples)
            or sum(len(s['text']) for s in samples) > MAX_CHARS):
        raise ComparisonError('SampleBoundsExceeded')
    return samples


def estimate(samples, today=None):
    today = today or date.today()
    chars = sum(len(s['text']) for s in samples)
    published = dict(RATES)
    if date(2026, 10, 4) <= today < date(2026, 10, 12):
        published['eleven_v4'] = 22
    reserved = sum(chars * price / 1_000_000 for price in RATES.values())
    if len(samples) * len(MODELS) > MAX_CALLS or chars > MAX_CHARS or reserved > MAX_USD:
        raise ComparisonError('EvaluationBudgetExceeded')
    return {'characters_per_model': chars, 'maximum_synthesis_calls': 12,
            'conservative_ceiling_usd': MAX_USD, 'conservative_estimate_usd': round(reserved, 6),
            'reserved_usd_per_million_characters': RATES,
            'published_usd_per_million_characters': published,
            'published_estimate_usd': round(sum(chars * p / 1_000_000 for p in published.values()), 6),
            'pricing_verified_on': '2026-10-04', 'pricing_applied_on': today.isoformat(),
            'v4_promotion_ends': '2026-10-12', 'sources': PRICING_SOURCES,
            'actual_charge_usd': None,
            'limitation': 'Published character-rate estimate; subscription credits, taxes and actual charges are not verified.'}


def load_credentials(path, names=('ELEVENLABS_API_KEY', 'OPENROUTER_API_KEY')):
    from dotenv import dotenv_values
    if not path.is_file():
        raise ComparisonError('ConfigurationUnavailable')
    values = dotenv_values(path, interpolate=False)
    for source in (os.environ, values):
        if any(str(source.get(k) or '').strip().lower() not in ('', '0', 'false', 'no', 'off') for k in HOSTED_FLAGS):
            raise ComparisonError('HostedTrialRequiresMeteredAdapters')
    keys = {name: os.environ.get(name) or values.get(name) for name in names}
    if not all(isinstance(v, str) and v.strip() for v in keys.values()):
        raise ComparisonError('ConfigurationUnavailable')
    return keys


def checked(response):
    if not 200 <= response.status_code < 300:
        response.close()
        raise ComparisonError('ProviderHTTP' + str(response.status_code))
    return response


def preflight(client, keys, eleven_voice, mai_voice):
    """Read-only model/voice and credential checks; synthesis access can still fail."""
    def read(url, headers=None):
        response = checked(client.get(url, headers=headers or {}, timeout=(10, 30)))
        try:
            return response.json()
        finally:
            response.close()
    eh = {'xi-api-key': keys['ELEVENLABS_API_KEY']}
    models = read('https://api.elevenlabs.io/v1/models', eh)
    available = {m.get('model_id') for m in models if isinstance(m, dict)}
    if not {'eleven_multilingual_v2', 'eleven_v4'} <= available:
        raise ComparisonError('ElevenLabsModelUnavailable')
    voice = read('https://api.elevenlabs.io/v1/voices/' + eleven_voice, eh)
    if voice.get('voice_id') != eleven_voice:
        raise ComparisonError('ElevenLabsVoiceUnavailable')
    catalogue = read('https://openrouter.ai/api/v1/models?output_modalities=speech')
    entries = [m for m in catalogue.get('data', []) if m.get('id') == MODEL_MAI]
    if not entries:
        raise ComparisonError('MAIModelUnavailable')
    if mai_voice not in entries[0].get('supported_voices', []):
        raise ComparisonError('MAIVoiceUnavailable')
    rate = float(entries[0].get('pricing', {}).get('prompt', 'nan'))
    if not math.isfinite(rate) or rate < 0 or rate > RATES[MODEL_MAI] / 1_000_000:
        raise ComparisonError('MAIPriceExceedsReservation')
    account = read('https://openrouter.ai/api/v1/key', {'Authorization': 'Bearer ' + keys['OPENROUTER_API_KEY']})
    if not isinstance(account.get('data'), dict):
        raise ComparisonError('OpenRouterCredentialUnavailable')
    tuning = voice.get('fine_tuning', {}).get('state', {}).get('eleven_v4')
    return {'eleven_voice_category': voice.get('category') if voice.get('category') in ('professional', 'cloned', 'generated', 'premade') else 'unreported',
            'eleven_v4_fine_tuning': tuning if tuning in ('fine_tuned', 'not_fine_tuned', 'fine_tuning', 'failed', 'queued') else 'unreported',
            'read_only_checks': 4, 'models_listed': list(MODELS), 'eleven_voice_accessible': True,
            'mai_voice_listed': True, 'openrouter_key_authenticated': True,
            'limitation': 'Catalogue availability does not guarantee synthesis access or remaining paid credit.'}


def request_for(model, text, eleven_voice, mai_voice, keys):
    if model == MODEL_MAI:
        return ('https://openrouter.ai/api/v1/audio/speech',
                {'Authorization': 'Bearer ' + keys['OPENROUTER_API_KEY']},
                {'model': model, 'input': text, 'voice': mai_voice, 'response_format': 'mp3'})
    settings = {'stability': 0.8, 'similarity_boost': 0.85}
    if model == 'eleven_multilingual_v2':
        settings['style'] = 0.0
    elif model != 'eleven_v4':
        raise ComparisonError('UnrecognisedModel')
    return ('https://api.elevenlabs.io/v1/text-to-speech/' + eleven_voice + '?output_format=mp3_44100_128',
            {'xi-api-key': keys['ELEVENLABS_API_KEY']},
            {'text': text, 'model_id': model, 'voice_settings': settings})


def synthesize(client, request, clock=time.monotonic):
    url, headers, body = request
    start = clock()
    response = checked(client.post(url, headers=headers, json=body, stream=True, timeout=(10, 90)))
    first, first_size, data = None, 0, bytearray()
    try:
        for chunk in response.iter_content(chunk_size=4096):
            if chunk:
                if first is None:
                    first = clock()
                    first_size = len(chunk)
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ComparisonError('AudioSizeExceeded')
        end = clock()
        if first is None:
            raise ComparisonError('EmptyAudio')
        return bytes(data), {'first_body_chunk_ms': round((first - start) * 1000),
                             'complete_response_ms': round((end - start) * 1000),
                             'first_chunk_bytes': first_size,
                             'content_type': 'audio/mpeg' if response.headers.get('Content-Type', '').split(';')[0] == 'audio/mpeg' else 'other'}
    finally:
        response.close()


def prepare_audio(raw, directory, stem):
    from pydub import AudioSegment
    if not (raw.startswith(b'ID3') or (len(raw) > 1 and raw[0] == 255 and raw[1] & 224 == 224)):
        raise ComparisonError('InvalidMP3')
    # Keep the paid response even if decoding or normalization fails later.
    source = directory / (stem + '.raw.mp3')
    source.write_bytes(raw)
    source.chmod(0o600)
    audio = AudioSegment.from_file(io.BytesIO(raw), format='mp3')
    if not 200 <= len(audio) <= 90000 or not math.isfinite(audio.dBFS):
        raise ComparisonError('InvalidAudioDurationOrSilence')
    normalized = audio.set_channels(1).set_frame_rate(44100)
    normalized = normalized.apply_gain(-20.0 - normalized.dBFS)
    output = io.BytesIO()
    normalized.export(output, format='mp3', bitrate='128k')
    listen = output.getvalue()
    # Decode the published listening copy as well; malformed output never gets a player.
    if abs(len(AudioSegment.from_file(io.BytesIO(listen), format='mp3')) - len(audio)) > 100:
        raise ComparisonError('NormalizationIntegrityFailure')
    path = directory / (stem + '.listen.mp3')
    path.write_bytes(listen)
    path.chmod(0o600)
    return {'raw_file': stem + '.raw.mp3', 'raw_sha256': digest(raw), 'raw_bytes': len(raw),
            'listen_file': stem + '.listen.mp3', 'listen_sha256': digest(listen),
            'duration_ms': len(audio), 'raw_sample_rate': audio.frame_rate, 'raw_channels': audio.channels,
            'normalization': {'target_dbfs': -20.0, 'sample_rate': 44100, 'channels': 1, 'bitrate': '128k'}}


def render_html(result, directory):
    escape = html.escape
    sections = []
    for sample in result['samples']:
        cards = []
        rows = sorted((r for r in result['results'] if r['sample_id'] == sample['id']), key=lambda r: r['blind_label'])
        for row in rows:
            label = escape(row['blind_label'])
            audio = row.get('audio')
            player = (f'<audio controls preload="none" aria-label="{escape(sample["title"], quote=True)}: sample {label}" src="{escape(audio["listen_file"], quote=True)}"></audio>'
                      if audio else '<p>Recording unavailable.</p>')
            download = (f'<p><a href="{escape(audio["raw_file"], quote=True)}" download>Download original audio</a></p>'
                        if audio and audio.get('raw_file') else '')
            timing = row.get('timing', {})
            stats = f'{timing.get("first_body_chunk_ms", "—")} ms first chunk · {timing.get("complete_response_ms", "—")} ms complete'
            cards.append(f'<article><h3>Sample {label}</h3>{player}<div class="identity" hidden>'
                         f'<p>{escape(row["model"])}<br>{escape(row["voice"])}</p><p>{stats}</p>{download}</div></article>')
        sections.append(f'<section><h2>{escape(sample["title"])}</h2><p lang="ru" class="transcript">'
                        f'{escape(sample["text"])}</p><div class="grid">{"".join(cards)}</div></section>')
    caveat = ('<p>ElevenLabs v4 support for this professional voice was unconfirmed at preflight. This run is also a compatibility test; successful synthesis does not prove equivalent voice support.</p>'
              if result.get('allow_unverified_voice') else '')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Russian speech comparison</title><style>body{font:17px/1.5 system-ui;max-width:1160px;margin:36px auto;padding:0 20px;color:#242742;background:#fffaf0}h1{font-size:30px}h2{font-size:23px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px}article{border:1px solid #bbb;padding:18px;border-radius:12px}audio{width:100%}section{margin:36px 0}.transcript{white-space:pre-line;max-width:85ch}button{padding:10px 16px;font:inherit}article p{overflow-wrap:anywhere}.identity{font-size:14px}@media(max-width:750px){.grid{grid-template-columns:1fr}}</style>
<h1>Russian speech comparison</h1><p>Listen to each version before revealing its model. Samples share the same text and average audio level. MAI uses a different voice; this is a provider-and-voice comparison.</p>
<p>Compare pronunciation and endings, stress, natural pacing, dialogue expression, and any omitted or added words. The last passage is a diagnostic probe, not lesson prose.</p>
<p><a href="transcripts.json" download>Download transcripts</a></p><button id="reveal" type="button" aria-expanded="false">Reveal models and timings</button>
<div class="identity" hidden><p><a href="manifest.json" download>Download results</a></p><p>First chunk is network timing, not demonstrated browser playback latency. Estimates are not actual charges.</p><pre id="cost"></pre></div>
''' + '<div class="identity" hidden>' + caveat + '</div>' + ''.join(sections) + '<script>document.getElementById("reveal").onclick=function(){document.querySelectorAll(".identity").forEach(e=>e.hidden=!e.hidden);this.setAttribute("aria-expanded",this.getAttribute("aria-expanded")==="false"?"true":"false");this.textContent=this.textContent.startsWith("Reveal")?"Hide models and timings":"Reveal models and timings"};document.getElementById("cost").textContent=' + json.dumps('Conservative estimate: $' + str(result['budget']['conservative_estimate_usd']) + '\nPublished-rate estimate: $' + str(result['budget']['published_estimate_usd']) + '\nActual charge: unknown') + ';document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>document.querySelectorAll("audio").forEach(b=>{if(a!==b)b.pause()})));</script></html>'
    temporary = directory / 'listen.html.tmp'
    temporary.write_text(document)
    temporary.replace(directory / 'listen.html')


def run(samples, keys, directory, eleven_voice, mai_voice=VOICE_MAI, seed=20261004,
        client=None, audio_processor=prepare_audio, clock=time.monotonic, allow_unverified_voice=False):
    import requests
    if directory.exists() or directory.resolve().is_relative_to(ROOT):
        raise ComparisonError('UseFreshExternalOutputDirectory')
    if not eleven_voice.isalnum() or len(eleven_voice) > 100 or mai_voice != VOICE_MAI:
        raise ComparisonError('InvalidVoiceSelection')
    budget = estimate(samples)
    directory.mkdir(parents=True, mode=0o700)
    client = client or requests.Session()
    client.trust_env = False
    # Requests' default adapter has zero retries. Set it explicitly for production runs.
    if isinstance(client, requests.Session):
        for prefix in ('https://', 'http://'):
            client.mount(prefix, requests.adapters.HTTPAdapter(max_retries=0))
    result = {'version': 'russian-tts-comparison-v1', 'at': datetime.now(timezone.utc).isoformat(),
              'state': 'preflight', 'automatic_retries': 0, 'seed': seed, 'budget': budget,
              'production_changed': False, 'allow_unverified_voice': allow_unverified_voice, 'samples': [dict(s, sha256=digest(s['text'].encode())) for s in samples],
              'calls': 0, 'results': [], 'independent_listening_completed': False}
    manifest = directory / 'manifest.json'
    save(manifest, result)
    save(directory / 'transcripts.json', result['samples'])
    try:
        result['preflight'] = preflight(client, keys, eleven_voice, mai_voice)
        save(manifest, result)
        if (result['preflight']['eleven_voice_category'] == 'professional'
                and result['preflight']['eleven_v4_fine_tuning'] != 'fine_tuned'
                and not allow_unverified_voice):
            raise ComparisonError('ProfessionalVoiceV4NotConfirmed')
        result['state'] = 'generating'
        save(manifest, result)
        rng = random.Random(seed)
        for index, sample in enumerate(samples):
            labels = list('ABC')
            rng.shuffle(labels)
            mapping = dict(zip(MODELS, labels))
            for model in MODELS[index % 3:] + MODELS[:index % 3]:
                row = {'sample_id': sample['id'], 'text_sha256': digest(sample['text'].encode()),
                       'model': model, 'voice': mai_voice if model == MODEL_MAI else eleven_voice,
                       'blind_label': mapping[model], 'state': 'requesting', 'actual_charge_usd': None}
                request = request_for(model, sample['text'], eleven_voice, mai_voice, keys)
                row['request'] = request[2]  # Headers and credentials are never persisted.
                result['results'].append(row)
                result['calls'] += 1
                save(manifest, result)
                try:
                    raw, timing = synthesize(client, request, clock)
                    row['timing'] = timing
                    started = clock()
                    row['audio'] = audio_processor(raw, directory, sample['id'] + '-' + mapping[model])
                    timing['normalization_ms'] = round((clock() - started) * 1000)
                    row['state'] = 'complete'
                except Exception as error:
                    row.update(state='failed', error_type=type(error).__name__,
                               error_code=str(error) if isinstance(error, ComparisonError) else None)
                    source = directory / (sample['id'] + '-' + mapping[model] + '.raw.mp3')
                    if source.is_file():
                        row['unverified_raw_audio'] = {'file': source.name,
                                                       'sha256': digest(source.read_bytes())}
                    # Stop paid work after any provider or audio failure; never retry.
                    result['state'] = 'stopped'
                    save(manifest, result)
                    render_html(result, directory)
                    return result
                save(manifest, result)
        result['state'] = 'complete'
    except Exception as error:
        result.update(state='stopped', error_type=type(error).__name__,
                      error_code=str(error) if isinstance(error, ComparisonError) else None)
    finally:
        client.close()
    save(manifest, result)
    render_html(result, directory)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--eleven-voice', help='One existing configured voice, shared by both ElevenLabs arms.')
    parser.add_argument('--seed', type=int, default=20261004)
    parser.add_argument('--allow-unverified-voice', action='store_true',
                        help='Explicitly attempt a professional voice whose v4 fine-tuning is unconfirmed.')
    args = parser.parse_args(argv)
    try:
        samples = load_samples()
        if not args.live:
            print(json.dumps({'live': False, 'models': MODELS, 'budget': estimate(samples),
                              'samples': samples, 'automatic_retries': 0}, ensure_ascii=False))
            return 0
        if args.env_file is None or args.output is None or not args.eleven_voice:
            parser.error('--live requires --env-file, --output and --eleven-voice.')
        result = run(samples, load_credentials(args.env_file), args.output, args.eleven_voice,
                     seed=args.seed, allow_unverified_voice=args.allow_unverified_voice)
        print(json.dumps({'state': result['state'], 'calls': result['calls'], 'output': str(args.output)}))
        return 0 if result['state'] == 'complete' else 1
    except Exception as error:
        print(json.dumps({'state': 'unavailable', 'error_type': type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
