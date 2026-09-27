"""Check configured providers without printing credentials or changing study data.

Run with --generate for small billable text, image and speech smoke tests.
Google refreshes are in-memory; this command never replaces credential files.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import pickle
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask_vocab_app'))
import config
import requests
from openai import OpenAI


def probe(name, operation):
    try:
        detail = operation()
        return {'provider': name, 'ok': True, 'detail': detail}
    except Exception as exc:
        result = {'provider': name, 'ok': False, 'error': type(exc).__name__}
        status = getattr(exc, 'status_code', None)
        if status is None and getattr(exc, 'response', None) is not None:
            status = exc.response.status_code
        if status is not None:
            result['http_status'] = status
        # Provider exception messages can echo keys. Return only known OAuth codes.
        for arg in exc.args:
            if isinstance(arg, dict) and arg.get('error') in ('invalid_grant', 'invalid_client'):
                result['oauth_error'] = arg['error']
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate', action='store_true')
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    client = OpenAI(api_key=config.OPENAI_API_KEY or 'missing', timeout=60, max_retries=0)

    def models():
        available = {m.id for m in client.models.list()}
        return {m: m in available for m in (config.OPENAI_MODEL_STORY, config.OPENAI_MODEL_FLASHCARDS, config.OPENAI_MODEL_HIGH,
                                           config.OPENAI_MODEL_FAST, config.OPENAI_IMAGE_MODEL)}

    def voices():
        r = requests.get('https://api.elevenlabs.io/v1/voices',
                         headers={'xi-api-key': config.ELEVENLABS_API_KEY}, timeout=20)
        r.raise_for_status()
        available = {v['voice_id'] for v in r.json().get('voices', [])}
        return {'configured_voices_available': {voice: voice in available for voice in config.ELEVENLABS_VOICE_IDS}}

    def yandex():
        r = requests.post('https://translate.api.cloud.yandex.net/translate/v2/translate',
                          headers={'Authorization': 'Api-Key ' + config.YANDEX_API_KEY},
                          json={'texts': ['кот'], 'sourceLanguageCode': 'ru', 'targetLanguageCode': 'en'}, timeout=20)
        r.raise_for_status()
        assert r.json()['translations'][0]['text']
        return 'Translation succeeded'

    def anki():
        r = requests.post(config.ANKI_CONNECT_URL, json={'action': 'version', 'version': 6}, timeout=5)
        r.raise_for_status()
        payload = r.json()
        if payload.get('error') or not isinstance(payload.get('result'), int) or payload['result'] < 6:
            raise ValueError('AnkiConnect version 6 required')
        return {'version': payload['result']}

    def drive():
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        settings = config.app_config()
        with open(settings['GOOGLE_DRIVE_TOKEN_FILE'], 'rb') as stream:
            credentials = pickle.load(stream)
        if not credentials.valid:
            credentials.refresh(Request())
        service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
        service.files().get(fileId=settings['GOOGLE_DRIVE_FILE_ID'], fields='id').execute()
        return 'Configured vocabulary file accessible'

    def text(model):
        r = client.responses.create(model=model, input='Translate кот into English. Return one word.',
                                    reasoning={'effort': 'low'}, max_output_tokens=1024, store=False)
        if 'cat' not in r.output_text.lower():
            raise ValueError('Unexpected translation')
        return 'Text generation succeeded'

    def card():
        from services.openai_service import OpenAIService
        value = OpenAIService(config.OPENAI_API_KEY).generate_native_card({'lemma': 'ключ', 'form': 'ключ'}, 'ru-en')
        if not all(isinstance(value.get(k), str) and value[k].strip() for k in ('english', 'sentence', 'sentence_english')):
            raise ValueError('Incomplete card')
        return 'Structured card generation succeeded'

    def image():
        r = client.images.generate(model=config.OPENAI_IMAGE_MODEL, prompt='A small red circle on white.',
                                   size='1024x1024', quality='low', n=1)
        if not (r.data[0].b64_json or r.data[0].url):
            raise ValueError('Missing image')
        return 'Image generation succeeded'

    def audio():
        from services.elevenlabs_service import ElevenLabsService
        with tempfile.TemporaryDirectory() as directory:
            if not ElevenLabsService(config.ELEVENLABS_API_KEY, directory).generate_audio('Привет! Это кот.', 'test.mp3'):
                raise ValueError('Audio generation failed')
        return 'Russian audio generated and decoded'

    checks = [('OpenAI models', models), ('ElevenLabs voices', voices), ('Yandex Cloud', yandex),
              ('AnkiConnect', anki), ('Google Drive', drive)]
    if args.generate:
        checks += [('Astra text', lambda: text(config.OPENAI_MODEL_STORY)),
                   ('Fast text', lambda: text(config.OPENAI_MODEL_FAST)), ('Flashcard', card),
                   ('Image', image), ('Russian audio', audio)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda item: probe(*item), checks))
    print(json.dumps(results, indent=2))
    return int(any(not result['ok'] for result in results))


if __name__ == '__main__':
    raise SystemExit(main())
