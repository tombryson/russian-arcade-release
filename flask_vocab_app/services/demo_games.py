"""Provider-free public samples. No visitor-controlled generation paths."""
import json
import re

from flask import current_app

from repositories.learning_repository import LearningError, encoded, identifier, timestamp, transaction

SAMPLE_GAMES = frozenset({'directions', 'pack-bag', 'scene-builder', 'missing-stamp'})


def start_sample(game_id, request_id):
    from services.first_delivery import _owner
    from services.first_steps import chapter_content
    from services.journey_games import _content, _game, _public, _read_row, _scope
    from services.journey_vocabulary_games import build_routes
    if game_id not in SAMPLE_GAMES | {'pairs'}:
        raise LearningError('demo_limit', 'This activity is available in your own installation. Choose a sample game to play here.', 403)
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request_id):
        raise LearningError('invalid_request', 'Start the game again to create a new request.')
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        profile, guest = _owner(conn)
        where, params = _scope(profile, guest)
        rows = conn.execute('SELECT * FROM journey_game_sessions WHERE '+where+' AND game_id=? ORDER BY created_at,rowid', (*params, game_id)).fetchall()
        for row in rows:
            if request_id in json.loads(row['request_ids_json']):
                return _public(conn, row)
        active = next((row for row in rows if row['completed_at'] is None and row['superseded_at'] is None), None)
        if active:
            requests = [*json.loads(active['request_ids_json']), request_id]
            conn.execute('UPDATE journey_game_sessions SET request_ids_json=? WHERE id=?', (encoded(requests), active['id']))
            return _public(conn, active)
        game, seed, session_id, now = _game(game_id), identifier(), identifier(), timestamp()
        if game_id == 'directions':
            content = build_routes(game, seed, {'source': 'sample', 'rounds': 5, 'word_policy': 'mixed-v1'})
        else:
            chapter = chapter_content()
            lessons = [dict(lesson, version=chapter['version']) for lesson in chapter['lessons']]
            lesson = dict(next(lesson for lesson in lessons if lesson['id'] == game['lesson_id']), related_lessons=lessons)
            content = _content(game, lesson, seed)
            content['options'] = {'source': 'sample', 'word_policy': 'mixed-v1'}
        content['source'] = {'kind': 'sample', 'title': 'Sample game', 'href': '#activities'}
        content['sample'] = True
        conn.execute('INSERT INTO journey_game_sessions(id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                     (session_id, profile, guest, game_id, seed, encoded([request_id]), encoded(content), now, now))
        return _public(conn, _read_row(conn, session_id, profile, guest))
