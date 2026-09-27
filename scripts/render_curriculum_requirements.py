#!/usr/bin/env python3
"""Render the inspected A1–B2 reference without importing app configuration."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))

from services.torfl_requirements import DOMAINS, LEVELS, reference_for_level, requirement_groups

OUTPUT = ROOT / 'docs' / 'curriculum-requirements.md'


def render():
    lines = [
        '# A1–B2 requirements catalogue', '',
        'This is an application authoring reference based on inspected TORFL publications. '
        'It defines observable tasks, not an official exam bank or a complete lexical minimum. '
        'See [research and assessment policy](curriculum-research.md) for editions, limits and progression decisions.', '',
        'Each level builds on the earlier levels. The requirements below are additions or developments. '
        'Topic teaching bands and word difficulty remain separate.', '',
        'The response mode is part of the requirement. Choosing an answer does not demonstrate independent writing or speaking. '
        'A source citation supports the language scope; it does not validate our task or pass threshold.', '',
        'Generated from `flask_vocab_app/data/torfl/` with `python scripts/render_curriculum_requirements.py`. '
        'Edit the catalogue, then regenerate this document. Use `--check` to verify it is current.', '',
    ]
    for level in LEVELS:
        data = reference_for_level(level)
        lines += [f'## {level}', '']
        if data['extends']:
            lines += [f'Includes the earlier {data["extends"]} requirements.', '']
        source_keys = {s['id']: f'{level.lower()}-{index}' for index, s in enumerate(data['sources'], 1)}
        groups = {group['id']: group for group in requirement_groups(level)['groups']}
        for domain, (title, _, mode) in DOMAINS.items():
            lines += [f'### {title}', '', f'Evidence mode: {mode.replace("_", " ")}.', '']
            sections = groups[domain]['sections'] or [{'label': None, 'items': groups[domain]['items']}]
            for section in sections:
                if section['label']:
                    lines += [f'#### {section["label"]}', '']
                for item in section['items']:
                    refs = '; '.join(f'[{ref["locator"]}][{source_keys[ref["source_id"]]}]' for ref in item['source_refs'])
                    lines += [f'- **{item["label_en"]}.** {item["expectation"]} '
                              f'`{item["id"]}` — {refs}']
                lines.append('')
        lines += ['### Sources', '']
        for source in data['sources']:
            key = source_keys[source['id']]
            lines += [f'- [{source["title"]}][{key}]. {source["edition"]}. {source["note"]}']
        lines.append('')
        for source in data['sources']:
            lines += [f'[{source_keys[source["id"]]}]: {source["url"]}']
        lines.append('')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if the document differs from the catalogue.')
    args = parser.parse_args()
    content = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != content:
            parser.exit(1, 'Curriculum requirements document is out of date. Run the renderer.\n')
        return
    OUTPUT.write_text(content, encoding='utf-8')


if __name__ == '__main__':
    main()
