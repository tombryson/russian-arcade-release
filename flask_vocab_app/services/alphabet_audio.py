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
        if not isinstance(letter, dict) or not isinstance(letter.get('id'), str) or not re.fullmatch(r'[a-z][a-z0-9-]*', letter['id']):
            raise ValueError('Alphabet audio needs a valid letter identity.')
        for field, kind in (('nameAudio', 'name'), ('exampleAudio', 'word')):
            variants = letter.get(field)
            if not isinstance(variants, dict) or set(variants) != {'female', 'male'}:
                raise ValueError('Alphabet audio needs both published voices.')
            for voice, path in variants.items():
                expected = PREFIX + ('male/' if voice == 'male' else '') + letter['id'] + '-' + kind + '.mp3'
                if path != expected:
                    raise ValueError('Alphabet audio needs an exact packaged recording URL.')
                if path in paths:
                    raise ValueError('Alphabet recording URLs must be unique.')
                paths.add(path)
        ipa, sounds = letter.get('soundIpa'), letter.get('soundAudio')
        if letter['id'] in ('hard-sign', 'soft-sign'):
            if 'soundIpa' not in letter or 'soundAudio' not in letter or ipa is not None or sounds is not None:
                raise ValueError('Hard and soft signs have no independent sound recording.')
            continue
        if (not isinstance(ipa, str) or not re.fullmatch(r'[a-zɡɨɫʂʐɕɛʲː͡]{1,12}', ipa)
                or not isinstance(sounds, dict) or set(sounds) != {'female', 'male'}):
            raise ValueError('Alphabet sounds need IPA and both published voices.')
        for voice, path in sounds.items():
            expected = PREFIX + 'sounds/' + voice + '/' + letter['id'] + '-sound.mp3'
            if path != expected:
                raise ValueError('Alphabet sounds need an exact packaged recording URL.')
            paths.add(path)
    if len(paths) != 194:
        raise ValueError('The alphabet needs its 194 distinct published recordings.')
    return frozenset(paths)


def is_public_alphabet_recording(filename):
    if not filename.startswith('audio/alphabet-v1/'):
        return False
    return '/static/' + filename in public_recordings()
