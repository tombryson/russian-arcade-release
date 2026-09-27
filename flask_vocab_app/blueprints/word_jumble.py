"""Sentence-building routes. HTML navigation and enhanced editor share one service."""
from datetime import datetime
import logging
import sqlite3

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from services.word_jumble_service import AssessmentUnavailable, DraftConflict, PreparationUnavailable
from services.curriculum import level_options, normalize_level, topic_options
from utils.i18n import translate_ui
from utils.shell import is_shell_navigation, render_page

logger = logging.getLogger(__name__)


def create_word_jumble_blueprint(service):
    blueprint = Blueprint('word_jumble', __name__)

    def t(key):
        return translate_ui('word_jumble.' + key, session.get('ui_lang', 'en'))

    def topic_label(topic):
        key = 'topic.' + topic
        label = translate_ui(key, session.get('ui_lang', 'en'))
        return topic.replace('_', ' ').capitalize() if label == key else label

    def present(game):
        if not game:
            return None
        game = dict(game)
        game.setdefault('draft', game.get('user_response') or '')
        game.setdefault('saved_draft', game['draft'])
        game.setdefault('revision', 0)
        attempts = game.get('attempts', [])
        # Support historical callers as well as migrated records.
        if not attempts and game.get('feedback'):
            score = game.get('score')
            attempts = [dict(response=game.get('user_response', ''), feedback=game['feedback'],
                             score=score, score_max=4 if type(score) is int and 0 <= score <= 4 else None,
                             source='legacy')]
        game['attempts'] = attempts
        game['topic_label'] = topic_label(game.get('topic', 'any'))
        level = normalize_level(game.get('difficulty', 'easy'), legacy='word_jumble')
        game['level_label'] = next(option['label'] for option in level_options(session.get('ui_lang', 'en')) if option['value'] == level)
        contract = game.get('task_contract')
        game['task_instruction'] = contract['instruction']['ru' if session.get('ui_lang') == 'ru' else 'en'] if contract else ''
        date = game.get('draft_saved_at') or game.get('created_at')
        try:
            date = datetime.fromisoformat(date)
            months = (['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
                      if session.get('ui_lang') == 'ru' else
                      ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
            game['display_date'] = f'{date.day} {months[date.month - 1]} {date.year}'
        except (TypeError, ValueError):
            game['display_date'] = ''
        game['state'] = ('draft_state' if game.get('draft_saved_at') and game['draft'] != (game.get('user_response') or '')
                         else 'checked_state' if game.get('feedback') else 'ready_state')
        from services.production_evidence import present_details
        present_details(game, session.get('ui_lang', 'en'))
        return game

    def page(game=None, **context):
        game = present(game)
        if request.headers.get('HX-Request') and not is_shell_navigation():
            return render_template('_word_jumble_content.html', game=game, **context)
        return render_page('word_jumble.html', game=game,
                           topics=topic_options(session.get('ui_lang', 'en')),
                           curriculum_levels=level_options(session.get('ui_lang', 'en')),
                           saved_games=[present(item) for item in service.get_saved_games()],
                           active_page='word_jumble', **context)

    @blueprint.get('/word_jumble')
    def home():
        options = {item['value']: item for item in topic_options()}
        topic = request.args.get('topic', 'any')
        if topic != 'any' and topic not in options:
            topic = 'any'
        explicit = bool(request.args.get('level'))
        try:
            level = normalize_level(request.args.get('level') or options.get(topic, {}).get('level', 'A1'), legacy='word_jumble')
        except ValueError:
            explicit = False
            level = options.get(topic, {}).get('level') or 'A1'
        return page(selected_topic=topic, selected_level=level, level_explicit=explicit)

    @blueprint.post('/word_jumble/create')
    def create():
        topic = request.form.get('topic', 'any')
        difficulty = request.form.get('difficulty', 'easy')
        explicit = bool(request.form.get('difficulty'))
        try:
            selected_level = normalize_level(difficulty, legacy='word_jumble')
        except ValueError:
            selected_level = 'A1'
            explicit = False
        try:
            game = service.create_game(topic, difficulty)
        except ValueError:
            return page(error=t('invalid_setup'), selected_topic=topic, selected_level=selected_level, level_explicit=explicit), 400
        except (PreparationUnavailable, sqlite3.Error) as error:
            cause = error.__cause__ or error
            logger.warning('Word Jumble preparation unavailable (%s, HTTP %s, SQLite %s)',
                           type(cause).__name__, getattr(cause, 'status_code', None),
                           getattr(cause, 'sqlite_errorname', None))
            return page(error=t('prepare_failed'), selected_topic=topic, selected_level=selected_level, level_explicit=explicit), 503
        return redirect(url_for('word_jumble.load', game_id=game['id']), code=303)

    @blueprint.get('/word_jumble/load/<game_id>')
    def load(game_id):
        game = service.get_game(game_id)
        return (page(error=t('missing')), 404) if not game else page(game)

    def submit(game_id, checking):
        game = service.get_game(game_id)
        response = request.form.get('user_response', '')
        revision = request.form.get('revision', type=int)
        enhanced = request.accept_mimetypes.best == 'application/json'
        try:
            if not game:
                raise LookupError('Practice not found')
            if revision is None or revision < 0:
                raise DraftConflict('Missing draft revision')
            if checking:
                updated = service.mark_response(game_id, response, revision, session.get('ui_lang', 'en'))
            else:
                updated = service.save_draft(game_id, response, revision)
        except (LookupError, ValueError, AssessmentUnavailable, sqlite3.Error) as error:
            if isinstance(error, LookupError):
                key, status = 'missing', 404
            elif isinstance(error, DraftConflict):
                key, status = 'conflict', 409
            elif isinstance(error, AssessmentUnavailable):
                key, status = 'check_failed', 503
                cause = error.__cause__
                logger.warning('Word Jumble assessment unavailable (%s, HTTP %s)',
                               type(cause).__name__, getattr(cause, 'status_code', None))
            elif isinstance(error, sqlite3.Error):
                key, status = 'request_failed', 503
                logger.warning('Word Jumble storage unavailable (%s, %s): %s',
                               type(error).__name__, getattr(error, 'sqlite_errorname', 'unknown'), error)
            else:
                key, status = 'invalid_response', 400
            if enhanced:
                return jsonify(error=t(key)), status
            if game:
                game = {**game, 'saved_draft': game['draft'], 'draft': response, 'revision': revision or 0}
            return page(game, error=t(key)), status
        if enhanced:
            current = present(service.get_game(game_id))
            return jsonify(revision=updated, message=t('checked_ok' if checking else 'saved_ok'),
                           state=t(current['state']), display_date=current['display_date'],
                           feedback=render_template('_word_jumble_feedback.html', game=current))
        return redirect(url_for('word_jumble.load', game_id=game_id), code=303)

    @blueprint.post('/word_jumble/save/<game_id>')
    def save(game_id):
        return submit(game_id, checking=False)

    @blueprint.post('/word_jumble/mark/<game_id>')
    def mark(game_id):
        return submit(game_id, checking=True)

    return blueprint
