"""Translation practice and its reference library, with resumable server-owned content."""
import logging
import sqlite3

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from repositories import WordRepository
from repositories.translation_repository import TranslationRepository, TranslationConflict
from services.sentence_service import TranslationUnavailable
from services.curriculum import LEVELS, level_options, normalize_level, topic_options
from utils.activity_display import topic_label, readable_date
from utils.i18n import translate_ui
from utils.shell import render_page
from utils.activity_owner import activity_profile_id
from models.database import connect_db

logger = logging.getLogger(__name__)


def create_sentences_blueprint(db_path, sentence_service, user_service):
    blueprint = Blueprint('sentences', __name__)
    repository = TranslationRepository(db_path)
    words = WordRepository(db_path)

    def language():
        return 'ru' if session.get('ui_lang') == 'ru' else 'en'

    def t(key):
        return translate_ui('translation.' + key, language())

    def present(item):
        if not item:
            return None
        item = dict(item)
        item['topic_label'] = topic_label(item.get('topic'), language())
        labels = {index: option['label'] for index, option in enumerate(level_options(language()), 1)}
        item['level_label'] = labels.get(item.get('difficulty'), '')
        item['display_date'] = readable_date(item.get('draft_saved_at') or item.get('created_at'), language())
        item.setdefault('draft', '')
        item.setdefault('saved_draft', item['draft'])
        item['state'] = ('draft' if item.get('draft_saved_at') and item['draft'] != item.get('checked_response')
                         else 'checked' if item.get('checked_response') is not None else 'ready')
        from services.production_evidence import present_details
        present_details(item, language())
        return item

    def context(active_page='sentences'):
        library = [present(item) for item in repository.list_saved()]
        topics = set(words.list_topics()) | {item['topic'] for item in library if item.get('topic')}
        return {'sentences': library, 'total_sentences': len(library), 'topics': sorted(
            [{'value': topic, 'label': topic_label(topic, language())} for topic in topics if topic != 'any'],
            key=lambda item: item['label'].casefold()),
            'curriculum_topics': topic_options(language()),
            'curriculum_levels': level_options(language()),
            'active_page': active_page}

    def stored_level(value):
        """The sentence's task level keeps its historical integer storage."""
        return LEVELS.index(normalize_level(value, legacy='translation')) + 1

    def page(practice=None, **extra):
        return render_page('sentences.html', practice=present(practice), **context(), **extra)

    def enhanced():
        return request.accept_mimetypes.best == 'application/json'

    def failure(error, practice=None, preparing=False):
        if isinstance(error, LookupError):
            key, status = 'missing', 404
        elif isinstance(error, TranslationConflict):
            key, status = 'conflict', 409
        elif isinstance(error, TranslationUnavailable):
            key, status = ('prepare_failed' if preparing else 'check_failed'), 503
        elif isinstance(error, sqlite3.Error):
            key, status = 'request_failed', 503
        else:
            key, status = 'invalid', 400
        if status == 503:
            logger.warning('Translation request unavailable (%s)', type(error).__name__)
        if enhanced():
            return jsonify(error=t(key)), status
        try:
            selected_level = normalize_level(request.form.get('difficulty', 'A1'), legacy='translation')
        except ValueError:
            selected_level = 'A1'
        return page(practice, error=t(key), selected_topic=request.form.get('topic', 'any'),
                    selected_level=selected_level, level_explicit=True), status

    @blueprint.get('/sentences')
    def sentences_page():
        topic = request.args.get('topic', 'any')
        options = {item['value']: item for item in topic_options()}
        if topic != 'any' and topic not in options:
            topic = 'any'
        explicit = bool(request.args.get('level'))
        try:
            level = normalize_level(request.args.get('level') or options.get(topic, {}).get('level', 'A1'), legacy='translation')
        except ValueError:
            explicit = False
            level = options.get(topic, {}).get('level') or 'A1'
        return page(selected_topic=topic, selected_level=level,
                    level_explicit=explicit, curriculum_selected=topic != 'any')

    @blueprint.get('/sentences/practice/<int:sentence_id>')
    def practice(sentence_id):
        item = repository.load(sentence_id)
        return page(item) if item else (page(error=t('missing')), 404)

    @blueprint.route('/sentence/generate', methods=['GET', 'POST'])
    def generate_sentence():
        # Keep old bookmarks/client URLs, but generate only on an explicit POST.
        if request.method == 'GET':
            if 'difficulty' in request.args:
                try:
                    stored_level(request.args['difficulty'])
                except ValueError:
                    return jsonify(error=t('invalid')), 400
            return redirect('/sentences', code=303)
        try:
            difficulty = stored_level(request.form.get('difficulty'))
            topic = request.form.get('topic', 'any')
            if not topic or len(topic) > 100:
                raise ValueError('Invalid setup')
            with connect_db(db_path) as conn:
                owner = activity_profile_id(conn)
            pair = sentence_service.get_sentence(topic, difficulty)
            sentence_id, _ = repository.save_content(pair['sentence'], pair['english'], topic, difficulty,
                curriculum_contract=pair.get('curriculum_contract'), expected_profile=owner)
        except (ValueError, LookupError, TranslationUnavailable, sqlite3.Error) as error:
            return failure(error, preparing=True)
        target = url_for('sentences.practice', sentence_id=sentence_id)
        return jsonify(url=target) if enhanced() else redirect(target, code=303)

    def submit(checking):
        sentence_id = request.form.get('sentence_id', type=int)
        response = request.form.get('user_response', '')
        revision = request.form.get('revision', type=int)
        item = repository.load(sentence_id)
        try:
            if not item:
                raise LookupError('Sentence not found')
            repository.validate_answer(response, checking=checking)
            repository.check_revision(sentence_id, revision)
            if checking:
                # No score, difficulty, prompt or reference answer is accepted from the browser.
                options = {'curriculum_contract': item['curriculum_contract']} if item.get('curriculum_contract') else {}
                with connect_db(db_path) as conn:
                    owner = activity_profile_id(conn)
                assessment = sentence_service.assess_translation(item['sentence'], item['english'], response, language(), **options)
                revision = repository.save_check(sentence_id, response, revision, assessment, language(), expected_profile=owner)
            else:
                revision = repository.save_draft(sentence_id, response, revision)
        except (ValueError, LookupError, TranslationUnavailable, sqlite3.Error) as error:
            if item:
                item = {**item, 'saved_draft': item['draft'], 'draft': response, 'revision': revision or 0}
            return failure(error, item)
        if enhanced():
            current = present(repository.load(sentence_id))
            return jsonify(revision=revision, message=t('checked_ok' if checking else 'saved_ok'),
                           state=t(current['state']), display_date=current['display_date'],
                           feedback=render_template('_translation_feedback.html', practice=current))
        return redirect(url_for('sentences.practice', sentence_id=sentence_id), code=303)

    @blueprint.post('/sentence/assess')
    def assess_sentence():
        return submit(checking=True)

    @blueprint.post('/sentence/save')
    def save_sentence():
        return submit(checking=False)

    @blueprint.post('/sentence/audio/<int:sentence_id>')
    def sentence_audio(sentence_id):
        item = repository.load(sentence_id)
        if not item:
            return jsonify(error=t('missing')), 404
        # Audio reveals the reference; keep it with feedback, after the first check.
        if not item['attempts']:
            return jsonify(error=t('check_first')), 400
        try:
            url = item['audio_url'] or sentence_service.generate_audio(item['sentence'])
            if not url:
                raise TranslationUnavailable('No audio')
            repository.save_audio(sentence_id, url)
        except (ValueError, TranslationUnavailable, sqlite3.Error):
            return jsonify(error=t('audio_failed')), 503
        return jsonify(html=render_template('_translation_audio.html', audio_url=url))

    @blueprint.post('/sentence/add')
    def add_sentence():
        topic, difficulty = request.form.get('topic') or 'general', 1
        try:
            russian = request.form.get('sentence', '')
            english = request.form.get('english', '')
            difficulty = stored_level(request.form.get('difficulty'))
            repository.validate_answer(russian, checking=True)
            if not english.strip():
                english = sentence_service.translate_for_library(russian)
            sentence_id, created = repository.save_content(russian, english, topic, difficulty)
        except (ValueError, TranslationUnavailable, sqlite3.Error) as error:
            if enhanced():
                return failure(error, preparing=True)
            library = context('sentences_saved')
            repository.record_reference_views([item['id'] for item in library['sentences']])
            return render_page('saved_sentences.html', **library, error=t('add_failed'),
                               added_russian=request.form.get('sentence', ''), added_english=request.form.get('english', ''),
                               added_topic=topic, added_level=difficulty,
                               add_open=True), 400
        target = url_for('sentences.sentences_saved', _anchor=f'sentence-{sentence_id}')
        return jsonify(url=target) if enhanced() else redirect(target, code=303)

    @blueprint.get('/sentences/saved/<int:sentence_id>')
    def sentences_saved_detail(sentence_id):
        item = repository.load(sentence_id)
        if not item:
            return page(error=t('missing')), 404
        repository.record_reference_views([sentence_id])
        return render_page('sentence_detail.html', sentence=present(item), active_page='sentences_saved')

    @blueprint.get('/sentences/saved')
    def sentences_saved():
        library = context('sentences_saved')
        if request.args.get('fetch_all') == 'true' and enhanced():
            repository.record_reference_views([item['id'] for item in library['sentences']])
            return jsonify(sentences=library['sentences'], topics=[topic['value'] for topic in library['topics']], error=None)
        selected = request.args.get('topic', '')
        selected_level = request.args.get('level', type=int)
        if selected_level not in range(1, 7):
            selected_level = ''
        search = request.args.get('q', '').strip()[:200]
        if selected:
            library['sentences'] = [item for item in library['sentences'] if item['topic'] == selected]
        if selected_level:
            library['sentences'] = [item for item in library['sentences'] if item['difficulty'] == selected_level]
        if search:
            query = search.casefold()
            library['sentences'] = [item for item in library['sentences']
                                    if query in (item.get('sentence') or '').casefold()
                                    or query in (item.get('english') or '').casefold()]
        repository.record_reference_views([item['id'] for item in library['sentences']])
        return render_page('saved_sentences.html', **library, selected_topic=selected,
                           selected_level=selected_level, search=search)

    return blueprint
