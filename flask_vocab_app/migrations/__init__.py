"""Explicit, transactional SQLite migrations and local administration commands."""
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import click

MIGRATION_DIR = Path(__file__).parent


def schema_version(conn):
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
    return conn.execute('SELECT COALESCE(MAX(version), 0) FROM schema_migrations').fetchone()[0] if exists else 0


def _validate_baseline(conn):
    # Compare column names with the baseline without assuming that historical
    # databases have identical defaults or indexes. Never rebuild personal tables.
    with closing(sqlite3.connect(':memory:')) as expected:
        expected.executescript((MIGRATION_DIR / '001_baseline.sql').read_text())
        for (table,) in expected.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"):
            required = {row[1] for row in expected.execute('PRAGMA table_info("' + table + '")')}
            actual = {row[1] for row in conn.execute('PRAGMA table_info("' + table + '")')}
            if required - actual:
                raise ValueError(f'Unsupported legacy schema in {table}: missing {sorted(required - actual)}. Restore/use the canonical flask_vocab_app database; do not replace it with a root or archived database.')
    if conn.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('Database contains orphaned references; repair a copy before upgrading.')


def upgrade_database(db_path, backup=True):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(MIGRATION_DIR.glob('[0-9][0-9][0-9]_*.sql'))
    backup_path = None
    with closing(sqlite3.connect(str(path), timeout=10)) as conn:
        current = schema_version(conn)
        latest = int(files[-1].name.split('_')[0])
        if current > latest:
            raise ValueError(f'Database version {current} is newer than this application ({latest}).')
        pending = [p for p in files if int(p.name.split('_')[0]) > current]
        if not pending:
            return current, None
        has_tables = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone()
        if backup and has_tables:
            backup_path = str(path) + '.pre-migration-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.bak'
            with closing(sqlite3.connect(backup_path)) as snapshot:
                conn.backup(snapshot)
                snapshot.execute('PRAGMA journal_mode=DELETE')
        # SQLite's supported table-rebuild procedure changes FK enforcement
        # before BEGIN, then checks all references before the atomic commit.
        rebuild = any(p.name in ('009_native_flashcards.sql', '012_four_review_ratings.sql', '017_lesson_word_selection.sql', '032_journey_game_library.sql', '045_course_releases.sql') for p in pending)
        conn.execute('PRAGMA foreign_keys=' + ('OFF' if rebuild else 'ON'))
        try:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
            for file in pending:
                version = int(file.name.split('_')[0])
                statement = ''
                for line in file.read_text().splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        conn.execute(statement)
                        statement = ''
                if statement.strip():
                    raise ValueError(f'Incomplete migration statement in {file.name}')
                if version == 1:
                    _validate_baseline(conn)
                if version == 9:
                    from services.learning_content import index_existing_decks
                    index_existing_decks(conn)
                if version == 22:
                    from repositories.speaking_repository import seed_catalogue
                    seed_catalogue(conn)
                if version == 23:
                    from services.progression import seed_progression
                    seed_progression(conn)
                if version == 24:
                    from repositories.speaking_repository import seed_levels
                    seed_levels(conn)
                if version == 32:
                    from services.journey_games import backfill_unlocks
                    backfill_unlocks(conn)
                if version == 38:
                    from services.game_access import backfill_access
                    backfill_access(conn)
                if version == 39:
                    from services.game_access import preserve_played_access
                    preserve_played_access(conn)
                if version == 42:
                    from repositories.speaking_repository import seed_curriculum
                    seed_curriculum(conn)
                if version == 45 and not has_tables:
                    # Migration 025 creates the local bootstrap profile. In a
                    # brand-new database it has never used the legacy course;
                    # leave enrolment to its first command and current release.
                    conn.execute("DELETE FROM course_enrolments WHERE migration_source='schema-044'")
                conn.execute('INSERT INTO schema_migrations(version) VALUES (?)', (version,))
            if conn.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Migration would leave orphaned references; no changes were committed.')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return latest, backup_path


def seed_demo(db_path):
    with closing(sqlite3.connect(db_path)) as conn, conn:
        if schema_version(conn) == 0:
            raise ValueError('Run db-upgrade before seed-demo.')
        if conn.execute('SELECT COUNT(*) FROM words').fetchone()[0]:
            raise ValueError('Demo seeding requires an empty vocabulary; personal data was not changed.')
        for lemma, topic in [('кофе', 'food'), ('семья', 'family'), ('школа', 'school')]:
            cursor = conn.execute("INSERT INTO words(lemma,pos,count,lemma_difficulty,topic,date_added) VALUES (?, 'NOUN',0,1,?,date('now'))", (lemma, '["' + topic + '"]'))
            conn.execute("INSERT INTO forms(word_id,form,count,tags,form_difficulty) VALUES (?,?,0,?,1)", (cursor.lastrowid, lemma, '{"case":"nomn","number":"sing"}'))


def register_cli(app):
    @app.cli.command('db-upgrade')
    def upgrade_command():
        """Create/upgrade the configured DB; back up an existing DB first."""
        try:
            version, backup_path = upgrade_database(app.config['DB_PATH'])
        except (ValueError, sqlite3.Error) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f'Database: {app.config["DB_PATH"]}\nSchema version: {version}')
        if backup_path:
            click.echo(f'Backup: {backup_path}')

    @app.cli.command('seed-demo')
    def seed_command():
        """Add three synthetic words to an empty, migrated database."""
        try:
            seed_demo(app.config['DB_PATH'])
        except (ValueError, sqlite3.Error) as error:
            raise click.ClickException(str(error)) from error
        click.echo('Added three demo words.')

    @app.cli.command('db-status')
    def status_command():
        """Show the configured database and version without creating it."""
        path = Path(app.config['DB_PATH'])
        click.echo(f'Database: {path}')
        if not path.exists():
            click.echo('Not initialized. Run db-upgrade.')
            return
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
            click.echo(f'Schema version: {schema_version(conn)}')
