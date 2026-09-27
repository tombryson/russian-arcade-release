"""Explicit local administration; imports are drafts, never auto-approved."""
from functools import wraps
import json
from pathlib import Path
import sqlite3

import click

from repositories.learning_repository import LearningError
from services.learning_assets import import_asset
from services.learning_backup import backup_learning_store


def cli_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (LearningError, OSError, sqlite3.Error, json.JSONDecodeError) as error:
            raise click.ClickException(str(error)) from error
    return wrapped


def register_learning_cli(app, household, content, store):
    @app.cli.group('word-post')
    def word_post():
        """Set up the household and prepare reviewed local content."""

    @word_post.command('setup')
    @click.option('--name', default='Our Word Post', show_default=True)
    @click.password_option('--pin', prompt='Grown-up PIN (6–12 digits)')
    @cli_errors
    def setup(name, pin):
        """Create the local household after db-upgrade; never replace an existing PIN."""
        household.configure(name, pin)
        click.echo('Household created. Enable WORD_POST_HOUSEHOLD_ENABLED=true and open /post/household.')

    @word_post.command('reset-pin')
    @click.option('--name', default='Our Word Post', show_default=True)
    @click.password_option('--pin', prompt='New grown-up PIN (6–12 digits)')
    @cli_errors
    def reset_pin(name, pin):
        """Local recovery: replace the PIN and revoke all browser access."""
        household.configure(name, pin, reset=True)
        click.echo('PIN replaced. All browsers must unlock again; learning data is retained.')

    @word_post.command('import-pack')
    @click.argument('filename', type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @cli_errors
    def import_pack(filename):
        """Validate a JSON pack and save a draft for grown-up review."""
        if filename.stat().st_size > 256 * 1024:
            raise click.ClickException('Content packs must be at most 256 KB.')
        version_id = content.import_draft(json.loads(filename.read_text(encoding='utf-8')))
        click.echo(f'Content version: {version_id}\nInspect its publication status and review it at /post/household?version={version_id}')

    @word_post.command('prepare-starter-cards')
    @click.option('--dry-run',is_flag=True,help='Report exact vocabulary matches without saving drafts.')
    @cli_errors
    def prepare_starter_cards(dry_run):
        """Prepare ten contextual examples where their vocabulary exists; never publish."""
        from services.card_preparation import prepare_starter
        report=prepare_starter(app.config['DB_PATH'],content,dry_run=dry_run)
        click.echo(json.dumps(report,ensure_ascii=False,indent=2))
        click.echo('No cards were published. Review the prepared wording at /post/flashcards/manage.')

    @word_post.command('import-asset')
    @click.argument('filename', type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option('--source', required=True, help='Provenance and permission to use the media.')
    @cli_errors
    def asset(filename, source):
        """Store validated private media; publication happens with its content pack."""
        with filename.open('rb') as stream:
            data = stream.read(store.MAX_BYTES + 1)
        asset_id = import_asset(app.config['DB_PATH'], store, data, source)
        click.echo(f'Asset ID: {asset_id}')

    @word_post.command('backup')
    @click.argument('destination', type=click.Path(path_type=Path))
    @cli_errors
    def backup(destination):
        """Snapshot SQLite and Word Post assets into a new private directory."""
        manifest = backup_learning_store(app.config['DB_PATH'], store, destination, app.config['UPLOAD_FOLDER'])
        click.echo(f'Backup verified: {destination}\nWord Post assets: {len(manifest["assets"])}')
        click.echo(f'Lesson files: {len(manifest["lesson_files"])}. Also back up other legacy media, the Anki collection and Drive separately.')
