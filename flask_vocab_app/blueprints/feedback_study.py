"""Small previews which hand explicit learner choices to existing study tools."""
from flask import Blueprint, current_app, redirect, request
from repositories.learning_repository import LearningError, transaction
from services.feedback_study import capture_for_cards, require_capability, source, word_choices
from utils.activity_owner import activity_profile_id
from utils.shell import render_page


def create_feedback_study_blueprint():
    bp = Blueprint('feedback_study', __name__)

    def page(activity, identity, error=None, status=200):
        intent = 'flashcards' if request.method == 'POST' else request.args.get('intent', 'phrasebook')
        require_capability(intent)
        with transaction(current_app.config['DB_PATH']) as conn:
            data = source(conn, activity_profile_id(conn), activity, identity)
            if intent == 'flashcards':
                data['words'] = [word_choices(conn, text) for text in data['examples']]
        return render_page('feedback_study.html', study=data, intent=intent, error=error, active_page='writing'), status

    @bp.get('/study/feedback/<activity>/<identity>')
    def preview(activity, identity):
        return page(activity, identity)

    @bp.post('/study/feedback/<activity>/<identity>/word')
    def select_word(activity, identity):
        try:
            word_id = capture_for_cards(current_app.config['DB_PATH'], activity, identity,
                                        request.form.get('example'), request.form.get('reading'))
        except LearningError as error:
            if error.status in (404, 403):
                raise
            return page(activity, identity, str(error), error.status)
        return redirect('/#generate?word_id=' + str(word_id), code=303)

    return bp
