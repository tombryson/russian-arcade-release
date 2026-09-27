from flask import Flask, render_template, render_template_string, request, redirect, session, url_for, send_from_directory
from flask_session import Session
import json
from services.flashcard_service import FlashcardService
from services.openai_service import OpenAIService
from services.yandex_service import YandexService
from services.elevenlabs_service import ElevenLabsService
from services.anki_connect import AnkiConnect
from services.google_drive_service import GoogleDriveService
from services.sync_service import SyncService
from services.comprehension_service import ComprehensionService
from services.writing_service import WritingService
from services.lesson_service import LessonService
from services.lesson_companion import LessonCompanion
from services.lesson_cards import LessonCards
from services.lesson_ocr import LessonOCR
from services.lesson_selection import LessonSelection
from services.lesson_ai import LessonAI
from blueprints.lessons import create_lessons_blueprint
from services.word_jumble_service import WordJumbleService
from services.sentence_service import SentenceService
from services.user_service import UserService
from config import app_config
from utils.lazy import LazyService
from models.database import close_db
from migrations import register_cli
from story_cli import register_story_cli
from lesson_cli import register_lesson_cli
from blueprints.comprehension import create_comprehension_blueprint
from blueprints.word_jumble import create_word_jumble_blueprint
from blueprints.writing import create_writing_blueprint
from blueprints.flashcards import create_flashcards_blueprint
from blueprints.sentences import create_sentences_blueprint
from blueprints.user import create_user_blueprint
from blueprints.vocab import create_vocab_blueprint
from blueprints.word_post import create_word_post_blueprint
from blueprints.learning import create_learning_blueprint
from blueprints.user_sessions import create_user_sessions_blueprint
from blueprints.onboarding import create_onboarding_blueprint
from blueprints.first_steps import create_first_steps_blueprint
from blueprints.journey_games import create_journey_games_blueprint
from learning_cli import register_learning_cli
from services.household_service import HouseholdService
from services.learning_assets import LocalAssetStore
from services.learning_content import ContentService
from services.learning_service import LearningService
from services.native_review import NativeReviewService
from blueprints.native_review import create_native_review_blueprint
from services.card_authoring import CardAuthoringService
from services.card_generation import CardGenerationService
from services.card_media import CardMediaService, NativeMediaProvider
from blueprints.card_generation import create_card_generation_blueprint
from blueprints.card_authoring import create_card_authoring_blueprint
from blueprints.conversation import create_conversation_blueprint
from services.conversation_service import ConversationService
from services.conversation_ai import ConversationAI
from services.live_conversation import LiveConversationService
from services.speaking_assessment import SpeakingAssessment
from services.live_voice_provider import LiveVoiceProvider
from blueprints.live_conversation import create_live_conversation_blueprint
from services.speech_provider import SpeechProvider
from services.step_conversation import StepConversationService
from blueprints.step_conversation import create_step_conversation_blueprint
from utils.household_access import access_policy, install_household_policy
from utils.shell import render_page, is_shell_navigation
from utils.i18n import SUPPORTED_UI_LANGUAGES, normalize_ui_language, translate_ui
from utils.navigation import activity_navigation
from blueprints.ui_preferences import create_ui_preferences_blueprint
from blueprints.curriculum import create_curriculum_blueprint
from filters import register_filters
import logging
import os
import base64

logger = logging.getLogger(__name__)


