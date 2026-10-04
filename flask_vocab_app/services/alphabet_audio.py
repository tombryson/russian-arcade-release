"""Exact packaged alphabet recordings; playback never calls a provider."""
from functools import lru_cache
import json
from pathlib import Path
import re

CONTENT = Path(__file__).resolve().parents[1] / 'ui' / 'src' / 'alphabet-data.json'
PREFIX = '/static/audio/alphabet-v1/'


@lru_cache(maxsize=1)
def public_recordings():
    """Use the same published URLs as the alphabet interface."""
    letters = json.loads(CONTENT.read_text(encoding='utf-8'))
    if not isinstance(letters, list) or len(letters) != 33:
        raise ValueError('The alphabet needs its 33 published entries.')
    paths = set()
    for letter in letters:
        for field in ('nameAudio', 'exampleAudio'):
            path = letter.get(field)
            if not isinstance(path, str) or not re.fullmatch(re.escape(PREFIX) + r'[a-z0-9-]+\.mp3', path):
                raise ValueError('Alphabet audio needs an exact packaged recording URL.')
            if path in paths:
                raise ValueError('Alphabet recording URLs must be unique.')
            paths.add(path)
    return frozenset(paths)


def is_public_alphabet_recording(filename):
    if not filename.startswith('audio/alphabet-v1/'):
        return False
    return '/static/' + filename in public_recordings()
