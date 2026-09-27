from concurrent.futures import Future
import base64
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services.speaking_lifecycle import NaturalEnding
from services.trial_live_delegation import TrialLiveDelegation

SCENARIO = {'scenario_id': 'cafe', 'goals': ['Order tea'], 'goals_ru': ['Закажите чай'],
            'worker_brief': 'Serve tea', 'menu': {'чай': 100}}


class TrialDelegationTests(unittest.TestCase):
    def setUp(self):
        self.ending = NaturalEnding(SCENARIO)
        self.handler = TrialLiveDelegation({'CONVERSATION_MODEL': 'gpt-5.6-luna'}, SCENARIO, self.ending)
        self.addCleanup(self.handler.close)
        self.handler.executor.shutdown(wait=True)
        self.handler.executor = Mock()
        self.future = Future()
        self.handler.executor.submit.return_value = self.future

    def transcript(self, text, role='input', event_id='text1', end=100):
        event = {'type': f'session.{role}_transcript.delta', 'event_id': event_id,
                 'delta': text, 'start_ms': 0, 'end_ms': end}
        self.ending.receive(event, now=10)
        return self.handler.receive(event)

    def delegate(self, identifier='opaque-id', **extra):
        return self.handler.receive({'type': 'session.delegation.created', 'delegation': {
            'id': identifier, 'target': 'client', **extra}})

    def test_only_client_delegations_call_backend_and_original_id_is_preserved(self):
        self.transcript('Чай, пожалуйста.')
        self.delegate(target='responses')
        self.handler.executor.submit.assert_not_called()
        self.delegate()
        self.delegate()  # Duplicated metadata must not start another paid call.
        self.handler.executor.submit.assert_called_once()
        self.future.set_result({'reply': 'Чай стоит сто рублей.', 'finish': None})
        commands = self.handler.tick()
        self.assertEqual(commands[0]['delegation_id'], 'opaque-id')
        self.assertEqual(commands[0]['type'], 'session.thinking.append')
        self.assertEqual(self.handler.tick(), [])

    def test_transcript_fragments_keep_role_and_duplicate_events_are_ignored(self):
        self.transcript('Мне ')
        self.transcript('Мне ')
        self.transcript('чай.', event_id='text2')
        self.transcript('Пожалуйста.', role='output', event_id='text3')
        self.delegate()
        history = self.handler.executor.submit.call_args.args[1]
        self.assertEqual(history, [{'role': 'user', 'content': 'Мне чай.'},
                                   {'role': 'assistant', 'content': 'Пожалуйста.'}])

    def test_pending_and_per_session_call_limits_prevent_more_provider_work(self):
        self.transcript('Мне чай.')
        self.delegate('first')
        self.assertEqual(self.delegate('second')[0]['type'], 'session.thinking.append')
        self.handler.executor.submit.assert_called_once()
        self.future.set_result({'reply': 'Хорошо.', 'finish': None})
        self.handler.tick()
        replacement = Future()
        self.handler.executor.submit.return_value = replacement
        self.delegate('third')
        replacement.set_result({'reply': 'Хорошо.', 'finish': None})
        self.handler.tick()
        self.delegate('fourth')
        self.assertEqual(self.handler.executor.submit.call_count, 2)

    def test_backend_errors_do_not_leak_exception_text_or_retry(self):
        self.transcript('Мне чай.')
        self.delegate()
        self.future.set_exception(RuntimeError('private provider details'))
        commands = self.handler.tick()
        self.assertNotIn('private', json.dumps(commands))
        self.handler.executor.submit.assert_called_once()

    def test_new_learner_speech_invalidates_delayed_ending(self):
        self.transcript('До свидания.')
        self.delegate()
        self.transcript('Подождите, ещё вопрос.', event_id='new', end=200)
        self.future.set_result({'reply': '', 'finish': {'reason': 'learner_finished',
            'learner_quote': 'До свидания.', 'goal_evidence': []}})
        self.assertEqual(self.handler.tick()[0]['type'], 'session.thinking.append')
        self.assertFalse(self.ending.pending)

    def test_ending_needs_real_quote_and_reflected_farewell(self):
        self.transcript('До свидания.')
        self.delegate()
        self.future.set_result({'reply': '', 'finish': {'reason': 'learner_finished',
            'learner_quote': 'До свидания.', 'goal_evidence': []}})
        self.assertEqual(self.handler.tick()[0]['type'], 'session.instructions.append')
        self.assertTrue(self.ending.pending)
        self.assertIsNone(self.ending.tick())
        self.assertFalse(self.ending.propose_client_ending(json.dumps({
            'reason': 'task_complete', 'learner_quote': 'Мне кофе.', 'goal_evidence': []}), 'other'))

    def test_close_drops_results_and_new_delegations(self):
        self.transcript('Мне чай.')
        self.delegate()
        self.handler.close()
        self.assertEqual(self.handler.tick(), [])
        self.assertEqual(self.delegate('later'), [])
        self.handler.executor.shutdown.assert_called_with(wait=False, cancel_futures=True)

    def test_close_does_not_shutdown_the_tenant_executor(self):
        executor = Mock()
        future = Future()
        executor.submit.return_value = future
        handler = TrialLiveDelegation({}, SCENARIO, self.ending, executor=executor)
        handler.receive({'type': 'session.input_transcript.delta', 'delta': 'Привет.'})
        handler.receive({'type': 'session.delegation.created', 'delegation': {'id': 'work', 'target': 'client'}})
        handler.close()
        self.assertTrue(future.cancelled())
        executor.shutdown.assert_not_called()

    @patch('services.trial_live_delegation.openai_client')
    def test_worker_uses_metered_client_bounded_output_and_no_paid_tools(self, factory):
        client = factory.return_value.__enter__.return_value
        client.responses.create.return_value = SimpleNamespace(status='completed',
            output_text=json.dumps({'reply': 'Сто рублей.', 'finish': None}))
        result = self.handler._run([{'role': 'user', 'content': 'Сколько стоит чай?'}])
        self.assertEqual(result['reply'], 'Сто рублей.')
        call = client.responses.create.call_args.kwargs
        self.assertEqual(call['model'], 'gpt-5.6-luna')
        self.assertEqual(call['max_output_tokens'], 1024)
        self.assertNotIn('tools', call)
        self.assertEqual(factory.call_args.kwargs['max_retries'], 0)
        self.assertEqual(factory.call_args.kwargs['timeout'], 15)


