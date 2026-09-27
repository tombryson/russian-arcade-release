"""Explicit, reversible data maintenance for authored story titles."""
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

import click

from utils.story_content import validate_story_title
from repositories.story_repository import english_story_title


def story_text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _title_changes(conn, plan, language="ru"):
    if not isinstance(plan, dict) or plan.get("version") != 1 or not isinstance(plan.get("stories"), list):
        raise ValueError("Expected a version 1 plan with a stories list.")
    changes, seen = [], set()
    for entry in plan["stories"]:
        if not isinstance(entry, dict) or type(entry.get("id")) is not int:
            raise ValueError("Each planned story needs an integer ID.")
        story_id = entry["id"]
        if story_id in seen:
            raise ValueError(f"Repeated story ID: {story_id}")
        seen.add(story_id)
        title = validate_story_title(entry.get("title"))
        row = conn.execute("SELECT title, text FROM saved_stories WHERE id = ?", (story_id,)).fetchone()
        if not row:
            raise ValueError(f"Story {story_id} does not exist.")
        if story_text_hash(row[1]) != entry.get("text_sha256"):
            raise ValueError(f"Story {story_id} has different text; review the plan again.")
        current_title = english_story_title(conn, story_id) if language == "en" else row[0]
        if current_title == title:
            continue  # Re-running the same migration is safe.
        if not isinstance(entry.get("expected_title"), str) or current_title != entry["expected_title"]:
            raise ValueError(f"Story {story_id} has a different title; review the plan again.")
        changes.append({"id": story_id, "before": current_title, "after": title})
    return changes


def retitle_stories(db_path, plan, apply=False, language="ru"):
    """Validate every entry first. English plans add only the translation table."""
    if language not in {"en", "ru"}:
        raise ValueError("Choose English (en) or Russian (ru).")
    path = Path(db_path).resolve()
    backup = None
    with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=10)) as conn:
        changes = _title_changes(conn, plan, language)
        if not apply or not changes:
            return changes, backup
        backup = path.with_name(path.name + ".pre-migration-story-titles-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".bak")
        with closing(sqlite3.connect(backup)) as snapshot:
            conn.backup(snapshot)
            # Keep the backup self-contained even when the source uses WAL.
            snapshot.execute("PRAGMA journal_mode=DELETE")
        try:
            conn.execute("BEGIN IMMEDIATE")
            changes = _title_changes(conn, plan, language)
            if language == "en":
                # The same idempotent DDL is used by full upgrades. A title-only
                # maintenance run need not enable the household schema first.
                schema = Path(__file__).parent / "migrations/005_story_title_translations.sql"
                conn.execute(schema.read_text())
            for change in changes:
                if language == "en":
                    conn.execute("INSERT INTO story_title_translations(story_id, language, title) VALUES (?, 'en', ?) ON CONFLICT(story_id, language) DO UPDATE SET title=excluded.title", (change["id"], change["after"]))
                else:
                    conn.execute("UPDATE saved_stories SET title = ? WHERE id = ?", (change["after"], change["id"]))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return changes, str(backup)


def register_story_cli(app):
    @app.cli.command("story-titles")
    @click.option("--plan", "plan_path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option("--apply", is_flag=True, help="Back up the database and apply the validated plan.")
    @click.option("--language", type=click.Choice(["ru", "en"]), default="ru", show_default=True)
    def titles_command(plan_path, apply, language):
        """Preview/apply an authored title plan against the configured database."""
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            changes, backup = retitle_stories(app.config["DB_PATH"], plan, apply=apply, language=language)
        except (OSError, ValueError, sqlite3.Error) as error:
            raise click.ClickException(str(error)) from error
        for change in changes:
            click.echo(f'{change["id"]}: {change["before"]} → {change["after"]}')
        click.echo(f'{"Updated" if apply else "Would update"} {len(changes)} stories.')
        if backup:
            click.echo(f"Backup: {backup}")
