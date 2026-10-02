"""Versioned authored sequence assets. Reading never allocates learner work.

These sources remain diagnostic drafts until their release checks are recorded.
An asset hash pins its complete server-side content, including private keys.
Callers must build a learner projection before returning content to a browser.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from contracts.curriculum import freeze_task_contract
from services.curriculum_requirement_map import content_digest

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
SEQUENCE_ID = 'location-destination-sequence-v1'
UNIT_ID = 'location-destination-v2'
ASSET_KINDS = {'teaching', 'choice', 'controlled_text', 'reading', 'listening', 'writing', 'speaking', 'task_group'}
ADAPTER_KINDS = {'teaching': 'teaching', 'unit_practice': 'choice', 'unit_forms': 'controlled_text',
                 'comprehension': 'reading', 'unit_listening': 'listening', 'writing': 'writing',
                 'unit_exchange': 'speaking', 'task_group': 'task_group'}
_ID = re.compile(r'[a-z][a-z0-9-]{0,99}')


def is_public_teaching_recording(filename):
    """Only exact bundled teaching clips can play without a learner profile."""
    if not re.fullmatch(r'audio/course/curriculum/location-destination-sequence-v1/[0-9a-f]{64}\.mp3', filename):
        return False
    try:
        teaching = load_asset('location-teaching-v2')
        clips = [example.get('audio', {}) for group in teaching['content']['groups'] for example in group['examples']]
        expected = next((clip for clip in clips if clip.get('url') == '/static/' + filename), None)
        if expected is None:
            return False
        data = (DATA_DIR.parent / 'static' / filename).read_bytes()
        return len(data) == expected['size_bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256']
    except (LookupError, OSError, ValueError, KeyError, TypeError):
        return False


def _read(directory, identity):
    if not isinstance(identity, str) or not _ID.fullmatch(identity):
        raise ValueError('Use an authored content identity.')
    path = DATA_DIR / directory / (identity + '.json')
    if not path.is_file():
        raise LookupError('Authored content not found.')
    return json.loads(path.read_text(encoding='utf-8'))


def _validate_exchange(asset):
    turns = asset['content'].get('turns')
    if not isinstance(turns, list) or [t['id'] for t in turns] != ['location', 'destination']:
        raise ValueError('The unit exchange needs both authored turns.')
    mapping = asset['content'].get('criterion_turns')
    criteria = {criterion['id'] for criterion in asset['criteria']}
    turn_ids = {turn['id'] for turn in turns}
    if (not isinstance(mapping, dict) or set(mapping) != criteria
            or any(not isinstance(ids, list) or not ids
                   or any(not isinstance(identity, str) or identity not in turn_ids for identity in ids)
                   or len(set(ids)) != len(ids) for ids in mapping.values())):
        raise ValueError('Every Speaking criterion must name its distinct authored response turns.')


def load_asset(content_id):
    asset = _read('curriculum_sequence_assets', content_id)
    if (asset.get('schema_version') != 1 or asset.get('id') != content_id
            or asset.get('version') != content_id or asset.get('unit_id') != UNIT_ID
            or asset.get('kind') not in ASSET_KINDS or asset.get('level') != 'A1'
            or asset.get('topic_id') != 'places' or asset.get('status') not in ('draft', 'reviewed', 'released')
            or not isinstance(asset.get('content'), dict) or not asset['content']
            or not isinstance(asset.get('criteria'), list)):
        raise ValueError('The authored asset identity or scope is invalid.')
    if asset['kind'] in ('choice', 'controlled_text', 'listening'):
        items = asset['content'].get('items')
        if (not isinstance(items, list) or not items or len({i['id'] for i in items}) != len(items)
                or {i['id'] for i in items} != {c['id'] for c in asset['criteria']}):
            raise ValueError('Authored questions need exactly matching criteria.')
        for item in items:
            for name in ('hint_ru', 'explanation_ru'):
                if not isinstance(item.get(name), str) or not item[name].strip():
                    raise ValueError('Authored practice needs Russian hints and feedback.')
            if 'prompt_ru' in item and (not isinstance(item['prompt_ru'], str) or not item['prompt_ru'].strip()):
                raise ValueError('Localized practice prompts must contain text.')
            if item['type'] == 'controlled_text':
                if item['answer'] not in item['accepted_answers']:
                    raise ValueError('The model answer must be accepted.')
            else:
                choices = item['choices']
                if len({c['id'] for c in choices}) != len(choices) or item['answer'] not in {c['id'] for c in choices}:
                    raise ValueError('An authored choice needs one named answer.')
            task_contract(asset, 'validation:' + content_id + ':' + item['id'], item_id=item['id'])
    elif asset['kind'] == 'reading':
        reading_contracts(asset, 'validation:' + content_id)
    elif asset['kind'] in ('writing', 'speaking'):
        task_contract(asset, 'validation:' + content_id)
    elif asset['criteria']:
        raise ValueError('Teaching and task groups cannot manufacture assessed criteria.')
    return deepcopy(asset)


def pack_item(asset, item_id):
    """Return only fields understood by the existing owned practice player."""
    found = [item for item in asset['content'].get('items', []) if item['id'] == item_id]
    if len(found) != 1:
        raise LookupError('Authored item not found.')
    item = found[0]
    fields = ('id', 'type', 'prompt', 'answer', 'hint')
    fields += ('accepted_answers',) if item['type'] == 'controlled_text' else ('choices',)
    if item['type'] == 'listening_choice':
        fields += ('transcript', 'audio')
    return deepcopy({field: item[field] for field in fields})


def _spec(asset, task_id, purpose, content, criteria, *, activity, rubric, support=None):
    return {'schema_version': 2, 'contract_version': 'curriculum-task-v2',
            'reference_version': 'torfl-reference-v1', 'task_id': task_id, 'activity': activity,
            'content_version': asset['id'], 'level': asset['level'], 'topic_ids': [asset['topic_id']],
            'purpose': purpose, 'content': deepcopy(content), 'rubric_version': rubric,
            'support': deepcopy(support or asset['support']), 'criteria': deepcopy(criteria)}


def task_contract(asset, task_id, purpose='practice', item_id=None):
    """Freeze the exact owned task; this grants neither rewards nor access."""
    if item_id is not None:
        item = pack_item(asset, item_id)
        original = next(i for i in asset['content']['items'] if i['id'] == item_id)
        criteria = [c for c in asset['criteria'] if c['id'] == item_id]
        rubric = ('authored-controlled-form-v1' if item['type'] == 'controlled_text' else
                  'authored-listening-choice-v1' if item['type'] == 'listening_choice' else 'authored-choice-v1')
        content = {'item': item, 'explanation': original['explanation'], 'unit_id': asset['unit_id']}
        # Localized display text belongs beside the immutable player item. Its
        # answer, scoring fields and published pack bytes remain unchanged.
        if original.get('explanation_ru'):
            content['explanation_ru'] = original['explanation_ru']
        localized = {name: original[name + '_ru'] for name in ('hint', 'prompt') if original.get(name + '_ru')}
        if localized:
            content['item_locale_ru'] = localized
        if asset.get('title_ru'):
            content['title_ru'] = asset['title_ru']
        return freeze_task_contract(_spec(asset, task_id, purpose, content, criteria,
                                          activity='curriculum_unit', rubric=rubric))
    if asset['kind'] not in ('writing', 'speaking'):
        raise ValueError('Use per-item contracts or reading_contracts for this activity.')
    if asset['kind'] == 'speaking':
        _validate_exchange(asset)
    content = deepcopy(asset['content'])
    content.update(unit_id=asset['unit_id'], sequence_asset_id=asset['id'])
    return freeze_task_contract(_spec(asset, task_id, purpose, content, asset['criteria'],
        activity='writing' if asset['kind'] == 'writing' else 'speaking', rubric='unit-original-production-v1'))


def reading_contracts(asset, task_id, purpose='practice'):
    if asset['kind'] != 'reading':
        raise ValueError('Expected an authored reading task.')
    rows = asset['content'].get('questions')
    text = asset['content'].get('passage')
    if not isinstance(text, str) or not text.strip() or not isinstance(rows, list) or len(rows) != 3:
        raise ValueError('This authored reading format needs a passage and three questions.')
    questions = [q['prompt'] for q in rows]
    if len(set(questions)) != len(questions) or any(not q.strip() for q in questions):
        raise ValueError('Reading questions must be distinct and nonempty.')
    if {c['id'] for c in asset['criteria']} != {q['id'] for q in rows}:
        raise ValueError('Reading questions and criteria must match exactly.')
    output = {}
    for index, question in enumerate(rows):
        content = {'text': text, 'questions': questions, 'question_index': index,
                   'expected_answer': question['expected_answer'], 'requested_topic': asset['topic_id'],
                   'topic_id': asset['topic_id'], 'sequence_asset_id': asset['id'], 'unit_id': asset['unit_id']}
        criteria = [c for c in asset['criteria'] if c['id'] == question['id']]
        output[str(index)] = freeze_task_contract(_spec(asset, task_id + ':' + str(index), purpose, content,
            criteria, activity='comprehension', rubric='authored-reading-message-v1'))
    return output


def load_manifest(sequence_id=SEQUENCE_ID):
    manifest = _read('curriculum_sequences', sequence_id)
    if (manifest.get('schema_version') != 1 or manifest.get('id') != SEQUENCE_ID
            or sequence_id != SEQUENCE_ID or manifest.get('unit_id') != UNIT_ID
            or manifest.get('level') != 'A1' or manifest.get('topic_id') != 'places'
            or manifest.get('completion_policy') != 'responses-reviewed-v1'):
        raise ValueError('Unknown lesson sequence or completion policy.')
    ids = set()
    from services.curriculum_units import get_unit
    if manifest.get('next_unit_id'):
        get_unit(manifest['next_unit_id'])
    for step in manifest['steps']:
        if step['id'] in ids:
            raise ValueError('Duplicate sequence step.')
        ids.add(step['id'])
        asset = load_asset(step['content_id'])
        if ADAPTER_KINDS.get(step['adapter']) != asset['kind']:
            raise ValueError('The sequence adapter must match its authored content kind.')
        if step['content_sha256'] != content_digest(asset):
            raise ValueError('Sequence asset changed; publish and pin a new version.')
        if step['requirement_ids'] != sorted({c['requirement_id'] for c in asset['criteria']}):
            raise ValueError('Step requirements do not match its authored criteria.')
        expected_policy = 'unit-transfer-no-effects-v1' if step['id'] == 'transfer' else 'existing-activity-effects-v1'
        if step['effects_policy'] != expected_policy:
            raise ValueError('Sequence effects policy changed.')
    paths = manifest.get('completion_paths')
    if (not isinstance(paths, dict) or set(paths) != {'guided', 'challenge'}
            or paths['challenge'] != ['transfer'] or set(paths['guided']) != ids - {'learn'}
            or len(paths['guided']) != len(set(paths['guided']))):
        raise ValueError('Completion paths must name required response steps.')
    group = load_asset(next(s['content_id'] for s in manifest['steps'] if s['id'] == 'transfer'))
    if [{k: f[k] for k in ('id', 'exposure_family_id', 'task_ids')} for f in manifest['transfer_families']] != group['content']['families']:
        raise ValueError('Transfer family identities changed.')
    for family in manifest['transfer_families']:
        if (len(family['task_ids']) != 5 or len(set(family['task_ids'])) != 5
                or {load_asset(identity)['kind'] for identity in family['task_ids']}
                != {'reading', 'listening', 'writing', 'speaking', 'controlled_text'}):
            raise ValueError('Each transfer family needs distinct tasks across the five domains.')
        if set(family['content_hashes']) != set(family['task_ids']):
            raise ValueError('Every transfer task needs a content pin.')
        for identity in family['task_ids']:
            if content_digest(load_asset(identity)) != family['content_hashes'][identity]:
                raise ValueError('Transfer content changed; retain the exposed version.')
    return deepcopy(manifest)


def media_inventory(asset):
    """Describe prepared files truthfully; never invoke a provider or backfill."""
    rows = []
    content = asset['content']
    candidates = content.get('items', []) + content.get('turns', [])
    candidates += [example for group in content.get('groups', []) for example in group.get('examples', [])]
    if content.get('closing'):
        candidates += [content['closing']]
    seen = set()
    for item in candidates:
        key = item.get('audio_key')
        if not key or key in seen:
            continue
        seen.add(key)
        audio = item.get('audio')
        valid = False
        if isinstance(audio, dict) and isinstance(audio.get('url'), str) and audio['url'].startswith('/static/audio/course/'):
            root = (DATA_DIR.parent / 'static/audio/course').resolve()
            path = DATA_DIR.parent / audio['url'].lstrip('/')
            valid = (path.resolve().is_relative_to(root) and path.is_file() and not path.is_symlink() and
                     hashlib.sha256(path.read_bytes()).hexdigest() == audio.get('sha256'))
        rows.append({'id': key, 'status': 'verified' if valid else 'unavailable',
                     'text': item.get('transcript', item.get('prompt', item.get('text', item.get('ru', '')))),
                     'audio': deepcopy(audio)})
    return rows
