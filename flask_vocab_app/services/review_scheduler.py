"""Pinned FSRS boundary. Queue selection and learner ownership live elsewhere."""
from datetime import datetime, timezone
import hashlib
import json

from fsrs import Card, Rating, Scheduler

from repositories.learning_repository import LearningError


POLICY_ID = 'native-fsrs-v2-four-ratings'
RATINGS = {'again': Rating.Again, 'hard': Rating.Hard, 'good': Rating.Good, 'easy': Rating.Easy}


class ReviewScheduler:
    def __init__(self):
        self.scheduler = Scheduler(desired_retention=0.9)

    @property
    def policy(self):
        return {'id': POLICY_ID, 'library': 'fsrs==6.3.2', 'scheduler': json.loads(self.scheduler.to_json())}

    @staticmethod
    def initial(card_id, now):
        # FSRS needs a numeric identifier; our relational ID remains authoritative.
        numeric_id = int(hashlib.sha256(card_id.encode()).hexdigest()[:15], 16)
        return Card(card_id=numeric_id, due=datetime.fromtimestamp(now, timezone.utc)).to_json()

    def review(self, state, rating, now):
        card = Card.from_json(state)
        instant = datetime.fromtimestamp(now, timezone.utc)
        if card.last_review and instant < card.last_review:
            raise LearningError('clock_changed', 'The clock moved backwards. Check the time before reviewing again.', 409)
        if rating not in RATINGS:
            raise LearningError('invalid_input', 'Choose Again, Hard, Good or Easy.')
        changed, log = self.scheduler.review_card(card, RATINGS[rating], review_datetime=instant)
        return changed.to_json(), int(changed.due.timestamp()), json.loads(log.to_json())
