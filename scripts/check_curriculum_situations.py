#!/usr/bin/env python3
"""Check fresh A1 situation generation; dry run unless --live is explicit.

Samples use authored teaching inputs, never a learner database. Listening samples
check text only: this command does not synthesize or play audio. Structural
acceptance is separate from Russian-language review, which remains pending.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
from types import SimpleNamespace
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))
MAX_CALLS = 12
MAX_OUTPUT_TOKENS = 6500
FORMAT_VERSION = 'curriculum-situation-check-v1'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def load_config(path=None):
    """Read only an explicitly selected env file; shell values take precedence."""
    values = {}
    if path is not None:
        from dotenv import dotenv_values
        path = Path(path)
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 65536:
            raise ValueError('Use a readable configuration file of at most 64 KiB.')
        values.update(dotenv_values(path, interpolate=False))
    values.update(os.environ)
    config = {name: value for name, value in values.items() if name.startswith('AI_TRIAL_')}
    config['OPENAI_API_KEY'] = values.get('OPENAI_API_KEY')
    config['OPENAI_MODEL_FLASHCARDS'] = (values.get('OPENAI_MODEL_FLASHCARDS') or 'gpt-5.6-luna').removeprefix('openai/')
    for name in ('AI_TRIAL_ENABLED', 'HOSTED_AI_TRIAL', 'PUBLIC_DEMO'):
        flag = str(values.get(name) or '').strip().lower()
        if flag not in {'', '0', 'false', 'no', 'off', '1', 'true', 'yes', 'on'}:
            raise ValueError('Hosted budget flags must be explicit booleans.')
        config[name] = flag in {'1', 'true', 'yes', 'on'}
    if not config['OPENAI_API_KEY'] or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,100}', config['OPENAI_MODEL_FLASHCARDS']):
        raise ValueError('Configured provider credentials and model are required.')
    if any(config[name] for name in ('AI_TRIAL_ENABLED', 'HOSTED_AI_TRIAL', 'PUBLIC_DEMO')):
        if set(name for name in config if name.startswith('AI_TRIAL_')) - {
                'AI_TRIAL_ENABLED', 'AI_TRIAL_IDENTITY', 'AI_TRIAL_LEDGER_PATH'}:
            # Today the application's limits are ledger-service constants, not
            # environment overrides. Never silently ignore an operator's cap.
            raise ValueError('This provider does not support extra trial settings; run through the configured application instead.')
        if (not config['AI_TRIAL_ENABLED'] or not config.get('AI_TRIAL_IDENTITY')
                or not config.get('AI_TRIAL_LEDGER_PATH') or not Path(config['AI_TRIAL_LEDGER_PATH']).is_file()):
            raise ValueError('Live hosted checks need an enabled, existing budget ledger and identity.')
    return config


def configured_provider(config):
    """Use the application's provider boundary, preserving any hosted budget."""
    from services.trial_provider import openai_client
    return SimpleNamespace(flashcard_model=config['OPENAI_MODEL_FLASHCARDS'],
        client=openai_client(config=config, api_key=config['OPENAI_API_KEY'], timeout=60, max_retries=0))


def new_output_directory(value):
    path = Path(value).absolute()
    if path.is_symlink():
        raise ValueError('The output directory must not be a symbolic link.')
    # Resolve parent aliases before checking containment and writing. This also
    # permits macOS's standard /tmp -> /private/tmp alias without weakening the
    # rule against output inside the source checkout.
    path = path.resolve()
    if path == ROOT or path.is_relative_to(ROOT) or path.exists() or not path.parent.is_dir():
        raise ValueError('Choose a new output directory outside the repository, with an existing parent.')
    return path


