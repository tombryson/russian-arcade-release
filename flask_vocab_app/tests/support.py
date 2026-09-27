import tempfile
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch
from flask.testing import FlaskClient
from app import create_app
from services.sync_service import SyncService
from migrations import MIGRATION_DIR, upgrade_database, seed_demo


def latest_schema_version():
    return max(int(path.name.split("_")[0]) for path in MIGRATION_DIR.glob("[0-9][0-9][0-9]_*.sql"))


def strip_course_progression(conn):
    """Remove course migrations and markers when a test rewinds its schema."""
    for table in ('assessment_pilot_requests', 'assessment_pilot_reviews', 'assessment_pilot_submissions', 'assessment_pilot_support', 'assessment_pilot_components', 'assessment_pilot_sessions', 'translation_reference_views', 'comprehension_support_receipts', 'comprehension_attempts', 'comprehension_tasks', 'learning_item_support', 'activity_criterion_reports', 'activity_task_contracts', 'course_checkpoint_followups', 'course_release_switches', 'course_target_observations', 'course_target_practice_receipts',
                  'course_target_practice_requests', 'course_target_practice_attempts', 'course_continuation_entitlements', 'course_enrolments',
                  'course_checkpoint_requests', 'course_checkpoint_submissions',
                  'course_chapter_passes', 'course_evidence', 'course_checkpoint_attempts'):
        conn.execute('DROP TABLE IF EXISTS ' + table)
    for table in ('translation_attempts', 'word_jumble_attempts'):
        columns = {row[1] for row in conn.execute('PRAGMA table_info(' + table + ')')}
        for column in ('criterion_report_json', 'criterion_support_json'):
            if column in columns:
                conn.execute('ALTER TABLE ' + table + ' DROP COLUMN ' + column)
    conn.execute('DELETE FROM schema_migrations WHERE version IN (44,45,46,47,48,49,50,51,52,53,54)')


def strip_progression_and_levels(conn):
    """Remove migrations 023 onward when a test constructs an older SQLite shape.

    This helper is test-only. Dropping their version markers alone would leave
    tables/indexes behind and prevent the real migrations from being exercised.
    """
    strip_course_progression(conn)
    conn.execute('DROP TABLE IF EXISTS step_conversation_answers')
    conn.execute('DROP TABLE IF EXISTS step_conversation_sessions')
    conn.execute('DROP TABLE IF EXISTS speaking_scenario_levels')
    columns = {row[1] for row in conn.execute('PRAGMA table_info(word_jumble_games)')}
    if 'task_json' in columns:
        conn.execute('ALTER TABLE word_jumble_games DROP COLUMN task_json')
    conn.execute('DROP TABLE IF EXISTS journey_route_preparations')
    conn.execute('DROP TABLE IF EXISTS journey_route_audio_cache')
    conn.execute('DROP TABLE IF EXISTS journey_route_actions')
    conn.execute('DROP TABLE IF EXISTS journey_route_state')
    conn.execute('DROP TABLE IF EXISTS journey_game_corrections')
    conn.execute('DROP TABLE IF EXISTS journey_game_preparations')
    conn.execute('DROP TABLE IF EXISTS journey_game_examples')
    conn.execute('DROP TABLE IF EXISTS journey_game_media')
    conn.execute('DROP TABLE IF EXISTS journey_game_sessions')
    conn.execute('DROP TABLE IF EXISTS journey_game_unlocks')
    conn.execute('DROP TABLE IF EXISTS journey_game_purchases')
    conn.execute('DROP TABLE IF EXISTS journey_game_access')
    conn.execute('DROP TABLE IF EXISTS first_steps_attempts')
    conn.execute('DROP TABLE IF EXISTS first_delivery_attempts')
    conn.execute('DROP TABLE IF EXISTS profile_onboarding')
    for table in ('saved_stories', 'writing_exercises', 'word_jumble_games', 'sentences'):
        conn.execute('DROP INDEX IF EXISTS ' + table + '_owner')
        columns = {row[1] for row in conn.execute('PRAGMA table_info(' + table + ')')}
        if 'owner_profile_id' in columns:
            conn.execute('ALTER TABLE ' + table + ' DROP COLUMN owner_profile_id')
    for table in ('journey_answers','journey_progress','journey_worlds',
                  'progression_claims','progression_entries','progression_events',
                  'progression_preferences','progression_settings'):
        conn.execute('DROP TABLE IF EXISTS ' + table)
    conn.execute('DROP INDEX IF EXISTS live_sessions_level')
    conn.execute('DROP INDEX IF EXISTS speaking_variants_level')
    for table in ('live_conversation_sessions','speaking_scenario_variants'):
        columns = {row[1] for row in conn.execute('PRAGMA table_info(' + table + ')')}
        if 'target_level' in columns:
            conn.execute('ALTER TABLE ' + table + ' DROP COLUMN target_level')
    conn.execute('DELETE FROM schema_migrations WHERE version>=23')


