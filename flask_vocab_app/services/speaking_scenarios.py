"""Built-in Speaking fixtures used by migrations and offline test tools.

The running application reads its editable catalogue from SQLite through
repositories.speaking_repository. This file no longer owns a competing copy
of the café curriculum. Saved conversations always use their own snapshots.
"""
from copy import deepcopy
import json
from pathlib import Path
import random

_DATA = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'speaking_catalogue.json').read_text())
_VARIANTS = {variant['seed']: variant for scenario in _DATA['scenarios'] for variant in scenario['variants']}
SEEDS = tuple(_VARIANTS)


def build_scenario(seed):
    """Return an independent built-in snapshot, for offline tools and tests."""
    if not isinstance(seed, str) or seed not in _VARIANTS:
        raise ValueError('Unknown speaking scenario seed.')
    return deepcopy(_VARIANTS[seed])


def choose_scenario(previous_seeds=()):
    """Compatibility helper for offline tools; live selection is DB-backed."""
    recent = list(dict.fromkeys(seed for seed in previous_seeds if isinstance(seed, str) and seed in _VARIANTS))
    available = [seed for seed in SEEDS if seed not in recent]
    return build_scenario(random.choice(available) if available else recent[-1])
