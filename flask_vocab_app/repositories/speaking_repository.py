"""Speaking catalogue and variant selection. SQLite owns the live catalogue."""
import json
from pathlib import Path
import random

from repositories.learning_repository import LearningError, encoded


CATALOGUE_FILE = Path(__file__).resolve().parents[1] / 'data' / 'speaking_catalogue.json'
LEVELS_FILE = Path(__file__).resolve().parents[1] / 'data' / 'speaking_levels.json'
LEVELS = ('A1', 'A2', 'B1', 'B2')


def validate_level(value):
    if value is not None and (not isinstance(value, str) or value not in LEVELS):
        raise LearningError('invalid_input', 'Choose A1, A2, B1 or B2 for speaking practice.')
    return value


def seed_levels(conn):
    """Migration 024 only: author the catalogue, never relabel saved attempts."""
    data = json.loads(LEVELS_FILE.read_text())
    for item in data['variants']:
        level = validate_level(item['target_level'])
        existing = conn.execute('SELECT scenario_id,payload_json FROM speaking_scenario_variants WHERE id=?',
                                (item['seed'],)).fetchone()
        if existing:
            snapshot = json.loads(existing[1])
            if existing[0] != item['scenario_id']:
                raise ValueError('Speaking level seed changed scenario membership.')
        else:
            snapshot = dict(item['snapshot'])
        snapshot['target_level'] = level
        snapshot['learning_contract'] = item['learning_contract']
        if snapshot['learning_contract']['target_level'] != level:
            raise ValueError('Speaking learning contract has a different target level.')
        if existing:
            conn.execute('UPDATE speaking_scenario_variants SET target_level=?,payload_json=? WHERE id=?',
                         (level,encoded(snapshot),item['seed']))
        else:
            conn.execute('INSERT INTO speaking_scenario_variants(id,scenario_id,payload_json,target_level) VALUES (?,?,?,?)',
                         (item['seed'],item['scenario_id'],encoded(snapshot),level))


def seed_catalogue(conn):
    """Migration seed only; never overwrite edited curriculum on app startup."""
    data = json.loads(CATALOGUE_FILE.read_text())
    activity = data['activity']
    conn.execute('INSERT OR IGNORE INTO learning_activity_types(id,title,title_ru) VALUES (?,?,?)',
                 (activity['id'],activity['title'],activity['title_ru']))
    columns = ('id','title','title_ru','description','description_ru','role','role_ru','icon','sign','sort_order')
    for scenario in data['scenarios']:
        conn.execute('INSERT OR IGNORE INTO speaking_scenarios(activity_type_id,'+','.join(columns)+') VALUES ('+','.join('?' for _ in range(len(columns)+1))+')',
                     (activity['id'],*(scenario[key] for key in columns)))
        for variant in scenario['variants']:
            conn.execute('INSERT OR IGNORE INTO speaking_scenario_variants(id,scenario_id,payload_json) VALUES (?,?,?)',
                         (variant['seed'],scenario['id'],encoded(variant)))
    # Recognised café history acquires a relationship without rewriting its
    # original task, captions, recordings, report or model settings.
    conn.execute("""UPDATE live_conversation_sessions SET scenario_id='cafe'
        WHERE scenario_id IS NULL AND json_valid(scenario_json)
        AND (json_extract(scenario_json,'$.id')='cafe-v1'
             OR json_extract(scenario_json,'$.seed') IN
                (SELECT id FROM speaking_scenario_variants WHERE scenario_id='cafe'))""")
    conn.execute("""UPDATE live_conversation_sessions
        SET variant_id=json_extract(scenario_json,'$.seed')
        WHERE variant_id IS NULL AND json_valid(scenario_json)
        AND json_extract(scenario_json,'$.seed') IN
            (SELECT id FROM speaking_scenario_variants WHERE scenario_id=live_conversation_sessions.scenario_id)""")


def seed_curriculum(conn):
    """Migration 042 publishes new tasks; historical attempts and rows survive."""
    from services.speaking_curriculum import compiled_situations, level_details
    original = json.loads(CATALOGUE_FILE.read_text())
    metadata = {s['id']:{**s, 'conversation_role':s['variants'][0]['conversation_role']}
                for s in original['scenarios']}
    snapshots = compiled_situations(metadata)
    for details in level_details():
        columns = tuple(details)
        conn.execute('INSERT OR REPLACE INTO speaking_scenario_levels (' + ','.join(columns)
                     + ') VALUES (' + ','.join('?' for _ in columns) + ')', tuple(details.values()))
    # Retain old IDs for session foreign keys and historic snapshots. Only
    # supplied v1 catalogue IDs are retired; user-authored additions survive.
    old_ids = {v['seed'] for s in original['scenarios'] for v in s['variants']}
    old_ids.update(v['seed'] for v in json.loads(LEVELS_FILE.read_text())['variants'])
    conn.executemany('UPDATE speaking_scenario_variants SET enabled=0 WHERE id=?',
                     ((seed,) for seed in old_ids))
    for snapshot in snapshots:
        conn.execute('INSERT INTO speaking_scenario_variants '
                     '(id,scenario_id,payload_json,target_level) VALUES (?,?,?,?) '
                     'ON CONFLICT(id) DO UPDATE SET scenario_id=excluded.scenario_id, '
                     'payload_json=excluded.payload_json,target_level=excluded.target_level,enabled=1',
                     (snapshot['seed'],snapshot['scenario_id'],encoded(snapshot),snapshot['target_level']))


