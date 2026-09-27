"""Explicit imports and repair of historical lesson source references."""
from pathlib import Path
import click
from repositories.learning_repository import LearningError


def register_lesson_cli(app, service):
    @app.cli.group("lessons")
    def lessons():
        """Import tutor materials and prepare source-grounded practice."""

    @lessons.command("import")
    @click.argument(
        "filename", type=click.Path(exists=True, dir_okay=False, path_type=Path)
    )
    @click.option(
        "--lesson-id",
        default=None,
        help="Attach an updated document to an existing lesson.",
    )
    @click.option("--title", default="")
    @click.option("--focus", default="")
    @click.option(
        "--prepare",
        is_flag=True,
        help="Call the configured model to prepare exercises now.",
    )
    def import_lesson(filename, lesson_id, title, focus, prepare):
        try:
            material = service.files.receive(filename.read_bytes(), filename.name)
            if lesson_id:
                rid = service.revise(lesson_id, [material])
            else:
                lesson_id, rid, _ = service.create(title, focus, [material])
            click.echo(f"Lesson: {lesson_id}\nRevision: {rid}")
            if prepare:
                service.process(rid)
                row = service.revision(rid)
                if row["state"] != "ready":
                    raise click.ClickException(
                        row["error"] or "Preparation is already running."
                    )
                click.echo("All pages read; practice ready.")
            click.echo(f"Open /lessons/load/{lesson_id}?revision={rid}")
        except LearningError as error:
            raise click.ClickException(str(error)) from error

    @lessons.command("adopt-legacy")
    def adopt_legacy():
        """Copy old lesson files into portable storage without calling a model."""
        failures = 0
        for lesson in service.legacy.get_saved_lessons():
            try:
                rid = service.adopt_legacy(lesson["id"])
                click.echo(f"Saved source: {lesson['id']} -> {rid}")
            except LearningError as error:
                failures += 1
                click.echo(f"Needs source file: {lesson['id']}: {error}")
        if failures:
            raise click.ClickException(
                f"{failures} lesson(s) need their original files uploaded again."
            )
