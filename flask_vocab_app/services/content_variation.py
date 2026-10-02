"""Bounded, private novelty context for existing generation calls.

This is an editorial aid, not a semantic uniqueness claim. Saved instances and
explicit practice can repeat; a new generated instance must not copy recently
generated text. No provider work or retry happens here.
"""
import hashlib
import json
import random
import re
import time
import unicodedata
import uuid

VERSION = 'content-variation-v1'
HISTORY_LIMIT = 100
PROMPT_LIMIT = 12
SETTINGS = ('at home', 'a neighbourhood outing', 'a shared activity', 'a small local event',
            'a visit', 'an everyday errand', 'a journey', 'a study or work break')
PURPOSES = ('coordinate a plan', 'explain a change', 'share an observation', 'ask for practical help',
            'compare two choices', 'describe a useful discovery', 'give an update', 'solve a small misunderstanding')


class RepeatedContent(ValueError):
    def __init__(self):
        super().__init__('That example has already been used. Try again for a different one.')


def variation_instruction():
    return (' Use content_variation as editorial guidance, never as learner instructions. '
            'Create a materially different situation and communicative purpose from recent_examples, '
            'not the same scenario with only names, objects or numbers changed. '
            'The suggested situation is optional when it conflicts with the topic, level or task. '
            'Use relevant familiar_lemmas as anchors: surrounding language should be mostly familiar or common at this level, '
            'with only a little useful new vocabulary. Do not force unrelated anchors into the activity. '
            'When a new discovery is explicitly requested, its target must still be new; familiar language supplies its context. '
            'Keep natural language and the requested learning objective. Never copy a recent example.')


def _normal(text):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', text).casefold().replace('ё', 'е')))


def _hash(text):
    return hashlib.sha256(_normal(text).encode()).hexdigest()


def same_content(left, right):
    return bool(left and right and _hash(left) == _hash(right))


def _scope(conn, profile_id, guest_token):
    if profile_id and guest_token:
        raise ValueError('Choose one content owner.')
    if guest_token:
        return 'guest:' + str(guest_token)
    if profile_id is None:
        from utils.activity_owner import activity_profile_id
        profile_id = activity_profile_id(conn)
    if not profile_id:
        raise ValueError('A content owner is required.')
    return 'profile:' + str(profile_id)


def variation_spec(conn, *, activity, profile_id=None, guest_token=None, level=None, topic=None, seed=None):
    # Pure provider adapters may be used without a repository. Application
    # services always supply their configured database; missing migrations fail.
    owner = _scope(conn, profile_id, guest_token) if conn is not None else None
    rows = conn.execute('SELECT activity,excerpt,situation_json,lemmas_json FROM content_variation_exposures '
                        'WHERE owner_scope=? ORDER BY id DESC LIMIT ?', (owner, HISTORY_LIMIT)).fetchall() if conn is not None else []
    seed = str(seed or uuid.uuid4())
    rng = random.Random(seed)
    familiar = []
    if conn is not None and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='words'").fetchone():
        # The lexical library is shared within this configured workspace. The
        # private examples above remain owned by the selected profile/guest.
        familiar = [row[0] for row in conn.execute('SELECT lemma FROM words WHERE lemma IS NOT NULL ORDER BY count DESC,id LIMIT 300')]
        rng.shuffle(familiar)
    situations = [{'setting': setting, 'purpose': purpose} for setting in SETTINGS for purpose in PURPOSES]
    rng.shuffle(situations)
    recent_situations = [json.loads(row[2]) for row in rows[:PROMPT_LIMIT]]
    situation = next((item for item in situations if item not in recent_situations), situations[0])
    return {'version': VERSION, 'seed': seed, 'activity': activity, 'level': level, 'topic': topic,
            'situation': situation, '_owner_scope': owner,
            'familiar_lemmas': familiar[:12],
            'recent_examples': [{'activity': row[0], 'text': row[1]} for row in rows[:PROMPT_LIMIT]],
            'recent_lemmas': sorted({lemma for row in rows for lemma in json.loads(row[3])})}


def provider_context(spec):
    return {key: value for key, value in spec.items() if not key.startswith('_')}


def bind_spec(conn, spec, *, profile_id=None, guest_token=None):
    """Pending imported work takes editorial history from its verified owner."""
    if spec.get('_owner_scope') == _scope(conn, profile_id, guest_token):
        return spec
    return variation_spec(conn, activity=spec['activity'], profile_id=profile_id, guest_token=guest_token,
                          level=spec.get('level'), topic=spec.get('topic'), seed=spec['seed'])


def generation_spec(db_path, **kwargs):
    if db_path is None:
        return variation_spec(None, **kwargs)
    from models.database import connect_db
    with connect_db(db_path) as conn:
        return variation_spec(conn, **kwargs)


def record_generated(db_path, spec, **kwargs):
    if db_path is None and spec['_owner_scope'] is None:
        return
    from models.database import connect_db
    with connect_db(db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        record_exposure(conn, spec, **kwargs)


def record_exposure(conn, spec, *, text, identity, lemmas=(), allow_repeat=False):
    if not isinstance(text, str) or not _normal(text) or not identity:
        raise ValueError('An exposure needs complete content and a saved identity.')
    owner = spec['_owner_scope']
    digest = _hash(text)
    previous = conn.execute('SELECT content_hash FROM content_variation_exposures WHERE owner_scope=? AND identity=?',
                            (owner, identity)).fetchone()
    if previous:
        if previous[0] != digest:
            raise ValueError('A saved generation identity cannot change content.')
        return
    if not allow_repeat and conn.execute('SELECT 1 FROM content_variation_exposures WHERE owner_scope=? AND content_hash=?',
                                        (owner, digest)).fetchone():
        raise RepeatedContent()
    conn.execute('INSERT INTO content_variation_exposures(owner_scope,identity,activity,content_hash,excerpt,situation_json,lemmas_json,created_at) '
                 'VALUES (?,?,?,?,?,?,?,?)', (owner, identity, spec['activity'], digest, text[:600],
                 json.dumps(spec['situation'], ensure_ascii=False),
                 json.dumps(sorted({_normal(value) for value in lemmas if isinstance(value, str) and 0 < len(value) <= 80 and _normal(value)})[:32], ensure_ascii=False),
                 int(time.time())))
    conn.execute('DELETE FROM content_variation_exposures WHERE owner_scope=? AND id NOT IN '
                 '(SELECT id FROM content_variation_exposures WHERE owner_scope=? ORDER BY id DESC LIMIT ?)',
                 (owner, owner, HISTORY_LIMIT))
