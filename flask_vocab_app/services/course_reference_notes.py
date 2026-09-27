"""Editable reference examples, separate from frozen course assessments."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re

from services.course_releases import RELEASES, load_release

DATA_FILE = Path(__file__).resolve().parents[1] / 'data' / 'course_reference_notes.json'


def _text(value, limit):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and '\x00' not in value


def validate_reference_notes(data):
    """Require explicit categories and translated examples for known preparation."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    require(isinstance(data, dict) and type(data.get('version')) is int and data['version'] == 1,
            'Reference notes must use schema version 1.')
    releases = data.get('releases')
    require(isinstance(releases, dict) and bool(releases), 'Reference notes need a course release.')
    for release_id, preparation in releases.items():
        require(release_id in RELEASES and RELEASES[release_id]['status'] == 'published',
                'Reference notes must identify a published course release.')
        catalogue = load_release(release_id)
        expected = {item['id'] for chapter in catalogue['chapters']
                    for item in chapter.get('preparation', []) if item.get('id')}
        require(isinstance(preparation, dict) and bool(expected) and set(preparation) == expected,
                'Reference notes must cover the release preparation IDs exactly.')
        for entry in preparation.values():
            require(isinstance(entry, dict), 'Each preparation reference must contain groups.')
            groups = entry.get('groups')
            require(isinstance(groups, list) and 1 <= len(groups) <= 4,
                    'Each preparation reference needs 1–4 groups.')
            group_ids = set()
            item_count = 0
            for group in groups:
                require(isinstance(group, dict), 'Reference groups must be objects.')
                group_id = group.get('id')
                require(isinstance(group_id, str) and re.fullmatch(r'[a-z][a-z0-9-]{0,79}', group_id)
                        and group_id not in group_ids, 'Reference group IDs must be distinct within preparation.')
                group_ids.add(group_id)
                require(all(_text(group.get(field), 100) for field in ('title', 'title_ru')),
                        'Reference groups need short bilingual titles.')
                items = group.get('items')
                require(isinstance(items, list) and 1 <= len(items) <= 4,
                        'Reference groups need 1–4 examples.')
                item_count += len(items)
                for item in items:
                    require(isinstance(item, dict)
                            and all(_text(item.get(field), 100) for field in ('label', 'label_ru'))
                            and all(_text(item.get(field), 300) for field in ('ru', 'en')),
                            'Reference examples need short bilingual labels and translated sentences.')
            require(item_count <= 9, 'Each preparation reference allows at most nine examples.')
    return data


@lru_cache(maxsize=1)
def _catalogue():
    return validate_reference_notes(json.loads(DATA_FILE.read_text(encoding='utf-8')))


def reference_groups(release_id, preparation_id):
    """Return independent display data without changing course content or receipts."""
    if not preparation_id:
        return []
    entry = _catalogue()['releases'].get(release_id, {}).get(preparation_id, {})
    return deepcopy(entry.get('groups', []))
