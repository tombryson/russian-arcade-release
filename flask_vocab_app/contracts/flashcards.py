"""Card-specific senses and contexts, never a single translation on a word."""
from contracts.learning import fields, key, text, reject
from repositories.learning_repository import payload_hash


def validate_deck(pack):
    fields(pack, {'schema_version','id','kind','title','source','items'}, {'title_ru'})
    if pack['schema_version'] != 2 or pack['kind'] != 'deck':
        reject('Schema 2 describes a flashcard deck.')
    key(pack['id']); text(pack['title'], 'Title', 120); text(pack['source'], 'Source', 500)
    if 'title_ru' in pack:
        text(pack['title_ru'], 'Russian title', 120)
    if not isinstance(pack['items'], list) or not 1 <= len(pack['items']) <= 100:
        reject('A deck needs 1–100 cards.')
    seen, cards = set(), set()
    for item in pack['items']:
        fields(item, {'id','card_id','word_id','type','direction','sense_key','sense_label','context','prompt','answer'},
               {'form_id','sense_label_ru','cue_en','context_meaning','explanation','explanation_ru','hint','assets','topic','difficulty','metadata'})
        for name in ('id','card_id','sense_key'):
            key(item[name], name)
        if item['id'] in seen or item['card_id'] in cards:
            reject('Item IDs and card IDs must be distinct in a deck.')
        seen.add(item['id']); cards.add(item['card_id'])
        if type(item['word_id']) is not int or item['word_id'] < 1:
            reject('Choose a vocabulary word for this card.')
        if 'form_id' in item and (type(item['form_id']) is not int or item['form_id'] < 1):
            reject('Choose a valid target form.')
        for name in ('sense_label','context','prompt','answer'):
            text(item[name], name, 2000 if name != 'sense_label' else 160)
        for name in ('sense_label_ru','cue_en','context_meaning','explanation','explanation_ru','hint','topic'):
            if name in item:
                text(item[name], name, 160 if name in ('sense_label_ru','topic') else 2000)
        if 'difficulty' in item and (type(item['difficulty']) is not int or not 1 <= item['difficulty'] <= 8):
            reject('Difficulty must be between 1 and 8.')
        if item['type'] == 'cloze':
            if item['direction'] != 'ru-cloze' or item['prompt'].count('[[blank]]') != 1:
                reject('A cloze needs one blank and the Russian cloze practice type.')
            if item['prompt'].replace('[[blank]]', item['answer']) != item['context']:
                reject('The answer must restore the exact Russian sentence, including punctuation.')
            if any(c in item['answer'] for c in '.,!?;:«»"\n'):
                reject('Keep sentence punctuation outside the blank.')
            left,right=item['prompt'].split('[[blank]]')
            if (left and left[-1].isalnum()) or (right and right[0].isalnum()):
                reject('Blank a complete word, not part of another word.')
        elif item['type'] != 'basic' or item['direction'] not in ('ru-en','en-ru') or '[[blank]]' in item['prompt']:
            reject('Choose a meaning card, Russian recall card, or single-blank sentence.')
        if 'metadata' in item:
            metadata = fields(item['metadata'], {'pos','grammar','topics'}, {'lemma_difficulty','form_difficulty'})
            text(metadata['pos'], 'Part of speech', 32)
            fields(metadata['grammar'], set(), {'case','number','gender','animacy','tense','person','mood','aspect','voice'})
            for name, value in metadata['grammar'].items():
                text(value, name, 40)
            if not isinstance(metadata['topics'],list) or len(metadata['topics'])>50:
                reject('Choose at most 50 topics.')
            for value in metadata['topics']:
                text(value, 'Topic', 120)
            for name in ('lemma_difficulty','form_difficulty'):
                if name in metadata and (type(metadata[name]) is not int or not 1<=metadata[name]<=8):
                    reject('Difficulty must be between 1 and 8.')
        assets = item.get('assets', [])
        if not isinstance(assets, list) or len(assets) > 4:
            reject('Attach at most four prepared assets.')
        asset_keys, asset_roles, kinds = set(), {}, set()
        for asset in assets:
            fields(asset, {'id','role'}, {'kind'})
            if 'kind' in asset and asset['kind'] not in ('image','word_audio','sentence_audio'):
                reject('Unknown card media kind.')
            key(asset['id'])
            identity = (asset['id'],asset.get('kind'))
            if (asset['role'] not in ('prompt','answer','hint') or identity in asset_keys
                or asset_roles.get(asset['id'],asset['role']) != asset['role']
                or (asset.get('kind') and asset['kind'] in kinds)):
                reject('Give each asset one prompt, answer or hint role.')
            asset_keys.add(identity)
            asset_roles[asset['id']] = asset['role']
            if asset.get('kind'):kinds.add(asset['kind'])
    return pack


def card_item(pack, item):
    """Read v1 packs without rewriting their immutable payloads."""
    if pack['schema_version'] == 2:
        return dict(item)
    card_id = 'v1-' + payload_hash({'pack': pack['id'], 'item': item['id']})[:32]
    mode = 'ru-cloze' if item['type'] == 'cloze' else item['direction']
    return {**item, 'card_id': card_id, 'direction': mode, 'sense_key': card_id,
            'sense_label': pack['title'], 'context': item['prompt'].replace('[[blank]]', item['answer']),
            # Old assets had no reveal role; conservatively put them on the back.
            'assets': [{'id': asset, 'role': 'answer'} for asset in item.get('asset_ids', [])]}


def objective(item):
    return payload_hash({name: item.get(name) for name in
                         ('type','direction','word_id','form_id','sense_key','context','context_meaning','prompt','answer')})


def asset_ids(pack, item):
    return [asset['id'] for asset in item.get('assets', [])] if pack['schema_version'] == 2 else item.get('asset_ids', [])
