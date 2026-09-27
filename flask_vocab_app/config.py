"""Application configuration.

Secrets are loaded from a `.env` file at the repo root via python-dotenv.
Copy `.env.example` to `.env` and fill in your own keys. Never commit `.env`.
"""
import os
from pathlib import Path

app_root = Path(__file__).resolve().parent
repo_root = app_root.parent


def _load_dotenv_fallback(path: Path) -> None:
    """Small .env loader for local runs when python-dotenv is unavailable."""
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


try:
    from dotenv import load_dotenv
    # Shell variables win; app-local values precede repo-wide defaults.
    load_dotenv(app_root / ".env")
    load_dotenv(repo_root / ".env")
except ImportError:
    _load_dotenv_fallback(app_root / ".env")
    _load_dotenv_fallback(repo_root / ".env")


def missing_external_keys():
    return [
        name
        for name in ("OPENAI_API_KEY", "YANDEX_API_KEY", "ELEVENLABS_API_KEY")
        if not os.environ.get(name)
    ]


# API keys are optional at startup so DB-backed pages can render in dev mode.
# Features that call the providers will still fail clearly if a key is missing.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")

# Models are selected per workload. Story preparation uses structured Responses;
# the other activity integrations retain their existing model settings.
OPENAI_MODEL_STORY = os.environ.get("OPENAI_MODEL_STORY", "gpt-6-astra")
OPENAI_STORY_REASONING_EFFORT = os.environ.get("OPENAI_STORY_REASONING_EFFORT", "low")
OPENAI_MODEL_FLASHCARDS = os.environ.get("OPENAI_MODEL_FLASHCARDS", "gpt-5.6-luna").removeprefix("openai/")
OPENAI_MODEL_HIGH = os.environ.get("OPENAI_MODEL_HIGH", "gpt-5.2")
OPENAI_MODEL_FAST = os.environ.get("OPENAI_MODEL_FAST", "gpt-5-mini")
OPENAI_MODEL_VISION = os.environ.get("OPENAI_MODEL_VISION", OPENAI_MODEL_HIGH)
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2")

ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_VOICE_IDS = tuple(value.strip() for value in os.environ.get(
    "ELEVENLABS_VOICE_IDS", "ymDCYd8puC7gYjxIamPt,gXMhWmiqsFkrcssqVb5k,sRk0zCqhS2Cmv0bzx5wA,3EuKHIEZbSzrHGNmdYsx"
).split(",") if value.strip())

# Flask session secret. Use FLASK_SECRET_KEY outside local development.
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")

# Paths (override via env if running on a different machine)
MEDIA_DIR = os.environ.get(
    "ANKI_MEDIA_DIR",
    str(Path.home() / "Library/Application Support/Anki2/User 1/collection.media"),
)
DB_PATH = os.environ.get(
    "VOCAB_DB_PATH",
    str(Path(__file__).resolve().parent / "vocab.db"),
)

# Flask Config
FLASK_CONFIG = {
    "JSON_AS_ASCII": False,
    "JSONIFY_MIMETYPE": "application/json; charset=utf-8",
}

# AnkiConnect
ANKI_CONNECT_URL = os.environ.get("ANKI_CONNECT_URL", "http://localhost:8765")
DEFAULT_DECK = os.environ.get("ANKI_DEFAULT_DECK", "Russian")

# Google Drive OAuth. Disabled by default so startup never opens a browser.
GOOGLE_DRIVE_AUTO_AUTH = os.environ.get("GOOGLE_DRIVE_AUTO_AUTH", "false").lower() in {
    "1",
    "true",
    "yes",
}


