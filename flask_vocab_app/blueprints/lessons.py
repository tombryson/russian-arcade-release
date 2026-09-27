"""Lesson library, source versions, reading bookmarks and one exercise at a time."""
import json
import io
from pathlib import Path
from PIL import Image

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    send_file,
    url_for,
    current_app,
    abort,
)

from repositories.learning_repository import (
    LearningError,
    identifier,
    require_access,
    timestamp,
    transaction,
)
from utils.household_access import access_id
from utils.shell import render_page, is_shell_navigation
from utils.activity_display import readable_date


def create_lessons_blueprint(legacy, companion, cards=None, selection=None):
    bp = Blueprint("lessons", __name__)

    def profile():
        with transaction(companion.db_path) as conn:
            return require_access(conn, access_id(), timestamp())["id"]

    def lang():
        return "ru" if session.get("ui_lang") == "ru" else "en"

    @bp.context_processor
    def strings():
        return {
            "lt": lambda en, ru: ru if lang() == "ru" else en,
            "lesson_language": lang(),
        }

    def page(lesson_id=None, **extra):
        lesson = legacy.get_lesson(lesson_id) if lesson_id else None
        if lesson_id and not lesson:
            raise LearningError("not_found", "This lesson was not found.", 404)
        person = profile()
        library = companion.library(person)
        for item in library:
            item["display_date"] = readable_date(item.get("created_at"), lang())
        state = (
            companion.snapshot(lesson_id, person, request.args.get("revision"))
            if lesson
            else None
        )
        selected = None
        number = request.args.get("page", type=int)
        if state:
            number = max(
                1,
                min(
                    number or state["progress"].get("page", 1), len(state["pages"]) or 1
                ),
            )
            task_id = request.args.get("task") or state["progress"].get("task_id")
            selected = next(
                (t for t in state["tasks"] if t["id"] == task_id),
                next(
                    (t for t in state["tasks"] if not t["checked"]),
                    state["tasks"][0] if state["tasks"] else None,
                ),
            )
        view = request.args.get("view", "overview")
        if view not in {"overview", "materials", "practice", "flashcards"}:
            view = "overview"
        page_image_size = None
        if state and state['pages'] and (view in {'materials', 'flashcards'} or not state['plan']):
            try:
                with Image.open(companion.files.path(state['pages'][number-1]['image_digest'])) as image:
                    page_image_size = image.size
            except OSError:
                pass  # Keep the reader usable if its original image needs repair.
        context = dict(
            lesson=lesson,
            saved_lessons=library,
            companion=state,
            selected_task=selected,
            page_number=number,
            page_image_size=page_image_size,
            lesson_view=view,
            lesson_card_history=cards.history(access_id(), lesson_id) if cards and lesson and view=='flashcards' else [],
            submission_key=identifier(),
            active_page="lessons",
            **extra
        )
        if request.headers.get("HX-Request") and not is_shell_navigation():
            return render_template("_lesson_content.html", **context)
        return render_page("lessons.html", **context)

    def location(lesson_id, revision=None, **kwargs):
        return url_for(
            "lessons.load",
            lesson_id=lesson_id,
            **({"revision": revision} if revision else {}),
            **kwargs
        )

    @bp.errorhandler(LearningError)
    def failure(error):
        if request.accept_mimetypes.best == "application/json":
            return jsonify(error=str(error)), error.status
        lesson_id = (request.view_args or {}).get('lesson_id') if request.endpoint in {'lessons.create_cards','lessons.prepare_cards'} else None
        return page(lesson_id if lesson_id and legacy.get_lesson(lesson_id) else None, error=str(error)), error.status

    @bp.get("/lessons")
    def home():
        return page()

    @bp.get("/lessons/load/<lesson_id>")
    def load(lesson_id):
        return page(lesson_id)

    @bp.post("/lessons/create")
    def create():
        materials = companion.receive(
            [request.files.get("pdf"), *request.files.getlist("images")]
        )
        lesson_id, rid, duplicate = companion.create(
            request.form.get("title"), request.form.get("description"), materials
        )
        if not duplicate:
            companion.dispatch(rid)
        return redirect(location(lesson_id, rid), 303)

    @bp.post('/lessons/<lesson_id>/flashcards')
    def create_cards(lesson_id):
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED']:
            abort(404)
        request_id = cards.create(access_id(), lesson_id, request.form.get('revision_id'),
                                  request.form.get('first_page', type=int), request.form.get('last_page', type=int),
                                  request.form.get('quantity', type=int))
        return redirect(location(lesson_id, request.form.get('revision_id'), view='flashcards', card_request=request_id), 303)

    @bp.get('/lessons/<lesson_id>/word-selection/<revision_id>')
    def selected_words(lesson_id,revision_id):
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED']:abort(404)
        return jsonify(selection.pending(access_id(),lesson_id,revision_id))

    @bp.get('/lessons/<lesson_id>/word-selection/<revision_id>/<int:number>')
    def selection_page(lesson_id,revision_id,number):
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED']:abort(404)
        return jsonify(selection.page(access_id(),lesson_id,revision_id,number))

    @bp.post('/lessons/<lesson_id>/word-selection/<revision_id>/area')
    def select_area(lesson_id,revision_id):
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED']:abort(404)
        selection.pending(access_id(),lesson_id,revision_id)
        data=request.get_json(silent=True) or {}
        if not isinstance(data,dict):
            raise LearningError('invalid_selection','Choose a word on the page.',422)
        if type(data.get('page')) is not int:
            raise LearningError('invalid_page','Choose a lesson page.',422)
        return jsonify(selection.ocr.read_area(lesson_id,revision_id,data['page'],data.get('box')))

    @bp.get('/lessons/<lesson_id>/word-selection/<revision_id>/<int:number>/crop/<region_id>')
    def selection_crop(lesson_id,revision_id,number,region_id):
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED']:abort(404)
        selection.pending(access_id(),lesson_id,revision_id)
        region=selection.ocr.region(lesson_id,revision_id,number,region_id)
        picture=selection.ocr.crop(lesson_id,revision_id,number,region)
        content=io.BytesIO();picture.save(content,format='PNG');content.seek(0)
        return send_file(content,mimetype='image/png',max_age=0)

    @bp.post('/lessons/<lesson_id>/word-selection/<revision_id>')
    def select_word(lesson_id,revision_id):
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED']:abort(404)
        data=request.get_json(silent=True) or {}
        if not isinstance(data,dict):
            raise LearningError('invalid_selection','Choose a word on the page.',422)
        if data.get('action')=='edit':
            result=selection.edit(access_id(),lesson_id,revision_id,data.get('id'),data.get('surface'))
        else:
            if type(data.get('page')) is not int:
                raise LearningError('invalid_page','Choose a lesson page.',422)
            result=selection.choose(access_id(),lesson_id,revision_id,data['page'],data.get('token'),data.get('selected'),surface=data.get('surface'),confirmed=data.get('confirmed',False))
        return jsonify(result)

    @bp.post('/lessons/<lesson_id>/word-selection/<revision_id>/create')
    def create_selected_cards(lesson_id,revision_id):
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED']:abort(404)
        request_id=selection.create(access_id(),lesson_id,revision_id)
        target=location(lesson_id,revision_id,view='flashcards',card_request=request_id)
        if request.accept_mimetypes.best=='application/json':return jsonify(url=target)
        return redirect(target,303)

    @bp.post('/lessons/<lesson_id>/flashcards/<request_id>/prepare')
    def prepare_cards(lesson_id, request_id):
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED']:
            abort(404)
        result = cards.advance(access_id(), request_id, lesson_id)
        result['url'] = '/#generate/'+result['batch_id'] if result['batch_id'] else location(lesson_id, view='flashcards', card_request=request_id)
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(result)
        return redirect(result['url'], 303)

    @bp.post("/lessons/<lesson_id>/revision")
    def revise(lesson_id):
        materials = companion.receive(
            [request.files.get("pdf"), *request.files.getlist("images")]
        )
        rid = companion.revise(lesson_id, materials)
        companion.dispatch(rid)
        return redirect(location(lesson_id, rid), 303)

    @bp.post("/lessons/generate/<lesson_id>")
    def prepare(lesson_id):
        rid = request.form.get("revision_id")
        if rid:
            companion.revision(rid, lesson_id)
        else:
            rid = companion.adopt_legacy(lesson_id)
        companion.dispatch(rid)
        return redirect(location(lesson_id, rid), 303)

    @bp.get("/lessons/<lesson_id>/status/<revision_id>")
    def status(lesson_id, revision_id):
        state = companion.snapshot(lesson_id, profile(), revision_id)
        r = state["revision"]
        return jsonify(
            state=r["state"],
            stage=r["stage"],
            pages_read=state["pages_read"],
            page_total=state["page_total"],
            retryable=state["retryable"],
            error=r["error"],
            url=location(lesson_id, revision_id),
        )

    @bp.get("/lessons/<lesson_id>/source/<int:index>")
    def source(lesson_id, index):
        rid = request.args.get("revision")
        if rid:
            r = companion.revision(rid, lesson_id)
            materials = json.loads(r["materials"])
            if not 0 <= index < len(materials):
                raise LearningError("not_found", "This file was not found.", 404)
            m = materials[index]
            return send_file(
                companion.files.path(m["digest"]),
                mimetype=m["media_type"],
                download_name=m["name"],
            )
        lesson = legacy.get_lesson(lesson_id)
        if not lesson:
            raise LearningError("not_found", "This lesson was not found.", 404)
        refs = ([lesson["pdf_path"]] if lesson.get("pdf_path") else []) + lesson.get(
            "images", []
        )
        if not 0 <= index < len(refs):
            raise LearningError("not_found", "This file was not found.", 404)
        path = companion.files.legacy(refs[index])
        mime = companion.files.inspect(path.read_bytes())[0]
        return send_file(
            path,
            mimetype=mime,
            download_name="lesson.pdf" if mime == "application/pdf" else "lesson-image",
        )

    @bp.get("/lessons/<lesson_id>/page/<revision_id>/<int:number>")
    def image(lesson_id, revision_id, number):
        companion.revision(revision_id, lesson_id)
        with transaction(companion.db_path) as conn:
            p = conn.execute(
                "SELECT image_digest FROM lesson_pages WHERE revision_id=? AND number=?",
                (revision_id, number),
            ).fetchone()
        if not p:
            raise LearningError("not_found", "This page was not found.", 404)
        return send_file(companion.files.path(p["image_digest"]), mimetype="image/jpeg")

    @bp.post("/lessons/<lesson_id>/bookmark")
    def bookmark(lesson_id):
        rid = request.form.get("revision_id")
        number = request.form.get("page", type=int)
        task = request.form.get("task_id")
        companion.bookmark(profile(), lesson_id, rid, number, task)
        if request.accept_mimetypes.best == "application/json":
            return jsonify(saved=True)
        return redirect(
            location(
                lesson_id,
                rid,
                view="practice" if task else "materials",
                page=number,
                **({"task": task} if task else {})
            ),
            303,
        )

    @bp.post("/lessons/<lesson_id>/draft")
    def draft(lesson_id):
        revision = companion.save_draft(
            profile(),
            lesson_id,
            request.form.get("task_id"),
            request.form.get("answer", ""),
            request.form.get("draft_revision", type=int),
        )
        return jsonify(revision=revision)

    @bp.post("/lessons/<lesson_id>/check")
    def check(lesson_id):
        task_id = request.form.get("task_id")
        person = profile()
        task = companion.task(task_id, lesson_id)
        answer = request.form.get("answer", "")
        try:
            companion.assess(
                person,
                lesson_id,
                task_id,
                answer,
                request.form.get("draft_revision", type=int),
                request.form.get("submission_key"),
            )
        except LearningError as error:
            if request.accept_mimetypes.best == "application/json":
                return jsonify(error=str(error)), error.status
            return redirect(
                location(
                    lesson_id,
                    task["revision_id"],
                    view="practice",
                    task=task_id,
                    notice="check-failed",
                ),
                303,
            )
        url = location(lesson_id, task["revision_id"], view="practice", task=task_id)
        if request.accept_mimetypes.best == "application/json":
            return jsonify(url=url)
        return redirect(url, 303)

    @bp.post("/lessons/mark/<lesson_id>")
    def legacy_check(lesson_id):
        # Old generated questions/history remain visible, but cannot be assessed
        # without source analysis. New tasks use the versioned marking contract.
        raise LearningError(
            "lesson_prepare",
            "Prepare this lesson to practise with questions checked against its source.",
        )

    return bp