def make_plan(unit_ids=(), modes=('reading', 'listening'), *, limit=4, seed=None):
    from services import curriculum_situation_content as content
    from services.curriculum_units import DATA_DIR, UNIT_IDS, get_unit
    if type(limit) is not int or not 1 <= limit <= MAX_CALLS:
        raise ValueError('Choose a sample limit from 1 to 12.')
    selected = list(unit_ids) or list(UNIT_IDS)
    if len(selected) != len(set(selected)) or not set(selected) <= set(UNIT_IDS):
        raise ValueError('Choose distinct existing A1 unit IDs.')
    if not modes or len(modes) != len(set(modes)) or not set(modes) <= {'reading', 'listening'}:
        raise ValueError('Choose reading, listening or both modes.')
    seed = seed or uuid.uuid4().hex
    if not isinstance(seed, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', seed):
        raise ValueError('Use a seed of 1–80 letters, digits, dots, dashes or underscores.')
    cases = []
    pairs = [(uid, mode) for uid in selected for mode in modes]
    for index in range(limit):
        uid, mode = pairs[index % len(pairs)]
        sample_id = 'sample-' + str(index + 1).zfill(2)
        request = content.build_request(get_unit(uid), f'{seed}-{sample_id}', mode=mode)
        prompt = content.prompt_for(request) if hasattr(content, 'prompt_for') else None
        cases.append({'id': sample_id, 'unit_id': uid, 'mode': mode, 'request': request,
                      'request_sha256': digest(request),
                      'unit_sha256': hashlib.sha256((DATA_DIR / (uid + '.json')).read_bytes()).hexdigest(),
                      'schema_sha256': digest(content.provider_schema(request)),
                      'planned_system_messages_sha256': digest([{'role': 'system', 'content': prompt}]) if prompt else None})
    return {'format_version': FORMAT_VERSION, 'content_version': content.VERSION, 'seed': seed,
            'generator_sha256': hashlib.sha256(Path(content.__file__).read_bytes()).hexdigest(),
            'prompt_provenance': 'Each live sample hashes the exact system messages sent to the provider.',
            'maximum_calls': limit, 'maximum_output_tokens_per_call': MAX_OUTPUT_TOKENS,
            'automatic_retries': 0, 'audio_calls': 0, 'learner_data_used': False, 'samples': cases}


def sanitizer(secrets=()):
    secrets = tuple(value for value in secrets if isinstance(value, str) and value)
    def clean(value):
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, '[REDACTED]')
            return re.sub(r'\bsk-[A-Za-z0-9_-]{12,}\b', '[REDACTED]', value)
        if isinstance(value, dict):
            return {key: clean(child) for key, child in value.items()}
        if isinstance(value, (tuple, list)):
            return [clean(child) for child in value]
        return value
    return clean


def _field(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def usage_record(value):
    """Copy numeric usage only, never a whole SDK object or response headers."""
    result = {}
    for name in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'input_tokens', 'output_tokens'):
        number = _field(value, name)
        if type(number) is int and number >= 0:
            result[name] = number
    for name in ('prompt_tokens_details', 'completion_tokens_details', 'input_tokens_details', 'output_tokens_details'):
        details = _field(value, name)
        numbers = {key: _field(details, key) for key in ('cached_tokens', 'reasoning_tokens', 'audio_tokens', 'cache_write_tokens')
                   if type(_field(details, key)) is int and _field(details, key) >= 0}
        if numbers:
            result[name] = numbers
    return result or None


def validation_reason(error):
    """Expose only errors raised by our local validator, never provider bodies."""
    if isinstance(error, json.JSONDecodeError):
        return error.msg
    frame = error.__traceback__
    while frame is not None and frame.tb_next is not None:
        frame = frame.tb_next
    validator = ROOT / 'flask_vocab_app/services/curriculum_situation_content.py'
    if type(error) is ValueError and frame is not None and Path(frame.tb_frame.f_code.co_filename) == validator:
        return str(error)[:500]
    return None


def command_reason(error):
    frame = error.__traceback__
    while frame is not None and frame.tb_next is not None:
        frame = frame.tb_next
    if type(error) is ValueError and frame is not None and Path(frame.tb_frame.f_code.co_filename) == Path(__file__):
        return str(error)[:500]
    return None


class RecordingClient:
    """Retain assistant text before the normal generator validates its output."""
    def __init__(self, client, row, save, clean, state=None):
        self.client, self.row, self.save, self.clean = client, row, save, clean
        self.state = state if state is not None else {'calls': 0}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def with_options(self, **options):
        options['max_retries'] = 0
        return RecordingClient(self.client.with_options(**options), self.row, self.save, self.clean, self.state)

    def create(self, **kwargs):
        if self.state['calls'] or kwargs.get('n', 1) != 1 or kwargs.get('stream'):
            raise ValueError('The check permits one non-streaming provider call per sample.')
        if not 1 <= kwargs.get('max_completion_tokens', 0) <= MAX_OUTPUT_TOKENS:
            raise ValueError('The generation request exceeds the evaluation token cap.')
        self.state['calls'] += 1
        self.row.update(state='requesting', calls=1, provider_request=self.clean(deepcopy(kwargs)),
                        provider_request_sha256=digest(kwargs),
                        system_messages_sha256=digest([message for message in kwargs.get('messages', [])
                                                       if message.get('role') in ('system', 'developer')]))
        self.save()
        result = self.client.chat.completions.create(**kwargs)
        choices = _field(result, 'choices', [])
        choice = choices[0] if choices else None
        message = _field(choice, 'message')
        raw = _field(message, 'content')
        self.row.update(state='received', raw_response=self.clean(raw),
                        raw_response_sha256=hashlib.sha256(raw.encode()).hexdigest() if isinstance(raw, str) else None,
                        finish_reason=self.clean(_field(choice, 'finish_reason')),
                        refusal_present=bool(_field(message, 'refusal')),
                        received_model=self.clean(_field(result, 'model')),
                        usage=usage_record(_field(result, 'usage')))
        self.save()  # A local validation failure must not discard the paid output.
        return result


