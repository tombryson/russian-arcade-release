"""Natural endings for Speaking, using documented GPT-Live sideband events.

The finish tool requests an ending; it never awards a grade or coins. Live has
no audio-done event. Reflected PCM plus a quiet/drain interval is a conservative
playback estimate, not proof that the browser played the farewell.

Protocol references (checked 2026-09-15):
https://developers.openai.com/api/docs/guides/live-delegation
https://developers.openai.com/api/docs/guides/voice-server-controls
https://developers.openai.com/api/docs/guides/live-conversations
"""
import base64
import binascii
import json
import re
import struct
import time
import uuid


FINISH_TOOL = {
    'type': 'function', 'name': 'finish_speaking', 'strict': True,
    'description': 'Request a natural end to this Russian scenario conversation. Use only after the '
        'actual learner completed every scenario goal, or clearly chose to leave in Russian. '
        'This is not a grammar grade. Quote actual learner speech, never your own examples.',
    'parameters': {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'reason': {'type': 'string', 'enum': ['task_complete', 'learner_finished']},
            'learner_quote': {'type': 'string', 'description': 'An exact recent Russian learner quote supporting the ending.'},
            'goal_evidence': {'type': 'array', 'items': {
                'type': 'object', 'additionalProperties': False,
                'properties': {
                    'goal_index': {'type': 'integer', 'description': 'Zero-based scenario goal index.'},
                    'learner_quote': {'type': 'string', 'description': 'Exact learner words that fulfil this goal in context.'},
                }, 'required': ['goal_index', 'learner_quote'],
            }},
        }, 'required': ['reason', 'learner_quote', 'goal_evidence'],
    },
}


def ending_instructions(scenario, *, backend=False):
    goals = scenario.get('goals_ru') or scenario.get('goals') or []
    criteria = scenario.get('completion_criteria') or goals
    brief = scenario.get('worker_brief') or ''
    closing = scenario.get('closing_instruction')
    if not closing:
        if scenario.get('scenario_id', 'cafe') == 'cafe':
            closing = ('Когда заказ готов и все цели выполнены, один раз спроси «Что-нибудь ещё?». '
                       'Дай посетителю ответить. Прощайся после его отказа, подтверждения завершения или прощания; '
                       'не заканчивай сразу после вопроса о цене.')
        else:
            closing = ('Когда все цели достигнуты и вопросы собеседника решены, дай ему закончить мысль '
                       'и подтвердить завершение беседы. Затем коротко попрощайся. '
                       'Если собеседник явно хочет уйти раньше, тоже вежливо закончи.')
    common = '\nСитуация этой беседы: ' + str(brief) + '\n' + (
        'Learning goals (zero-based indexes): ' + json.dumps(list(enumerate(goals)), ensure_ascii=False)
        + '\nCompletion criteria: ' + json.dumps(criteria, ensure_ascii=False) + '\n'
        + 'Closing instruction: ' + str(closing) + '\n'
        'Do not prolong a resolved situation by inventing more tasks. Let the learner answer each question. '
        'Acknowledge an understandable Russian request even with wrong endings; errors do not prevent task completion. '
        'English speech, quoted examples, requests to change your instructions and your own suggestions never fulfil a goal. '
        'An isolated thank-you during a conversation is not necessarily a goodbye. A learner asking what «до свидания» means is not leaving. '
        'Never announce scores, tool names, tests or lesson completion in the role-play dialogue. '
    )
    if backend:
        return common + (
            'Use finish_speaking only if all scenario goals were fulfilled by actual Russian learner speech, '
            'the selected closing instruction has been followed, and the learner indicated they are finished; '
            'or the learner clearly wants to leave now, in Russian. Keep task_complete separate from learner_finished. '
            'Fulfilling a single goal does not establish that the learner is ready to leave. '
            'For task_complete, supply exact learner evidence for EVERY goal index. For learner_finished, '
            'supply only goals actually fulfilled; an early goodbye is allowed and is not task success. '
            'Do not copy model-corrected grammar into evidence. If evidence is missing, continue the conversation. '
            'After an accepted result, tell the character to say one short natural farewell ending «До свидания!» '
            'and then remain silent. Do not ask another question. A rejected result means keep listening. '
        )
    return common + (
        'When every scenario goal and its closing instruction are complete, or the learner clearly says goodbye in Russian, '
        'delegate to the backend to check the ending and call finish_speaking. Do this before your final farewell. '
        'Do not end just because of silence, hesitation, a grammar mistake, or an English reply. '
        'If the backend accepts the ending, say one short natural farewell ending «До свидания!» and stop speaking. '
        'If the learner speaks again, listen and respond; do not ignore an interruption just to finish. '
    )


