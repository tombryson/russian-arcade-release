#!/usr/bin/env python3
"""Export an optional editorial review packet for the five-domain A1 pilot."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_curriculum_review import digest, write_packet
from services.assessment_pilot_content import blueprint, validate_blueprint
from services.curriculum_requirement_map import content_digest, requirement_index

FIXTURE = ROOT / 'flask_vocab_app/data/curriculum_evaluation/a1-pilot-review-v1.json'


def read_fixture(path=FIXTURE):
    fixture = json.loads(Path(path).read_text(encoding='utf-8'))
    source = validate_blueprint(blueprint())
    if fixture.get('schema_version') != 1 or fixture.get('blueprint_sha256') != content_digest(source):
        raise ValueError('Pilot source changed; review the changes and issue a new review version.')
    return fixture


def build_packet(fixture):
    source = validate_blueprint(blueprint())
    if fixture['blueprint_sha256'] != content_digest(source):
        raise ValueError('Pilot source differs from the pinned review fixture.')
    audio_path = ROOT / 'flask_vocab_app/static/audio/course/assessment-pilot/manifest.json'
    manifest = json.loads(audio_path.read_text(encoding='utf-8')) if audio_path.is_file() else {}
    units, keys, audio_files = [], [], []
    for domain in source['domains']:
        for task in source['forms'][domain['id']]:
            identity = task['domain'] + '-' + task['form_id']
            context = {k: deepcopy(task[k]) for k in ('domain', 'form_id', 'title', 'title_ru', 'prompt', 'prompt_ru', 'format', 'hint')}
            context['criteria'] = deepcopy(task['contract']['criteria'])
            context['support'] = deepcopy(task['contract']['support'])
            context['contract_sha256'] = task['contract']['contract_sha256']
            for field in ('passage', 'transcript'):
                if field in task:
                    context[field] = task[field]
            if task['domain'] == 'listening':
                asset = ROOT / 'flask_vocab_app' / task['audio_url'].lstrip('/')
                clip = manifest.get('clips', {}).get('a1-pilot-' + task['form_id'] + '-v1')
                ready = bool(clip and asset.is_file() and digest(asset.read_bytes()) == clip['audio_sha256']
                             and digest(task['transcript'].encode()) == clip['text_sha256'])
                context['recording_status'] = 'prepared; editorial audio review not recorded' if ready else 'not prepared'
                context['audio_file'] = 'audio/' + asset.name if ready else None
                if ready:
                    context['audio_sha256'] = clip['audio_sha256']
                    context['duration_seconds'] = clip['duration']
                    audio_files.append({'path': context['audio_file'], 'source': str(asset.relative_to(ROOT)), 'sha256': clip['audio_sha256']})
            prompts, answers = [], []
            for item in task.get('items', [{'id': 'reply', 'prompt': task['prompt'], 'prompt_ru': task['prompt_ru']}]):
                visible = {k: deepcopy(v) for k, v in item.items() if k not in ('answer', 'explanation')}
                prompt = {'stage': task['domain'], 'item': visible,
                          'review': {'natural_russian': None, 'level_fit': None, 'unambiguous': None, 'requirement_fit': None, 'notes': ''}}
                if item.get('requirement_id'):
                    prompt['requirement'] = requirement_index()[item['requirement_id']]
                prompts.append(prompt)
                if 'answer' in item:
                    answers.append({k: deepcopy(item[k]) for k in ('id', 'answer', 'explanation')})
            units.append({'unit_id': identity, 'title': task['title'], 'level': source['level'], 'source': context,
                          'questions': prompts,
                          'teaching_review': {'classification': None, 'accuracy': None, 'useful_contrasts': None, 'missing_prerequisites': '', 'notes': ''}})
            keys.append({'unit_id': identity, 'answers': answers})
    reviewer = {'packet_id': fixture['id'], 'status': 'optional editorial review not recorded',
                'reviewer': {'name_or_id': '', 'qualification': '', 'date': '', 'kind': ''},
                'blueprint_sha256': fixture['blueprint_sha256'], 'limitations': source['limitations'], 'units': units, 'cases': []}
    return {'reviewer.json': reviewer,
            'author-key.json': {'packet_id': fixture['id'], 'status': 'provisional authored keys', 'units': keys, 'cases': []},
            'manifest.json': {'packet_id': fixture['id'], 'packet_kind': 'assessment_pilot', 'blueprint_sha256': fixture['blueprint_sha256'],
                              'fixture_sha256': digest(json.dumps(fixture, ensure_ascii=False, sort_keys=True).encode()),
                              'review_status': 'not completed', 'provider_calls': 0, 'audio_files': audio_files,
                              'limitations': source['limitations'] + ['Editorial review is optional maintainer QA. It never blocks a learner or requires a tutor.']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, default=FIXTURE)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    packet = build_packet(read_fixture(args.fixture))
    if not args.check and not args.output_dir:
        parser.error('Choose --check or --output-dir.')
    if args.output_dir:
        write_packet(packet, args.output_dir)
    print('Checked two forms across all five domains. No human review or provider evaluation performed.')


if __name__ == '__main__':
    main()
