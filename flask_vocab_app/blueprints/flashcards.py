import logging

from flask import Blueprint, jsonify, render_template_string, request

from repositories import WordRepository
from utils.pos_case import CASE_LIST, POS_LIST
from utils.shell import render_page

logger = logging.getLogger(__name__)


def create_flashcards_blueprint(db_path, flashcard_service, user_service):
    blueprint = Blueprint("flashcards", __name__)
    word_repository = WordRepository(db_path)

    @blueprint.route("/tools/anki/")
    def index():
        words = word_repository.list_basic()
        try:
            topics = word_repository.list_topics()
        except Exception as e:
            logger.error("Database error fetching topics: %s", str(e))
            topics = []

        return render_page(
            "index.html",
            pos_list=POS_LIST,
            case_list=CASE_LIST,
            words=words,
            topics=topics,
            active_page="flashcards",
        )

    @blueprint.route("/generate", methods=["POST"])
    def generate():
        """Generate flashcards based on user input."""
        pos = request.form.getlist("pos")
        case = request.form.get("case", "")
        difficulty = request.form.getlist("difficulty")
        topics = request.form.getlist("topics[]")
        max_sentences = int(request.form.get("max_sentences", 10))
        batch_size = int(request.form.get("batch_size", 20))

        logger.debug(
            "Generate request: pos=%s, case=%s, difficulty=%s, topics=%s, max_sentences=%s, batch_size=%s",
            pos,
            case,
            difficulty,
            topics,
            max_sentences,
            batch_size,
        )

        if "any" in pos:
            pos = ["any"]
        if "any" in difficulty:
            difficulty = ["any"]
        if "" in topics:
            topics = ["any"]

        if difficulty != ["any"]:
            try:
                difficulty = [int(d) for d in difficulty]
                if any(d < 1 or d > 8 for d in difficulty):
                    return jsonify({"error": "Difficulty must be between 1 and 8"}), 400
            except ValueError:
                return jsonify({"error": "Invalid difficulty value"}), 400

        try:
            cards_added, total_forms, errors = flashcard_service.process_batch(
                1, difficulty, pos, case, topics, max_sentences, batch_size
            )
            logger.debug(
                "Process batch result: cards_added=%s, total_forms=%s, errors=%s",
                cards_added,
                total_forms,
                errors,
            )

            message = f"Successfully added {cards_added} card{'s' if cards_added != 1 else ''} to Anki."
            if errors:
                message += f"<br>Errors for {len(errors)} form{'s' if len(errors) != 1 else ''}:<ul>"
                for error in errors:
                    message += f"<li>{error}</li>"
                message += "</ul>"

            response_html = (
                f'<div id="result" class="alert alert-{"success" if cards_added > 0 else "warning"}">'
                f"{message}</div>"
            )
            logger.debug("Generate response: %s", response_html)
            return response_html
        except Exception as e:
            logger.error("Error generating flashcards: %s", str(e), exc_info=True)
            return render_template_string(
                '<div id="result" class="alert alert-danger">Error generating flashcards: {{ error | e }}</div>',
                error=str(e),
            ), 500

    @blueprint.route("/generate_word_forms", methods=["POST"])
    def generate_word_forms():
        word = request.form.get("word")
        logger.debug("Generate word forms request: word=%s", word)

        word_data = word_repository.find_basic_by_lemma(word)
        if not word_data:
            response_html = f'<div id="word-result" class="alert alert-danger">Word "{word}" not found.</div>'
            logger.debug("Generate word forms response: %s", response_html)
            return response_html

        cards_added, total_forms, errors = flashcard_service.process_word_forms(
            word_data["id"], word_data["lemma"], word_data["pos"]
        )

        logger.debug(
            "Process word forms result: cards_added=%s, total_forms=%s, errors=%s",
            cards_added,
            total_forms,
            errors,
        )

        message = f"Successfully added {cards_added} card{'s' if cards_added != 1 else ''} for forms of '{word}'."
        if errors:
            message += f"<br>Errors for {len(errors)} form{'s' if len(errors) != 1 else ''}:<ul>"
            for error in errors:
                message += f"<li>{error}</li>"
            message += "</ul>"

        response_html = (
            f'<div id="word-result" class="alert alert-{"success" if cards_added > 0 else "warning"}">'
            f"{message}</div>"
        )
        logger.debug("Generate word forms response: %s", response_html)
        return response_html

    @blueprint.route("/review_cards", methods=["POST"])
    def review_cards():
        """Inspect the optional Anki collection; app rewards come from practice."""
        try:
            result = user_service.check_anki_cards(user_id=1)
            if not result:
                logger.error("Failed to process Anki cards")
                return render_template_string(
                    '<div class="alert alert-danger">Error processing Anki cards</div>'
                ), 500
            feedback = result.get("feedback", "No feedback available")
            cards_eligible = result.get("cards_eligible", 0)
            return render_template_string(
                """
                <div class="alert alert-success">
                    <p>{{ 'Карточек с интервалом больше пяти дней и не более одного забывания:' if ui_lang == 'ru' else 'Cards with a review interval over five days and at most one lapse:' }} {{ cards_eligible }}</p>
                    <p>{{ 'Прогресс Anki остаётся в Anki. Практикуйтесь в приложении, чтобы получать лингокоины.' if ui_lang == 'ru' else feedback }}</p>
                </div>
                """,
                cards_eligible=cards_eligible,
                feedback=feedback,
            )
        except Exception as e:
            logger.error("Error reviewing Anki cards: %s", str(e), exc_info=True)
            return render_template_string(
                '<div class="alert alert-danger">Error reviewing Anki cards: {{ error | e }}</div>',
                error=str(e),
            ), 500

    return blueprint
