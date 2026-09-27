"""Bounded, server-owned provider calls for the hosted AI trial.

Local clients pass through unchanged. Trial clients expose only the operations
used by this app, forbid tools/streams/remote state, disable SDK retries, and
reserve spend in the persistent shared ledger before any network call.

Rates checked 2026-09-17 against provider pricing. Reservations use UTF-8 bytes
as a conservative upper bound for text tokens (including schemas), plus bounded
image/audio inputs. Unknown models fail closed. Missing usage or network errors
consume the reservation; this is an allowance charge, not an invoice estimate.

Pricing references:
https://developers.openai.com/api/docs/pricing
https://developers.openai.com/api/docs/guides/image-generation#calculating-costs
https://elevenlabs.io/pricing/api
https://openrouter.ai/microsoft/mai-transcribe-2
"""
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING
import base64
import hashlib
import io
import json
import logging
import math
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import uuid
import wave

from .ai_trial_budget import AITrialBudget, TrialDenied

logger = logging.getLogger(__name__)

# USD per million tokens. Decimal strings avoid binary floating-point money.
TEXT_RATES = {
    'gpt-6-astra': ('10', '50'),
    'gpt-5.6-sol': ('4', '20'),
    'gpt-5.6': ('4', '20'),
    'gpt-5.6-terra': ('2', '12'),
    'gpt-5.6-luna': ('.20', '1.20'),
    'gpt-5.2': ('1.75', '14'),
    'gpt-5-mini': ('.25', '2'),
    'gpt-audio-1.5': ('2.50', '10'),
}
IMAGE_RATES = {'gpt-image-2': ('2.50', '15')}
TRANSCRIPTION_MODELS = {'gpt-transcribe', 'gpt-4o-transcribe', 'gpt-4o-mini-transcribe', 'whisper-1'}
MAX_TEXT_BYTES = 96_000
MAX_OUTPUT_TOKENS = 12_000
MAX_IMAGE_BYTES = 8_000_000
MAX_IMAGE_COUNT = 4
MAX_AUDIO_BYTES = 16_000_000
MAX_AUDIO_SECONDS = 300


def config_snapshot(config=None):
    """Capture app ownership now, so background work never consults a browser."""
    if config is None:
        from flask import current_app, has_app_context
        config = current_app.config if has_app_context() else {}
    snapshot = dict(config)
    return MappingProxyType(snapshot) if trial_enabled(snapshot) else snapshot


def trial_enabled(config):
    # A hosted deployment with its toggle off must not become an unmetered app.
    return bool(config.get('AI_TRIAL_ENABLED') or config.get('HOSTED_AI_TRIAL') or config.get('PUBLIC_DEMO'))


def _ceil(value):
    return int(Decimal(value).to_integral_value(rounding=ROUND_CEILING))


def _tokens_cost(input_tokens, output_tokens, rates):
    return _ceil(Decimal(input_tokens) * Decimal(rates[0]) + Decimal(output_tokens) * Decimal(rates[1]))


