#!/usr/bin/env python3
"""Render provisional definition links and actual shipped static content."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))
from services.curriculum_requirement_map import coverage_report
from services.curriculum_units import UNIT_IDS, LISTENING_IDS, get_unit, listening_content
from services.torfl_requirements import LEVELS

OUTPUT = ROOT / 'docs' / 'curriculum-coverage.md'


def render():
    data = coverage_report()
    lines = [
        '# Curriculum coverage inventory', '',
        'Generated with `python scripts/render_curriculum_coverage.py`; use `--check` to verify this document.', '',
        'This is a provisional model-reviewed crosswalk. It has not been validated by a human Russian-language assessor. '
        'Definitions have been compared individually; shared topics alone do not establish equivalence. '
        'The map never transfers learner grades or changes course progression.', '',
        'All 239 source requirements and 110 legacy targets are listed. Later-level inheritance is not counted twice. '
        'Requirement counts are not proficiency weights.', '',
        '## Status', '',
        '| Relation | Links |', '| --- | ---: |',
    ]
    for relation in ('equivalent', 'partial', 'related', 'unmapped'):
        lines.append(f"| {relation} | {data['mapping_counts'].get(relation, 0)} |")
    lines += ['', '**Equivalent** compares the scope and response mode of two definitions; it does not certify a task or transfer history. '
              '**Partial** covers a narrower compatible capability. **Related** authorises no evidence transfer. '
              '**Unmapped** has no suitable new-reference link.', '',
              'The static inventory includes the 32 focused preparation items and target-linked questions in published course releases. '
              'Counts below are candidate associations through equivalent or partial definition links. '
              'They do not mean the full requirement is taught or assessed. Related-only links contribute no item counts.', '',
              f"Shipped target-linked items: {data['shipped_item_counts']}. "
              f"A further {len(data['unattributed_items'])} legacy questions or optional writing prompts have no item-level target contract in this inventory.", '',
              'Runtime-generated tasks are not part of this static count. Source editions beyond those inspected, complete lexical minima, and human assessment validation remain unaudited. '
              'Independent production and whole-level assessment coverage must be established separately. '
              'Authored unit contracts are listed separately below; they remain practice/diagnostic tasks, not validated level assessments. '
              'A task count is never a release-readiness claim.', '',
              '## Authored teaching units', '',
              '| Unit | Contextual choices | Typed forms | Prepared listening items |',
              '| --- | ---: | ---: | ---: |']
    for unit_id in UNIT_IDS:
        unit = get_unit(unit_id)
        listening_count = len(listening_content(unit_id)['items']) if unit_id in LISTENING_IDS else 0
        lines.append(f"| {unit['title']} (`{unit_id}`) | {len(unit['questions'])} | {len(unit['forms']['questions'])} | {listening_count} |")
    lines += ['', 'Each unit also opens its own Writing task. A zero listening count means that no listening activity is offered for that unit. '
              'Speaking links to existing scenarios do not automatically add a unit-specific Speaking criterion. '
              'See [the validation record and reviewer workflow](curriculum-validation.md) for the pending language and learner review.', '',
              f"There are {len(data['direct_task_contracts'])} directly authored task definitions linked to "
              f"{len({item['requirement_id'] for item in data['direct_task_contracts']})} reference requirements. "
              'These counts include the narrow mapped Speaking diagnostics listed below.', '',
              '## Authored reference tasks', '',
              '| Task | Requirement | Kind |', '| --- | --- | --- |']
    for item in data['direct_task_contracts']:
        lines.append(f"| `{item['id']}` | `{item['requirement_id']}` | {item['kind']} |")
    lines += ['', 'These task definitions use frozen contracts at runtime. They do not establish full requirement coverage, '
              'human validation or independent proficiency. The mapped A1 Speaking situations have a narrow original-audio diagnostic; '
              'support independence remains unverified. Controlled-text items are application practice targets, not a change to the source exam format.', '']
    for level in LEVELS:
        lines += [f'## {level} requirement coverage', '',
                  '| Requirement | Legacy definition links | Teaching / practice / checkpoint candidates | Authored reference tasks |',
                  '| --- | --- | --- | ---: |']
        for row in data['requirements']:
            if row['level'] != level:
                continue
            links = '<br>'.join(f"`{link['legacy_target_id']}` ({link['relation']})" for link in row['legacy_links']) or 'Unallocated'
            counts = f"{row['teaching_item_count']} / {row['practice_item_count']} / {row['checkpoint_item_count']}"
            lines.append(f"| `{row['requirement_id']}` — {row['label_en']} | {links} | {counts} | {len(row['direct_task_contracts'])} |")
        lines += ['', 'Every row above remains **not validated** for new-reference assessment. '
                  'Source locators and response modes are recorded in [the requirements catalogue](curriculum-requirements.md).', '']
    lines += ['## Legacy target crosswalk', '',
              '| Legacy target | Reference / relation | Scope and limitation |', '| --- | --- | --- |']
    for row in data['legacy_mappings']:
        if not row['links']:
            lines.append(f"| `{row['legacy_target_id']}` | Unmapped | {row['unmapped_reason']} |")
        for link in row['links']:
            lines.append(f"| `{row['legacy_target_id']}` | `{link['requirement_id']}` / {link['relation']} | {link['rationale']} |")
    lines += ['', '## Traceability', '',
              'The machine-readable report includes each candidate item ID, source file and content hash. '
              'Published catalogues are read through their existing hash-checked release loader. '
              'Legacy definitions also have hashes: changing a definition requires an explicit mapping review.', '',
              'No learner database is opened. No answers, personal vocabulary, recordings or profile states appear in this report.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    rendered = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != rendered:
            parser.exit(1, 'Curriculum coverage is out of date; run the renderer.\n')
    else:
        OUTPUT.write_text(rendered, encoding='utf-8')


if __name__ == '__main__':
    main()
