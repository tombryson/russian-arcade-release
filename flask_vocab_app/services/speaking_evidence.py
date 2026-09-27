"""Narrow authored Speaking diagnostics and original-audio identity helpers."""
from functools import lru_cache
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import wave

from contracts.curriculum import CONTRACT_VERSION, freeze_task_contract, validate_task_contract, validate_judgements
from services.curriculum_requirement_map import requirement_index
from services.torfl_requirements import VERSION


AUDIO_VERSION = 'speaking-audio-v1'
_HASH = re.compile(r'[0-9a-f]{64}')
_DIRECTIONS = {
    'directions-a1-park-v2': ('Ask where the park is', 'Спросите, где находится парк', 'Ask for the location of парк.'),
    'directions-a1-pharmacy-v2': ('Ask where the pharmacy is', 'Спросите, где находится аптека', 'Ask for the location of аптека.'),
    'directions-a1-post-office-v2': ('Ask where the post office is', 'Спросите, где находится почта', 'Ask for the location of почта.'),
}


@lru_cache(maxsize=1)
def _interaction_mappings():
    source = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'speaking_evidence_targets.json').read_text())
    if source['version'] != 'speaking-interaction-diagnostic-v1':
        raise ValueError('Unknown Speaking interaction mapping version.')
    return source['mappings']


def _interaction_contract(scenario):
    mapping = _interaction_mappings().get(scenario.get('seed'))
    if mapping is None:
        return None
    if any(scenario.get(key) != expected for key, expected in mapping['expected'].items()):
        raise ValueError('The authored Speaking situation no longer matches its diagnostic mapping.')
    criterion = mapping['criterion']
    ref = requirement_index()[criterion['requirement_id']]
    return freeze_task_contract({
        'schema_version': 1, 'contract_version': CONTRACT_VERSION, 'reference_version': VERSION,
        'task_id': scenario['seed'] + '.' + criterion['id'], 'activity': 'speaking',
        'content_version': 'speaking-interaction-diagnostic-v1', 'level': 'A1',
        'topic_ids': [mapping['topic_id']], 'purpose': 'diagnostic',
        'content': {'scenario': scenario, 'goal_ids': mapping['goal_ids'],
                    'criterion_labels': {criterion['id']: {'label': mapping['label'], 'label_ru': mapping['label_ru']}}},
        'rubric_version': 'speaking-elicited-interaction-v1',
        'support': {'allowed': ['hint', 'model_answer'], 'independence_breakers': ['hint', 'model_answer']},
        'criteria': [{**criterion, 'response_mode': 'independent_speaking', 'evidence_scope': 'reference',
                      'max_score': 2, 'source_refs': ref['source_refs']}]})


def speaking_criterion_labels(contract, criterion_id):
    """Display the exact frozen criterion; preserve legacy location labels."""
    labels = contract['content'].get('criterion_labels', {}).get(criterion_id)
    if labels is not None:
        return {name: labels[name] for name in ('label', 'label_ru')}
    scenario = contract['content']['scenario']
    return {'label': scenario['goals'][0], 'label_ru': scenario['goals_ru'][0]}


def speaking_task_contract(scenario):
    """Freeze only explicitly mapped elicitation, never every scenario goal."""
    expected = _DIRECTIONS.get(scenario.get('seed'))
    if expected is None:
        return _interaction_contract(scenario)
    if (scenario.get('scenario_id') != 'directions' or scenario.get('target_level') != 'A1'
            or scenario.get('scenario_version') != 2
            or [next(iter(scenario.get(key) or []), None) for key in ('goals', 'goals_ru', 'completion_criteria')] != list(expected)
            or next(iter(scenario.get('goal_ids') or []), None) != 'objective-1'):
        raise ValueError('The authored Speaking goal no longer matches its diagnostic mapping.')
    ref = requirement_index()['a1.speaking.ask-and-answer']
    return freeze_task_contract({
        'schema_version': 1, 'contract_version': CONTRACT_VERSION, 'reference_version': VERSION,
        'task_id': scenario['seed'] + '.location-question', 'activity': 'speaking',
        'content_version': 'speaking-directions-diagnostic-v1', 'level': 'A1',
        'topic_ids': ['places'], 'purpose': 'diagnostic',
        'content': {'scenario': scenario, 'goal_ids': ['objective-1']},
        'rubric_version': 'speaking-location-question-v1',
        'support': {'allowed': ['hint', 'model_answer'], 'independence_breakers': ['hint', 'model_answer']},
        'criteria': [{'id': 'ask-location', 'target_id': 'speaking-directions-a1.ask-location',
                      'requirement_id': ref['id'], 'response_mode': 'independent_speaking',
                      'evidence_scope': 'reference', 'expectation': expected[2] +
                      ' Assess only this location question in the original learner audio. Accept an intelligible short question '
                      'and alternative phrasing; do not require a particular construction, a follow-up answer or other goals.',
                      'max_score': 2, 'source_refs': ref['source_refs']}]})


def validate_speaking_contract(contract, scenario):
    frozen = validate_task_contract(contract)
    if (frozen['activity'] != 'speaking' or frozen['content'].get('scenario') != scenario
            or frozen['level'] != scenario.get('target_level')
            or any(c['response_mode'] != 'independent_speaking' for c in frozen['criteria'])):
        raise ValueError('Speaking criteria must match the exact saved audio task.')
    return frozen