def create_app(config_overrides=None, service_overrides=None):
    """Build an independent app. Creating it never opens a database or provider."""
    app = Flask(__name__)
    app.config.from_mapping(app_config())
    app.config.update(config_overrides or {})
    from services.ai_trial_budget import TrialDenied

    @app.errorhandler(TrialDenied)
    def trial_budget_unavailable(error):
        from flask import jsonify
        return jsonify(error={'code': 'trial_limit', 'message': str(error)}), 429

    register_filters(app)
    app.teardown_appcontext(close_db)
    register_cli(app)
    register_story_cli(app)
    overrides = service_overrides or {}
    app.extensions["services"] = {}

    def service(name, factory):
        instance = overrides[name] if name in overrides else LazyService(name, factory)
        app.extensions["services"][name] = instance
        return instance

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    Session(app)
    install_household_policy(app)
    app.register_blueprint(create_user_sessions_blueprint())
    app.register_blueprint(create_ui_preferences_blueprint())
    app.register_blueprint(create_onboarding_blueprint())
    app.register_blueprint(create_first_steps_blueprint())
    app.register_blueprint(create_journey_games_blueprint())
    app.register_blueprint(create_curriculum_blueprint())
    household = HouseholdService(app.config['DB_PATH'])
    asset_store = LocalAssetStore(app.config['WORD_POST_ASSET_DIR'])
    content = ContentService(app.config['DB_PATH'], asset_store)
    learning = LearningService(app.config['DB_PATH'], native_review_enabled=app.config['NATIVE_FLASHCARDS_ENABLED'])
    review = NativeReviewService(app.config['DB_PATH'])
    app.extensions['learning'] = {'household': household, 'content': content, 'sessions': learning, 'assets': asset_store, 'review': review}
    register_learning_cli(app, household, content, asset_store)
    app.register_blueprint(create_learning_blueprint(household, content, learning, asset_store))
    app.register_blueprint(create_native_review_blueprint(review))
    from blueprints.progression import create_progression_blueprint
    app.register_blueprint(create_progression_blueprint(app.config['DB_PATH']))
    authoring = CardAuthoringService(app.config['DB_PATH'], content)
    app.extensions['learning']['card_authoring'] = authoring
    app.register_blueprint(create_card_authoring_blueprint(authoring, content))
    # Speaking and the archived recorded sessions/lab share these services.
    speech = service('SpeechProvider', lambda: SpeechProvider(app.config))
    conversation_ai = service('ConversationAI', lambda: ConversationAI(app.config))
    conversation = ConversationService(app.config['DB_PATH'], speech, conversation_ai, app.config)
    app.extensions['learning']['conversation'] = conversation
    app.register_blueprint(create_conversation_blueprint(conversation))
    step_conversation = StepConversationService(app.config['DB_PATH'], speech, conversation_ai, app.config)
    app.extensions['learning']['step_conversation'] = step_conversation
    app.register_blueprint(create_step_conversation_blueprint(step_conversation))
    live = LiveConversationService(app.config['DB_PATH'],
        service('LiveVoiceProvider', lambda: LiveVoiceProvider(app.config)),
        speech, conversation_ai, app.config,
        service('SpeakingAssessment', lambda: SpeakingAssessment(app.config)))
    app.extensions['learning']['live_conversation'] = live
    app.register_blueprint(create_live_conversation_blueprint(live))


    @app.context_processor
    def inject_ui_language():
        ui_lang = normalize_ui_language(session.get("ui_lang", "en"))
        return {
            "ui_lang": ui_lang,
            "ui_languages": SUPPORTED_UI_LANGUAGES,
            "ui_t": lambda key: translate_ui(key, ui_lang),
            "activity_navigation": activity_navigation(ui_lang),
        }


    @app.route("/ui-language", methods=["POST"])
    @access_policy("public")
    def set_ui_language():
        session["ui_lang"] = normalize_ui_language(request.form.get("lang"))
        next_url = request.form.get("next") or request.referrer or "/"
        if not next_url.startswith("/") or next_url.startswith("//") or "\\" in next_url or any(ord(char) < 32 for char in next_url):
            next_url = "/"
        return redirect(next_url)

    @app.route("/static/media/<path:filename>")
    def generated_media(filename):
        from utils.activity_media import require_activity_media
        require_activity_media('media', filename)
        return send_from_directory(app.config["APP_MEDIA_DIR"], filename)

    @app.route("/static/uploads/<path:filename>")
    def uploaded_file(filename):
        from utils.activity_media import require_activity_media
        require_activity_media('uploads', filename)
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    db_path = app.config["DB_PATH"]
    media_dir = app.config["ANKI_MEDIA_DIR"]

    openai_service = service("OpenAIService", lambda: OpenAIService(config=app.config, api_key=app.config["OPENAI_API_KEY"], flashcard_model=app.config["OPENAI_MODEL_FLASHCARDS"], high_model=app.config["OPENAI_MODEL_HIGH"], fast_model=app.config["OPENAI_MODEL_FAST"], image_model=app.config["OPENAI_IMAGE_MODEL"]))
    yandex_service = service("YandexService", lambda: YandexService(config=app.config, api_key=app.config["YANDEX_API_KEY"]))
    elevenlabs_service = service(
        "ElevenLabsService",
        lambda: ElevenLabsService(config=app.config, api_key=app.config["ELEVENLABS_API_KEY"], media_dir=media_dir, voice_ids=app.config["ELEVENLABS_VOICE_IDS"], model=app.config["ELEVENLABS_MODEL"]),
    )


    def create_anki_connect():
        service = AnkiConnect(url=app.config["ANKI_CONNECT_URL"], default_deck=app.config["ANKI_DEFAULT_DECK"])
        service.set_media_dir(media_dir)
        return service


    anki_connect = service("AnkiConnect", create_anki_connect)
    flashcard_service = service(
        "FlashcardService",
        lambda: FlashcardService(db_path, openai_service, yandex_service, elevenlabs_service, anki_connect),
    )
    drive_service = service("GoogleDriveService", lambda: GoogleDriveService(auto_auth=app.config["GOOGLE_DRIVE_AUTO_AUTH"], file_id=app.config["GOOGLE_DRIVE_FILE_ID"], credentials_file=app.config["GOOGLE_DRIVE_CREDENTIALS_FILE"], token_file=app.config["GOOGLE_DRIVE_TOKEN_FILE"], cache_file=app.config["GOOGLE_DRIVE_CACHE_FILE"]))
    sync_service = service("SyncService", lambda: SyncService(db_path, config=app.config, drive_service=drive_service, api_key=app.config["OPENAI_API_KEY"]))
    comprehension_service = service(
        "ComprehensionService",
        lambda: ComprehensionService(db_path, openai_service, elevenlabs_service, app.config["APP_MEDIA_DIR"], config=app.config, api_key=app.config["OPENAI_API_KEY"], story_model=app.config["OPENAI_MODEL_STORY"], story_reasoning_effort=app.config["OPENAI_STORY_REASONING_EFFORT"]),
    )
    writing_service = service(
        "WritingService",
        lambda: WritingService(db_path, openai_service, config=app.config, api_key=app.config["OPENAI_API_KEY"]),
    )
    lesson_service = service(
        "LessonService",
        lambda: LessonService(db_path, openai_service, api_key=app.config["OPENAI_API_KEY"], upload_folder=app.config['UPLOAD_FOLDER']),
    )
    word_jumble_service = service(
        "WordJumbleService",
        lambda: WordJumbleService(db_path, openai_service, config=app.config, api_key=app.config["OPENAI_API_KEY"]),
    )
    sentence_service = service(
        "SentenceService",
        lambda: SentenceService(db_path, openai_service, elevenlabs_service, config=app.config, api_key=app.config["OPENAI_API_KEY"], media_dir=app.config["APP_MEDIA_DIR"]),
    )
    user_service = service("UserService", lambda: UserService(db_path))
    media_provider = service('CardMediaProvider', lambda: NativeMediaProvider(openai_service, elevenlabs_service))
    card_media = CardMediaService(db_path,content,media_provider,household=app.config['WORD_POST_HOUSEHOLD_ENABLED'])
    app.extensions['learning']['card_media'] = card_media
    from services.journey_game_media import JourneyGameMediaService
    from services.journey_games import allowlisted_media
    from blueprints.journey_game_media import create_journey_game_media_blueprint
    game_media = JourneyGameMediaService(db_path, asset_store, media_provider, allowlisted_media)
    app.extensions['learning']['journey_game_media'] = game_media
    from services.journey_game_preparation import JourneyGamePreparationService
    from services.journey_games import authorize_preparation
    game_preparation = JourneyGamePreparationService(db_path, asset_store, openai_service, media_provider, authorize_preparation,
                                                    discover=overrides.get('GameDiscovery'))
    game_preparation.shared_audio = game_media
    app.extensions['learning']['journey_game_preparation'] = game_preparation
    from services.radio_broadcast import RadioBroadcastService
    app.extensions['learning']['radio_broadcast'] = RadioBroadcastService(db_path, asset_store, openai_service, media_provider, authorize_preparation)
    from services.route_preparation import RoutePreparationService
    app.extensions['learning']['route_preparation'] = RoutePreparationService(db_path, asset_store, openai_service, speech, app.config)
    card_media.shared_audio = game_media
    app.register_blueprint(create_journey_game_media_blueprint(game_media))
    generator = CardGenerationService(db_path, content, openai_service, media=card_media, household=app.config['WORD_POST_HOUSEHOLD_ENABLED'], vocabulary=sync_service, config=app.config)
    app.extensions['learning']['generator'] = generator
    app.register_blueprint(create_card_generation_blueprint(generator, authoring))
    app.register_blueprint(create_flashcards_blueprint(db_path, flashcard_service, user_service))
    app.register_blueprint(create_vocab_blueprint(db_path, drive_service, sync_service))
    app.register_blueprint(create_comprehension_blueprint(db_path, comprehension_service, drive_service, user_service))
    app.register_blueprint(create_sentences_blueprint(db_path, sentence_service, user_service))
    app.register_blueprint(create_user_blueprint(db_path))
    app.register_blueprint(create_word_post_blueprint())
    app.register_blueprint(create_word_jumble_blueprint(word_jumble_service))
    app.register_blueprint(create_writing_blueprint(db_path, writing_service))
    from services.assessment_pilot import AssessmentPilotService
    from blueprints.assessment_pilot import create_assessment_pilot_blueprint
    pilot = AssessmentPilotService(db_path, writing_service, app.extensions['services']['SpeakingAssessment'], app.config)
    app.extensions['learning']['assessment_pilot'] = pilot
    app.register_blueprint(create_assessment_pilot_blueprint(pilot))
    lesson_ai = service('LessonAI', lambda: LessonAI(app.config))
    lessons = LessonCompanion(db_path, lesson_service, lesson_ai, app.config)
    app.extensions['learning']['lessons'] = lessons
    lesson_cards = LessonCards(lessons, generator)
    app.extensions['learning']['lesson_cards'] = lesson_cards
    lesson_selection = LessonSelection(lesson_cards, LessonOCR(lessons))
    app.extensions['learning']['lesson_selection'] = lesson_selection
    register_lesson_cli(app, lessons)
    app.register_blueprint(create_lessons_blueprint(lesson_service, lessons, lesson_cards, lesson_selection))

    @app.route('/phrasebook')
    def phrasebook():
        return redirect('/sentences/saved')

    return app