def evaluate(plan, directory, provider=None, *, secrets=()):
    from services.curriculum_situation_content import generate
    if not 1 <= len(plan['samples']) <= MAX_CALLS or plan['maximum_calls'] != len(plan['samples']):
        raise ValueError('Evaluation requires a bounded sample plan.')
    directory = new_output_directory(directory)
    directory.mkdir(mode=0o700)
    clean = sanitizer(secrets)
    report = {key: deepcopy(value) for key, value in plan.items() if key != 'samples'}
    report.update(at=datetime.now(timezone.utc).isoformat(), live=provider is not None,
                  configured_model=provider.flashcard_model if provider is not None else None,
                  state='running' if provider else 'dry_run', samples=[],
                  linguistic_review={'status': 'pending', 'reviewer': None, 'grammatical_acceptance': None},
                  proficiency_validated=False)
    output = directory / 'results.json'
    def save():
        temporary = directory / 'results.tmp'
        with temporary.open('w', encoding='utf-8') as handle:
            os.chmod(temporary, 0o600)
            handle.write(json.dumps(clean(report), ensure_ascii=False, indent=2) + '\n')
        temporary.replace(output)
    save()
    # Suppress library request/debug logs for this bounded run. Results contain
    # synthetic content only; provider exception strings are never persisted.
    logging_disabled = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        for sample in plan['samples']:
            row = {**deepcopy(sample), 'state': 'not_run', 'calls': 0,
                   'structural_acceptance': None, 'linguistic_review': 'pending', 'usage': None}
            report['samples'].append(row)
            save()
            if provider is None:
                continue
            recorder = RecordingClient(provider.client, row, save, clean)
            wrapped = SimpleNamespace(client=recorder, flashcard_model=provider.flashcard_model)
            started = time.monotonic()
            try:
                document = generate(sample['request'], wrapped)
                row.update(state='accepted', structural_acceptance=True, accepted_document=document)
            except Exception as error:
                # A returned completion rejected by local validation is distinct
                # from transport/auth/allowance failure. Neither proves language quality.
                received = 'raw_response' in row
                row.update(state='rejected' if received else 'provider_unavailable',
                           structural_acceptance=False if received else None,
                           error_type=type(error).__name__)
                if received:
                    row['validation_reason'] = validation_reason(error)
            finally:
                row['duration_seconds'] = round(time.monotonic() - started, 3)
                save()
            if row['state'] == 'provider_unavailable':
                break  # No implicit retries or further calls after provider failure.
        report['state'] = 'complete' if provider and len(report['samples']) == len(plan['samples']) and all(
            row['state'] != 'provider_unavailable' for row in report['samples']) else 'stopped' if provider else 'dry_run'
        report['summary'] = dict(Counter(row['state'] for row in report['samples']))
        report['provider_calls'] = sum(row['calls'] for row in report['samples'])
        save()
    finally:
        logging.disable(logging_disabled)
    return clean(report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Explicitly permit bounded provider calls.')
    parser.add_argument('--unit', action='append', default=[], dest='units', help='A1 unit ID; repeat to choose units.')
    parser.add_argument('--mode', choices=('reading', 'listening', 'both'), default='both')
    parser.add_argument('--limit', type=int, default=4, help='Total samples, including both modes; 1–12.')
    parser.add_argument('--seed', help='Reproducible batch seed; a new seed is generated if omitted.')
    parser.add_argument('--env-file', type=Path, help='Read this file only on --live; shell values take precedence.')
    parser.add_argument('--output-dir', type=Path, help='New external output directory with an existing parent; required for --live.')
    args = parser.parse_args(argv)
    try:
        if args.live and args.output_dir is None:
            raise ValueError('--live requires a new --output-dir outside the repository.')
        if args.output_dir is not None:
            new_output_directory(args.output_dir)
        modes = ('reading', 'listening') if args.mode == 'both' else (args.mode,)
        plan = make_plan(args.units, modes, limit=args.limit, seed=args.seed)
        provider = None
        if args.live:
            config = load_config(args.env_file)
            provider = configured_provider(config)
        if args.output_dir is not None:
            report = evaluate(plan, args.output_dir, provider,
                              secrets=[config['OPENAI_API_KEY']] if args.live else ())
            summary = {key: report[key] for key in ('state', 'summary', 'provider_calls', 'linguistic_review')}
        else:
            summary = {**{key: value for key, value in plan.items() if key != 'samples'}, 'state': 'dry_run',
                       'provider_calls': 0, 'samples': [{key: row[key] for key in ('id', 'unit_id', 'mode')} for row in plan['samples']]}
    except Exception as error:
        # Even constructor errors may include connection details. The CLI emits
        # only a safe class name; argparse itself reports invalid argument types.
        print(json.dumps({'state': 'unavailable', 'error_type': type(error).__name__,
                          'reason': command_reason(error)}))
        return 1
    finally:
        if 'provider' in locals() and provider is not None:
            try:
                provider.client.close()
            except Exception:
                pass
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary['state'] == 'stopped' or summary.get('summary', {}).get('rejected') else 0


if __name__ == '__main__':
    raise SystemExit(main())
