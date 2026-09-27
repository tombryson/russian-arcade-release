import base64
import json
import logging
import io
import hashlib

from services.onboarding import onboarding_state
from services.story_vocabulary import story_key
from services.curriculum import level_options, normalize_level, topic_options

from asgiref.sync import async_to_sync
from flask import Blueprint, jsonify, render_template, render_template_string, request, session, make_response, redirect, send_file
from markupsafe import escape

from repositories import StoryRepository
from repositories.comprehension_repository import ComprehensionRepository, ComprehensionConflict
from utils.shell import render_page, is_shell_navigation
from utils.story_display import present_story
from utils.story_processing import process_story_words
from utils.story_content import validate_story_title

logger = logging.getLogger(__name__)


def create_comprehension_blueprint(db_path, comprehension_service, drive_service, user_service):
    blueprint = Blueprint("comprehension", __name__)
    story_repository = StoryRepository(db_path)
    reading_repository = ComprehensionRepository(db_path)

    def reading_error(error, status):
        # Preserve the answer form on failure. Provider/internal errors are
        # logged, never interpolated into the learner's page.
        return render_template('_comprehension_check_error.html', message=str(error)), status

    def check_reading_task():
        task_id = request.form.get('task_id', '')
        submission_id = request.form.get('submission_id', '')
        try:
            revision = int(request.form.get('task_revision', '-1'))
            answers = request.form.getlist('answers[]')
            task, saved = reading_repository.begin_check(task_id, revision, submission_id, answers)
            if saved is None:
                try:
                    assessment = comprehension_service.assess_task(task['payload'], answers)
                    saved = reading_repository.finish_check(task_id, revision, submission_id, answers, assessment,
                                                           expected_owner=task['profile_id'], lease_token=task['check_token'])
                except Exception:
                    reading_repository.abandon_check(task_id, submission_id, task['check_token'])
                    raise
            return render_template('_comprehension_checked.html', reading_result=saved, task_id=task_id, update_form=True)
        except LookupError:
            return reading_error('This story is not available in the selected profile.', 404)
        except ComprehensionConflict as error:
            return reading_error(error, 409)
        except ValueError:
            return reading_error('Your answers could not be checked. They are still here; please try again.', 400)
        except Exception:
            logger.exception('Comprehension check failed')
            return reading_error('Your answers could not be checked. They are still here; please try again.', 503)

    def require_legacy_form():
        """Old forms cannot overwrite a new immutable question set."""
        if 'task_revision' in request.form or 'submission_id' in request.form:
            raise ComprehensionConflict('This story uses a newer answer form. Reload it to continue.')
        raw_id = request.form.get('story_id')
        if not raw_id:
            try:
                text = base64.b64decode(request.form.get('story_text', '')).decode('utf-8')
                raw_id = story_repository.find_existing(text, request.form.get('topic', 'any'), request.form.get('difficulty', 'beginner'))
            except (ValueError, UnicodeError):
                pass  # The existing legacy parser reports malformed forms.
        if raw_id and reading_repository.latest(raw_id):
            raise ComprehensionConflict('This story uses a newer answer form. Reload it to continue.')

    def story_for_display(story):
        displayed = present_story(story, session.get("ui_lang", "en"))
        if story.get("text"):
            displayed["capture_key"] = story_key(story["text"])
        return displayed

    def topics_and_stories():
        stories = []
        for story in story_repository.list_saved():
            task = reading_repository.latest(story['id'])
            if task and task['payload'].get('practice_mode') == 'listening':
                displayed = reading_repository.display(task['id'])
                story.update(title=displayed['title'], title_en=displayed['title_en'])
            stories.append(story_for_display(story))
        return topic_options(session.get("ui_lang", "en")), stories

    @blueprint.route('/comprehension/tasks/<task_id>/audio', methods=['GET'])
    def comprehension_audio(task_id):
        try:
            task = reading_repository.load(task_id)
            path = reading_repository.audio_path(task_id)
            data = path.read_bytes()
            identity = task['payload']['audio']
            if len(data) != identity['size_bytes'] or hashlib.sha256(data).hexdigest() != identity['sha256']:
                raise ValueError('The original recording is unavailable.')
            response = send_file(io.BytesIO(data), mimetype='audio/mpeg', conditional=True,
                                 download_name=f'{task_id}.mp3')
            response.headers['Cache-Control'] = 'private, no-store'
            return response
        except LookupError:
            return jsonify(error='Recording not found for this profile.'), 404
        except (ValueError, OSError):
            return jsonify(error='This recording is unavailable. You can read the transcript instead.'), 409

    @blueprint.route('/comprehension/tasks/<task_id>/support', methods=['POST'])
    def comprehension_support(task_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Send a support request as JSON.'), 400
        try:
            revision = data.get('task_revision', data.get('revision'))
            if 'task_revision' in data and 'revision' in data and data['task_revision'] != data['revision']:
                raise ValueError('This support request has conflicting revisions.')
            state = reading_repository.record_support(task_id, revision, data.get('request_key'), data.get('operation'), word=data.get('word'))
            story = reading_repository.display(task_id)
            result = {'task_id': task_id, 'revision': story['revision'], **state,
                      'audio_unavailable': story.get('practice_mode') == 'listening' and not story.get('audio_available')}
            if data.get('operation') == 'transcript':
                displayed = story_for_display(story)
                words = story_words(displayed['text'])
                result.update(text=displayed['text'], words=words, capture_key=displayed.get('capture_key', ''),
                              title=displayed['title'], title_en=displayed.get('title_en', ''), image_url=displayed.get('image_url', ''))
            return jsonify(result)
        except LookupError:
            return jsonify(error='This story is not available in the selected profile.'), 404
        except ComprehensionConflict as error:
            return jsonify(error=str(error)), 409
        except ValueError as error:
            return jsonify(error=str(error)), 400

    @blueprint.context_processor
    def curriculum_form_context():
        options = topic_options(session.get('ui_lang', 'en'))
        topic = request.values.get('topic', 'any')
        selected = next((item for item in options if item['value'] == topic), None)
        raw_level = request.form.get('difficulty') if request.method == 'POST' else request.args.get('level')
        level_explicit = bool(raw_level)
        try:
            level = normalize_level(raw_level, legacy='reading') if raw_level else ((selected or {}).get('level') or 'A1')
        except ValueError:
            level_explicit = False
            level = ((selected or {}).get('level') or 'A1')
        return dict(levels=level_options(session.get('ui_lang', 'en')),
                    selected_topic=topic if selected else 'any', selected_level=level,
                    level_explicit=level_explicit)

    def story_words(story_text):
        return process_story_words(
            story_text,
            db_path=db_path,
            drive_service=drive_service,
            added_lemmas=session.get("added_lemmas", set()),
        )

    def submitted_story(story_text, topic, difficulty):
        """Use the persisted title for saved work, including forms opened before retitling."""
        raw_id = request.form.get("story_id")
        story_id = int(raw_id) if raw_id else story_repository.find_existing(story_text, topic, difficulty)
        if story_id:
            saved = story_repository.load(story_id)
            if not saved:
                raise LookupError('Story not found')
            if (saved["text"], saved["topic"], saved["difficulty"]) != (story_text, topic, difficulty):
                raise ValueError("The selected story does not match this activity. Please reload it.")
            return story_id, validate_story_title(saved["title"]), saved.get("title_en", "")
        current = session.get("current_story_data", {})
        cached_title = current.get("title") if current.get("text") == story_text else None
        cached_english = current.get("title_en") if current.get("text") == story_text else None
        title_en = request.form.get("story_title_en") or cached_english
        return None, validate_story_title(request.form.get("story_title") or cached_title), validate_story_title(title_en) if title_en else ""

    def rating_context_matches(story_id, story_text, topic, difficulty, questions):
        # Hidden form fields are editable. Only rate the saved/generated task,
        # while still allowing ordinary feedback on a different question set.
        trusted = story_repository.load(story_id) if story_id else session.get('reading_rating_context', {})
        return bool(trusted and (trusted.get('text'), trusted.get('topic'), trusted.get('difficulty'), trusted.get('questions'))
                    == (story_text, topic, difficulty, questions))

    def course_context(story_id, story_text, topic, difficulty, questions):
        trusted = story_repository.load(story_id) if story_id else session.get('reading_rating_context', {})
        return comprehension_service.course_task_context(story_id, trusted, story_text, topic, difficulty, questions)

    @blueprint.route("/comprehension", methods=["GET", "POST"])
    def comprehension():
        topics, saved_stories = topics_and_stories()
        logger.debug("Topics: %s, Saved stories: %s", topics, saved_stories)
        if request.method == "GET":
            return render_page(
                "comprehension.html",
                topics=topics,
                saved_stories=saved_stories,
                active_page="comprehension",
            )

        try:
            normalize_level(request.form.get("difficulty", "beginner"), legacy='reading')
            practice_mode = request.form.get('practice_mode', 'reading')
            if practice_mode not in ('reading', 'listening'):
                raise ValueError('Invalid practice mode')
            if practice_mode == 'listening':
                from services.comprehension_evidence import listening_candidates
                if not listening_candidates(request.form.get('difficulty', 'beginner')):
                    raise ValueError('Listening practice is available at A1–B2.')
            if request.form.get('topic', 'any') not in {'any', *(item['value'] for item in topics)}:
                raise ValueError('Invalid topic')
        except ValueError:
            return render_page('comprehension.html', topics=topics, saved_stories=saved_stories,
                               error=('Выберите тему и уровень из списка.' if session.get('ui_lang') == 'ru' else 'Choose a topic and level from the list.'), active_page='comprehension'), 400

        try:
            expected_owner = reading_repository.owner()
            topic = str(request.form.get("topic", "any"))
            difficulty = str(request.form.get("difficulty", "beginner"))
            visibility = str(request.form.get("visibility", "revealed"))
            custom_story = request.form.get("custom_story", "").strip()
            logger.debug(
                "POST data: topic=%s, difficulty=%s, visibility=%s, custom_story=%s",
                topic,
                difficulty,
                visibility,
                custom_story[:100],
            )

            generation_options = {'practice_mode': 'listening'} if practice_mode == 'listening' else {}
            if custom_story:
                prepared = async_to_sync(comprehension_service.prepare_story_from_text)(custom_story, topic, difficulty, **generation_options)
            else:
                prepared = async_to_sync(comprehension_service.generate_story)(topic, difficulty, **generation_options)
            title = validate_story_title(prepared.get("title"))
            title_en = validate_story_title(prepared.get("title_en"))
            story_text = prepared["text"]
            questions = prepared["questions"]
            image_url = prepared.get("image_url", "")

            if not image_url and practice_mode != 'listening':
                image_url = comprehension_service.generate_image(story_text)
            logger.debug("Image URL: %s", image_url)

            try:
                audio_url = comprehension_service.generate_audio(story_text)
            except Exception:
                logger.exception('Story prepared, but its recording could not be generated')
                audio_url = ''
            logger.debug("Audio URL: %s", audio_url)

            words = [] if practice_mode == 'listening' and not custom_story else story_words(story_text)
            logger.debug("Words data: %s", words[:5])
            story_data = story_for_display({
                "title": title,
                "title_en": title_en,
                "text": story_text,
                "words": words,
                "questions": questions,
                "audio_url": audio_url,
                "image_url": image_url,
                "topic": topic,
                "difficulty": difficulty,
                "answers": [],
            })
            if practice_mode == 'listening' or prepared.get('reading_focus'):
                from services.comprehension_evidence import build_contracts, freeze_audio
                audio = freeze_audio(audio_url) if practice_mode == 'listening' else None
                contracts = build_contracts(prepared, topic, difficulty, practice_mode=practice_mode, audio=audio, track_support=True)
                task_id, _ = reading_repository.create({**prepared, 'audio_url': audio_url, 'image_url': image_url},
                    topic, difficulty, contracts, expected_owner=expected_owner, practice_mode=practice_mode,
                    track_support=True, initial_transcript=bool(custom_story), audio=audio)
                story_data = story_for_display(reading_repository.display(task_id))
                story_data['words'] = story_words(story_data['text'])
            try:
                json.dumps(story_data)
            except ValueError:
                logger.error("JSON serialization error in story_data")
                return render_page(
                    "comprehension.html",
                    topics=topics,
                    saved_stories=saved_stories,
                    error="Invalid story data format",
                    active_page="comprehension",
                ), 500
            session["current_story_text"] = story_data['text']
            session["current_story_data"] = story_data
            # Only provider-created URLs can authorize an unsaved media preview.
            session["generated_story_media"] = [audio_url] if practice_mode == 'listening' else [audio_url, image_url]
            session['reading_rating_context'] = {key: story_data[key] for key in ('text', 'topic', 'difficulty', 'questions')}
            session["visibility"] = visibility
            logger.debug("Story data: %s", story_data)
            if request.headers.get("HX-Request") and not is_shell_navigation():
                logger.debug("Rendering _comprehension_content.html for HTMX")
                response = make_response(render_template("_comprehension_content.html", story=story_data, visibility=visibility))
                if story_data.get('task_id'):
                    response.headers['HX-Replace-Url'] = f"/comprehension/load/{story_data['id']}"
                return response
            logger.debug("Rendering comprehension.html")
            if story_data.get('task_id'):
                return redirect(f"/comprehension/load/{story_data['id']}", code=303)
            return render_page(
                "comprehension.html",
                topics=topics,
                saved_stories=saved_stories,
                story=story_data,
                visibility=visibility,
                active_page="comprehension",
            )
        except Exception as e:
            logger.error("Comprehension error: %s", str(e), exc_info=True)
            error_message = "Не удалось сгенерировать историю. Попробуйте снова!"
            if request.headers.get("HX-Request") and not is_shell_navigation():
                logger.debug("Returning error div for HTMX")
                return render_template_string('<div class="alert alert-danger">{{ ui_t("comprehension.generation_failed") }}</div>'), 503
            logger.debug("Rendering comprehension.html with error")
            return render_page(
                "comprehension.html",
                topics=topics,
                saved_stories=saved_stories,
                error=error_message,
                active_page="comprehension",
            )

    @blueprint.route("/comprehension/answer", methods=["POST"])
    def answer_questions():
        if request.form.get('task_id'):
            return check_reading_task()
        try:
            require_legacy_form()
        except ComprehensionConflict as error:
            return reading_error(error, 409)
        logger.debug("Raw request data: %s", request.data)
        logger.debug("Form data dict: %s", request.form.to_dict())
        logger.debug("Raw form data: %s", request.form)
        answers = request.form.getlist("answers[]")
        story_text_b64 = request.form.get("story_text", "")
        questions_b64 = request.form.get("questions_b64", "")
        topic = str(request.form.get("topic", "any"))
        difficulty = str(request.form.get("difficulty", "beginner"))
        story_id = request.form.get("story_id", None)

        logger.debug("Raw questions_b64: %s, story_id: %s", questions_b64, story_id)

        try:
            story_text = base64.b64decode(story_text_b64).decode("utf-8")
            logger.debug("Decoded story_text: %s", story_text)
            if questions_b64:
                questions_raw = base64.b64decode(questions_b64).decode("utf-8")
                questions = json.loads(questions_raw)
                logger.debug("Parsed questions: %s", questions)
            else:
                logger.warning("questions_b64 is empty, defaulting to empty list")
                questions = []
        except base64.binascii.Error:
            logger.error("Base64 decode error: story_text_b64=%s, questions_b64=%s", story_text_b64, questions_b64)
            return '<div class="alert alert-danger">Ошибка обработки текста или вопросов</div>', 400
        except json.JSONDecodeError:
            logger.error("JSON decode error, raw questions: %s", questions_raw)
            return '<div class="alert alert-danger">Ошибка обработки вопросов</div>', 400

        if not answers or not questions:
            logger.error("Missing answers or questions: answers=%s, questions=%s", answers, questions)
            return '<div class="alert alert-danger">Ответы или вопросы отсутствуют. Попробуйте снова.</div>', 400

        try:
            user_id = None  # Historical reward compatibility resolves the activity owner.
            story_id, title, title_en = submitted_story(story_text, topic, difficulty)
            course_matches, course_questions_hash = course_context(story_id, story_text, topic, difficulty, questions)
            feedback, scores, total_score, can_reward = comprehension_service.evaluate_answers(
                story_text, questions, answers, user_id, story_id, topic, difficulty
            )
            logger.debug(
                "Evaluation: feedback=%s, scores=%s, total_score=%s, can_reward=%s",
                feedback,
                scores,
                total_score,
                can_reward,
            )
            feedback_html = ""
            if scores:
                for q, a, f, s in zip(questions, answers, feedback, scores):
                    feedback_html += (
                        f"<p><strong>Вопрос:</strong> {escape(q)}<br><strong>Ваш ответ:</strong> {escape(a)}<br>"
                        f"<strong>Отзыв:</strong> {escape(f)}<br><strong>Оценка:</strong> {escape(s)}/10</p>"
                    )
            else:
                for q, a, f in zip(questions, answers, feedback):
                    feedback_html += (
                        f"<p><strong>Вопрос:</strong> {escape(q)}<br><strong>Ваш ответ:</strong> {escape(a)}<br>"
                        f"<strong>Отзыв:</strong> {escape(f)}</p>"
                    )
            feedback_html += f"<p><strong>Общая оценка:</strong> {total_score:.1f}/10</p>"

            progression_result = {}
            story_id_new = comprehension_service.save_story(
                title=title, title_en=title_en, story_id=story_id, topic=topic, difficulty=difficulty,
                text=story_text, audio_url=request.form.get("audio_url", ""),
                image_url=request.form.get("image_url", ""), questions=questions,
                answers=answers, feedback=feedback, score=total_score,
                assessed=True, progression_result=progression_result,
                fresh_assessment=scores is not None and rating_context_matches(story_id, story_text, topic, difficulty, questions),
                course_task_context_matches=course_matches,
                course_task_questions_hash=course_questions_hash,
            )
            if story_id_new:
                if progression_result.get('coins_earned') and onboarding_state()['coins_introduced']:
                    feedback_html += render_template_string('<p>{{ ui_t("translation.coins") }}: {{ coins }}</p>', coins=progression_result['coins_earned'])
                feedback_html += render_template_string('<p>{{ ui_t("comprehension.saved_ok") }}</p>')
            else:
                logger.error("Failed to save story or find existing story")
                feedback_html += "<p><strong>Error:</strong> Failed to save story</p>"

            return f'<div class="alert alert-info">{feedback_html}</div>'
        except LookupError:
            return '<div class="alert alert-danger">История не найдена</div>', 404
        except Exception:
            logger.error(
                "Answer evaluation error: raw request data=%s, form data=%s",
                request.data,
                request.form.to_dict(),
                exc_info=True,
            )
            feedback_html = "<p><strong>Error:</strong> Failed to evaluate answers</p>"
            return f'<div class="alert alert-danger">{feedback_html}</div>', 500

    @blueprint.route("/comprehension/save", methods=["POST"])
    def save_comprehension():
        if request.form.get('task_id'):
            return check_reading_task()
        try:
            require_legacy_form()
        except ComprehensionConflict as error:
            return reading_error(error, 409)
        logger.debug("Raw form data: %s", request.form.to_dict())
        try:
            story_text_b64 = request.form.get("story_text", "")
            audio_url = request.form.get("audio_url", "")
            image_url = request.form.get("image_url", "")
            questions_b64 = request.form.get("questions_b64", "")
            answers = request.form.getlist("answers[]")
            topic = str(request.form.get("topic", "any"))
            difficulty = str(request.form.get("difficulty", "beginner"))
            user_id = None
            story_id = request.form.get("story_id", None)

            story_text = base64.b64decode(story_text_b64).decode("utf-8")
            questions = json.loads(base64.b64decode(questions_b64).decode("utf-8")) if questions_b64 else []

            story_id, title, title_en = submitted_story(story_text, topic, difficulty)
            course_matches, course_questions_hash = course_context(story_id, story_text, topic, difficulty, questions)
            feedback, scores, total_score, can_reward = comprehension_service.evaluate_answers(
                story_text, questions, answers, user_id, story_id, topic, difficulty
            )

            story_id_new = comprehension_service.save_story(
                title=title,
                title_en=title_en,
                story_id=story_id,
                topic=topic,
                difficulty=difficulty,
                text=story_text,
                audio_url=audio_url,
                image_url=image_url,
                questions=questions,
                answers=answers,
                feedback=feedback,
                score=total_score,
                assessed=True,
                fresh_assessment=scores is not None and rating_context_matches(story_id, story_text, topic, difficulty, questions),
                course_task_context_matches=course_matches,
                course_task_questions_hash=course_questions_hash,
            )
            if story_id_new:
                logger.debug("Story saved with id %s", story_id_new)
                return render_template_string('<div class="alert alert-success">{{ ui_t("comprehension.saved_ok") }}</div>')
            logger.error("Failed to save story")
            return '<div class="alert alert-danger">Ошибка сохранения истории!</div>', 500
        except LookupError:
            return '<div class="alert alert-danger">История не найдена</div>', 404
        except Exception as e:
            logger.error("Save story error: %s", str(e), exc_info=True)
            return f'<div class="alert alert-danger">Ошибка сохранения: {str(e)}</div>', 500

    @blueprint.route("/comprehension/load/<story_id>")
    def load_comprehension(story_id):
        topics, saved_stories = topics_and_stories()
        logger.debug("Load story: story_id=%s", story_id)

        try:
            story = story_repository.load(story_id)
            if not story:
                logger.error("Story not found: %s", story_id)
                if request.headers.get("HX-Request") and not is_shell_navigation():
                    return '<div class="alert alert-danger">История не найдена</div>', 404
                return render_page(
                    "comprehension.html",
                    topics=topics,
                    saved_stories=saved_stories,
                    error="История не найдена",
                    active_page="comprehension",
                ), 404
            task = reading_repository.latest(story_id)
            if task:
                story = reading_repository.display(task['id'])
            story = story_for_display(story)
            story["words"] = story_words(story["text"])
            session["current_story_text"] = story["text"]
            session["current_story_data"] = story
            session["visibility"] = "revealed"
            logger.debug("Loaded story: %s", story)
            if request.headers.get("HX-Request") and not is_shell_navigation():
                logger.debug("Rendering _comprehension_content.html for HTMX")
                return render_template("_comprehension_content.html", story=story, visibility="revealed")
            logger.debug("Rendering comprehension.html")
            return render_page(
                "comprehension.html",
                topics=topics,
                saved_stories=saved_stories,
                story=story,
                visibility="revealed",
                active_page="comprehension",
            )
        except Exception as e:
            logger.error("Load story error: %s", str(e), exc_info=True)
            error_message = f"Ошибка загрузки: {str(e)}"
            if request.headers.get("HX-Request") and not is_shell_navigation():
                return f'<div class="alert alert-danger">{error_message}</div>'
            return render_page(
                "comprehension.html",
                topics=topics,
                saved_stories=saved_stories,
                error=error_message,
                active_page="comprehension",
            )

    @blueprint.route("/comprehension/generate_more_questions", methods=["POST"])
    def generate_more_questions():
        if request.form.get('task_id'):
            task = None
            try:
                from services.comprehension_evidence import reissue_contracts
                task = reading_repository.begin_questions(request.form['task_id'], int(request.form.get('task_revision', '-1')))
                payload = task['payload']
                new_questions = comprehension_service.generate_additional_questions(payload['text'], payload['topic'], payload['difficulty'], payload['questions'])
                if not isinstance(new_questions, list) or not 1 <= len(new_questions) <= 3:
                    raise ValueError('Invalid additional questions')
                questions = payload['questions'] + new_questions
                contracts = reissue_contracts(payload, questions)
                prepared = {**payload, 'questions': questions, 'title': task['title'], 'title_en': task['title_en']}
                task_id, _ = reading_repository.create(prepared, payload['topic'], payload['difficulty'], contracts,
                    expected_owner=task['profile_id'], story_id=task['story_id'], parent_id=task['id'], lease_token=task['check_token'])
                story = reading_repository.display(task_id)
                # Keep the current draft while issuing a new question-set identity.
                previous = request.form.getlist('answers[]')[:len(payload['questions'])]
                story['answers'] = previous + [''] * (len(questions) - len(previous))
                return render_template('_questions_partial.html', story=story, preserve_answers=True)
            except LookupError:
                return reading_error('This story is not available in the selected profile.', 404)
            except ComprehensionConflict as error:
                return reading_error(error, 409)
            except Exception:
                logger.exception('Additional reading questions failed')
                return reading_error('More questions could not be prepared. Your existing questions are still here.', 503)
            finally:
                if task:
                    reading_repository.abandon_check(task['id'], task['check_token'], task['check_token'])
        try:
            require_legacy_form()
        except ComprehensionConflict as error:
            return reading_error(error, 409)
        logger.debug("Raw form data: %s", request.form.to_dict())
        story_text_b64 = request.form.get("story_text", "")
        questions_b64 = request.form.get("questions_b64", "")
        audio_url = request.form.get("audio_url", "")
        image_url = request.form.get("image_url", "")
        topic = str(request.form.get("topic", "any"))
        difficulty = str(request.form.get("difficulty", "beginner"))

        try:
            story_text = base64.b64decode(story_text_b64).decode("utf-8")
            if questions_b64:
                questions_raw = base64.b64decode(questions_b64).decode("utf-8")
                existing_questions = json.loads(questions_raw)
            else:
                logger.warning("questions_b64 is empty, defaulting to empty list")
                existing_questions = []
            logger.debug("Decoded story_text: %s, existing_questions: %s", story_text, existing_questions)

            story_id, title, title_en = submitted_story(story_text, topic, difficulty)
            new_questions = comprehension_service.generate_additional_questions(
                story_text, topic, difficulty, existing_questions
            )
            logger.debug("New questions: %s", new_questions)

            updated_questions = existing_questions + new_questions
            existing_answers = request.form.getlist("answers[]")[:len(existing_questions)]
            existing_answers += [""] * (len(existing_questions) - len(existing_answers))
            previous_story = session.get("current_story_data", {})
            if previous_story.get("text") != story_text:
                previous_story = {}
            story_data = {
                "text": story_text,
                "title": title,
                "title_en": title_en,
                "words": previous_story.get("words", []),
                "questions": updated_questions,
                "answers": existing_answers + [""] * len(new_questions),
                "audio_url": audio_url,
                "image_url": image_url,
                "topic": topic,
                "difficulty": difficulty,
            }
            story_data = story_for_display(story_data)
            if story_id:
                story_data["id"] = story_id
            session["current_story_text"] = story_text
            session["current_story_data"] = story_data
            session["visibility"] = "revealed"
            logger.debug("Updated story_data: %s", story_data)
            return render_template("_questions_partial.html", story=story_data, preserve_answers=True)
        except LookupError:
            return '<div class="alert alert-danger">История не найдена</div>', 404
        except Exception as e:
            logger.error("Generate more questions error: %s", str(e), exc_info=True)
            return render_template_string('<div class="alert alert-danger">{{ ui_t("comprehension.questions_failed") }}</div>'), 503

    return blueprint
