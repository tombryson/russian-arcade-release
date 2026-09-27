"""Choose resources for the activity, not one universal flashcard pipeline."""

PICTURE_GAMES = frozenset(('pack-bag', 'pairs', 'detective'))


def activity_policy(game_id):
    if game_id == 'radio':
        return {'kind': 'broadcast', 'pictures': 0, 'questions': 4}
    if game_id == 'directions':
        return {'kind': 'route', 'pictures': 0}
    if game_id in PICTURE_GAMES:
        return {'kind': 'examples', 'familiar': 3, 'new': 1, 'required_media': ['image']}
    return {'kind': 'examples', 'familiar': 4, 'new': 1,
            'required_media': ['sentence_audio'] if game_id == 'letter-back' else []}


def discovery_request(known_lemmas, familiar, options, seed, requirements):
    return {'identity': 'discovery:'+seed, 'word_id': None, 'form_id': None,
            'lemma': '', 'form': '', 'tags': {}, 'required_media': list(requirements),
            '_discovery': {'known_lemmas': known_lemmas, 'familiar_records': familiar,
                           'options': options, 'seed': seed}}
