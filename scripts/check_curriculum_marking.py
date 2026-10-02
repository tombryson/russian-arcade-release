"""Bounded smoke check of the real Writing assessor on synthetic Russian.

Dry run by default. This checks communication/grammar separation and natural
alternatives. It is neither independent language review nor exam validation.
No learner database or learner response is read. Stops on provider failure.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))

CASES = (
    ('correct', 'Я в школе. Иду в библиотеку. Встретимся в библиотеке.', 'satisfied', None),
    ('wrong-ending', 'Я в школе. Иду в библиотека. Встретимся в библиотеке.', 'not_satisfied', None),
    ('natural-alternative', 'Я в школе. Иду к библиотеке. Встретимся у библиотеки.', 'insufficient_evidence', 'valid_alternative'),
    ('omitted-details', 'Я в школе.', 'insufficient_evidence', 'feature_not_used'),
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--case', choices=[case[0] for case in CASES], action='append')
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    for path in args.env_file:
        if not path.is_file():
            parser.error('The configuration file does not exist.')
        load_dotenv(path, override=False)
    from services.curriculum_sequence_content import load_asset, task_contract
    asset = load_asset('location-message-v2')
    cases = [case for case in CASES if not args.case or case[0] in args.case]
    if not args.execute:
        print(json.dumps({'asset': asset['id'], 'requests': len(cases), 'max_output_tokens_per_request': 4096,
                          'cases': [case[0] for case in cases], 'execute': False}))
        return 0
    from config import app_config, model_for
    from services.writing_service import WritingService
    from services.trial_provider import openai_client
    config = app_config()
    if not config.get('OPENAI_API_KEY'):
        parser.error('The configured writing service is unavailable.')
    service = WritingService(None, None, config['OPENAI_API_KEY'], config=config)
    service.client = openai_client(config=config, api_key=config['OPENAI_API_KEY'], max_retries=0, timeout=60.0)
    result = {'kind': 'synthetic-provider-smoke-check', 'at': datetime.now(timezone.utc).isoformat(),
              'model': model_for('OPENAI_MODEL_FAST'), 'asset': asset['id'], 'cases': [],
              'independent_review': False, 'proficiency_validated': False}
    for identity, text, expected_outcome, expected_reason in cases:
        contract = task_contract(asset, 'synthetic-' + identity)
        try:
            checked = service.assess_writing(asset['content']['task'], asset['content']['required_words'], 30,
                text, difficulty='A1', language='en', topic='places', curriculum_contract=contract, include_provenance=True)
        except Exception as error:
            # Exception bodies can contain provider details. Only persist type.
            result['cases'].append({'id': identity, 'state': 'unavailable', 'error_type': type(error).__name__})
            if isinstance(error.__cause__, ValueError):
                result['cases'][-1]['validation_error'] = str(error.__cause__)
            break
        rows = {row['criterion_id']: row for row in checked['criterion_report']['judgements']}
        destination = rows['destination-form']
        expected_communication = ('satisfied', 'not_satisfied', 'not_satisfied') if identity == 'omitted-details' else ('satisfied',) * 3
        passed = (destination['outcome'] == expected_outcome and destination['reason_code'] == expected_reason
                  and tuple(rows[c]['outcome'] for c in ('current-place', 'next-place', 'meeting-place')) == expected_communication)
        result['cases'].append({'id': identity, 'state': 'passed' if passed else 'disagreement', 'response': text,
                               'contract_sha256': contract['contract_sha256'],
                               'judgements': checked['criterion_report']['judgements'],
                               'assessor': checked['assessment_provenance']})
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    result['passed'] = len(result['cases']) == len(cases) and all(c['state'] == 'passed' for c in result['cases'])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'model': result['model'], 'cases': [{k: c[k] for k in ('id', 'state')} for c in result['cases']],
                      'passed': result['passed']}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
