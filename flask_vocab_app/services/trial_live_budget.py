"""Reserve live voice separately from metered delegated text and audio review."""
import hashlib
import json
import math

from services.ai_trial_budget import AITrialBudget, TrialDenied

TRIAL_SECONDS = 60
VOICE_RESERVATION = 100_000  # US$0.10, including connection/closing allowance.


class LiveTrialBudget:
    def __init__(self, config):
        self.config = config
        self.enabled = bool(config.get('HOSTED_AI_TRIAL'))
        self.identity = config.get('AI_TRIAL_IDENTITY')
        self.ledger = (AITrialBudget(config['AI_TRIAL_LEDGER_PATH'],
                                    enabled=bool(config.get('AI_TRIAL_ENABLED')))
                       if self.enabled else None)

    def reserve(self, session, scenario):
        if not self.enabled:
            return
        if session['model'] != 'gpt-live-1':
            raise TrialDenied('This live voice model has no verified demo budget.')
        digest = hashlib.sha256(json.dumps({'session': session['id'], 'scenario': scenario,
            'seconds': TRIAL_SECONDS}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        row = self.ledger.reserve(self.identity, 'live:' + session['id'], digest, VOICE_RESERVATION, lane='voice')
        if not row['created']:
            raise TrialDenied('This live connection was already started. Start a new conversation.')

    def finish(self, session_id, usage=None):
        if not self.enabled:
            return
        seconds = usage.get('seconds') if isinstance(usage, dict) else None
        if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(seconds) and seconds >= 0:
            self.ledger.settle(self.identity, 'live:' + session_id,
                               math.ceil(seconds * 50_000 / 60))
        else:
            # A missing final event is not proof that provider billing stopped.
            self.ledger.uncertain(self.identity, 'live:' + session_id)