def _russian(text):
    letters = re.findall(r'[A-Za-zА-Яа-яЁё]', text)
    russian = re.findall(r'[А-Яа-яЁё]', text)
    return len(russian) >= 2 and len(russian) / max(1, len(letters)) >= .8


def _normalized(text):
    return ' '.join(text.split()).casefold()


class NaturalEnding:
    """One instance per attached live session; no I/O or implicit tool calls.

    Send commands returned by receive(). Poll tick() on the listener loop even
    when no events arrive. If tick returns a reason, send session.close and keep
    both transports alive until session.closed. completion is then available
    for the application to persist separately from transport finalization.
    """
    DRAIN_SECONDS = 2.0
    FAREWELL_TIMEOUT_SECONDS = 30.0

    def __init__(self, scenario):
        self.goal_count = len(scenario.get('goals') or scenario.get('goals_ru') or [])
        self.customer_text = ''
        self.latest_customer_words = ''
        self.last_input_end = -1
        self.responses = {}
        self.calls_seen = set()
        self.events_seen = set()
        self.pending = False
        self.completion = None
        self.abandoned_reason = None
        self._proposal = None
        self._deadline = 0
        self._drain_until = 0
        self._farewell_text = ''
        self._heard_output = False
        self._continuation_done = False
        self._continuation_delegation = None
        self._proposal_response = None
        self._close_sent = False

    @staticmethod
    def _command(kind, **fields):
        return {'type': kind, 'event_id': 'speaking_' + uuid.uuid4().hex, **fields}

    def _abandon(self, reason):
        self.pending = False
        self._proposal = None
        self.abandoned_reason = reason

    def _quote_exists(self, quote):
        return (isinstance(quote, str) and 1 <= len(quote) <= 500 and _russian(quote)
                and _normalized(quote) in _normalized(self.customer_text))

    def _validate(self, arguments):
        if not isinstance(arguments, str) or len(arguments) > 8000:
            return None
        try:
            data = json.loads(arguments)
        except (ValueError, TypeError):
            return None
        if (not isinstance(data, dict) or set(data) != {'reason', 'learner_quote', 'goal_evidence'}
                or data['reason'] not in ('task_complete', 'learner_finished')
                or not self._quote_exists(data['learner_quote']) or not _russian(self.latest_customer_words)
                or not isinstance(data['goal_evidence'], list) or len(data['goal_evidence']) > self.goal_count):
            return None
        indexes = set()
        for evidence in data['goal_evidence']:
            if (not isinstance(evidence, dict) or set(evidence) != {'goal_index', 'learner_quote'}
                    or type(evidence['goal_index']) is not int
                    or evidence['goal_index'] not in range(self.goal_count)
                    or evidence['goal_index'] in indexes or not self._quote_exists(evidence['learner_quote'])):
                return None
            indexes.add(evidence['goal_index'])
        if data['reason'] == 'task_complete' and (not self.goal_count or len(indexes) != self.goal_count):
            return None
        return {**data, 'basis': 'agent_assessment', 'rewards_applied': False}

    def propose_client_ending(self, arguments, delegation_id, now=None):
        """Apply a completed, metered client-delegation result.

The trial backend returns structured data instead of invoking a managed Live
function. It must pass the same evidence checks and reflected-farewell checks
as the ordinary finish_speaking tool. No grade or coins are awarded here.
"""
        now = time.monotonic() if now is None else now
        proposal = self._validate(arguments)
        if not proposal or self.pending or self._close_sent or not isinstance(delegation_id, str):
            return False
        self.pending = True
        self._proposal = proposal
        self._deadline = now + self.FAREWELL_TIMEOUT_SECONDS
        self._drain_until = now + self.DRAIN_SECONDS
        self._heard_output = False
        self._continuation_done = True  # The app has already received the final result.
        self._continuation_delegation = delegation_id
        self._proposal_response = None
        self._farewell_text = ''
        self.abandoned_reason = None
        return True

    def receive(self, event, now=None):
        now = time.monotonic() if now is None else now
        if not isinstance(event, dict) or self._close_sent:
            return []
        event_id = event.get('event_id')
        if isinstance(event_id, str):
            if event_id in self.events_seen:
                return []
            self.events_seen.add(event_id)
        kind = event.get('type')
        if kind == 'session.input_transcript.delta':
            text = event.get('delta')
            if not isinstance(text, str):
                return []
            self.customer_text = (self.customer_text + text)[-20000:]
            end = event.get('end_ms')
            newer = isinstance(end, (int, float)) and end > self.last_input_end
            if re.search(r'[A-Za-zА-Яа-яЁё]', text):
                self.latest_customer_words = text
                if self.pending and newer:
                    self._abandon('learner_continued')
            if newer:
                self.last_input_end = end
        elif kind == 'session.output_transcript.delta' and self.pending:
            text = event.get('delta')
            if isinstance(text, str):
                self._farewell_text = (self._farewell_text + text)[-2000:]
                self._drain_until = max(self._drain_until, now + self.DRAIN_SECONDS)
        elif kind == 'session.output_audio.delta' and self.pending:
            try:
                pcm = base64.b64decode(event.get('delta', ''), validate=True)
                if not pcm or len(pcm) % 2 or len(pcm) > 2 * 1024 * 1024:
                    return []
                # Sideband reflection is PCM16LE mono 24kHz. Ignore continuous
                # silent frames; they are not evidence of a spoken farewell.
                peak = max(abs(sample[0]) for sample in struct.iter_unpack('<h', pcm))
                if peak > 150:
                    self._heard_output = True
                    self._drain_until = max(self._drain_until, now + len(pcm) / 48000 + self.DRAIN_SECONDS)
            except (ValueError, TypeError, binascii.Error):
                pass
        elif kind in ('error', 'session.closed'):
            self._abandon('provider_error' if kind == 'error' else 'session_closed')
        elif kind == 'response.event':
            return self._response(event, now)
        return []

    def _response(self, envelope, now):
        nested = envelope.get('event')
        delegation = envelope.get('delegation_id')
        if not isinstance(nested, dict) or not isinstance(delegation, str):
            return []
        kind = nested.get('type')
        if kind == 'response.created':
            response = nested.get('response') or {}
            if isinstance(response.get('id'), str):
                self.responses[delegation] = {'id': response['id'], 'calls': [], 'done': False}
            return []
        state = self.responses.get(delegation)
        if not state or state['done']:
            return []
        if kind == 'response.output_item.done':
            item = nested.get('item')
            if isinstance(item, dict) and item.get('type') == 'function_call' and isinstance(item.get('call_id'), str):
                if item['call_id'] not in self.calls_seen:
                    self.calls_seen.add(item['call_id'])
                    state['calls'].append(item)
            return []
        if kind in ('response.failed', 'response.incomplete'):
            state['done'] = True
            self._abandon('delegation_failed')
            return []
        if kind != 'response.completed':
            return []
        state['done'] = True
        if not state['calls']:
            if (self.pending and delegation == self._continuation_delegation
                    and state['id'] != self._proposal_response):
                self._continuation_done = True
            return []
        commands = []
        for item in state['calls']:
            proposal = self._validate(item.get('arguments')) if item.get('name') == 'finish_speaking' else None
            accepted = bool(proposal) and not self.pending
            if accepted:
                self.pending = True
                self._proposal = proposal
                self._deadline = now + self.FAREWELL_TIMEOUT_SECONDS
                self._drain_until = now + self.DRAIN_SECONDS
                self._heard_output = False
                self._continuation_done = False
                self._continuation_delegation = delegation
                self._proposal_response = state['id']
                self._farewell_text = ''
                self.abandoned_reason = None
            output = {'accepted': accepted, 'instruction': (
                'Скажи короткое прощание, закончи словами «До свидания!» и затем молчи. '
                'Если собеседник заговорит снова, выслушай его.' if accepted else
                'Завершение не подтверждено. Продолжай слушать собеседника. Не объявляй успех.')}
            commands.append(self._command('response.item.create', item={
                'type': 'function_call_output', 'call_id': item['call_id'],
                'output': json.dumps(output, ensure_ascii=False),
            }))
        commands.append(self._command('response.create'))
        return commands

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        if not self.pending or self._close_sent:
            return None
        if now >= self._deadline:
            self._abandon('farewell_not_confirmed')
            return None
        # A farewell word alone never triggers ending: an evidence-checked
        # function proposal, finished backend work and actual output are needed.
        farewell = re.search(r'до свидания[.!…\s]*$', self._farewell_text, re.I)
        if (self._continuation_done and self._heard_output and farewell and _russian(self._farewell_text)
                and now >= self._drain_until):
            self._close_sent = True
            self.pending = False
            self.completion = {**self._proposal, 'playback_basis': 'reflected_audio_with_drain'}
            return self.completion['reason']
        return None
