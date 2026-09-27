from models.database import connect_db
import json
import logging
import os
import sqlite3
import tempfile
import uuid
from urllib.parse import unquote

import pymorphy3
from flask import Blueprint, jsonify, render_template, request, session

from repositories import FormRepository, WordRepository
from repositories.vocabulary_inventory import word_inventory
from utils.shell import is_shell_navigation, render_page

logger = logging.getLogger(__name__)
_morph = None


def get_morph():
    global _morph
    if _morph is None:
        _morph = pymorphy3.MorphAnalyzer()
    return _morph


def create_vocab_blueprint(db_path, drive_service, sync_service=None):
    blueprint = Blueprint("vocab", __name__)
    word_repository = WordRepository(db_path)
    form_repository = FormRepository(db_path)

    @blueprint.after_request
    def fresh_inventory(response):
        if request.path.startswith('/vocab'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def cloud_vocab_page(page=1, per_page=50):
        offset = (page - 1) * per_page
        cloud_content = drive_service.download_vocab_list()
        cloud_lemmas = sorted([w.strip() for w in cloud_content.split() if w.strip()])
        total_words = len(cloud_lemmas)
        total_pages = (total_words + per_page - 1) // per_page if total_words > 0 else 1
        words = [{"lemma": lemma} for lemma in cloud_lemmas[offset : min(offset + per_page, total_words)]]
        return words, total_pages

    def process_story_words(story_text):
        import re
        import unicodedata

        story_words = re.findall(r"\w+|[^\w\s]", story_text, re.UNICODE)
        word_objs = []
        added_lemmas = session.get("added_lemmas", set())
        try:
            cloud_content = drive_service.download_vocab_list()
            cloud_lemmas = {w.strip().lower() for w in cloud_content.split() if w.strip()}
            added_lemmas.update(cloud_lemmas)
            with connect_db(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT lemma FROM words")
                db_lemmas = {row[0].lower() for row in cursor.fetchall()}
            added_lemmas.update(db_lemmas)
            logger.debug("Fetched %s cloud lemmas, %s db lemmas", len(cloud_lemmas), len(db_lemmas))
        except Exception as e:
            logger.error("Error fetching added lemmas: %s", str(e))

        def sanitize(text):
            if text is None:
                return None
            text = unicodedata.normalize("NFKC", text)
            text = "".join(c for c in text if c.isprintable() and c not in '"\'\\')
            return text.encode("utf-8").decode("utf-8")

        for word in story_words:
            if not re.match(r"\w+", word, re.UNICODE):
                word_objs.append({"word": word, "lemma": None, "added": False})
                continue
            parsed = get_morph().parse(word)[0]
            lemma = parsed.normal_form if parsed.normal_form else None
            word = sanitize(word)
            lemma = sanitize(lemma)
            added = lemma.lower() in added_lemmas if lemma else False
            word_objs.append({"word": word, "lemma": lemma, "added": added})

        try:
            json.dumps(word_objs, ensure_ascii=False)
        except ValueError as e:
            logger.error("JSON serialization error in word_objs: %s, raw_data: %s", str(e), word_objs[:5])
            return [{"word": "Error", "lemma": None, "added": False}]

        return word_objs

    @blueprint.route("/metrics")
    def metrics():
        difficulty = request.args.get("difficulty", "all")
        topic = request.args.get("topic", "any")
        logger.debug("Metrics request: difficulty=%s, topic=%s", difficulty, topic)

        words = word_repository.list_basic()
        forms = form_repository.list_all()

        total_words = len(words)
        flashcard_total = sum(w["count"] for w in words)
        flashcard_percentage = (flashcard_total / total_words) * 100 if total_words > 0 else 0

        pos_distribution = {}
        for word in words:
            pos = word["pos"]
            pos_distribution[pos] = pos_distribution.get(pos, 0) + word["count"]

        case_distribution = {}
        conjugation_distribution = {}
        for form in forms:
            tags = form["tags"]
            if "case" in tags:
                case_distribution[tags["case"]] = case_distribution.get(tags["case"], 0) + form["count"]
            if "conjugation" in tags:
                conjugation_distribution[tags["conjugation"]] = (
                    conjugation_distribution.get(tags["conjugation"], 0) + form["count"]
                )

        difficulty_distribution = {}
        difficulty_word_counts = {}
        if difficulty == "all":
            try:
                difficulty_distribution, difficulty_word_counts = word_repository.difficulty_counts()
            except sqlite3.Error as e:
                logger.error("Difficulty query error: %s", str(e))

        topic_distribution = {}
        topic_word_counts = {}
        if topic == "any":
            try:
                topic_distribution, topic_word_counts = word_repository.topic_counts()
            except sqlite3.Error as e:
                logger.error("Topic query error: %s", str(e))

        data = {
            "total_words": total_words,
            "flashcard_total": flashcard_total,
            "flashcard_percentage": flashcard_percentage,
            "pos_distribution": pos_distribution,
            "case_distribution": case_distribution,
            "conjugation_distribution": conjugation_distribution,
            "difficulty_distribution": difficulty_distribution,
            "difficulty_word_counts": difficulty_word_counts,
            "topic_distribution": topic_distribution,
            "topic_word_counts": topic_word_counts,
        }

        logger.debug("Metrics response: %s", json.dumps(data, ensure_ascii=False))
        return jsonify(data)

    @blueprint.route("/vocab")
    def vocab_list():
        page = request.args.get("page", type=int) if "page" in request.args else 1
        if page is None or page < 1:
            return jsonify({"error": "Page must be a positive integer"}), 400
        source = request.args.get("source", "db")
        sort = request.args.get("sort", "lemma")
        order = request.args.get("order", "asc")
        fetch_all = request.args.get("fetch_all", "false").lower() == "true"
        per_page = 100
        offset = (page - 1) * per_page
        valid_columns = ["lemma", "pos", "topic", "lemma_difficulty", "mnemonic", "date_added", "count"]
        sort_column = sort if sort in valid_columns else "lemma"
        sort_order = "ASC" if order.lower() == "asc" else "DESC"

        error = None
        words = []
        total_pages = 1

        logger.debug(
            "Vocab request: page=%s, source=%s, sort=%s, order=%s, fetch_all=%s, accept=%s",
            page,
            source,
            sort_column,
            sort_order,
            fetch_all,
            request.headers.get("Accept"),
        )

        if source == "cloud":
            try:
                cloud_content = drive_service.download_vocab_list()
                cloud_lemmas = sorted([w.strip() for w in cloud_content.split() if w.strip()])
                total_words = len(cloud_lemmas)
                if fetch_all:
                    words = [{"lemma": lemma} for lemma in cloud_lemmas]
                    total_pages = 1
                else:
                    total_pages = (total_words + per_page - 1) // per_page if total_words > 0 else 1
                    start_idx = offset
                    end_idx = min(start_idx + per_page, total_words)
                    words = [{"lemma": lemma} for lemma in cloud_lemmas[start_idx:end_idx]]
                logger.debug("Cloud vocab: %s lemmas, page %s, %s displayed", total_words, page, len(words))
            except Exception as e:
                logger.error("Error fetching cloud vocab: %s", str(e))
                error = f"Ошибка загрузки vocab_list.txt: {str(e)}"
                words = []
                total_pages = 1
                page = 1
        else:
            try:
                total_words = word_repository.count()
                if fetch_all:
                    words = word_repository.list_vocab(sort_column, sort_order)
                    total_pages = 1
                else:
                    total_pages = (total_words + per_page - 1) // per_page if total_words > 0 else 1
                    words = word_repository.list_vocab(sort_column, sort_order, limit=per_page, offset=offset)
                logger.debug(
                    "Database vocab: %s lemmas, page %s, %s displayed, sort=%s, order=%s",
                    total_words,
                    page,
                    len(words),
                    sort_column,
                    sort_order,
                )
            except sqlite3.Error as e:
                logger.error("Database error: %s", str(e))
                error = f"Ошибка базы данных: {str(e)}"
                words = []
                total_pages = 1
                page = 1

        if "application/json" in request.headers.get("Accept", "") and source == "db":
            logger.debug("Returning JSON for source=%s", source)
            return jsonify(
                {
                    "words": words,
                    "page": page,
                    "total_pages": total_pages,
                    "source": source,
                    "error": error,
                    "sort": sort_column,
                    "order": sort_order,
                }
            )

        if request.headers.get("HX-Request") and not is_shell_navigation():
            logger.debug("Returning HTMX HTML for source=%s", source)
            return render_template(
                "_vocab_dynamic_content.html",
                words=words,
                page=page,
                total_pages=total_pages,
                source=source,
                error=error,
                sort=sort_column,
                order=sort_order,
            )

        logger.debug("Returning full HTML for source=%s", source)
        return render_page(
            "vocab-list.html",
            words=words,
            page=page,
            total_pages=total_pages,
            source=source,
            error=error,
            sort=sort_column,
            order=sort_order,
            active_page="vocab",
        )

    @blueprint.route("/add_word", methods=["POST"])
    def add_word():
        word = request.form.get("word", "").strip()
        page = request.args.get("page", type=int) if "page" in request.args else 1
        if page is None or page < 1:
            return jsonify({"error": "Page must be a positive integer"}), 400
        is_comprehension = request.form.get("is_comprehension", "false") == "true"

        if not word:
            error_response = {"error": "Введите слово"}
            return (
                jsonify(error_response)
                if request.accept_mimetypes.accept_json
                else '<div class="alert alert-danger">Введите слово</div>',
                400,
            )
        try:
            if drive_service.add_word(word):
                added_lemmas = session.get("added_lemmas", set())
                added_lemmas.add(word.lower())
                session["added_lemmas"] = added_lemmas
                logger.debug("Added %s to vocab list, updated added_lemmas: %s", word, added_lemmas)
                if is_comprehension:
                    story_text = session.get("current_story_text", "")
                    if story_text:
                        words = process_story_words(story_text)
                        story_data = session.get("current_story_data", {})
                        story_data["words"] = words
                        if request.accept_mimetypes.accept_json:
                            return jsonify({"success": f'Слово "{word}" добавлено в список!', "story_data": story_data})
                        return render_template(
                            "_comprehension_content.html",
                            story=story_data,
                            visibility=session.get("visibility", "revealed"),
                        )
                    success_response = {"success": f'Слово "{word}" добавлено в список!'}
                    return (
                        jsonify(success_response)
                        if request.accept_mimetypes.accept_json
                        else f'<div class="alert alert-success">Слово "{word}" добавлено в список!</div>'
                    )

                words, total_pages = cloud_vocab_page(page=page)
                return render_template(
                    "_vocab_dynamic_content.html",
                    words=words,
                    page=page,
                    total_pages=total_pages,
                    source="cloud",
                    error=None,
                )

            error_response = {"error": f'Слово "{word}" уже существует'}
            return (
                jsonify(error_response)
                if request.accept_mimetypes.accept_json
                else f'<div class="alert alert-warning">Слово "{word}" уже существует</div>',
                400,
            )
        except Exception as e:
            logger.error("Add word error: %s", str(e))
            error_response = {"error": f"Ошибка добавления: {str(e)}"}
            return (
                jsonify(error_response)
                if request.accept_mimetypes.accept_json
                else f'<div class="alert alert-danger">Ошибка добавления: {str(e)}</div>',
                500,
            )

    @blueprint.route("/edit_word", methods=["POST"])
    def edit_word():
        old_word = request.form.get("old_word", "").strip()
        new_word = request.form.get("new_word", "").strip()
        if not old_word or not new_word:
            return '<div class="alert alert-danger">Введите оба слова</div>', 400
        try:
            if drive_service.update_word(old_word, new_word):
                return render_template(
                    "_vocab_dynamic_content.html",
                    words=[{"lemma": new_word}],
                    page=1,
                    total_pages=1,
                    source="cloud",
                    error=None,
                )
            return f'<div class="alert alert-warning">Слово "{old_word}" не найдено или "{new_word}" уже существует</div>', 400
        except Exception as e:
            logger.error("Edit word error: %s", str(e))
            return f'<div class="alert alert-danger">Ошибка редактирования: {str(e)}</div>', 500

    @blueprint.route("/delete_word", methods=["POST"])
    def delete_word():
        word = request.form.get("word", "").strip()
        if not word:
            return '<div class="alert alert-danger">Введите слово</div>', 400
        try:
            if drive_service.delete_word(word):
                return render_template(
                    "_vocab_dynamic_content.html",
                    words=[],
                    page=1,
                    total_pages=1,
                    source="cloud",
                    error=None,
                )
            return f'<div class="alert alert-warning">Слово "{word}" не найдено</div>', 400
        except Exception as e:
            logger.error("Delete word error: %s", str(e))
            return f'<div class="alert alert-danger">Ошибка удаления: {str(e)}</div>', 500

    @blueprint.route("/sync/preview", methods=["GET"])
    def sync_preview():
        logger.debug("Handling GET /sync/preview")
        db_only, cloud_only, error = sync_service.compare_vocab()
        if error:
            logger.error("Compare vocab error: %s", error)
            return jsonify({"error": error}), 500
        preview, error = sync_service.preview_sync(cloud_only)
        if error:
            logger.error("Preview sync error: %s", error)
            return jsonify({"error": error}), 500
        if not isinstance(preview, dict):
            logger.error("Invalid preview: %s", preview)
            preview = {"to_add": [], "rejected": []}
        preview.setdefault("to_add", [])
        preview.setdefault("rejected", [])
        logger.debug("Sync preview (API): %s", preview)
        return jsonify({"db_only": db_only, "preview": preview})

    @blueprint.route("/sync", methods=["POST"])
    def sync():
        logger.debug("Handling POST /sync")
        try:
            data = request.get_json()
            if not data or "to_add" not in data:
                logger.error("Invalid sync request: missing to_add")
                return jsonify({"error": "Missing to_add data"}), 400
            to_add = data.get("to_add", [])
            if not isinstance(to_add, list):
                logger.error("Invalid to_add format: %s", to_add)
                return jsonify({"error": "Invalid to_add format"}), 400
            if any(not isinstance(entry, dict) or not isinstance(entry.get("word", entry.get("lemma")), str) for entry in to_add):
                return jsonify({"error": "Each selected entry must contain a word"}), 400
            captures = [entry.get("word", entry.get("lemma")) for entry in to_add]
            result = sync_service.sync_vocab(captures)
            return jsonify(result)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except Exception:
            logger.error("Unexpected error in sync", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500

    @blueprint.route("/sync/history")
    def sync_history():
        with connect_db(db_path) as conn:
            rows = conn.execute("SELECT id, started_at, finished_at, status, summary FROM sync_runs ORDER BY id DESC LIMIT 20").fetchall()
        return jsonify({"runs": [dict(id=r[0], started_at=r[1], finished_at=r[2], status=r[3], result=json.loads(r[4])) for r in rows]})

    @blueprint.route("/sync_vocab", methods=["GET", "POST"])
    def sync_vocab():
        logger.debug("Handling %s /sync_vocab", request.method)
        try:
            db_only, cloud_only, error = sync_service.compare_vocab()
            if error:
                logger.error("Compare vocab error: %s", error)
                return render_template("_error.html", error=error), 500
            preview, error = sync_service.preview_sync(cloud_only)
            if error:
                logger.error("Preview sync error: %s", error)
                return render_template("_error.html", error=error), 500
            if not isinstance(preview, dict):
                logger.error("Invalid preview: %s", preview)
                preview = {"to_add": [], "rejected": []}
            preview.setdefault("to_add", [])
            preview.setdefault("rejected", [])
            logger.debug("Sync preview: %s", preview)
            return render_template("_sync_preview.html", db_only=db_only, preview=preview)
        except Exception:
            logger.error("Unexpected error in sync_vocab", exc_info=True)
            return render_template("_error.html", error="Internal server error"), 500

    @blueprint.route("/sanitize_vocab", methods=["POST"])
    def sanitize_vocab():
        logger.debug("Handling POST /sanitize_vocab")
        try:
            sanitization, to_keep, error = sync_service.sanitize_vocab_list()
            if error:
                return render_template("_error.html", error=error), 500
            sanitization_id = str(uuid.uuid4())
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as temp_file:
                json.dump(to_keep, temp_file)
                temp_file_path = temp_file.name
            session["sanitization"] = sanitization
            session["sanitization_id"] = sanitization_id
            session["temp_file_path"] = temp_file_path
            logger.debug(
                "Sanitize session set: id=%s, temp_file=%s, sanitization_keys=%s",
                sanitization_id,
                temp_file_path,
                list(sanitization.keys()),
            )
            return render_template("_sanitize_preview.html", sanitization=sanitization, sanitization_id=sanitization_id)
        except Exception as e:
            logger.error("Unexpected error in sanitize_vocab: %s", str(e))
            return render_template("_error.html", error=str(e)), 500

    @blueprint.route("/apply_sanitization", methods=["POST"])
    def apply_sanitization():
        logger.debug("Handling POST /apply_sanitization")
        try:
            logger.debug("Apply sanitization requested")
            sanitization = session.get("sanitization")
            sanitization_id = session.get("sanitization_id")
            temp_file_path = session.get("temp_file_path")
            consolidate = request.form.get("consolidate") == "true"
            expected_id = request.form.get("sanitization_id")

            logger.debug(
                "Apply sanitization: sanitization_id=%s, expected_id=%s, temp_file_path=%s, consolidate=%s",
                sanitization_id,
                expected_id,
                temp_file_path,
                consolidate,
            )

            if not sanitization or not temp_file_path or not sanitization_id:
                raise ValueError("Missing session data: sanitization, sanitization_id, or temp_file_path")
            if sanitization_id != expected_id:
                raise ValueError("Sanitization ID mismatch")

            with open(temp_file_path, "r") as temp_file:
                to_keep = json.load(temp_file)
            os.unlink(temp_file_path)

            if consolidate:
                new_to_keep = []
                seen_lemmas = set()
                for entry in to_keep:
                    lemma = entry["lemma"]
                    pos = entry["pos"]
                    lemma_pos = (lemma, pos)
                    if lemma_pos in seen_lemmas:
                        continue
                    seen_lemmas.add(lemma_pos)
                    word = lemma if entry["word"] != lemma else entry["word"]
                    new_to_keep.append({"word": word, "lemma": lemma, "pos": pos})
                to_keep = new_to_keep

            error = sync_service.apply_sanitization(to_keep)
            if error:
                return render_template("_error.html", error=error), 500

            session.pop("sanitization", None)
            session.pop("sanitization_id", None)
            session.pop("temp_file_path", None)
            logger.debug("Sanitization applied, session cleared")
            return jsonify({"status": "success"})
        except Exception as e:
            logger.error("Apply sanitization error: %s", str(e))
            return render_template("_error.html", error=str(e)), 500

    @blueprint.get('/vocab/words/<int:word_id>')
    def inventory(word_id):
        with connect_db(db_path) as conn:
            conn.row_factory = sqlite3.Row
            result = word_inventory(conn, word_id)
        if result is None:
            return jsonify(error='This word was not found.'), 404
        return jsonify(result)

    @blueprint.route("/word-details/<word>", methods=['GET', 'POST'])
    def word_details(word):
        from contracts.learning import fields
        from repositories.learning_repository import LearningError
        from services.story_vocabulary import lookup_story_word
        try:
            source = request.get_json(silent=True) if request.method == 'POST' else request.args
            if not isinstance(source, dict) and request.method == 'POST':
                raise LearningError('json_required', 'Reopen this story before choosing a word.', 415)
            if request.method == 'POST':
                source = fields(source, {'story_key'}, {'story_id', 'task_id'})
            return jsonify(lookup_story_word(db_path, word, source))
        except LearningError as error:
            return jsonify(error={'code': error.code, 'message': str(error), **error.details}), error.status

    @blueprint.route("/add-vocab/<lemma>", methods=["POST"])
    def add_vocab(lemma):
        from contracts.learning import fields
        from repositories.learning_repository import LearningError
        from services.story_vocabulary import capture_story_word
        try:
            if not request.is_json:
                raise LearningError('json_required', 'Reopen this story before adding a word.', 415)
            data = fields(request.get_json(silent=True), {'word', 'pos', 'story_key'}, {'story_id', 'task_id'})
            return jsonify(capture_story_word(db_path, data['word'], lemma, data['pos'], data))
        except LearningError as error:
            return jsonify(error={'code': error.code, 'message': str(error), **error.details}), error.status

    return blueprint
