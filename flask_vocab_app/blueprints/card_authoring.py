"""Optional card editing, with publication controls in household mode."""
from flask import Blueprint, abort, current_app, redirect, render_template, request

from blueprints.word_post import BuildUnavailable, build_assets
from repositories.learning_repository import LearningError
from utils.household_access import access_id, access_policy


def create_card_authoring_blueprint(authoring,content):
    bp=Blueprint('card_authoring',__name__)

    @bp.before_request
    def enabled():
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED']:abort(404)

    def page(data=None,error=None,status=200):
        values=data or {}
        state=authoring.workspace(access_id(),query=request.args.get('q',''),word_id=values.get('word_id') or request.args.get('word_id'),edit=values.get('edit') or request.args.get('edit'))
        try:assets=build_assets(current_app.config['WORD_POST_DIST_DIR'])
        except BuildUnavailable:assets={'styles':[]}
        return render_template('card_authoring.html',state=state,values=values,error=error,assets=assets),status

    @bp.get('/post/flashcards/manage')
    @access_policy('adult')
    def workspace():
        reviewing = current_app.config['WORD_POST_HOUSEHOLD_ENABLED'] and request.args.get('review')
        if not reviewing and not any(request.args.get(key) for key in ('edit','manual')):
            word=request.args.get('word_id','')
            return redirect('/#generate'+('?word_id='+word if word.isdigit() else ''))
        return page()

    @bp.post('/post/flashcards/drafts')
    @access_policy('adult')
    def save():
        try:
            version=authoring.save(access_id(),request.form)
        except LearningError as error:
            # Keep every typed field on validation/stale-write failures.
            return page(request.form,str(error),error.status)
        if not current_app.config['WORD_POST_HOUSEHOLD_ENABLED']:
            if content.inspect(access_id(),version)['status']=='draft':
                content.publish(access_id(),version,'Me')
            return redirect('/#flashcards')
        return redirect('/post/flashcards/manage?review=1#version-'+version)

    @bp.post('/post/flashcards/actions')
    @access_policy('adult')
    def action():
        operation=request.form.get('action')
        if operation=='publish':
            household = current_app.config['WORD_POST_HOUSEHOLD_ENABLED']
            if household and request.form.get('approved')!='yes':raise LearningError('approval_required','Check this card and explicitly approve it first.')
            content.publish(access_id(),request.form.get('version_id'),request.form.get('reviewer') if household else 'Me')
        elif operation=='discard':authoring.discard(access_id(),request.form.get('version_id'))
        elif operation=='retire':authoring.retire(access_id(),request.form.get('card_id'))
        else:raise LearningError('invalid_action','Choose an available card action.')
        return redirect('/post/flashcards/manage?review=1' if current_app.config['WORD_POST_HOUSEHOLD_ENABLED'] else '/#flashcards')

    return bp
