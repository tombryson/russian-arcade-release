"""Authored introductory speech. Playback never makes a provider request."""
from functools import lru_cache
import json
from pathlib import Path
import re

INTRO_SPEECH = {
    'word-hello': {'word_display': 'Приве́т!', 'audio_text': 'Привет!',
                   'reading_help': 'Stress the second syllable: при-ВЕТ. The Russian letter в sounds like v.'},
    'word-letter': {'word_display': 'письмо́', 'audio_text': 'Письмо.',
                    'reading_help': 'Stress the final syllable. The soft sign ь has no sound of its own; it softens the consonant before it.'},
    'word-thanks': {'word_display': 'Спаси́бо!', 'audio_text': 'Спасибо!',
                    'reading_help': 'Stress си: спа-СИ-бо. Listen to the last vowel; an unstressed Russian о sounds different from a stressed о.'},
}
PREFIX = '/static/audio/first-steps-v2/'
RECORDING_REVISIONS = {'word-letter': 'hello-word-letter-r2.mp3'}
CONTENT = Path(__file__).resolve().parents[1] / 'data' / 'first_steps_v2.json'


def intro_speech(question_id):
    speech = INTRO_SPEECH.get(question_id)
    filename = RECORDING_REVISIONS.get(question_id, 'hello-' + question_id + '.mp3')
    return {**speech, 'audio_url': PREFIX + filename} if speech else {}


@lru_cache(maxsize=1)
def authored_clips():
    """Exact published URLs, used by preparation and the public asset guard."""
    clips = {intro_speech(qid)['audio_url']: item['audio_text'] for qid, item in INTRO_SPEECH.items()}
    content = json.loads(CONTENT.read_text(encoding='utf-8'))
    for lesson in content['lessons']:
        for item in [*lesson['teaching'], *lesson['questions']]:
            if not item.get('audio_url'):
                continue
            url, text = item['audio_url'], item.get('audio_text')
            if not re.fullmatch(re.escape(PREFIX) + r'[a-z0-9-]+\.mp3', url) or not isinstance(text, str) or not text.strip():
                raise ValueError('Introductory audio needs a fixed public path and authored text.')
            if url in clips and clips[url] != text:
                raise ValueError('A recording URL cannot name two different utterances.')
            clips[url] = text
    return clips


def is_public_recording(filename):
    return '/static/' + filename in authored_clips()
