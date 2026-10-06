"""Presentation hints for the frozen introductory lesson editions.

Hints direct attention or recall a strategy without supplying the target word,
translation, form, or gender answer. Omit a hint when it would only repeat the
prompt or identify the correct choice. Explicit teaching belongs before the
question; answer explanations and listening transcripts belong after answering.

Resolve outgoing hints here without rewriting authored content or saved evidence.
Never fall back to a frozen hint: earlier editions include direct answer reveals.
"""


_HINTS = {
    'first-delivery-v1': {
        'greeting': 'Look at what each person says when the conversation begins.',
        'letter': 'The second sentence refers back to an object in the first.',
        'thanks': 'Reread what Masha does before Barsik speaks.',
    },
    'first-delivery-v2': {
        'word-hello': None,
        'word-letter': None,
        'word-thanks': None,
    },
    'first-steps-v1': {
        'bag-name-letter': None,
        'bag-name-bag': None,
        'bag-name-map': None,
        'direction-follow-straight': None,
        'direction-follow-left': None,
        'direction-follow-right': None,
        'help-name-market': None,
        'help-ask-where': None,
        'help-ask-show': None,
        'help-say-thanks': None,
        'set-off-greet': 'Think about how well Barsik knows the person he is speaking to.',
        'set-off-carry': None,
        'set-off-turn': 'Follow the order of the directions. The question asks about the second step.',
        'set-off-destination': 'Separate the place being named from the directions that follow.',
    },
    'first-steps-v2': {
        'bag-name-letter': None,
        'bag-name-bag': None,
        'bag-name-house': None,
        'bag-name-map': None,
        'bag-listen-object': 'Replay the recording and focus on the word after это.',
        'introductions-name-phrase': None,
        'introductions-read-name': None,
        'introductions-ask-back': None,
        'introductions-listen-name': 'Replay the recording and focus on the name after the introduction phrase.',
        'introductions-answer': None,
        'gender-house': 'Look at the noun’s last letter and recall the ending patterns.',
        'gender-bag': 'Look at the noun’s last letter and recall the ending patterns.',
        'gender-letter': 'Look at the noun’s last letter and recall the ending patterns.',
        'gender-map': 'Look at the noun’s last letter and recall the ending patterns.',
        'gender-match-group': 'Compare the endings of the three choices with the noun in the question.',
        'ownership-guided-house': 'The form of “my” agrees with the object’s grammatical gender.',
        'ownership-guided-bag': 'The form of “my” agrees with the object’s grammatical gender.',
        'ownership-letter': 'Use the noun’s ending to recall its gender, then choose the matching form of “my”.',
        'ownership-map': 'Use the noun’s ending to recall its gender, then choose the matching form of “my”.',
        'ownership-introduce-letter': 'Focus on the final sentence in each choice.',
        'ownership-listen-exchange': 'Replay the recording and focus on the object named after the introduction.',
    },
}


def hint_for(version: str, question_id: str) -> str | None:
    """Return an authored cue, or no hint for an unsupported or omitted question."""
    return _HINTS.get(version, {}).get(question_id)