def app_config():
    """Defaults for one application; factory overrides always take precedence."""
    def path(name, default):
        value = Path(os.environ.get(name, str(default))).expanduser()
        return str(value if value.is_absolute() else repo_root / value)

    return {
        'SECRET_KEY': SECRET_KEY,
        'COURSE_DEFAULT_RELEASE': os.environ.get('COURSE_DEFAULT_RELEASE') or None,
        'DB_PATH': path('VOCAB_DB_PATH', app_root / 'vocab.db'),
        'ANKI_MEDIA_DIR': path('ANKI_MEDIA_DIR', Path.home() / 'Library/Application Support/Anki2/User 1/collection.media'),
        'APP_MEDIA_DIR': path('APP_MEDIA_DIR', app_root / 'static/media'),
        'UPLOAD_FOLDER': path('VOCAB_UPLOAD_DIR', app_root / 'static/uploads'),
        'SESSION_TYPE': 'filesystem',
        'SESSION_FILE_DIR': path('VOCAB_SESSION_DIR', app_root / 'flask_session'),
        'SESSION_PERMANENT': True,
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'PERMANENT_SESSION_LIFETIME': 3600,
        'MAX_CONTENT_LENGTH': 25 * 1024 * 1024,
        'OPENAI_API_KEY': OPENAI_API_KEY,
        'OPENROUTER_API_KEY': os.environ.get('OPENROUTER_API_KEY', ''),
        'CONVERSATION_TRANSCRIPTION_MODEL': os.environ.get('CONVERSATION_TRANSCRIPTION_MODEL', 'microsoft/mai-transcribe-2'),
        'CONVERSATION_COMPARISON_MODEL': os.environ.get('CONVERSATION_COMPARISON_MODEL', 'gpt-transcribe'),
        'CONVERSATION_MODEL': os.environ.get('CONVERSATION_MODEL', 'gpt-5.6-luna').removeprefix('openai/'),
        'LIVE_CONVERSATION_MODEL': os.environ.get('LIVE_CONVERSATION_MODEL', 'gpt-live-1'),
        'SPEAKING_ASSESSMENT_MODEL': os.environ.get('SPEAKING_ASSESSMENT_MODEL', 'gpt-audio-1.5'),
        'LIVE_CONVERSATION_VOICES': tuple(v.strip() for v in os.environ.get('LIVE_CONVERSATION_VOICES', 'marin,cedar').split(',') if v.strip()) or ('marin',),
        'OPENAI_MODEL_FLASHCARDS': OPENAI_MODEL_FLASHCARDS,
        'OPENAI_MODEL_HIGH': OPENAI_MODEL_HIGH,
        'OPENAI_MODEL_FAST': OPENAI_MODEL_FAST,
        'OPENAI_MODEL_VISION': OPENAI_MODEL_VISION,
        'OPENAI_MODEL_LESSONS': os.environ.get('OPENAI_MODEL_LESSONS', 'gpt-6-astra').removeprefix('openai/'),
        'OPENAI_LESSONS_REASONING_EFFORT': os.environ.get('OPENAI_LESSONS_REASONING_EFFORT', 'low'),
        'LESSON_PDF_RENDERER': os.environ.get('LESSON_PDF_RENDERER', 'pdftoppm'),
        'LESSON_OCR_BINARY': os.environ.get('LESSON_OCR_BINARY', 'tesseract'),
        'LESSON_OCR_DATA_DIR': path('LESSON_OCR_DATA_DIR', '') if os.environ.get('LESSON_OCR_DATA_DIR') else None,
        'LESSON_BACKGROUND_ENABLED': True,
        'OPENAI_IMAGE_MODEL': OPENAI_IMAGE_MODEL,
        'ELEVENLABS_MODEL': ELEVENLABS_MODEL,
        'ELEVENLABS_VOICE_IDS': ELEVENLABS_VOICE_IDS,
        'OPENAI_MODEL_STORY': OPENAI_MODEL_STORY,
        'OPENAI_STORY_REASONING_EFFORT': OPENAI_STORY_REASONING_EFFORT,
        'YANDEX_API_KEY': YANDEX_API_KEY,
        'ELEVENLABS_API_KEY': ELEVENLABS_API_KEY,
        'ANKI_CONNECT_URL': ANKI_CONNECT_URL,
        'ANKI_DEFAULT_DECK': DEFAULT_DECK,
        'GOOGLE_DRIVE_AUTO_AUTH': GOOGLE_DRIVE_AUTO_AUTH,
        'GOOGLE_DRIVE_FILE_ID': os.environ.get('GOOGLE_DRIVE_FILE_ID', '12O28VK4QwFxA5j1bGBXLNWyoBiWxdB_Y'),
        'GOOGLE_DRIVE_CREDENTIALS_FILE': path('GOOGLE_DRIVE_CREDENTIALS_FILE', app_root / 'credentials.json'),
        'GOOGLE_DRIVE_TOKEN_FILE': path('GOOGLE_DRIVE_TOKEN_FILE', app_root / 'token.json'),
        'GOOGLE_DRIVE_CACHE_FILE': path('GOOGLE_DRIVE_CACHE_FILE', app_root / 'vocab_list_cache.txt'),
        'WORD_POST_ENABLED': os.environ.get('WORD_POST_ENABLED', 'true').lower() in {'1', 'true', 'yes'},
        'DIRECTIONS_DELIVERIES_ENABLED': os.environ.get('DIRECTIONS_DELIVERIES_ENABLED', 'true').lower() in {'1', 'true', 'yes'},
        'WORD_POST_CATALOGUE_ENABLED': os.environ.get('WORD_POST_CATALOGUE_ENABLED', 'false').lower() in {'1', 'true', 'yes'},
        'WORD_POST_DIST_DIR': path('WORD_POST_DIST_DIR', app_root / 'ui/dist'),
        'WORD_POST_HOUSEHOLD_ENABLED': os.environ.get('WORD_POST_HOUSEHOLD_ENABLED', 'false').lower() in {'1', 'true', 'yes'},
        'PERSONAL_STUDY_TIMEZONE': os.environ.get('PERSONAL_STUDY_TIMEZONE', 'UTC'),
        'NATIVE_FLASHCARDS_ENABLED': os.environ.get('NATIVE_FLASHCARDS_ENABLED', 'true').lower() in {'1', 'true', 'yes'},
        'WORD_POST_ASSET_DIR': path('WORD_POST_ASSET_DIR', repo_root / 'instance/word-post-assets'),
        'WORD_POST_ALLOWED_HOSTS': ('localhost', '127.0.0.1', '::1'),
    }


def model_for(name):
    """Respect per-app overrides while supporting standalone utilities."""
    from flask import current_app, has_app_context
    return current_app.config.get(name, globals()[name]) if has_app_context() else globals()[name]