def validate_speaking_judgements(contract, review, duration_ms):
    """Audio bounds are structural proof only; uncertainty must remain unscored."""
    report = review.get('criterion_report')
    validate_judgements(contract, report, audio_duration_ms=duration_ms)
    uncertain = (review.get('speech_status') in ('no_russian', 'unclear')
                 or bool(review.get('uncertain_phrases')))
    if uncertain and any(j['outcome'] != 'insufficient_evidence' for j in report['judgements']):
        raise ValueError('Unclear speech cannot become scored Speaking criterion evidence.')
    return report


def _metadata(recordings):
    position, result = 0, []
    if not recordings:
        raise ValueError('There is no saved learner audio.')
    for ordinal, row in enumerate(recordings, 1):
        if (not isinstance(row.get('id'), str) or not row['id']
                or type(row.get('ordinal')) is not int or row['ordinal'] != ordinal
                or type(row.get('start_sample')) is not int or row['start_sample'] != position
                or type(row.get('sample_count')) is not int or row['sample_count'] < 0
                or type(row.get('sample_rate')) is not int or row['sample_rate'] != 24000
                or row.get('state') == 'capturing'):
            raise ValueError('The recording has a gap or incomplete sample metadata.')
        result.append({key: row[key] for key in ('id', 'ordinal', 'start_sample', 'sample_count', 'sample_rate')})
        position += row['sample_count']
    if not 4800 <= position <= 320 * 24000 or len({r['id'] for r in result}) != len(result):
        raise ValueError('The saved audio duration or recording identity is invalid.')
    return result, position * 1000 // 24000


def recorded_audio_source(recordings, audio_root, *, target_path=None):
    """Read original chunks once, preserving silence and their sample clock."""
    metadata, duration = _metadata(recordings)
    root, output = Path(audio_root), io.BytesIO()
    with wave.open(output, 'wb') as assembled:
        assembled.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        for row, item in zip(recordings, metadata):
            filename = row.get('filename')
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise ValueError('The recording filename is invalid.')
            path = root / filename
            # Refuse links rather than following a saved filename outside its root.
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
            with os.fdopen(fd, 'rb') as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ValueError('The recording must be a regular file.')
                raw = handle.read(32 * 1024 * 1024 + 1)
            if len(raw) > 32 * 1024 * 1024:
                raise ValueError('The recording is too large.')
            with wave.open(io.BytesIO(raw), 'rb') as source:
                if source.getparams()[:3] != (1, 2, 24000) or source.getnframes() != row['sample_count']:
                    raise ValueError('The recording has a gap or changed sample metadata.')
                pcm = source.readframes(source.getnframes())
                if len(pcm) != row['sample_count'] * 2:
                    raise ValueError('Part of the recording is missing.')
            item['sha256'] = hashlib.sha256(raw).hexdigest()
            assembled.writeframes(pcm)
    raw_audio = output.getvalue()
    if target_path is not None:
        Path(target_path).write_bytes(raw_audio)
    return {'version': AUDIO_VERSION, 'sha256': hashlib.sha256(raw_audio).hexdigest(),
            'duration_ms': duration, 'recordings': metadata, 'independence': 'unverified'}


def verify_audio_source(conn, profile_id, session_id, manifest, *, audio_root=None):
    """Validate DB bindings; an explicit audio root additionally verifies bytes."""
    if not conn.execute('SELECT 1 FROM live_conversation_sessions WHERE id=? AND profile_id=?',
                        (session_id, profile_id)).fetchone():
        raise LookupError('Speaking audio is not owned by this profile.')
    cursor = conn.execute('SELECT * FROM live_conversation_recordings WHERE session_id=? ORDER BY ordinal', (session_id,))
    columns = [column[0] for column in cursor.description]
    recordings = [dict(zip(columns, row)) for row in cursor.fetchall()]
    metadata, duration = _metadata(recordings)
    if (not isinstance(manifest, dict)
            or set(manifest) != {'version', 'sha256', 'duration_ms', 'recordings', 'independence'}
            or manifest['version'] != AUDIO_VERSION or manifest['independence'] != 'unverified'
            or type(manifest['duration_ms']) is not int or manifest['duration_ms'] != duration
            or not isinstance(manifest['sha256'], str) or not _HASH.fullmatch(manifest['sha256'])
            or not isinstance(manifest['recordings'], list) or len(manifest['recordings']) != len(metadata)):
        raise ValueError('Invalid original-audio identity.')
    for saved, expected in zip(manifest['recordings'], metadata):
        if (not isinstance(saved, dict) or set(saved) != set(expected) | {'sha256'}
                or any(type(saved[key]) is not type(value) or saved[key] != value for key, value in expected.items())
                or not isinstance(saved['sha256'], str) or not _HASH.fullmatch(saved['sha256'])):
            raise ValueError('Original audio no longer matches its saved recording manifest.')
    if audio_root is not None and recorded_audio_source(recordings, audio_root) != manifest:
        raise ValueError('Original audio bytes changed after they were reviewed.')
    return manifest
