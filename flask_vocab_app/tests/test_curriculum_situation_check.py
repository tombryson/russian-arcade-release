"""Offline generation checks retain evidence without inventing language review."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.test_curriculum_situation_content import legacy_build_request, situation_response, provider_response

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('situation_check', ROOT / 'scripts/check_curriculum_situations.py')
command = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command)


class SituationCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve() / 'new-check'
        # The authored provider replies below belong to source-v2. Preserve
        # that contract for journal/cost/failure tests; other plan tests still
        # exercise the current generator and its stricter language policy.
        with patch('services.curriculum_situation_content.build_request', side_effect=legacy_build_request):
            self.plan = command.make_plan(['present-actions-v1'], limit=2, seed='test-batch')

    def provider(self, outputs):
        client = Mock()
        client.with_options.return_value = client
        def answer(**kwargs):
            value = outputs.pop(0)
            if isinstance(value, BaseException):
                raise value
            return SimpleNamespace(model='configured-model', choices=[SimpleNamespace(
                finish_reason='stop', message=SimpleNamespace(content=value, refusal=None))],
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=200, total_tokens=300,
                    private_token='not-for-report'))
        client.chat.completions.create.side_effect = answer
        return SimpleNamespace(client=client, flashcard_model='configured-model')

    def wire(self, sample):
        response = provider_response(situation_response(sample['request']),
            legacy=sample['request'].get('generation_revision') is None)
        return json.dumps(response, ensure_ascii=False)

    def test_default_cli_does_not_load_credentials_create_provider_or_write(self):
        with patch.object(command, 'load_config') as config, patch.object(command, 'configured_provider') as provider:
            output = io.StringIO()
            with redirect_stdout(output):
                result = command.main(['--unit', 'calendar-and-duration-v1', '--limit', '2', '--seed', 'dry',
                                       '--env-file', '/does/not/exist'])
            self.assertEqual(result, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report['state'], 'dry_run')
            self.assertEqual(report['provider_calls'], 0)
            self.assertEqual({s['mode'] for s in report['samples']}, {'reading', 'listening'})
            config.assert_not_called()
            provider.assert_not_called()
        self.assertFalse(self.directory.exists())

    def test_synthetic_vocabulary_profiles_reach_writer_without_claiming_known_grammar(self):
        plan = command.make_plan(['location-destination-v1'], limit=2, seed='lexical-inputs',
                                 vocabulary_profile='places-visits')
        self.assertFalse(plan['learner_data_used'])
        self.assertEqual(plan['vocabulary_fixture'], command.VOCABULARY_PROFILES['places-visits'])
        for sample in plan['samples']:
            request = sample['request']
            self.assertIn('библиотека', request['known_lemmas'])
            rows = {row['lemma']: row for row in request['writer_brief']['familiar_words']}
            self.assertEqual(rows['музей']['forms'], ['музей', 'музее'])
            self.assertNotIn('музеем', rows['музей']['forms'])
        plan['vocabulary_fixture'].clear()
        self.assertTrue(command.VOCABULARY_PROFILES['places-visits'])
        with self.assertRaises(ValueError):
            command.make_plan(vocabulary_profile='private-user')

    def test_full_passage_observations_do_not_treat_all_unknown_candidates_as_errors(self):
        request = {'known_lemmas': ['книга', 'читать'],
                   'vocabulary': [{'lemma': 'книга', 'forms': ['книгу']}]}
        document = {'response': {'text': 'Анна читает книгу. Потом она думает о музыке.'}}
        observations = command.lexical_observations(request, document)
        self.assertEqual(observations['familiar_fixture_lemmas_used'], ['книга'])
        candidates = {row['form']: row for row in observations['outside_known_lemma_candidates']}
        self.assertNotIn('читает', candidates)
        self.assertTrue(candidates['Анна']['possible_name'])
        self.assertIn('музыка', candidates['музыке']['possible_lemmas'])
        self.assertNotIn('unfamiliar_word_count', observations)

    def test_cost_report_is_a_labelled_budget_estimate_not_a_bill(self):
        cost = command.estimated_cost('gpt-5.6-luna', {'prompt_tokens': 1000, 'completion_tokens': 1000})
        self.assertAlmostEqual(cost['usd'], 0.0014)
        self.assertIn('Not a provider invoice', cost['basis'])
        self.assertIsNone(command.estimated_cost('unknown-model', {'prompt_tokens': 10, 'completion_tokens': 20}))

    def test_optional_dry_output_contains_requests_but_no_claim_of_acceptance(self):
        with patch('services.curriculum_situation_content.generate') as generate:
            report = command.evaluate(self.plan, self.directory)
        generate.assert_not_called()
        self.assertEqual(report['provider_calls'], 0)
        self.assertEqual(report['audio_calls'], 0)
        self.assertEqual(report['linguistic_review']['status'], 'pending')
        self.assertTrue(all(row['structural_acceptance'] is None for row in report['samples']))
        self.assertEqual(report['samples'][0]['request'], self.plan['samples'][0]['request'])
        self.assertEqual(json.loads((self.directory / 'results.json').read_text()), report)

    def test_accepted_response_records_usage_and_hashes_without_grammatical_claim(self):
        raw = [self.wire(sample) for sample in self.plan['samples']]
        provider = self.provider(raw.copy())
        report = command.evaluate(self.plan, self.directory, provider)
        self.assertEqual(report['summary'], {'accepted': 2})
        self.assertEqual(report['provider_calls'], 2)
        self.assertEqual(report['linguistic_review']['grammatical_acceptance'], None)
        self.assertFalse(report['proficiency_validated'])
        for index, row in enumerate(report['samples']):
            self.assertEqual(row['raw_response'], raw[index])
            self.assertEqual(row['usage'], {'prompt_tokens': 100, 'completion_tokens': 200, 'total_tokens': 300})
            self.assertTrue(row['structural_acceptance'])
            self.assertEqual(row['linguistic_review'], 'pending')
            self.assertRegex(row['raw_response_sha256'], r'^[a-f0-9]{64}$')
            self.assertRegex(row['unit_sha256'], r'^[a-f0-9]{64}$')
            self.assertRegex(row['schema_sha256'], r'^[a-f0-9]{64}$')
            self.assertEqual(row['system_messages_sha256'], command.digest([
                message for message in row['provider_request']['messages'] if message['role'] in ('system', 'developer')]))
            if row['planned_system_messages_sha256']:
                self.assertEqual(row['planned_system_messages_sha256'], row['system_messages_sha256'])
            self.assertGreaterEqual(row['duration_seconds'], 0)
            self.assertEqual(row['provider_request']['model'], 'configured-model')
        self.assertNotIn('not-for-report', json.dumps(report))
        self.assertTrue(all(call.kwargs['max_retries'] == 0 for call in provider.client.with_options.call_args_list))

    def test_validation_rejection_keeps_raw_response_before_next_sample(self):
        provider = self.provider(['{broken', self.wire(self.plan['samples'][1])])
        report = command.evaluate(self.plan, self.directory, provider)
        rejected = report['samples'][0]
        self.assertEqual(rejected['state'], 'rejected')
        self.assertEqual(rejected['raw_response'], '{broken')
        self.assertEqual(rejected['error_type'], 'JSONDecodeError')
        self.assertTrue(rejected['validation_reason'])
        self.assertEqual(report['samples'][1]['state'], 'accepted')
        self.assertEqual(provider.client.chat.completions.create.call_count, 2)
        self.assertEqual(report['state'], 'complete')

    def test_provider_failure_stops_batch_and_does_not_save_secret_error_body(self):
        provider = self.provider([RuntimeError('api_key=private-secret request payload')])
        report = command.evaluate(self.plan, self.directory, provider, secrets=['private-secret'])
        self.assertEqual(report['state'], 'stopped')
        self.assertEqual(report['samples'][0]['state'], 'provider_unavailable')
        self.assertEqual(report['samples'][0]['error_type'], 'RuntimeError')
        self.assertEqual(report['provider_calls'], 1)
        self.assertNotIn('private-secret', (self.directory / 'results.json').read_text())
        self.assertNotIn('request payload', json.dumps(report))
        with self.assertRaises(ValueError):
            command.evaluate(self.plan, self.directory, provider)
        self.assertEqual(provider.client.chat.completions.create.call_count, 1)

    def test_response_redaction_preserves_raw_digest_but_never_secret_values(self):
        raw = 'this reply accidentally repeats test-provider-credential'
        provider = self.provider([raw])
        report = command.evaluate(command.make_plan(['present-actions-v1'], limit=1, seed='test'),
                                  self.directory, provider, secrets=['test-provider-credential'])
        self.assertEqual(report['samples'][0]['raw_response'], 'this reply accidentally repeats [REDACTED]')
        self.assertNotIn('test-provider-credential', (self.directory / 'results.json').read_text())
        self.assertTrue(report['samples'][0]['raw_response_sha256'])

    def test_interrupted_call_is_durable_and_cannot_be_retried_into_same_directory(self):
        provider = self.provider([KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            command.evaluate(self.plan, self.directory, provider)
        report = json.loads((self.directory / 'results.json').read_text())
        self.assertEqual(report['samples'][0]['state'], 'requesting')
        with self.assertRaises(ValueError):
            command.evaluate(self.plan, self.directory, provider)
        self.assertEqual(provider.client.chat.completions.create.call_count, 1)

    def test_limits_invalid_units_paths_and_missing_live_output_fail_before_provider(self):
        arguments = [
            ['--limit', '0'], ['--limit', '13'], ['--unit', 'not-a-unit'],
            ['--seed', '../bad'], ['--live'], ['--live', '--output-dir', str(ROOT / 'inside')],
            ['--live', '--output-dir', str(self.directory.parent)],
            ['--live', '--output-dir', str(self.directory / 'missing-parent')],
        ]
        with patch.object(command, 'load_config') as config, patch.object(command, 'configured_provider') as provider:
            for args in arguments:
                with self.subTest(args=args), redirect_stdout(io.StringIO()):
                    self.assertEqual(command.main(args), 1)
            config.assert_not_called()
            provider.assert_not_called()
        alias = self.directory.parent / 'alias'
        alias.symlink_to(self.directory.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            command.new_output_directory(alias)
        self.assertEqual(command.new_output_directory(alias / 'fresh'), self.directory.parent / 'fresh')
        source_alias = self.directory.parent / 'source-alias'
        source_alias.symlink_to(ROOT, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'outside the repository'):
            command.new_output_directory(source_alias / 'new-report')
        self.assertEqual(len(command.make_plan(limit=12, seed='upper-bound')['samples']), 12)

    def test_environment_file_is_read_only_shell_wins_and_configured_model_is_preserved(self):
        path = self.directory.parent / 'explicit.env'
        ledger = self.directory.parent / 'existing-ledger.sqlite3'
        ledger.touch()
        original = ('OPENAI_API_KEY=file-secret\nOPENAI_MODEL_FLASHCARDS=openai/gpt-6-astra\n'
                    'AI_TRIAL_ENABLED=true\nAI_TRIAL_IDENTITY=verified-identity\n'
                    'AI_TRIAL_LEDGER_PATH=' + str(ledger) + '\n')
        path.write_text(original)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'shell-secret'}, clear=True):
            config = command.load_config(path)
        self.assertEqual(config['OPENAI_API_KEY'], 'shell-secret')
        self.assertEqual(config['OPENAI_MODEL_FLASHCARDS'], 'gpt-6-astra')
        self.assertTrue(config['AI_TRIAL_ENABLED'])
        self.assertEqual(path.read_text(), original)
        with patch('services.trial_provider.openai_client') as client:
            command.configured_provider(config)
        self.assertEqual(client.call_args.kwargs['config'], config)
        self.assertEqual(client.call_args.kwargs['max_retries'], 0)

    def test_hosted_configuration_never_falls_back_to_unmetered_calls(self):
        configurations = [
            {'HOSTED_AI_TRIAL': 'true'},
            {'AI_TRIAL_ENABLED': 'true', 'AI_TRIAL_IDENTITY': 'someone'},
            {'AI_TRIAL_ENABLED': 'unknown'},
            {'PUBLIC_DEMO': 'true', 'AI_TRIAL_ENABLED': 'false'},
            {'AI_TRIAL_ENABLED': 'true', 'AI_TRIAL_DAILY_LIMIT': '1'},
        ]
        for values in configurations:
            with self.subTest(values=values), patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', **values}, clear=True):
                with self.assertRaises(ValueError):
                    command.load_config()

    def test_recording_wrapper_rejects_hidden_second_request_and_excess_output(self):
        provider = self.provider(['{}'])
        row, save = {}, Mock()
        client = command.RecordingClient(provider.client, row, save, lambda v: v)
        with self.assertRaises(ValueError):
            client.create(max_completion_tokens=6501)
        provider.client.chat.completions.create.assert_not_called()
        client.create(max_completion_tokens=6500)
        with self.assertRaises(ValueError):
            client.with_options(timeout=60).create(max_completion_tokens=6500)
        provider.client.chat.completions.create.assert_called_once()


if __name__ == '__main__':
    unittest.main()
