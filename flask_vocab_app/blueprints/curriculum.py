"""Read-only course catalogue. Activity links prefill existing generators."""
from flask import Blueprint, abort, current_app, jsonify, redirect, request, session

from services.curriculum import band_summaries, get_topic
from services.speaking_curriculum import scenario_for_topic
from services.torfl_requirements import requirement_groups
from services.curriculum_units import get_unit, unit_summaries, start_practice, start_writing
from repositories.learning_repository import LearningError, identifier, require_access, timestamp, transaction
from utils.household_access import access_policy, access_id
from utils.shell import render_page


def create_curriculum_blueprint():
    blueprint = Blueprint('curriculum', __name__)

    def sequences():
        from services.curriculum_sequences import CurriculumSequenceService
        return CurriculumSequenceService(current_app.config['DB_PATH'])

    def json_body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise LearningError('invalid_input', 'Send a lesson request.')
        return value

    @blueprint.get('/api/v1/curriculum/summary')
    @access_policy('child')
    def assessed_summary():
        from services.curriculum_summary import summary
        return jsonify(summary(current_app.config['DB_PATH'], access_id(), request.args.get('level', 'A1')))

    @blueprint.post('/api/v1/curriculum/units/<unit_id>/runs')
    @access_policy('child')
    def start_run(unit_id):
        return jsonify(sequences().start(access_id(), unit_id, json_body()))

    @blueprint.get('/api/v1/curriculum/runs/<run_id>')
    @access_policy('child')
    def read_run(run_id):
        return jsonify(sequences().read(access_id(), run_id))

    @blueprint.post('/api/v1/curriculum/runs/<run_id>/steps/<step_id>/start')
    @access_policy('child')
    def start_run_step(run_id, step_id):
        return jsonify(sequences().command(access_id(), run_id, 'start_step', json_body(), step_id))

    @blueprint.post('/api/v1/curriculum/runs/<run_id>/steps/<step_id>/retry')
    @access_policy('child')
    def retry_run_step(run_id, step_id):
        return jsonify(sequences().command(access_id(), run_id, 'retry', json_body(), step_id))

    @blueprint.post('/api/v1/curriculum/runs/<run_id>/navigation')
    @access_policy('child')
    def navigate_run(run_id):
        return jsonify(sequences().command(access_id(), run_id, 'navigation', json_body()))

    @blueprint.get('/curriculum')
    @access_policy('public')
    def index():
        language = 'ru' if session.get('ui_lang') == 'ru' else 'en'
        return render_page('curriculum.html', active_page='curriculum',
                           bands=band_summaries(language), language=language,
                           requirement_groups=requirement_groups)

    @blueprint.get('/curriculum/levels/<level>')
    @access_policy('public')
    def outcomes_page(level):
        language = 'ru' if session.get('ui_lang') == 'ru' else 'en'
        reference = requirement_groups(level, language)
        if reference is None:
            abort(404)
        return render_page('curriculum_outcomes.html', active_page='curriculum',
                           language=language, reference=reference)

    @blueprint.get('/curriculum/topics/<topic_id>')
    @access_policy('public')
    def topic_page(topic_id):
        topic = get_topic(topic_id)
        if topic is None:
            abort(404)
        language = 'ru' if session.get('ui_lang') == 'ru' else 'en'
        from services.curriculum_sequence_content import load_manifest
        manifest = load_manifest()
        units = unit_summaries()
        # Prefer the connected edition in the catalogue. Issued v1 lessons
        # retain their original URL, content and evidence.
        units = [{**manifest, 'id': manifest['unit_id']} if unit['id'] == 'location-destination-v1' else unit for unit in units]
        return render_page('curriculum_topic.html', active_page='curriculum',
                           language=language, topic=topic, band={'id': topic['band']},
                           speaking_scenario=scenario_for_topic, units=units)

    def unit_or_404(unit_id):
        from services.curriculum_sequences import UNIT
        if unit_id == UNIT:
            from services.curriculum_sequence_content import load_manifest, load_asset
            manifest = load_manifest()
            teaching = load_asset(next(s['content_id'] for s in manifest['steps'] if s['adapter'] == 'teaching'))
            return {**manifest, 'id': UNIT, 'groups': teaching['content']['groups'], 'teaching': teaching['content']}
        try:
            return get_unit(unit_id)
        except LookupError:
            abort(404)

    @blueprint.get('/curriculum/units/<unit_id>')
    @access_policy('public')
    def unit_page(unit_id):
        language = 'ru' if session.get('ui_lang') == 'ru' else 'en'
        profile_id = None
        if access_id():
            with transaction(current_app.config['DB_PATH']) as conn:
                try:
                    profile_id = require_access(conn, access_id(), timestamp())['id']
                except LearningError:
                    pass
        from services.curriculum_sequences import UNIT, _capability
        sequence = None
        if unit_id == UNIT:
            from services.curriculum_sequence_content import load_manifest, load_asset
            run = sequences().read(access_id(), request.args['run']) if request.args.get('run') else None
            if run and run['unit_id'] != unit_id:
                abort(404)
            if not run and profile_id:
                from services.curriculum_sequences import SEQUENCE
                with transaction(current_app.config['DB_PATH']) as conn:
                    saved = conn.execute('SELECT id FROM curriculum_unit_runs WHERE profile_id=? AND sequence_id=? ORDER BY updated_at DESC,rowid DESC LIMIT 1',
                                         (profile_id, SEQUENCE)).fetchone()
                run = sequences().read(access_id(), saved[0]) if saved else None
            if run:
                from repositories.curriculum_sequence_repository import owned_run
                with transaction(current_app.config['DB_PATH']) as conn:
                    manifest = owned_run(conn, profile_id, run['id'])['manifest']
                asset_for = lambda identity: manifest['assets'][identity]
            else:
                manifest = load_manifest()
                asset_for = load_asset
            teaching = asset_for(next(s['content_id'] for s in manifest['steps'] if s['adapter'] == 'teaching'))
            unit = {**manifest, 'id': UNIT, 'groups': teaching['content']['groups'], 'teaching': teaching['content']}
            steps = []
            for step in manifest['steps']:
                asset = asset_for(step['content_id'])
                availability = _capability(asset)
                if asset['kind'] == 'task_group':
                    if run:
                        # An allocated run has one chosen family; unrelated
                        # recordings cannot disable its remaining work.
                        availability = next(s['availability'] for s in run['steps'] if s['id'] == step['id'])
                    else:
                        families = [[_capability(asset_for(cid)) for cid in family['task_ids']]
                                    for family in asset['content']['families']]
                        availability = ('available' if any(all(value == 'available' for value in family) for family in families)
                                        else next(value for family in families for value in family if value != 'available'))
                steps.append({'id': step['id'], 'label': asset['title'], 'label_ru': asset['title_ru'],
                              'availability': availability})
            sequence = {'id': manifest['id'], 'unit_id': unit_id, 'steps': steps, 'run': run}
            if manifest.get('next_unit_id'):
                following = get_unit(manifest['next_unit_id'])
                sequence['next_unit'] = {'url': '/curriculum/units/' + following['id'],
                                         'title': following['title'], 'title_ru': following['title_ru']}
        else:
            unit = unit_or_404(unit_id)
        return render_page('curriculum_unit.html', active_page='curriculum', unit=unit, curriculum_sequence=sequence,
                           language=language, profile_id=profile_id, request_id=identifier(), forms_request_id=identifier(), listening_request_id=identifier(),
                           unit_writing_available=not current_app.config.get('PUBLIC_DEMO'))

    @blueprint.post('/curriculum/units/<unit_id>/<activity>')
    @access_policy('child')
    def unit_start(unit_id, activity):
        from services.curriculum_sequences import UNIT
        fresh = activity in ('fresh-practice', 'fresh-forms') or (activity in ('practice', 'forms') and request.form.get('generation') == 'rules')
        if unit_id == UNIT and not fresh:
            return redirect('/curriculum/units/' + UNIT, code=303)
        unit_or_404(unit_id)
        if activity not in ('practice', 'forms', 'listening', 'writing', 'fresh-practice', 'fresh-forms'):
            abort(404)
        if activity == 'writing' and current_app.config['WORD_POST_HOUSEHOLD_ENABLED']:
            # The legacy Writing workspace belongs to the household adult.
            # Do not create an unreachable child-owned exercise in that store.
            raise LearningError('activity_unavailable', 'This writing workspace is not available for the selected learner.', 403)
        db_path = current_app.config['DB_PATH']
        with transaction(db_path) as conn:
            profile = require_access(conn, access_id(), timestamp())
            if request.form.get('profile_id') != profile['id']:
                raise LearningError('profile_changed', 'Your profile changed. Reopen this lesson before continuing.', 409)
        if activity == 'writing':
            return redirect('/writing/load/' + str(start_writing(db_path, access_id(), unit_id,
                            expected_profile_id=profile['id'])), code=303)
        if fresh:
            from services.curriculum_fresh_practice import start
            saved = start(db_path, access_id(), unit_id, request.form.get('request_id'),
                expected_profile_id=profile['id'], stage=activity.removeprefix('fresh-'))
            return redirect('/#practice/' + saved['id'], code=303)
        saved = start_practice(db_path, access_id(), unit_id, request.form.get('request_id'),
                               expected_profile_id=profile['id'], stage=activity)
        return redirect('/#practice/' + saved['id'], code=303)

    return blueprint