def catalogue(conn, level=None):
    validate_level(level)
    activity = conn.execute("SELECT * FROM learning_activity_types WHERE id='speaking'").fetchone()
    rows = conn.execute("""SELECT s.*,COUNT(v.id) AS variant_count FROM speaking_scenarios s
        JOIN speaking_scenario_variants v ON v.scenario_id=s.id AND v.enabled=1
        WHERE s.activity_type_id='speaking' AND s.enabled=1 GROUP BY s.id ORDER BY s.sort_order,s.id""").fetchall()
    scenarios = []
    for row in rows:
        item = dict(row)
        counts = dict(conn.execute('SELECT target_level,COUNT(*) FROM speaking_scenario_variants WHERE scenario_id=? AND enabled=1 GROUP BY target_level', (row['id'],)).fetchall())
        item['levels'] = [band for band in LEVELS if counts.get(band, 0)]
        item['level_details'] = {details['target_level']: {
            key:details[key] for key in ('title','title_ru','description','description_ru','topic_id')}
            for details in conn.execute('SELECT * FROM speaking_scenario_levels WHERE scenario_id=?', (row['id'],))}
        if level is not None:
            item['variant_count'] = counts.get(level, 0)
        item['available'] = item['variant_count'] > 0
        scenarios.append(item)
    counts = dict(conn.execute("""SELECT v.target_level,COUNT(*) FROM speaking_scenario_variants v
        JOIN speaking_scenarios s ON s.id=v.scenario_id
        WHERE v.enabled=1 AND s.enabled=1 AND s.activity_type_id='speaking' GROUP BY v.target_level""").fetchall())
    return {'activity':dict(activity), 'scenarios':scenarios, 'selected_level':level,
            'levels':[{'id':band,'available_count':counts.get(band,0)} for band in LEVELS]}


def choose_variant(conn, scenario_id='cafe', *, previous_seeds=(), seed=None, level=None):
    validate_level(level)
    if not isinstance(scenario_id,str):
        raise LearningError('invalid_input', 'Choose an available speaking scenario.')
    scenario = conn.execute("SELECT * FROM speaking_scenarios WHERE id=? AND activity_type_id='speaking' AND enabled=1", (scenario_id,)).fetchone()
    if not scenario:
        raise LearningError('not_found', 'This speaking scenario is not available.', 404)
    variants = {row['id']:row for row in conn.execute('SELECT id,payload_json,target_level FROM speaking_scenario_variants WHERE scenario_id=? AND enabled=1 AND (? IS NULL OR target_level=?) ORDER BY id', (scenario_id,level,level))}
    if not variants:
        raise LearningError('unavailable', 'This scenario has no available situations at this level yet.' if level else 'This scenario has no available situations yet.', 409)
    if seed is not None:
        if not isinstance(seed,str) or seed not in variants:
            raise LearningError('invalid_input', 'Choose a situation from this speaking scenario and level.')
    else:
        recent = list(dict.fromkeys(value for value in previous_seeds if isinstance(value,str) and value in variants))
        available = [key for key in variants if key not in recent]
        seed = random.choice(available) if available else recent[-1]
    snapshot = json.loads(variants[seed]['payload_json'])
    context = snapshot.get('curriculum_context')
    if isinstance(context, dict) and isinstance(context.get('topic_id'), str):
        from services.torfl_requirements import generation_reference
        reference = generation_reference(context['topic_id'], variants[seed]['target_level'], 'speaking')
        if reference is not None:
            # Refresh planning guidance only in the selected copy. Both modes
            # freeze it when creating a session; resumed sessions and persisted
            # catalogue facts/contracts are never rewritten by selection.
            snapshot['curriculum_context'] = {**context, 'proficiency_reference': reference}
    level_metadata = conn.execute('SELECT title,title_ru FROM speaking_scenario_levels WHERE scenario_id=? AND target_level=?',
                                  (scenario_id,variants[seed]['target_level'])).fetchone()
    # Metadata is copied into the immutable session snapshot, so future
    # catalogue edits cannot rename or change a saved learner's conversation.
    return {**snapshot,'id':seed,'seed':seed,'scenario_id':scenario_id,
            'category_title':level_metadata['title'] if level_metadata else scenario['title'],
            'category_title_ru':level_metadata['title_ru'] if level_metadata else scenario['title_ru'],
            'role':snapshot.get('role') or scenario['role'],'role_ru':snapshot.get('role_ru') or scenario['role_ru'],
            'icon':scenario['icon'],'sign':scenario['sign'],
            'target_level':variants[seed]['target_level']}
