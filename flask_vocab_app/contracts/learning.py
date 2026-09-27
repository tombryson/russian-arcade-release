"""Small, strict content schema for the first deck and deterministic test activity.

Card text is plain text, never trusted HTML. Publishing is a separate operation.
"""
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from repositories.learning_repository import LearningError


def reject(message):
    raise LearningError('invalid_input', message)


def text(value, label, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\x00' in value:
        reject(f'{label} must contain 1–{maximum} characters.')
    return value.strip()


def key(value, label='ID'):
    cleaned = text(value, label, 100)
    if cleaned != value:
        reject(f'{label} cannot have surrounding whitespace.')
    value = cleaned
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*', value):
        reject(f'{label} has an invalid format.')
    return value


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        reject('The submitted fields do not match this operation.')
    return value


def revision(value):
    if type(value) is not int or value < 0:
        reject('A non-negative integer revision is required.')
    return value


def timezone(value):
    value = text(value, 'Study timezone', 80)
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        reject('Choose a valid IANA study timezone, such as Australia/Melbourne.')
    return value


def normalize_controlled_text(value):
    """Authored form matching: retain words/endings, tolerate presentation."""
    return ' '.join(unicodedata.normalize('NFC', value).casefold().replace('ё', 'е').split()).rstrip('.!?…').rstrip()


def assess_activity_answer(item, answer):
    """Validate the issued response mode and retain the exact learner text."""
    if item['type'] == 'controlled_text':
        fields(answer, {'text'})
        text(answer['text'], 'Your answer', 200)
        return answer['text'], normalize_controlled_text(answer['text']) in {
            normalize_controlled_text(value) for value in item['accepted_answers']}
    fields(answer, {'choice_id'})
    key(answer['choice_id'], 'Choice ID')
    choice = next((choice for choice in item['choices'] if choice['id'] == answer['choice_id']), None)
    if choice is None:
        reject('Choose one of the issued answers.')
    return choice['text'], answer['choice_id'] == item['answer']


def activity_answer_text(item):
    return item['answer'] if item['type'] == 'controlled_text' else next(
        choice['text'] for choice in item['choices'] if choice['id'] == item['answer'])


def validate_pack(pack):
    if isinstance(pack, dict) and type(pack.get('schema_version')) is int and pack['schema_version'] == 2:
        from contracts.flashcards import validate_deck
        return validate_deck(pack)
    fields(pack, {'schema_version','id','kind','title','source','items'})
    if type(pack['schema_version']) is not int or pack['schema_version'] != 1:
        reject('Unsupported content schema version.')
    key(pack['id'], 'Content ID')
    text(pack['title'], 'Title', 120)
    text(pack['source'], 'Source', 500)
    if pack['kind'] not in ('deck','activity'):
        reject('Content must be a deck or activity.')
    if not isinstance(pack['items'], list) or not 1 <= len(pack['items']) <= 100:
        reject('A pack needs between 1 and 100 items.')
    seen = set()
    for item in pack['items']:
        fields(item, {'id','type','prompt','answer'}, {'word_id','hint','asset_ids','direction','choices','accepted_answers','audio','transcript'})
        item_id = key(item['id'], 'Item ID')
        if item_id in seen:
            reject('Item IDs must be unique within a pack.')
        seen.add(item_id)
        text(item['prompt'], 'Prompt')
        if item['type'] == 'listening_choice':
            if pack['kind'] != 'activity' or 'word_id' in item or 'asset_ids' in item:
                reject('Listening questions cannot use card or recall metadata.')
            text(item.get('transcript'), 'Transcript', 4000)
            audio = fields(item.get('audio'), {'url', 'sha256', 'duration_ms'})
            if not isinstance(audio['url'], str) or not re.fullmatch(r'/static/audio/course/curriculum/[a-z0-9-]+/[a-z0-9-]+\.mp3', audio['url']):
                reject('Listening audio must use a bundled curriculum recording.')
            if not isinstance(audio['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', audio['sha256']):
                reject('Listening audio needs its immutable file hash.')
            if type(audio['duration_ms']) is not int or not 1000 <= audio['duration_ms'] <= 180000:
                reject('Listening audio must last 1–180 seconds.')
        elif 'audio' in item or 'transcript' in item:
            reject('Only listening questions can contain audio and a transcript.')
        if 'hint' in item:
            text(item['hint'], 'Hint')
        if 'word_id' in item and (type(item['word_id']) is not int or item['word_id'] < 1):
            reject('Vocabulary links must be positive integer IDs.')
        assets = item.get('asset_ids', [])
        if not isinstance(assets, list) or len(assets) > 4 or len(set(map(str, assets))) != len(assets):
            reject('Use at most four distinct asset IDs.')
        for asset in assets:
            key(asset, 'Asset ID')
        if pack['kind'] == 'deck':
            if item['type'] not in ('basic','cloze') or 'choices' in item or 'accepted_answers' in item:
                reject('Decks support basic and single-target cloze cards.')
            if item.get('direction') not in ('ru-en','en-ru'):
                reject('Cards require an explicit ru-en or en-ru direction.')
            text(item['answer'], 'Answer')
            if item['type'] == 'cloze' and item['prompt'].count('[[blank]]') != 1:
                reject('A cloze prompt needs exactly one [[blank]] marker.')
        else:
            if item['type'] == 'controlled_text':
                if 'direction' in item or 'choices' in item or 'word_id' in item:
                    reject('Controlled form practice cannot use choice or recall metadata.')
                text(item['answer'], 'Answer', 200)
                accepted = item.get('accepted_answers')
                if not isinstance(accepted, list) or not 1 <= len(accepted) <= 8:
                    reject('Controlled form practice needs 1–8 authored answers.')
                for value in accepted:
                    text(value, 'Accepted answer', 200)
                    if not re.search('[А-Яа-яЁё]', value):
                        reject('Controlled form answers must contain Russian text.')
                normalized = {normalize_controlled_text(value) for value in accepted}
                if len(normalized) != len(accepted) or normalize_controlled_text(item['answer']) not in normalized:
                    reject('Authored variants must be distinct and include the displayed answer.')
                continue
            if item['type'] not in ('choice', 'listening_choice') or 'direction' in item or 'accepted_answers' in item:
                reject('Activities support reviewed choice questions and authored form practice.')
            choices = item.get('choices')
            if not isinstance(choices, list) or not 2 <= len(choices) <= 6:
                reject('A choice question needs 2–6 choices.')
            ids, labels = set(), set()
            for choice in choices:
                fields(choice, {'id','text'})
                cid, label = key(choice['id']), text(choice['text'], 'Choice', 200)
                if cid in ids or label in labels:
                    reject('Choice IDs and labels must be distinct.')
                ids.add(cid)
                labels.add(label)
            if not isinstance(item['answer'], str) or item['answer'] not in ids:
                reject('The answer must reference an offered choice ID.')
    return pack
