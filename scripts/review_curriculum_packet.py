#!/usr/bin/env python3
"""Validate submitted curriculum reviews and report unresolved decisions offline."""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path

OUTCOMES = {'satisfied', 'partial', 'not_satisfied', 'insufficient_evidence'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_json(path):
    def distinct(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=distinct)


def targets(document):
    result = {}
    for unit in document['units']:
        result[f"unit:{unit['unit_id']}:teaching"] = unit['teaching_review']
        for question in unit['questions']:
            result[f"unit:{unit['unit_id']}:{question['stage']}:{question['item']['id']}"] = question['review']
    for case in document['cases']:
        result['case:' + case['id']] = case['review']
    return result


def content(document):
    frozen = deepcopy(document)
    frozen.pop('reviewer', None)
    frozen.pop('status', None)
    for unit in frozen['units']:
        unit.pop('teaching_review')
        for question in unit['questions']:
            question.pop('review')
    for case in frozen['cases']:
        case.pop('review')
    return frozen


def identity(value):
    required = {'name_or_id', 'qualification', 'date', 'kind'}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('Reviewer identity needs name_or_id, qualification, date and kind.')
    if value['kind'] not in ('human', 'internal_model'):
        raise ValueError('Declare human or internal_model review; model work is not human review.')
    if any(not isinstance(value[field], str) or not 1 <= len(value[field].strip()) <= 500
           for field in ('name_or_id', 'qualification', 'date')):
        raise ValueError('Reviewer identity, qualification and date must be supplied.')
    try:
        date.fromisoformat(value['date'])
    except ValueError:
        raise ValueError('Use an ISO review date: YYYY-MM-DD.') from None


def validate_rating(rating, template):
    if not isinstance(rating, dict) or set(rating) != set(template):
        raise ValueError('Review fields do not match the packet.')
    for key, blank in template.items():
        value = rating[key]
        if key == 'outcome':
            valid = value is None or isinstance(value, str) and value in OUTCOMES
        elif blank is None:
            valid = value is None or type(value) is bool
        elif isinstance(blank, bool):
            valid = type(value) is bool
        elif isinstance(blank, list):
            valid = isinstance(value, list) and len(value) <= 100 and all(isinstance(v, str) and len(v) <= 5000 for v in value)
        else:
            valid = isinstance(value, str) and len(value) <= 10000
        if not valid:
            raise ValueError('Invalid review value for ' + key)


def validate_review(template, submitted):
    if content(template) != content(submitted):
        raise ValueError('Review content differs from the pinned packet; preserve prompts, responses and hashes.')
    identity(submitted['reviewer'])
    expected = targets(template)
    observed = targets(submitted)
    if set(expected) != set(observed):
        raise ValueError('Review target IDs do not match the packet.')
    for key in expected:
        validate_rating(observed[key], expected[key])
    return {'identity': submitted['reviewer'], 'sha256': fingerprint(submitted), 'ratings': observed}


def report(packet, submissions, adjudication=None):
    template = packet['reviewer.json']
    reviews = [validate_review(template, document) for document in submissions]
    names = [row['identity']['name_or_id'].strip().casefold() for row in reviews]
    if len(names) != len(set(names)):
        raise ValueError('Submit only one review per reviewer identity.')
    human = [row for row in reviews if row['identity']['kind'] == 'human']
    model = [row for row in reviews if row['identity']['kind'] == 'internal_model']
    author = {'case:' + row['id']: row for row in packet['author-key.json']['cases']}
    issues, decisions, agreements = [], {}, {}
    for key, blank in targets(template).items():
        judged_fields = [field for field, value in blank.items() if value is None]
        ratings = [row['ratings'][key] for row in human]
        completed = [row for row in ratings if all(row[field] is not None for field in judged_fields)]
        reasons = []
        if not completed:
            reasons.append('human_review_missing' if not human else 'rating_incomplete')
        for field in judged_fields:
            values = [row[field] for row in ratings if row[field] is not None]
            if len(set(values)) > 1:
                reasons.append('reviewer_disagreement:' + field)
            if field not in ('outcome', 'independent_evidence') and False in values:
                reasons.append('content_concern:' + field)
        if any(row.get('disputed') or row.get('corrections') or row.get('acceptable_alternatives')
               or row.get('missing_prerequisites', '').strip() for row in ratings):
            reasons.append('reviewer_flag')
        if key in author and any(row['outcome'] is not None and row['outcome'] != author[key]['outcome'] for row in ratings):
            reasons.append('author_key_disagreement')
        if reasons:
            issues.append({'target': key, 'reasons': reasons,
                           'reviews': [{'reviewer': row['identity']['name_or_id'], 'rating': row['ratings'][key]} for row in human]})
        elif completed:
            decisions[key] = {field: completed[0][field] for field in judged_fields}
            if len(completed) >= 2:
                agreements[key] = decisions[key]

    context = {'packet_id': template['packet_id'], 'content_sha256': fingerprint(content(template)),
               'review_sha256': sorted(row['sha256'] for row in reviews)}
    resolved = []
    if adjudication is not None:
        if not isinstance(adjudication, dict) or set(adjudication) != {*context, 'adjudicator', 'decisions'}:
            raise ValueError('Adjudication fields do not match this operation.')
        if any(adjudication[key] != value for key, value in context.items()):
            raise ValueError('Adjudication belongs to different content or review submissions.')
        identity(adjudication['adjudicator'])
        if adjudication['adjudicator']['kind'] != 'human':
            raise ValueError('Adjudication requires a human assessor.')
        if adjudication['adjudicator']['name_or_id'].strip().casefold() in names:
            raise ValueError('Use a separate assessor for adjudication.')
        if not isinstance(adjudication['decisions'], list):
            raise ValueError('Adjudication decisions must be a list.')
        seen = set()
        by_id = {row['target']: row for row in issues}
        for decision in adjudication['decisions']:
            if not isinstance(decision, dict) or set(decision) != {'target', 'decision', 'reason', 'rating'}:
                raise ValueError('An adjudication needs target, decision, reason and rating.')
            target = decision['target']
            if target not in by_id or target in seen:
                raise ValueError('Adjudicate each unresolved target at most once.')
            seen.add(target)
            fields = [field for field, value in targets(template)[target].items() if value is None]
            completed_ratings = [row['ratings'][target] for row in human if all(row['ratings'][target][field] is not None for field in fields)]
            if len(completed_ratings) < 2:
                raise ValueError('A disputed target needs a second independent rating before adjudication.')
            if decision['decision'] not in ('accept', 'revise', 'exclude'):
                raise ValueError('Choose accept, revise or exclude for adjudication.')
            if not isinstance(decision['reason'], str) or not 1 <= len(decision['reason'].strip()) <= 10000:
                raise ValueError('Adjudication needs an explanation.')
            validate_rating(decision['rating'], targets(template)[target])
            if any(decision['rating'][field] is None for field, value in targets(template)[target].items() if value is None):
                raise ValueError('Adjudication needs a completed rating.')
            resolved.append(deepcopy(decision))
        issues = [row for row in issues if row['target'] not in seen]
    return {**context, 'status': 'awaiting human review' if not human else 'review decisions pending' if issues else 'review decisions recorded',
            'human_submissions': len(human), 'internal_model_submissions': len(model),
            'reviewers': [{'identity': row['identity'], 'sha256': row['sha256']} for row in reviews],
            'recorded_ratings': decisions, 'agreements': agreements, 'unresolved': issues, 'adjudicated': resolved,
            'marking_comparison': 'two or more human submissions' if len(human) >= 2 else 'not performed',
            'release_actions': [row for row in resolved if row['decision'] != 'accept'],
            'adjudication_template': {**context, 'adjudicator': {'name_or_id': '', 'qualification': '', 'date': '', 'kind': 'human'}, 'decisions': []},
            'limitations': ['Reviewer identities and qualifications are declarations, not independently verified credentials.',
                            'Model reviews are recorded separately and never count as independent human ratings.',
                            'Recorded decisions do not establish a pass threshold, proficiency certification or release approval.',
                            'Revised or excluded material requires a new content version; no published content is rewritten.']}


def validate_packet(packet, directory=None, fixture_path=None):
    """Check the packet against pinned authored sources, then its bundled media."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import prepare_curriculum_review as units
    import prepare_assessment_pilot_review as pilot
    manifest = packet['manifest.json']
    template = packet['reviewer.json']
    if any(packet[name]['packet_id'] != template['packet_id'] for name in ('author-key.json', 'manifest.json')):
        raise ValueError('Packet files have different identities.')
    module = pilot if manifest.get('packet_kind') == 'assessment_pilot' else units
    fixture = Path(fixture_path) if fixture_path else units.ROOT / 'flask_vocab_app/data/curriculum_evaluation' / (template['packet_id'] + '.json')
    expected = module.build_packet(module.read_fixture(fixture))
    def source_only(value):
        if isinstance(value, dict):
            return {key: source_only(child) for key, child in value.items()
                    if key not in ('audio_file', 'audio_sha256', 'duration_seconds', 'recording_status')}
        if isinstance(value, list):
            return [source_only(child) for child in value]
        return value
    if source_only(content(template)) != source_only(content(expected['reviewer.json'])):
        raise ValueError('Packet content differs from the pinned authored sources.')
    if packet['author-key.json'] != expected['author-key.json']:
        raise ValueError('Packet answer keys differ from the pinned authored sources.')
    for field in ('fixture_sha256', 'unit_sha256', 'listening_sha256', 'blueprint_sha256'):
        if manifest.get(field) != expected['manifest.json'].get(field):
            raise ValueError('Packet manifest differs from the pinned authored sources.')
    # An earlier packet may legitimately mark audio pending before later publication.
    # Once a clip is included, its displayed metadata must match the published source.
    def recordings(document):
        result = {}
        for unit in document['units']:
            if 'recording_status' in unit.get('source', {}):
                result[unit['unit_id']] = unit['source']
            for question in unit['questions']:
                if 'recording_status' in question['item']:
                    result[unit['unit_id'] + ':' + question['item']['id']] = question['item']
        return result
    published_recordings = recordings(expected['reviewer.json'])
    included = []
    for key, item in recordings(template).items():
        if item.get('audio_file'):
            fields = ('audio_file', 'audio_sha256', 'duration_seconds', 'recording_status')
            if any(item.get(field) != published_recordings[key].get(field) for field in fields):
                raise ValueError('Recording metadata differs from its published source.')
            included.append(item['audio_file'])
        elif item.get('recording_status') != 'not prepared' or any(field in item for field in ('audio_sha256', 'duration_seconds')):
            raise ValueError('Unprepared recordings cannot claim verified media.')
    if sorted(included) != sorted(clip['path'] for clip in manifest.get('audio_files', [])):
        raise ValueError('Reviewer recording list differs from its manifest.')
    available = expected['manifest.json'].get('audio_files', [])
    for clip in manifest.get('audio_files', []):
        if clip not in available:
            raise ValueError('Review recording no longer matches its published source.')
        if directory is not None:
            path = Path(directory) / clip['path']
            if not path.is_file() or units.digest(path.read_bytes()) != clip['sha256']:
                raise ValueError('Review recording is missing or changed: ' + clip['path'])
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet-dir', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, help='Pinned source fixture; defaults to the packet identity.')
    parser.add_argument('--review', type=Path, action='append', default=[])
    parser.add_argument('--adjudication', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    packet = {name: read_json(args.packet_dir / name) for name in ('reviewer.json', 'author-key.json', 'manifest.json')}
    validate_packet(packet, args.packet_dir, args.fixture)
    result = report(packet, [read_json(path) for path in args.review], read_json(args.adjudication) if args.adjudication else None)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output.exists() and args.output.read_text(encoding='utf-8') != encoded:
        raise ValueError('Refusing to overwrite an existing report. Use a new output file.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists():
        with args.output.open('x', encoding='utf-8') as target:
            target.write(encoded)
    print(f"{result['human_submissions']} human submissions; {len(result['unresolved'])} unresolved targets. No release decision or pass threshold created.")


if __name__ == '__main__':
    main()