def _field(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _text_usage(response, rates, audio=False, cache_writes=False):
    usage = _field(response, 'usage')
    incoming = _count(_field(usage, 'input_tokens', _field(usage, 'prompt_tokens')))
    outgoing = _count(_field(usage, 'output_tokens', _field(usage, 'completion_tokens')))
    if incoming is None or outgoing is None:
        return None
    # Charge all input tokens at uncached rate; no unverified cache discount.
    if audio:
        details = _field(usage, 'prompt_tokens_details', {})
        audio_tokens = _count(_field(details, 'audio_tokens'))
        if audio_tokens is None or audio_tokens > incoming:
            return None
        return _tokens_cost(incoming - audio_tokens, outgoing, rates) + audio_tokens * 32
    cost = _tokens_cost(incoming, outgoing, rates)
    if cache_writes:
        details = _field(usage, 'input_tokens_details', _field(usage, 'prompt_tokens_details', {}))
        written = _count(_field(details, 'cache_write_tokens'))
        # Missing details cannot prove that no writes were billed. Reserve and
        # charge the premium for all input in that case, never invent a refund.
        if written is None:
            written = incoming
        if written > incoming:
            return None
        cost += _ceil(Decimal(written) * Decimal(rates[0]) * Decimal('.25'))
    return cost


def _image_usage(response, rates):
    usage = _field(response, 'usage')
    incoming = _count(_field(usage, 'input_tokens'))
    outgoing = _count(_field(usage, 'output_tokens'))
    if incoming is None or outgoing is None:
        return None
    return _tokens_cost(incoming, outgoing, rates)


def provider_call(config, operation, payload, maximum_cost, invoke, actual_cost=None):
    """Run one bounded operation; never accepts an identity from its payload."""
    config = config_snapshot(config)
    if not trial_enabled(config):
        return invoke()
    if not config.get('AI_TRIAL_ENABLED'):
        raise TrialDenied('AI generation is paused. Saved practice is still available.')
    identity = config.get('AI_TRIAL_IDENTITY')
    path = config.get('AI_TRIAL_LEDGER_PATH')
    if not isinstance(identity, str) or not identity or not path:
        raise TrialDenied('Sign in to use the AI trial.')
    ledger = AITrialBudget(path, enabled=True)
    request_id = uuid.uuid4().hex
    digest = hashlib.sha256(json.dumps({'operation': operation, 'payload': payload},
        sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    reservation = ledger.reserve(identity, request_id, digest, maximum_cost)
    if not reservation['created']:
        raise TrialDenied('This AI request has already been submitted.')
    try:
        result = invoke()
    except BaseException:
        # No automatic retries. HTTP errors can also be ambiguous at the edge.
        ledger.charge_reservation(identity, request_id)
        raise
    try:
        cost = actual_cost(result) if actual_cost else None
    except (TypeError, ValueError, ArithmeticError):
        cost = None
    if type(cost) is int and cost >= 0:
        ledger.settle(identity, request_id, cost)
    else:
        ledger.charge_reservation(identity, request_id)
    return result


def _decode_audio(encoded):
    if not isinstance(encoded, str) or len(encoded) > MAX_AUDIO_BYTES * 4 // 3 + 8:
        raise TrialDenied('That recording is too large for the AI trial.')
    try:
        data = base64.b64decode(encoded, validate=True)
        with wave.open(io.BytesIO(data), 'rb') as audio:
            duration = audio.getnframes() / audio.getframerate()
            if (audio.getnchannels() not in (1, 2) or audio.getsampwidth() != 2
                    or not 0 < duration <= MAX_AUDIO_SECONDS
                    or len(audio.readframes(audio.getnframes())) != audio.getnframes() * audio.getnchannels() * 2):
                raise ValueError()
        return duration, hashlib.sha256(data).hexdigest()
    except (ValueError, wave.Error, EOFError, ZeroDivisionError):
        raise TrialDenied('Use a playable recording of at most five minutes.') from None


def _sanitize_inputs(value, media):
    """Bound embedded media while excluding its base64 from text-token counts."""
    if isinstance(value, list):
        return [_sanitize_inputs(item, media) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get('type')
    if kind in ('input_file', 'file'):
        raise TrialDenied('Read the lesson pages before sending them to the AI trial.')
    if kind in ('input_image', 'image_url'):
        settings = value.get('image_url') if isinstance(value.get('image_url'), dict) else value
        if settings.get('detail') not in (None, 'low', 'high', 'auto'):
            raise TrialDenied('Use standard detail for lesson pages in the AI trial.')
        # Newer models treat omitted/auto detail as original, whose patch
        # count can be much greater than high. Make the priced mode explicit.
        settings['detail'] = 'high'
        url = value.get('image_url', '')
        url = url.get('url', '') if isinstance(url, dict) else url
        if not isinstance(url, str) or not url.startswith(('data:image/jpeg;base64,', 'data:image/png;base64,')):
            raise TrialDenied('The AI trial accepts uploaded page images only.')
        try:
            encoded = url.split(',', 1)[1]
            if len(encoded) > MAX_IMAGE_BYTES * 4 // 3 + 8:
                raise ValueError()
            data = base64.b64decode(encoded, validate=True)
            from PIL import Image
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                if min(width, height) < 1 or max(width, height) > 4096 or width * height > 16_000_000:
                    raise ValueError()
                image.verify()
        except (OSError, ValueError):
            raise TrialDenied('That lesson page image is too large or unreadable.') from None
        media['images'] += 1
        if media['images'] > MAX_IMAGE_COUNT:
            raise TrialDenied('Send at most four lesson pages in each AI request.')
        return {'type': kind, 'sha256': hashlib.sha256(data).hexdigest()}
    if kind == 'input_audio':
        audio = value.get('input_audio', {})
        if audio.get('format') != 'wav':
            raise TrialDenied('Speaking assessment needs a decoded WAV recording.')
        duration, digest = _decode_audio(audio.get('data'))
        media['seconds'] += duration
        if media['seconds'] > MAX_AUDIO_SECONDS:
            raise TrialDenied('Use a recording of at most five minutes.')
        return {'type': kind, 'sha256': digest}
    return {key: _sanitize_inputs(item, media) for key, item in value.items()}


def _text_request(operation, kwargs):
    values = deepcopy(kwargs)
    model = values.get('model')
    if model not in TEXT_RATES:
        logger.warning('AI trial text request denied: model has no configured budget rate')
        raise TrialDenied('AI generation is currently unavailable. Please try again later.')
    # Forbid indirect paid tools, hidden conversation history and alternate HTTP
    # bodies/headers which could bypass the checked model, caps or endpoint.
    forbidden = ('tools', 'functions', 'previous_response_id', 'conversation',
                 'extra_body', 'extra_query', 'extra_headers', 'background', 'stream',
                 'prompt', 'audio', 'prediction', 'web_search_options')
    if any(values.get(key) for key in forbidden):
        raise TrialDenied('This provider operation is not available in the AI trial.')
    if values.get('n', 1) != 1 or values.get('modalities', ['text']) != ['text']:
        raise TrialDenied('The AI trial supports one text answer per request.')
    if values.get('service_tier') not in (None, 'default'):
        raise TrialDenied('The AI trial uses standard provider processing.')
    limit_key = 'max_output_tokens' if operation == 'responses.create' else 'max_completion_tokens'
    requested = values.pop('max_tokens', values.get(limit_key, 4096))
    if type(requested) is not int or not 1 <= requested <= MAX_OUTPUT_TOKENS:
        raise TrialDenied('That AI response is too large for the trial.')
    values[limit_key] = requested
    values['store'] = False
    values['service_tier'] = 'default'
    media = {'images': 0, 'seconds': 0}
    sanitized = _sanitize_inputs(values, media)
    text_bytes = len(json.dumps(sanitized, ensure_ascii=False, separators=(',', ':')).encode())
    if text_bytes > MAX_TEXT_BYTES:
        raise TrialDenied('That lesson or conversation is too long for one AI request.')
    # UTF-8 byte length bounds text tokens, with an allowance for protocol roles.
    # Official high-detail limit is 2500 patches * 1.2 for Astra/5.6.
    # Older admitted models use <=6144 patches * 1.2; round their allowance up.
    # https://developers.openai.com/api/docs/guides/images-vision#calculating-costs
    image_tokens = 3000 if model.startswith(('gpt-6-', 'gpt-5.6')) else 8192
    incoming = text_bytes + 1024 + media['images'] * image_tokens
    # New-model cache writes can cost 1.25x input. Admission never assumes a
    # cache discount; settlement uses any reported cache-write token detail.
    if model.startswith(('gpt-6-', 'gpt-5.6')):
        incoming = math.ceil(incoming * 1.25)
    cost = _tokens_cost(incoming, requested, TEXT_RATES[model])
    if media['seconds']:
        if model != 'gpt-audio-1.5':
            raise TrialDenied('This configured model does not support audio assessment.')
        cost += math.ceil(media['seconds'] * 100) * 32
    return values, sanitized, max(1, cost), lambda result: _text_usage(
        result, TEXT_RATES[model], bool(media['seconds']), model.startswith(('gpt-6-', 'gpt-5.6')))


class TrialOpenAI:
    """Small explicit SDK facade. New paid endpoints require a budget adapter."""
    def __init__(self, client, config):
        self._client = client
        self._config = config_snapshot(config)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))
        self.responses = SimpleNamespace(create=self._responses)
        self.images = SimpleNamespace(generate=self._images)
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._transcription))

    def with_options(self, **options):
        if set(options) - {'timeout', 'max_retries'}:
            raise TrialDenied('Provider configuration cannot change during a trial request.')
        options['max_retries'] = 0
        return TrialOpenAI(self._client.with_options(**options), self._config)

    def _text(self, operation, invoke, values):
        values, digest, maximum, actual = _text_request(operation, values)
        return provider_call(self._config, 'openai.' + operation, digest, maximum,
                             lambda: invoke(**values), actual)

    def _chat(self, **values):
        return self._text('chat.completions.create', self._client.chat.completions.create, values)

    def _responses(self, **values):
        return self._text('responses.create', self._client.responses.create, values)

    def _images(self, **values):
        values = deepcopy(values)
        model = values.get('model')
        if model not in IMAGE_RATES or set(values) - {'model', 'prompt', 'n', 'size', 'quality', 'output_format'}:
            raise TrialDenied('This image operation is not configured for the AI trial.')
        prompt = values.get('prompt')
        if not isinstance(prompt, str) or not 1 <= len(prompt.encode()) <= 8000:
            raise TrialDenied('Use a shorter description for this image.')
        if values.get('n', 1) != 1 or values.get('size', '1024x1024') != '1024x1024':
            raise TrialDenied('The AI trial creates one 1024px picture at a time.')
        if values.get('quality') not in (None, 'medium'):
            raise TrialDenied('The AI trial uses medium image quality.')
        values.update(n=1, size='1024x1024', quality='medium')
        # Published 1024px medium GPT Image 2 output is $0.053. Reserve
        # $0.06 output plus the byte-bounded prompt; settle real token usage.
        maximum = 60_000 + _tokens_cost(len(prompt.encode()) + 512, 0, IMAGE_RATES[model])
        return provider_call(self._config, 'openai.images.generate', values, maximum,
            lambda: self._client.images.generate(**values), lambda result: _image_usage(result, IMAGE_RATES[model]))

    def _transcription(self, **values):
        if values.get('model') not in TRANSCRIPTION_MODELS or set(values) - {'model', 'file', 'prompt', 'language', 'response_format', 'timestamp_granularities'}:
            raise TrialDenied('This transcription is not configured for the AI trial.')
        file = values.get('file')
        if not hasattr(file, 'read') or not hasattr(file, 'seek'):
            raise TrialDenied('Use an uploaded recording for transcription.')
        offset = file.tell()
        data = file.read(MAX_AUDIO_BYTES + 1)
        file.seek(offset)
        if len(data) > MAX_AUDIO_BYTES:
            raise TrialDenied('That recording is too large for the trial.')
        from .speech_provider import audio_info
        duration = audio_info(Path(file.name))
        if len(str(values.get('prompt', '')).encode()) > 2000:
            raise TrialDenied('The transcription prompt is too long.')
        # Conservative $0.02/min ceiling, above all configured STT rates.
        maximum = math.ceil(duration / 60 * 20_000) + len(str(values.get('prompt', '')).encode()) * 5 + 1000
        digest = {key: item for key, item in values.items() if key != 'file'}
        digest['audio_sha256'] = hashlib.sha256(data).hexdigest()
        return provider_call(self._config, 'openai.audio.transcriptions', digest, maximum,
                             lambda: self._client.audio.transcriptions.create(**values))

    def close(self):
        return self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def openai_client(*, config=None, factory=None, **options):
    import openai
    config = config_snapshot(config)
    if trial_enabled(config):
        options['max_retries'] = 0
        if options.get('base_url') not in (None, 'https://api.openai.com/v1'):
            raise TrialDenied('Use the configured OpenAI endpoint for the trial.')
        # Ignore OPENAI_BASE_URL from process environment for sponsored calls.
        options['base_url'] = 'https://api.openai.com/v1'
    client = (factory or openai.OpenAI)(**options)
    return TrialOpenAI(client, config) if trial_enabled(config) else client


