"""Generate, preview and keep native cards with the existing vocabulary filters."""
import json
from flask import Blueprint, abort, current_app, jsonify, request
from repositories.learning_repository import LearningError, require_access, timestamp, transaction
from utils.household_access import access_id, access_policy


def create_card_generation_blueprint(generator, authoring):
    bp = Blueprint('card_generation', __name__)

    @bp.before_request
    def enabled():
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED'] and request.endpoint != 'card_generation.chapter_jumble':
            abort(404)

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data,dict):
            raise LearningError('invalid_input','Send the generation settings as a JSON object.')
        return data

    @bp.post('/api/v1/first-steps/<lesson_id>/flashcards')
    @access_policy('adult')
    def chapter_cards(lesson_id):
        from services.first_steps_practice import create_flashcards
        if body():
            raise LearningError('invalid_input', 'Use the words from this lesson.')
        return jsonify(create_flashcards(generator, access_id(), lesson_id)), 201

    @bp.post('/api/v1/first-steps/practice/word-jumble')
    @access_policy('adult')
    def chapter_jumble():
        from services.first_steps_practice import create_word_jumble
        if body():
            raise LearningError('invalid_input', 'Use the words from this chapter.')
        return jsonify(create_word_jumble(generator.db_path, access_id(), generator.clock())), 201

    @bp.post('/api/v1/games/sessions/<session_id>/flashcards')
    @access_policy('adult')
    def game_cards(session_id):
        from services.first_steps_practice import create_game_flashcards
        data = body()
        if set(data) - {'items'} or ('items' in data and data['items'] is None):
            raise LearningError('invalid_input', 'Use the words from your saved game.')
        return jsonify(create_game_flashcards(generator, access_id(), session_id, data.get('items'))), 201

    @bp.post('/api/v1/course/checkpoints/<attempt_id>/flashcards')
    @access_policy('adult')
    def course_cards(attempt_id):
        from services.course_followups import create_flashcards
        if body():
            raise LearningError('invalid_input', 'Use the words from your saved letter.')
        return jsonify(create_flashcards(generator, access_id(), attempt_id)), 201

    @bp.get('/api/v1/card-generation/options')
    @access_policy('adult')
    def options():
        with transaction(current_app.config['DB_PATH']) as conn:
            require_access(conn,access_id(),timestamp(),adult=True)
            topics = sorted({row[0] for row in conn.execute("SELECT DISTINCT j.value FROM words w, json_each(CASE WHEN json_valid(w.topic) THEN w.topic ELSE '[]' END) j WHERE j.type='text' AND json_type(CASE WHEN json_valid(w.topic) THEN w.topic ELSE '[]' END)='array'")})
            selected = conn.execute('SELECT id,lemma FROM words WHERE id=?',(request.args.get('word_id'),)).fetchone()
        return jsonify(topics=topics,word=dict(selected) if selected else None,
                       configured=bool(current_app.config['OPENAI_API_KEY']),household=current_app.config['WORD_POST_HOUSEHOLD_ENABLED'],
                       max_quantity=generator.max_quantity)

    @bp.post('/api/v1/card-generation/preview')
    @access_policy('adult')
    def preview():
        return jsonify(words=generator.preview(access_id(),body()))

    @bp.post('/api/v1/card-generation/batches')
    @access_policy('adult')
    def create():
        if not current_app.config['OPENAI_API_KEY']:
            raise LearningError('provider_unavailable','Add OPENAI_API_KEY to the app configuration to generate cards.',503)
        return jsonify(generator.create(access_id(),body())),201

    @bp.get('/api/v1/card-generation/batches/<batch_id>')
    @access_policy('adult')
    def read(batch_id):
        return jsonify(generator.read(access_id(),batch_id))

    @bp.post('/api/v1/card-generation/batches/<batch_id>/next')
    @access_policy('adult')
    def advance(batch_id):
        return jsonify(generator.next(access_id(),batch_id))

    @bp.post('/api/v1/flashcards/<card_id>/media')
    @access_policy('adult')
    def media(card_id):
        data = body()
        if set(data) - {'retry'} or ('retry' in data and type(data['retry']) is not bool):
            raise LearningError('invalid_input','Choose whether to retry missing media.')
        service = current_app.extensions['learning']['card_media']
        service.queue(access_id(),card_id)
        if data.get('retry'):
            service.retry(access_id(),card_id)
        return jsonify(service.advance(access_id(),card_id))

    @bp.post('/api/v1/card-generation/batches/<batch_id>/retry-media')
    @access_policy('adult')
    def retry_media(batch_id):
        batch = generator.read(access_id(),batch_id)
        for item in batch['items']:
            if item.get('card_id'):
                current_app.extensions['learning']['card_media'].retry(access_id(),item['card_id'])
        return jsonify(generator.read(access_id(),batch_id))

    @bp.post('/api/v1/card-generation/batches/<batch_id>/retry-cards')
    @access_policy('adult')
    def retry_cards(batch_id):
        with transaction(generator.db_path,write=True) as conn:
            _, items = generator._batch_items(conn,access_id(),batch_id)
            conn.executemany("UPDATE native_card_generation_items SET status='pending',error=NULL,claim_id=NULL,lease_until=0 WHERE id=? AND status='failed'",
                             [(item['id'],) for item in items])
        return jsonify(generator.read(access_id(),batch_id))

    @bp.post('/api/v1/card-generation/batches/<batch_id>/recheck-source')
    @access_policy('adult')
    def recheck_source(batch_id):
        current_app.extensions['learning']['lesson_cards'].recheck(access_id(),batch_id)
        return jsonify(generator.read(access_id(),batch_id))

    @bp.post('/api/v1/cards/<card_id>/delete')
    @access_policy('adult')
    def delete(card_id):
        authoring.retire(access_id(),card_id)
        return jsonify(deleted=True)

    return bp
