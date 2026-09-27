"""Shared provider adapters for the older standalone Anki utilities."""
import base64
from functools import lru_cache
from pathlib import Path
import sys
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask_vocab_app'))
from config import OPENAI_API_KEY, ELEVENLABS_API_KEY, MEDIA_DIR
from services.openai_service import OpenAIService
from services.elevenlabs_service import ElevenLabsService

@lru_cache(maxsize=1)
def provider():
    return OpenAIService(OPENAI_API_KEY)

_sentences = {}

@lru_cache(maxsize=256)
def card(word):
    result = provider().generate_native_card({'lemma': word, 'form': word}, 'ru-cloze')
    _sentences[result['sentence']] = result
    return result

def sentence(word):
    return card(word)['sentence']

def meaning(word, context):
    return (_sentences[context] if context in _sentences else card(word))['english']

def translation(text):
    if text not in _sentences:
        raise ValueError('Generate the sentence through the shared card provider first.')
    return _sentences[text]['sentence_english']

def image(sentence, word):
    return provider().generate_image_url(sentence, word)

def audio(text, filename, directory=MEDIA_DIR):
    return ElevenLabsService(ELEVENLABS_API_KEY, directory).generate_audio(text, filename)

def download(url, filename, directory=MEDIA_DIR):
    if not url:
        return None
    path = Path(directory) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith('data:image/'):
        content = base64.b64decode(url.split(',', 1)[1], validate=True)
    else:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        content = response.content
    path.write_bytes(content)
    return path.name
