#!/usr/bin/env python3
"""Validate authored fixtures and export a blank, provider-free review packet."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))
from contracts.learning import assess_activity_answer
from services.curriculum_units import DATA_DIR, get_unit, _pack, writing_task
from services.curriculum_requirement_map import requirement_index

FIXTURE = ROOT / 'flask_vocab_app/data/curriculum_evaluation/a1-units-review-v1.json'
CURRENT_FIXTURE = ROOT / 'flask_vocab_app/data/curriculum_evaluation/a1-units-review-v3.json'
OUTCOMES = {'satisfied', 'partial', 'not_satisfied', 'insufficient_evidence'}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read_fixture(path=FIXTURE):
    fixture = json.loads(Path(path).read_text(encoding='utf-8'))
    if fixture.get('schema_version') != 1 or fixture.get('reference_version') != 'torfl-reference-v1':
        raise ValueError('Unsupported reviewer fixture version.')
    for unit_id, expected in fixture['unit_sha256'].items():
        if digest((DATA_DIR / (unit_id + '.json')).read_bytes()) != expected:
            raise ValueError('Unit content changed; review the fixtures and issue a new review version: ' + unit_id)
    for listening_id, expected in fixture.get('listening_sha256', {}).items():
        if digest((DATA_DIR / (listening_id + '.json')).read_bytes()) != expected:
            raise ValueError('Listening source changed; issue a new review version: ' + listening_id)
    seen = set()
    for case in fixture['cases']:
        if case['id'] in seen or case['unit_id'] not in fixture['unit_sha256']:
            raise ValueError('Review cases need distinct IDs and a pinned unit.')
        seen.add(case['id'])
        if not isinstance(case['response'], str) or case['author_expectation']['outcome'] not in OUTCOMES:
            raise ValueError('Review cases need raw text and a valid authored expectation.')
        unit = get_unit(case['unit_id'])
        if case['stage'] == 'forms':
            items = {i['id']: i for i in _pack(unit, 'forms')['items']}
            item = items[case['item_id']]
            _, correct = assess_activity_answer(item, {'text': case['response']})
            expected = 'satisfied' if correct else 'not_satisfied'
            if expected != case['author_expectation']['outcome'] or case['support']:
                raise ValueError('Controlled fixture disagrees with the published matcher: ' + case['id'])
        elif case['stage'] == 'writing':
            contract = writing_task(unit)['curriculum_contract']
            if not set(case['support']) <= set(contract['support']['allowed']):
                raise ValueError('Unsupported Writing help type.')
        else:
            raise ValueError('Unknown reviewer fixture stage.')
    return fixture


def build_packet(fixture):
    """Keep author labels out of the reviewer file; never invent human results."""
    units, key_units, audio_files = [], [], []
    listening = [json.loads((DATA_DIR / (identity + '.json')).read_text(encoding='utf-8'))
                 for identity in fixture.get('listening_sha256', {})]
    for unit_id in fixture['unit_sha256']:
        unit = get_unit(unit_id)
        prompts = []
        answers = []
        for stage in ('practice', 'forms'):
            questions = {q['id']: q for q in (unit['questions'] if stage == 'practice' else unit['forms']['questions'])}
            for item in _pack(unit, stage)['items']:
                visible = {k: v for k, v in item.items() if k not in ('answer', 'accepted_answers')}
                requirement = requirement_index()[questions[item['id']]['requirement_id']]
                prompts.append({'stage': stage, 'item': visible, 'requirement': requirement,
                    'review': {'natural_russian': None, 'level_fit': None, 'unambiguous': None,
                               'requirement_fit': None, 'notes': ''}})
                answers.append({'stage': stage, 'item_id': item['id'], 'answer': item['answer'],
                                'accepted_answers': item.get('accepted_answers')})
        for pack in (item for item in listening if item['unit_id'] == unit_id):
            manifest_path = ROOT / 'flask_vocab_app/static/audio/course/curriculum' / pack['id'] / 'manifest.json'
            audio_manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
            for item in pack['items']:
                visible = {k: deepcopy(v) for k, v in item.items() if k not in ('answer', 'accepted_answers')}
                asset = ROOT / 'flask_vocab_app' / item['audio_url'].lstrip('/')
                clip = audio_manifest.get('clips', {}).get(item['id'])
                prepared = bool(clip and asset.is_file() and digest(asset.read_bytes()) == clip['audio_sha256']
                                and digest(item['transcript'].encode()) == clip['text_sha256'])
                visible['recording_status'] = 'prepared; human audio review pending' if prepared else 'not prepared'
                visible['audio_file'] = f"audio/{pack['id']}/{item['id']}.mp3" if prepared else None
                if prepared:
                    visible['audio_sha256'] = clip['audio_sha256']; visible['duration_seconds'] = clip['duration']
                    audio_files.append({'path': visible['audio_file'], 'source': str(asset.relative_to(ROOT)), 'sha256': clip['audio_sha256']})
                prompts.append({'stage': 'listening', 'item': visible, 'requirement': requirement_index()[item['requirement_id']],
                    'review': {'natural_russian': None, 'level_fit': None, 'unambiguous': None,
                               'requirement_fit': None, 'notes': ''}})
                answers.append({'stage': 'listening', 'item_id': item['id'], 'answer': item['answer']})
        units.append({'unit_id': unit_id, 'title': unit['title'], 'level': unit['level'],
            'groups': unit['groups'], 'questions': prompts,
            'writing_contract': writing_task(unit)['curriculum_contract'],
            'teaching_review': {'classification': None, 'accuracy': None, 'useful_contrasts': None,
                                'missing_prerequisites': '', 'notes': ''}})
        key_units.append({'unit_id': unit_id, 'answers': answers})
    cases = []
    for index, source in enumerate(fixture['cases'], start=1):
        case = {k: deepcopy(v) for k, v in source.items() if k != 'author_expectation'}
        # IDs must not reveal labels such as "error" or "clear" to a reviewer.
        case['id'] = 'case-' + str(index).zfill(3)
        unit = get_unit(source['unit_id'])
        if source['stage'] == 'forms':
            q = next(q for q in unit['forms']['questions'] if q['id'] == source['item_id'])
            case['task'] = {k: q[k] for k in ('prompt', 'requirement_id')}
            case['task']['reference_expectation'] = requirement_index()[q['requirement_id']]['expectation']
        else:
            task = writing_task(unit)
            case['task'] = {'prompt': task['task_en'], 'prompt_ru': task['task'],
                            'criteria': task['curriculum_contract']['criteria'],
                            'contract_sha256': task['curriculum_contract']['contract_sha256']}
        case['review'] = {'outcome': None, 'independent_evidence': None, 'reason': '',
                          'corrections': [], 'acceptable_alternatives': [], 'disputed': False}
        cases.append(case)
    reviewer = {'packet_id': fixture['id'], 'status': 'awaiting independent human review',
        'reviewer': {'name_or_id': '', 'qualification': '', 'date': '', 'kind': ''},
        'unit_sha256': fixture['unit_sha256'], 'units': units, 'cases': cases}
    author = {'packet_id': fixture['id'], 'status': fixture['status'], 'units': key_units,
              'cases': [{'id': 'case-' + str(i).zfill(3), 'source_id': c['id'], **c['author_expectation']}
                        for i, c in enumerate(fixture['cases'], start=1)]}
    manifest = {'packet_id': fixture['id'], 'unit_sha256': fixture['unit_sha256'],
        'listening_sha256': fixture.get('listening_sha256', {}), 'audio_files': audio_files,
        'fixture_sha256': digest(json.dumps(fixture, ensure_ascii=False, sort_keys=True).encode()),
        'review_status': 'not completed', 'provider_calls': 0,
        'limitations': ['Authored expectations are review hypotheses, not human ground truth.',
                       'Controlled matches test the implementation, not the linguistic validity of its key.',
                       'Recordings are included only when prepared; no human audio review, learner trial or model-grading evaluation is recorded.']}
    return {'reviewer.json': reviewer, 'author-key.json': author, 'manifest.json': manifest}


def write_packet(packet, directory):
    directory = Path(directory)
    encoded = {name: json.dumps(data, ensure_ascii=False, indent=2) + '\n' for name, data in packet.items()}
    # Preserve filled-in review work and any unrelated files on repeated runs.
    for name, value in encoded.items():
        path = directory / name
        if path.exists() and path.read_text(encoding='utf-8') != value:
            raise ValueError('Refusing to overwrite existing review work: ' + str(path))
    for clip in packet['manifest.json'].get('audio_files', []):
        source, target = ROOT / clip['source'], directory / clip['path']
        if not source.is_file() or digest(source.read_bytes()) != clip['sha256']:
            raise ValueError('Audio changed after the packet was prepared: ' + clip['path'])
        if target.exists() and digest(target.read_bytes()) != clip['sha256']:
            raise ValueError('Refusing to overwrite existing review audio: ' + str(target))
    directory.mkdir(parents=True, exist_ok=True)
    for name, value in encoded.items():
        path = directory / name
        if not path.exists():
            with path.open('x', encoding='utf-8') as output:
                output.write(value)
    for clip in packet['manifest.json'].get('audio_files', []):
        source, target = ROOT / clip['source'], directory / clip['path']
        if not source.is_file() or digest(source.read_bytes()) != clip['sha256']:
            raise ValueError('Audio changed after the packet was prepared: ' + clip['path'])
        if target.exists() and digest(target.read_bytes()) != clip['sha256']:
            raise ValueError('Refusing to overwrite existing review audio: ' + str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check structure and authored matcher expectations; no human or model grading.')
    parser.add_argument('--output-dir', type=Path, help='Export blank reviewer and separate author-key JSON files.')
    parser.add_argument('--fixture', type=Path, default=CURRENT_FIXTURE, help='Pinned review fixture; use v1 for an earlier review round.')
    args = parser.parse_args()
    fixture = read_fixture(args.fixture)
    packet = build_packet(fixture)
    if args.output_dir:
        write_packet(packet, args.output_dir)
    if not args.check and not args.output_dir:
        parser.error('Choose --check or --output-dir.')
    print(f"Checked {len(fixture['unit_sha256'])} pinned units and {len(fixture['cases'])} authored cases. No human review or provider evaluation performed.")


if __name__ == '__main__':
    main()
