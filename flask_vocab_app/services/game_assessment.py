"""Conservative evidence for games, distinct from completion and practice.

Chance baselines follow each saved mechanic's scoring rule. They are not task
calibration or a proficiency claim. Unknown formats produce no new evidence.
"""
from collections import Counter
from hashlib import sha256
from itertools import combinations
from math import comb
import re


def chance_score(item, game_id):
    mechanic = item.get('mechanic', game_id)
    expected = item['expected_answer']
    n = len(expected)
    if not n:
        return None
    if mechanic in ('missing-stamp', 'radio', 'detective'):
        choices = item.get('destinations' if mechanic == 'detective' else 'choices', [])
        return 1 / len(choices) if len(choices) > 1 else None
    if mechanic in ('pairs', 'mailbox-sort'):
        choices = item.get('right' if mechanic == 'pairs' else 'bins', [])
        if len(choices) < 2:
            return None
        # New matching rounds award credit per correct association.
        return 1 / len(choices)
    if mechanic == 'letter-back':
        tiles = item.get('tiles', [])
        if len(tiles) < 2:
            return None
        by_id = {tile['id']: tile['text'] for tile in tiles}
        counts = Counter(by_id.values())
        return sum(counts[by_id[token]] / len(tiles) for token in expected) / n
    if mechanic == 'directions':
        # All generated routes fit in the board. Positional credit for modern
        # rounds; exact sequence credit for the original introduction.
        return 1 / 3 if item.get('mechanic') else (1 / 3) ** n
    if mechanic == 'pack-bag':
        choices = sorted(obj['id'] for obj in item.get('objects', []))
        if len(choices) <= n:
            return None
        if not item.get('mechanic'):
            return 1 / comb(len(choices), n)
        # Pack sorts its choices, then awards positional credit. Enumerate its
        # small choice set rather than assuming independent selections.
        scores = [sum(a == b for a, b in zip(answer, expected)) / n
                  for answer in combinations(choices, n)]
        return sum(scores) / len(scores)
    return None


def evidence_keys(item):
    """Stable content identity across shuffled options, sessions and games.

    Builders can supply exact sentence identities. Older rounds are derived
    from their frozen text. Radio questions share audio but test different facts.
    """
    texts = item.get('evidence_texts')
    if texts is None:
        if item.get('mechanic') == 'radio' and item.get('choices') and all(c.get('text') for c in item['choices']):
            texts = ['radio:' + '|'.join(c.get('audio_key', '') for c in item.get('clues', [])) + ':' + item.get('prompt', '')]
        elif item.get('left') or item.get('sentences'):
            texts = [entry['text'] for entry in item.get('left', item.get('sentences', []))]
        else:
            texts = [clue.get('text', '') for clue in item.get('clues', [])]
            if item.get('sentence'):
                choices = {c['id']: c.get('text', '') for c in item.get('choices', [])}
                texts.append(item['sentence'].replace('[[blank]]', choices.get(item['expected_answer'][0], '')))
    return {sha256(re.sub(r'\s+', ' ', text.casefold()).strip().encode()).hexdigest()
            for text in texts if text and text.strip()}


def expected_score(rating, difficulty, chance=0):
    return chance + (1 - chance) / (1 + 10 ** ((difficulty - rating) / 400))