def elevenlabs_call(config, text, model, voice_id, invoke):
    config = config_snapshot(config)
    if not trial_enabled(config):
        return invoke()
    if model not in ('eleven_multilingual_v2', 'eleven_v3', 'eleven_turbo_v2_5', 'eleven_flash_v2_5'):
        logger.warning('AI trial audio request denied: voice model is not supported')
        raise TrialDenied('Audio playback is currently unavailable. Please try again later.')
    if not isinstance(text, str) or not 1 <= len(text) <= 3000:
        raise TrialDenied('Use at most 3,000 characters for one recording.')
    # $0.20/1K chars conservatively covers current $0.10 v2/v3 pricing.
    return provider_call(config, 'elevenlabs.tts', {'text': text, 'model': model, 'voice': voice_id},
                         len(text) * 200, invoke)


def mai_call(config, path, model, options, invoke):
    config = config_snapshot(config)
    if not trial_enabled(config):
        return invoke()
    if model != 'microsoft/mai-transcribe-2':
        raise TrialDenied('This transcription model is not configured for the AI trial.')
    from .speech_provider import audio_info
    path = Path(path)
    if path.stat().st_size > MAX_AUDIO_BYTES:
        raise TrialDenied('That recording is too large for the trial.')
    duration = audio_info(path)
    # $0.20/hour ceiling includes headroom over the published $0.10/hour.
    maximum = math.ceil(duration / 3600 * 200_000) + 1000
    return provider_call(config, 'openrouter.transcription', {'model': model, 'options': options,
        'audio_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}, maximum, invoke)


def yandex_call(config, text, target_language, invoke):
    config = config_snapshot(config)
    if not trial_enabled(config):
        return invoke()
    if not isinstance(text, str) or not 1 <= len(text) <= 3000:
        raise TrialDenied('Use at most 3,000 characters for one translation.')
    # $100/million-character allowance ceiling; no cloud credit assumptions.
    return provider_call(config, 'yandex.translate', {'text': text, 'target': target_language},
                         len(text) * 100, invoke)