def select_test_profile(client, profile_id="personal-learning"):
    """Select a learner through the same CSRF-protected flow as the browser.

    This helper deliberately uses public application routes; it neither forges
    a session nor disables the production identity checks.
    """
    state = client.get('/api/v1/user-session')
    if state.status_code != 200:
        raise AssertionError(f"Test profile picker failed: HTTP {state.status_code}")
    payload = state.get_json() or {}
    token = payload.get('csrf_token')
    if not token:
        raise AssertionError("Test profile picker did not return a CSRF token")
    selected = client.post('/api/v1/user-session/select',
                           json={'profile_id': profile_id},
                           headers={'X-CSRF-Token': token})
    if selected.status_code != 200:
        raise AssertionError(f"Test profile selection failed: HTTP {selected.status_code}")
    return selected.get_json()


class PersonalStudyTestClient(FlaskClient):
    """A signed-in personal client for existing activity behavior tests only."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Household tests configure their app after isolated_app returns. Check
        # at client creation so those clients still start fully signed out.
        if not self.application.config['WORD_POST_HOUSEHOLD_ENABLED']:
            select_test_profile(self)


class VocabularyEnrichmentStub(SyncService):
    """Provider-free completion for activity tests, with real committed writes."""

    def __init__(self, db_path, drive_service):
        super().__init__(db_path, drive_service=drive_service, api_key='', config={})
        self.calls = []
        self.pending = False
        self.error = None

    def enrich_words(self, word_ids=None, *, batch_size=20):
        ids = list(dict.fromkeys(word_ids or []))
        self.calls.append(ids)
        if self.error:
            raise self.error
        if self.pending:
            return {'updated': [], 'completed': [], 'pending': ids, 'warnings': ['Test provider unavailable.']}
        updated = []
        # A second writer also catches accidental provider work inside a write
        # transaction: tests fail promptly instead of silently skipping the lock.
        with sqlite3.connect(self.db_path, timeout=0) as conn:
            conn.row_factory = sqlite3.Row
            for word_id in ids:
                row = conn.execute('SELECT * FROM words WHERE id=?', (word_id,)).fetchone()
                topics = row['topic'] if row['topic'] and json.loads(row['topic']) else '["places"]'
                mnemonic = row['mnemonic'] or 'Test memory association for ' + row['lemma']
                if (topics, mnemonic) != (row['topic'], row['mnemonic']):
                    conn.execute('UPDATE words SET topic=?,mnemonic=? WHERE id=?', (topics, mnemonic, word_id))
                    updated.append(word_id)
        return {'updated': updated, 'completed': ids, 'pending': [], 'warnings': []}


def isolated_app(test_case, services=None, demo=True, *, signed_in=True):
    temporary = tempfile.TemporaryDirectory(prefix="russian-vocab-test-")
    test_case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    db = str(root / "vocab.db")
    upgrade_database(db, backup=False)
    if demo:
        seed_demo(db)
    network = patch("socket.socket.connect", side_effect=AssertionError("External network calls are forbidden in unit tests"))
    network.start()
    test_case.addCleanup(network.stop)
    from utils.lazy import LazyService
    providers = {'SyncService': LazyService('SyncService', lambda: VocabularyEnrichmentStub(db, app.extensions['services']['GoogleDriveService']))}
    providers.update(services or {})
    app = create_app({
        "TESTING": True, "SECRET_KEY": "test-only", "DB_PATH": db,
        "SESSION_FILE_DIR": str(root / "sessions"),
        "UPLOAD_FOLDER": str(root / "uploads"), "APP_MEDIA_DIR": str(root / "media"),
        "ANKI_MEDIA_DIR": str(root / "anki"),
        "WORD_POST_ASSET_DIR": str(root / "learning-assets"),
        "WORD_POST_HOUSEHOLD_ENABLED": False,
        "OPENAI_API_KEY": "", "YANDEX_API_KEY": "", "ELEVENLABS_API_KEY": "",
        "GOOGLE_DRIVE_AUTO_AUTH": False,
        "GOOGLE_DRIVE_CREDENTIALS_FILE": str(root / "credentials.json"),
        "GOOGLE_DRIVE_TOKEN_FILE": str(root / "token.json"),
        "GOOGLE_DRIVE_CACHE_FILE": str(root / "cache.txt"),
    }, providers)
    if signed_in:
        app.test_client_class = PersonalStudyTestClient
    return app