class ClientNaturalEndingTests(unittest.TestCase):
    def test_valid_proposal_waits_for_farewell_audio_then_finishes(self):
        ending = NaturalEnding(SCENARIO)
        ending.receive({'type': 'session.input_transcript.delta', 'delta': 'До свидания.', 'end_ms': 100}, now=0)
        proposal = {'reason': 'learner_finished', 'learner_quote': 'До свидания.', 'goal_evidence': []}
        self.assertTrue(ending.propose_client_ending(json.dumps(proposal), 'delegation', now=1))
        self.assertIsNone(ending.tick(now=2))
        ending.receive({'type': 'session.output_transcript.delta', 'delta': 'До свидания!'}, now=2)
        pcm = base64.b64encode(b'\xe8\x03' * 2400).decode()
        ending.receive({'type': 'session.output_audio.delta', 'delta': pcm}, now=2)
        self.assertEqual(ending.tick(now=5), 'learner_finished')
        self.assertFalse(ending.completion['rewards_applied'])

    def test_fabricated_goal_or_quote_never_ends(self):
        ending = NaturalEnding(SCENARIO)
        ending.receive({'type': 'session.input_transcript.delta', 'delta': 'Привет.', 'end_ms': 100}, now=0)
        for proposal in ({'reason': 'learner_finished', 'learner_quote': 'До свидания.', 'goal_evidence': []},
                         {'reason': 'task_complete', 'learner_quote': 'Привет.', 'goal_evidence': []}):
            self.assertFalse(ending.propose_client_ending(json.dumps(proposal), 'delegation', now=1))
        self.assertFalse(ending.pending)
