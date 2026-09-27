#!/usr/bin/env python3
"""Reproduce Writing regressions using authored responses, without learner data.

The default run validates fixtures and checks controlled forms without a provider.
--run-model explicitly enables up to eight selected Writing calls, through the
existing provider budget. Results are saved before moving on; reruns never retry
an interrupted/failed call automatically. Expectations are authored hypotheses,
not independent human labels or a proficiency validation.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


@contextmanager
def evaluation_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory / '.evaluation.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another evaluation is using this output directory. Let it finish before resuming.') from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def summarise(results):
    measured = [row for row in results if row['status'] == 'measured']
    matrix = Counter((row['expected'], row['actual']) for row in measured)
    return {
        'cases': len(results), 'measured': len(measured),
        'status_counts': dict(Counter(row['status'] for row in results)),
        'agreement_with_authored_expectations': sum(row['actual'] == row['expected'] for row in measured),
        'overstated_success': [row['case_id'] for row in measured if row['actual'] == 'satisfied' and row['expected'] != 'satisfied'],
        'missed_success': [row['case_id'] for row in measured if row['expected'] == 'satisfied' and row['actual'] != 'satisfied'],
        'abstentions': [row['case_id'] for row in measured if row['actual'] == 'insufficient_evidence'],
        'confusion': [{'expected': expected, 'actual': actual, 'count': count}
                      for (expected, actual), count in sorted(matrix.items())],
        'limitations': [
            'Authored expectations are hypotheses, not independent human ground truth.',
            'These are synthetic written responses, not real learner trials or speech measurements.',
            'No level result, course pass, reward or learner record is changed.',
        ],
    }


def evaluate(fixture, directory, *, assess=None, model=None, case_ids=()):
    # Hold a filesystem lock through the provider call and result publication.
    # The persistent claim file is never unlinked: all workers lock one inode.
    with evaluation_lock(directory):
        return _evaluate(fixture, directory, assess=assess, model=model, case_ids=case_ids)


def _evaluate(fixture, directory, *, assess=None, model=None, case_ids=()):
    from contracts.curriculum import validate_judgements
    from contracts.learning import assess_activity_answer
    from repositories.writing_repository import WritingRepository
    from services.curriculum_units import get_unit, _pack, writing_task

    directory = Path(directory)
    selected = set(case_ids)
    if selected - {case['id'] for case in fixture['cases']}:
        raise ValueError('Unknown case ID; choose an ID from the pinned fixture.')
    if assess is not None:
        paid = [case for case in fixture['cases'] if case['id'] in selected and case['stage'] == 'writing']
        if not selected or not 1 <= len(paid) <= 8 or len(paid) != len(selected):
            raise ValueError('Select one to eight Writing cases explicitly for model evaluation.')
    directory.mkdir(parents=True, exist_ok=True)
    service_hash = hashlib.sha256((ROOT / 'flask_vocab_app/services/writing_service.py').read_bytes()).hexdigest()
    results = []
    for case in fixture['cases']:
        if selected and case['id'] not in selected:
            continue
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,159}', case['id']):
            raise ValueError('Unsafe authored case ID.')
        unit = get_unit(case['unit_id'])
        task = writing_task(unit) if case['stage'] == 'writing' else next(
            item for item in _pack(unit, 'forms')['items'] if item['id'] == case['item_id'])
        identity = digest({'fixture': fixture, 'case': case, 'task': task,
                           'model': model, 'service_sha256': service_hash})
        path = directory / (case['id'] + '.json')
        if path.is_symlink():
            raise ValueError('Evaluation output must not be a symbolic link.')
        if path.exists():
            cached = json.loads(path.read_text())
            if cached.get('input_sha256') != identity:
                raise ValueError('Saved evaluation uses different content, code or model. Use a new output directory.')
            results.append(cached)
            continue
        row = {'case_id': case['id'], 'unit_id': case['unit_id'], 'stage': case['stage'],
               'input_sha256': identity, 'fixture_id': fixture['id'], 'model': model,
               'service_sha256': service_hash, 'original_response': case['response'],
               'support': case['support'], 'expected': case['author_expectation']['outcome'],
               'status': 'not_run', 'actual': None}
        if case['stage'] == 'forms':
            _, correct = assess_activity_answer(task, {'text': case['response']})
            row.update(status='measured', actual='satisfied' if correct else 'not_satisfied', assessor='authored_matcher')
        elif assess is not None:
            try:
                WritingRepository.validate_answer(case['response'], checking=True)
            except ValueError:
                row.update(status='input_rejected', assessor='input_validation')
            else:
                # Persist before requesting feedback. A crash cannot turn a rerun
                # into an invisible second charge; the operator sees interrupted.
                row.update(status='interrupted', contract_sha256=task['curriculum_contract']['contract_sha256'])
                write_json(path, row)
                try:
                    assessment = assess(unit, task, case['response'])
                    report = assessment['criterion_report']
                    WritingRepository.validate_assessment(assessment)
                    validate_judgements(task['curriculum_contract'], report, response_text=case['response'])
                    if len(report['judgements']) != 1:
                        raise ValueError('This fixture expects one communicative criterion per unit.')
                    row.update(status='measured', actual=report['judgements'][0]['outcome'],
                               assessment=assessment, independent=not bool(case['support']), assessor='configured_model')
                except Exception as error:
                    # Provider exception strings can contain request details. Keep
                    # the type only; never serialize keys or connection settings.
                    row.update(status='failed', error_type=type(error).__name__)
                    write_json(path, row)
                    results.append(row)
                    break  # Stop on failure; no automatic retry or further spend.
        write_json(path, row)
        results.append(row)
    report = {'fixture_id': fixture['id'], 'summary': summarise(results), 'results': results}
    ledger_path = directory / 'evaluation-budget.sqlite3'
    if assess is not None and ledger_path.is_file():
        with sqlite3.connect(ledger_path) as conn:
            report['allowance_charge_usd'] = conn.execute(
                'SELECT COALESCE(SUM(COALESCE(actual,reserved)),0)/1000000.0 FROM trial_requests').fetchone()[0]
    write_json(directory / 'results.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', action='append', default=[], dest='case_ids')
    parser.add_argument('--run-model', action='store_true')
    parser.add_argument('--env-file', action='append', type=Path, default=[])
    args = parser.parse_args(argv)
    # Load credentials read-only before importing application defaults. Neither
    # the Flask application nor any personal vocabulary database is opened.
    if args.run_model:
        from dotenv import load_dotenv
        for path in args.env_file:
            if not path.is_file():
                parser.error('The configuration file does not exist.')
            load_dotenv(path, override=False)
    import prepare_curriculum_review as packets
    fixture = packets.read_fixture(args.fixture or packets.CURRENT_FIXTURE)
    assess = model = None
    if args.run_model:
        from config import app_config
        from services.ai_trial_budget import AITrialBudget
        from services.writing_service import WritingService
        config = app_config()
        if not config.get('OPENAI_API_KEY'):
            parser.error('Configured provider credentials are required.')
        writing_ids = {case['id'] for case in fixture['cases'] if case['stage'] == 'writing'}
        if not 1 <= len(set(args.case_ids)) <= 8 or not set(args.case_ids) <= writing_ids:
            parser.error('Select one to eight Writing case IDs with --case.')
        args.output.mkdir(parents=True, exist_ok=True)
        ledger_path = args.output / 'evaluation-budget.sqlite3'
        if ledger_path.is_symlink():
            parser.error('The evaluation ledger must not be a symbolic link.')
        ledger = AITrialBudget(ledger_path, enabled=True)
        ledger.initialize()
        ledger.authorize_identity('authored-curriculum-evaluation')
        config.update(AI_TRIAL_ENABLED=True, AI_TRIAL_LEDGER_PATH=str(ledger_path),
                      AI_TRIAL_IDENTITY='authored-curriculum-evaluation')
        service = WritingService(None, None, config['OPENAI_API_KEY'], config=config)
        model = config['OPENAI_MODEL_FAST']
        def assess(unit, task, response):
            return service.assess_writing(task['task'], task['required_words'], 30, response,
                difficulty=unit['level'], language='en', topic=unit['topic_id'],
                curriculum_contract=task['curriculum_contract'], include_provenance=True)
    try:
        report = evaluate(fixture, args.output, assess=assess, model=model, case_ids=args.case_ids)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({key: value for key, value in report.items() if key != 'results'}, ensure_ascii=False, indent=2))
    return 1 if any(row['status'] in ('failed', 'interrupted') for row in report['results']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
