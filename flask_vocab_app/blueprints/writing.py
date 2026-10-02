"""A saved writing task, a durable draft and feedback for each checked version."""
import logging
import sqlite3

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from repositories.writing_repository import WritingRepository, WritingConflict, word_count
from repositories.learning_repository import LearningError
from services.writing_service import WritingUnavailable
from services.curriculum import level_options, normalize_level, topic_options
from services.curriculum_requirement_map import requirement_index
from utils.activity_display import topic_label, readable_date
from utils.i18n import translate_ui
from utils.shell import render_page

logger = logging.getLogger(__name__)


def create_writing_blueprint(db_path, service):
    blueprint = Blueprint('writing',__name__)
    repository = WritingRepository(db_path)

    @blueprint.post('/api/v1/writing/tasks/<int:exercise_id>/submissions')
    def save_original(exercise_id):
        from services.activity_review_submissions import submit as save_submission
        return jsonify(save_submission(db_path, 'writing', str(exercise_id), request.get_json(silent=True), language=language()))

    @blueprint.get('/api/v1/writing/submissions/<identity>')
    def read_original(identity):
        from services.activity_review_submissions import load as load_submission
        return jsonify(load_submission(db_path, identity, 'writing'))

    @blueprint.post('/api/v1/writing/submissions/<identity>/review')
    def review_original(identity):
        from services.activity_review_submissions import review as review_submission
        return jsonify(review_submission(db_path, identity, service, activity='writing'))

    @blueprint.post('/writing/support/<int:exercise_id>')
    @blueprint.post('/api/v1/writing/tasks/<int:exercise_id>/model-answer')
    def model_answer(exercise_id):
        from services.activity_review_submissions import disclose_writing_model
        data = request.get_json(silent=True) if request.is_json else request.form
        value = (data or {}).get('expected_revision')
        revision = int(value) if isinstance(value, str) and value.isdecimal() else value
        result = disclose_writing_model(db_path, str(exercise_id), revision)
        if request.is_json:
            return jsonify(result)
        return redirect(url_for('writing.load', exercise_id=exercise_id), code=303)

    def language():
        return 'ru' if session.get('ui_lang') == 'ru' else 'en'

    def t(key):
        return translate_ui('writing.'+key,language())

    def present(item):
        if item is None:
            return None
        item = dict(item)
        item['topic_label'] = topic_label(item['topic'],language())
        item['display_title'] = item.get('title' if language() == 'ru' else 'title_en') or item['topic_label']+' · '+t('title')
        item['display_task'] = item.get('task_en') if language() == 'en' and item.get('task_en') else item['task']
        item['task_language'] = 'en' if language() == 'en' and item.get('task_en') else 'ru'
        try:
            level = normalize_level(item['difficulty'], legacy='writing')
            item['level_label'] = next(option['label'] for option in level_options(language()) if option['value'] == level)
        except ValueError:
            item['level_label'] = item['difficulty']
        item['display_date'] = readable_date(item.get('draft_saved_at') or item.get('created_at'),language())
        item['saved_draft'] = item.get('saved_draft',item['draft'])
        item['word_count'] = word_count(item['draft'])
        item['state'] = 'draft' if item['draft'] != (item.get('checked_response') or '') else 'checked' if item.get('checked_response') is not None else 'ready'
        from repositories.learning_repository import transaction
        from services.curriculum_sequences import activity_context
        from utils.activity_owner import activity_profile_id
        with transaction(db_path) as conn:
            from services.feedback_study import actions as study_actions
            for attempt in item.get('attempts', []):
                attempt['study_actions'] = study_actions(conn, activity_profile_id(conn), 'writing', str(attempt['id']))
            item['sequence'] = activity_context(conn, activity_profile_id(conn), 'writing', str(item['id']))
            if item['sequence'] and item.get('curriculum_contract'):
                from services.activity_review_submissions import safe_scene, writing_help
                contract = item['curriculum_contract']
                item['writing_scene'] = safe_scene(contract['content'])
                item['writing_help'] = writing_help(conn, activity_profile_id(conn), str(item['id']), contract)
                item['model_answer_available'] = bool(contract['content'].get('model_answer'))
        if item.get('curriculum_contract'):
            from services.curriculum_units import unit_summaries
            unit = next((unit for unit in unit_summaries()
                         if unit['id'] == item['curriculum_contract']['content_version']), None)
            if unit:
                item['curriculum_origin'] = {
                    'href': '/curriculum/units/' + unit['id'],
                    'title': unit['title_ru' if language() == 'ru' else 'title'],
                }
            if item['sequence']:
                item['curriculum_origin'] = {'href': item['sequence']['lesson_url'], 'title': 'Back to lesson' if language() == 'en' else 'Вернуться к уроку'}
            criteria = {criterion['id']: criterion for criterion in item['curriculum_contract']['criteria']}
            references = requirement_index()
            outcomes = {
                'satisfied': ('Shown in this response', 'Есть в этом ответе'),
                'partial': ('Partly shown', 'Показано частично'),
                'not_satisfied': ('Needs practice', 'Стоит потренировать'),
                'insufficient_evidence': ('Not enough evidence', 'Недостаточно материала'),
            }
            for attempt in item.get('attempts', []):
                attempt['criterion_details'] = []
                for judgement in attempt.get('criterion_report', {}).get('judgements', []):
                    criterion = criteria[judgement['criterion_id']]
                    reference = references[criterion['requirement_id']]
                    attempt['criterion_details'].append({
                        'label': reference['label_ru' if language() == 'ru' else 'label_en'],
                        'outcome': outcomes[judgement['outcome']][language() == 'ru'],
                        'feedback': judgement['feedback'],
                    })
        return item

    def page(exercise=None,**extra):
        saved = [present(item) for item in repository.list_saved()]
        topics = topic_options(language())
        selected_topic = extra.pop('selected_topic', request.args.get('topic', 'any'))
        selected_option = next((item for item in topics if item['value'] == selected_topic), None)
        if selected_topic != 'any' and selected_option is None:
            selected_topic = 'any'
        requested_level = extra.pop('selected_level', request.args.get('level'))
        level_explicit = bool(requested_level)
        try:
            selected_level = normalize_level(requested_level, legacy='writing') if requested_level else ((selected_option or {}).get('level') or 'A1')
        except ValueError:
            level_explicit = False
            selected_level = ((selected_option or {}).get('level') or 'A1')
        context = dict(exercise=present(exercise),saved_exercises=saved,topics=topics,
                       levels=level_options(language()),selected_topic=selected_topic,selected_level=selected_level,
                       level_explicit=level_explicit,
                       active_page='writing',**extra)
        if request.headers.get('HX-Target') == 'writing-content':
            return render_template('_writing_content.html',**context)
        return render_page('writing.html',**context)

    def enhanced():
        return request.accept_mimetypes.best == 'application/json'

    def failure(error,exercise=None,preparing=False):
        if isinstance(error, LearningError):
            if enhanced():
                return jsonify(error={'code': error.code, 'message': str(error)}), error.status
            return page(exercise, error=str(error)), error.status
        if isinstance(error,LookupError):
            key,status = 'missing',404
        elif isinstance(error,WritingConflict):
            key,status = 'conflict',409
        elif isinstance(error,WritingUnavailable):
            key,status = ('prepare_failed' if preparing else 'check_failed'),503
        elif isinstance(error,sqlite3.Error):
            key,status = 'request_failed',503
        else:
            key,status = 'invalid',400
        if status == 503:
            logger.warning('Writing request unavailable (%s)',type(error).__name__)
        if enhanced():
            return jsonify(error=t(key)),status
        return page(exercise,error=t(key),selected_topic=request.form.get('topic','any'),
                    selected_level=request.form.get('difficulty','beginner'),selected_length=request.form.get('target_words','30')),status

    @blueprint.get('/writing')
    def home():
        return page()

    @blueprint.get('/writing/load/<int:exercise_id>')
    def load(exercise_id):
        exercise = repository.load(exercise_id)
        return page(exercise) if exercise else failure(LookupError())

    @blueprint.post('/writing/generate')
    def generate():
        try:
            topic = request.form.get('topic','any')
            difficulty = request.form.get('difficulty','beginner')
            target = request.form.get('target_words',type=int) if 'target_words' in request.form else 30
            normalize_level(difficulty, legacy='writing')
            if topic not in {'any', *(item['value'] for item in topic_options())} or target not in (30,100,300):
                raise ValueError('Invalid setup')
            task = service.generate_writing_task(topic,difficulty,target)
            exercise_id = repository.create(task,topic,difficulty,target)
        except (ValueError,WritingUnavailable,sqlite3.Error) as error:
            return failure(error,preparing=True)
        url = url_for('writing.load',exercise_id=exercise_id)
        return jsonify(url=url) if enhanced() else redirect(url,code=303)

    def submit(checking):
        exercise_id = request.form.get('exercise_id',type=int)
        revision = request.form.get('revision',type=int)
        response = request.form.get('user_response','')
        exercise = repository.load(exercise_id)
        try:
            if not exercise:
                raise LookupError('Writing not found')
            repository.validate_answer(response,checking=checking)
            from repositories.learning_repository import transaction, payload_hash
            from utils.activity_owner import activity_profile_id
            from services.activity_review_submissions import binding_for_task
            with transaction(db_path) as conn:
                bound = binding_for_task(conn, activity_profile_id(conn), 'writing', str(exercise_id))
            if bound and not checking:
                key = request.form.get('submission_id') or payload_hash({'task': exercise_id, 'revision': revision, 'response': response})[:32]
                saved_revision = repository.save_lesson_draft(exercise_id, response, revision, key)
                if enhanced():
                    return jsonify(revision=saved_revision, message=t('saved_ok'))
                return redirect(url_for('writing.load', exercise_id=exercise_id), code=303)
            if checking:
                from services.activity_review_submissions import submit as save_submission, review as review_submission
                if bound:
                    key = request.form.get('submission_id') or payload_hash({'task': exercise_id, 'revision': revision, 'response': response})[:32]
                    saved = save_submission(db_path, 'writing', str(exercise_id), {'submission_id': key, 'expected_revision': revision, 'response': {'text': response}}, language=language())
                    reviewed = review_submission(db_path, saved['id'], service, activity='writing')
                    if reviewed['work_state'] != 'reviewed':
                        if enhanced():
                            return jsonify(error=reviewed['message'], review_submission=reviewed, revision=revision + 1), 503
                        return page(repository.load(exercise_id), error=reviewed['message']), 503
                    current = present(repository.load(exercise_id))
                    if enhanced():
                        return jsonify(revision=current['revision'], message=t('checked_ok'), state=t(current['state']),
                            display_date=current['display_date'], feedback=render_template('_writing_feedback.html', exercise=current), review_submission=reviewed)
                    return redirect(url_for('writing.load', exercise_id=exercise_id), code=303)
            repository.check_revision(exercise_id,revision)
            assessment = None
            if checking:
                options = dict(task=exercise['task'], required_words=exercise['required_words'],
                    min_words=exercise['min_words'], response=response, difficulty=exercise['difficulty'],
                    language=language(), topic=exercise['topic'])
                if exercise.get('curriculum_contract') is not None:
                    options['curriculum_contract'] = exercise['curriculum_contract']
                assessment = service.assess_writing(**options)
            revision = repository.save(exercise_id,response,revision,assessment,language())
        except (ValueError,LookupError,WritingUnavailable,sqlite3.Error) as error:
            if exercise:
                exercise = {**exercise,'saved_draft':exercise['draft'],'draft':response,'revision':revision if type(revision) is int else -1}
            return failure(error,exercise)
        if enhanced():
            current = present(repository.load(exercise_id))
            return jsonify(revision=revision,message=t('checked_ok' if checking else 'saved_ok'),state=t(current['state']),
                display_date=current['display_date'],feedback=render_template('_writing_feedback.html',exercise=current))
        return redirect(url_for('writing.load',exercise_id=exercise_id),code=303)

    @blueprint.post('/writing/save')
    def save():
        return submit(False)

    @blueprint.post('/writing/assess')
    def assess():
        return submit(True)

    @blueprint.post('/writing/review/<identity>')
    def retry_saved_review(identity):
        from services.activity_review_submissions import review
        saved = review(db_path, identity, service, activity='writing')
        return redirect(url_for('writing.load', exercise_id=int(saved['task_key'])), code=303)

    return blueprint
