"""Versioned tutor material and resumable, source-grounded individual practice."""
from collections import Counter
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import threading

from repositories.learning_repository import (
    LearningError,
    encoded,
    identifier,
    payload_hash,
    timestamp,
    transaction,
)
from services.lesson_ai import Plan
from services.lesson_files import LessonFiles, MAX_PAGES

log = logging.getLogger(__name__)


def clean(value, maximum, name, required=True):
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or (required and not value.strip())
    ):
        raise LearningError("lesson_input", f"Enter a valid {name}.")
    return value.strip()


def compact(value):
    return " ".join(value.split())


class LessonCompanion:
    def __init__(self, db_path, legacy, ai, config):
        self.db_path, self.legacy, self.ai = db_path, legacy, ai
        self.config = config
        self.max_pages = min(MAX_PAGES, max(1, int(config.get("LESSON_MAX_PAGES", MAX_PAGES))))
        self.files = LessonFiles(
            db_path,
            config.get("UPLOAD_FOLDER"),
            config.get("LESSON_PDF_RENDERER", "pdftoppm"),
            max_pages=self.max_pages,
        )
        self._lock = threading.Lock()
        self._active = set()
        self._slots = threading.BoundedSemaphore(2)

    def receive(self, uploads):
        uploads = [upload for upload in uploads if upload and upload.filename]
        if not 1 <= len(uploads) <= 5:
            raise LearningError("lesson_file", "Choose 1–5 files for a lesson.")
        pending = []
        total = 0
        # Validate the whole upload before saving any files or starting work.
        for upload in uploads:
            data = upload.stream.read(25 * 1024 * 1024 + 1)
            media_type, pages = self.files.inspect(data, self.max_pages)
            total += pages
            if total > self.max_pages:
                raise LearningError("lesson_file", f"Choose up to {self.max_pages} pages in total.")
            pending.append((data, media_type, pages, Path(upload.filename).name[:200]))
        return [{"digest": self.files.put(data, media_type), "name": name,
                 "media_type": media_type, "pages": pages}
                for data, media_type, pages, name in pending]

    def create(self, title, description, materials):
        title = clean(title or Path(materials[0]["name"]).stem, 200, "lesson title")
        description = clean(description or "", 2000, "lesson focus", False)
        fingerprint = payload_hash([m["digest"] for m in materials])
        with transaction(self.db_path, write=True) as conn:
            old = conn.execute(
                "SELECT lesson_id,id FROM lesson_revisions WHERE fingerprint=? ORDER BY created_at LIMIT 1",
                (fingerprint,),
            ).fetchone()
            if old:
                return old["lesson_id"], old["id"], True
            lesson_id = identifier()
            conn.execute(
                "INSERT INTO lessons(id,title,description,created_at) VALUES (?,?,?,?)",
                (lesson_id, title, description, datetime.now().isoformat()),
            )
            revision = self._revision(conn, lesson_id, materials)
        return lesson_id, revision, False

    def _revision(self, conn, lesson_id, materials):
        fingerprint = payload_hash([m["digest"] for m in materials])
        old = conn.execute(
            "SELECT id FROM lesson_revisions WHERE lesson_id=? AND fingerprint=?",
            (lesson_id, fingerprint),
        ).fetchone()
        if old:
            return old["id"]
        if not conn.execute(
            "SELECT 1 FROM lessons WHERE id=?", (lesson_id,)
        ).fetchone():
            raise LearningError("not_found", "This lesson was not found.", 404)
        parent = conn.execute(
            "SELECT id,number FROM lesson_revisions WHERE lesson_id=? ORDER BY number DESC LIMIT 1",
            (lesson_id,),
        ).fetchone()
        revision = identifier()
        conn.execute(
            "INSERT INTO lesson_revisions(id,lesson_id,number,parent_id,fingerprint,materials,state,model,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                revision,
                lesson_id,
                parent["number"] + 1 if parent else 1,
                parent["id"] if parent else None,
                fingerprint,
                encoded(materials),
                "queued",
                self.ai.model,
                timestamp(),
            ),
        )
        return revision

    def revise(self, lesson_id, materials):
        with transaction(self.db_path, write=True) as conn:
            return self._revision(conn, lesson_id, materials)

    def adopt_legacy(self, lesson_id):
        """Copy sources into managed storage. Keep the old row and answer JSON untouched."""
        with transaction(self.db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM lesson_revisions WHERE lesson_id=? ORDER BY number DESC LIMIT 1",
                (lesson_id,),
            ).fetchone()
        if existing:
            return existing["id"]
        lesson = self.legacy.get_lesson(lesson_id)
        if not lesson:
            raise LearningError("not_found", "This lesson was not found.", 404)
        references = (
            [lesson["pdf_path"]] if lesson.get("pdf_path") else []
        ) + lesson.get("images", [])
        materials = []
        for reference in references:
            path = self.files.legacy(reference)
            name = re.sub(r"^[a-f0-9-]{32,36}_", "", path.name)
            materials.append(self.files.receive(path.read_bytes(), name))
        if not materials:
            raise LearningError(
                "lesson_file", "Add the lesson PDF or images before preparing practice."
            )
        if sum(m["pages"] for m in materials) > self.max_pages:
            raise LearningError(
                "lesson_file", f"Choose a section of up to {self.max_pages} pages."
            )
        return self.revise(lesson_id, materials)

    def revision(self, revision_id, lesson_id=None):
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM lesson_revisions WHERE id=?", (revision_id,)
            ).fetchone()
            if not row or (lesson_id is not None and row["lesson_id"] != lesson_id):
                raise LearningError(
                    "not_found", "This lesson version was not found.", 404
                )
            return dict(row)

    def dispatch(self, revision_id):
        if not self.config.get("LESSON_BACKGROUND_ENABLED", True):
            return
        with self._lock:
            if revision_id in self._active:
                return
            if len(self._active) >= 8:
                raise LearningError(
                    "lesson_busy",
                    "Several lessons are being prepared. Please try again shortly.",
                    503,
                )
            self._active.add(revision_id)

        def run():
            self._slots.acquire()
            try:
                self.process(revision_id)
            finally:
                with self._lock:
                    self._active.discard(revision_id)
                self._slots.release()

        threading.Thread(target=run, name="lesson-preparation", daemon=True).start()

    def _pulse(self, revision_id, token, stage):
        with transaction(self.db_path, write=True) as conn:
            if not conn.execute(
                "UPDATE lesson_revisions SET stage=?,lease_until=? WHERE id=? AND lease_token=?",
                (stage, timestamp() + 300, revision_id, token),
            ).rowcount:
                raise LearningError(
                    "lesson_superseded", "Preparation was resumed elsewhere.", 409
                )

    def _owns(self, conn, revision_id, token):
        if not conn.execute(
            "SELECT 1 FROM lesson_revisions WHERE id=? AND lease_token=?",
            (revision_id, token),
        ).fetchone():
            raise LearningError(
                "lesson_superseded", "Preparation was resumed elsewhere.", 409
            )

    def process(self, revision_id):
        token = identifier()
        with transaction(self.db_path, write=True) as conn:
            row = conn.execute(
                "SELECT * FROM lesson_revisions WHERE id=?", (revision_id,)
            ).fetchone()
            if not row or row["state"] == "ready" or row["lease_until"] > timestamp():
                return
            conn.execute(
                "UPDATE lesson_revisions SET state='processing',lease_token=?,lease_until=?,error='' WHERE id=?",
                (token, timestamp() + 300, revision_id),
            )
            revision = dict(row)
        try:
            materials = json.loads(revision["materials"])
            total = sum(m["pages"] for m in materials)
            number = 0
            for material in materials:
                with transaction(self.db_path) as conn:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM lesson_pages WHERE revision_id=? AND number>? AND number<=?",
                        (revision_id, number, number + material["pages"]),
                    ).fetchone()[0]
                if count == material["pages"]:
                    number += count
                    continue
                self._pulse(revision_id, token, "rendering")
                for source_page, (image, base) in enumerate(
                    self.files.render(material), 1
                ):
                    number += 1
                    key = self.files.put(image, "image/jpeg")
                    with transaction(self.db_path, write=True) as conn:
                        self._owns(conn, revision_id, token)
                        conn.execute(
                            "INSERT OR IGNORE INTO lesson_pages VALUES (?,?,?,?,?,?,NULL)",
                            (
                                revision_id,
                                number,
                                material["digest"],
                                source_page,
                                key,
                                base,
                            ),
                        )
            policy = self.ai.POLICY + ":" + revision["model"]
            with transaction(self.db_path, write=True) as conn:
                self._owns(conn, revision_id, token)
                conn.execute(
                    "UPDATE lesson_pages SET extraction=(SELECT payload FROM lesson_extraction_cache WHERE image_digest=lesson_pages.image_digest AND policy=?) WHERE revision_id=? AND extraction IS NULL",
                    (policy, revision_id),
                )
                pending = [
                    dict(p)
                    for p in conn.execute(
                        "SELECT * FROM lesson_pages WHERE revision_id=? AND extraction IS NULL ORDER BY number",
                        (revision_id,),
                    )
                ]
            for offset in range(0, len(pending), 4):
                batch = pending[offset : offset + 4]
                self._pulse(revision_id, token, "reading")
                results = self.ai.extract(
                    [self.files.path(p["image_digest"]).read_bytes() for p in batch]
                )
                if len(results) != len(batch):
                    raise LearningError(
                        "lesson_extraction",
                        "Some pages were not read. Retry preparation.",
                        503,
                    )
                with transaction(self.db_path, write=True) as conn:
                    self._owns(conn, revision_id, token)
                    for page, result in zip(batch, results):
                        conn.execute(
                            "INSERT OR REPLACE INTO lesson_extraction_cache VALUES (?,?,?)",
                            (page["image_digest"], policy, encoded(result)),
                        )
                        conn.execute(
                            "UPDATE lesson_pages SET extraction=? WHERE revision_id=? AND number=?",
                            (encoded(result), revision_id, page["number"]),
                        )
            pages = self.evidence(revision_id)
            if len(pages) != total or sum(len(p["text"].strip()) for p in pages) < 80:
                raise LearningError(
                    "lesson_extraction",
                    "There is not enough readable lesson text to prepare exercises.",
                    503,
                )
            self._pulse(revision_id, token, "planning")
            lesson = self.legacy.get_lesson(revision["lesson_id"])
            with transaction(self.db_path) as conn:
                words = [
                    r[0] for r in conn.execute("SELECT lemma FROM words ORDER BY id")
                ]
            plan = self.ai.prepare(
                lesson["title"], lesson.get("description", ""), pages, words
            )
            self._pulse(revision_id, token, "checking")
            plan = self.ai.validate(plan, pages)
            self.validate_plan(plan, pages)
            with transaction(self.db_path, write=True) as conn:
                self._owns(conn, revision_id, token)
                plan_id = identifier()
                conn.execute(
                    "INSERT INTO lesson_plans VALUES (?,?,?,?,?,?)",
                    (
                        plan_id,
                        revision_id,
                        encoded(plan),
                        revision["model"],
                        self.ai.POLICY,
                        timestamp(),
                    ),
                )
                for i, task in enumerate(plan["tasks"]):
                    conn.execute(
                        "INSERT INTO lesson_tasks VALUES (?,?,?,?)",
                        (identifier(), plan_id, i, encoded(task)),
                    )
                conn.execute(
                    "UPDATE lesson_revisions SET state='ready',stage='ready',lease_until=0,lease_token=NULL WHERE id=? AND lease_token=?",
                    (revision_id, token),
                )
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, LearningError)
                else "Preparation stopped. Your source files and completed pages are saved. Please retry."
            )
            log.warning("Lesson preparation failed (%s)", type(error).__name__)
            with transaction(self.db_path, write=True) as conn:
                conn.execute(
                    "UPDATE lesson_revisions SET state='failed',error=?,lease_until=0,lease_token=NULL WHERE id=? AND lease_token=?",
                    (message, revision_id, token),
                )

    @staticmethod
    def validate_plan(plan, pages):
        Plan.model_validate(plan)
        if (
            len(plan["objectives"]) != 3
            or len(plan["tasks"]) != 6
            or Counter(t["objective"] for t in plan["tasks"]) != {1: 2, 2: 2, 3: 2}
        ):
            raise LearningError(
                "lesson_plan",
                "The practice set did not cover all three objectives. Retry preparation.",
                503,
            )
        texts = {p["page"]: compact(p["text"]) for p in pages}
        for task in plan["tasks"]:
            if (
                not task["prompt"].strip()
                or not task["sample_answer"].strip()
                or not task["evidence"]
            ):
                raise LearningError(
                    "lesson_plan", "An exercise was incomplete. Retry preparation.", 503
                )
            for source in task["evidence"]:
                if len(source["quote"].strip()) < 5 or compact(
                    source["quote"]
                ) not in texts.get(source["page"], ""):
                    raise LearningError(
                        "lesson_plan",
                        "An exercise could not be traced to the source. Retry preparation.",
                        503,
                    )
        for word in plan["vocabulary"]:
            if (
                not word["surface"]
                or word["surface"] not in word["context"]
                or compact(word["context"]) not in texts.get(word["page"], "")
            ):
                raise LearningError(
                    "lesson_plan",
                    "A vocabulary example did not match the source. Retry preparation.",
                    503,
                )

    def evidence(self, revision_id):
        with transaction(self.db_path) as conn:
            return [
                {"page": p["number"], **json.loads(p["extraction"])}
                for p in conn.execute(
                    "SELECT number,extraction FROM lesson_pages WHERE revision_id=? AND extraction IS NOT NULL ORDER BY number",
                    (revision_id,),
                )
            ]

    def library(self, profile_id):
        lessons = self.legacy.get_saved_lessons()
        with transaction(self.db_path) as conn:
            for lesson in lessons:
                latest = conn.execute(
                    "SELECT r.*,p.payload FROM lesson_revisions r LEFT JOIN lesson_plans p ON p.revision_id=r.id WHERE lesson_id=? ORDER BY number DESC LIMIT 1",
                    (lesson["id"],),
                ).fetchone()
                progress = conn.execute(
                    "SELECT * FROM lesson_progress WHERE profile_id=? AND lesson_id=?",
                    (profile_id, lesson["id"]),
                ).fetchone()
                lesson["current"] = dict(latest) if latest else None
                lesson["plan"] = (
                    json.loads(latest["payload"])
                    if latest and latest["payload"]
                    else None
                )
                lesson["progress"] = dict(progress) if progress else None
        return sorted(
            lessons,
            key=lambda l: l["progress"]["updated_at"] if l["progress"] else 0,
            reverse=True,
        )

    def snapshot(self, lesson_id, profile_id, revision_id=None):
        with transaction(self.db_path) as conn:
            revisions = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM lesson_revisions WHERE lesson_id=? ORDER BY number DESC",
                    (lesson_id,),
                )
            ]
            if revision_id and not any(r["id"] == revision_id for r in revisions):
                raise LearningError(
                    "not_found", "This lesson version was not found.", 404
                )
            revision = next(
                (r for r in revisions if r["id"] == revision_id),
                revisions[0] if revisions else None,
            )
            progress = conn.execute(
                "SELECT * FROM lesson_progress WHERE profile_id=? AND lesson_id=?",
                (profile_id, lesson_id),
            ).fetchone()
            result = {
                "revisions": revisions,
                "revision": revision,
                "plan": None,
                "tasks": [],
                "pages": [],
                "materials": [],
                "progress": dict(progress) if progress else {},
                "changes": None,
            }
            if not revision:
                return result
            rid = revision["id"]
            result["materials"] = json.loads(revision["materials"])
            result["pages"] = [
                dict(p)
                for p in conn.execute(
                    "SELECT * FROM lesson_pages WHERE revision_id=? ORDER BY number",
                    (rid,),
                )
            ]
            for p in result["pages"]:
                p["reading"] = json.loads(p["extraction"]) if p["extraction"] else None
            result["pages_read"] = sum(bool(p["extraction"]) for p in result["pages"])
            result["page_total"] = sum(m["pages"] for m in result["materials"])
            result["retryable"] = revision["state"] in ("queued", "failed") or (
                revision["state"] == "processing"
                and revision["lease_until"] <= timestamp()
            )
            if progress and progress["base_digest"]:
                matching = [
                    p
                    for p in result["pages"]
                    if p["base_digest"] == progress["base_digest"]
                ]
                if len(matching) == 1:
                    result["progress"]["page"] = matching[0]["number"]
                elif progress["revision_id"] != rid:
                    result["progress"]["page"] = 1
            if revision["parent_id"]:
                parent = {
                    r["base_digest"]: r["image_digest"]
                    for r in conn.execute(
                        "SELECT base_digest,image_digest FROM lesson_pages WHERE revision_id=?",
                        (revision["parent_id"],),
                    )
                }
                result["changes"] = {
                    "new": sum(p["base_digest"] not in parent for p in result["pages"]),
                    "annotated": sum(
                        p["base_digest"] in parent
                        and parent[p["base_digest"]] != p["image_digest"]
                        for p in result["pages"]
                    ),
                    "unchanged": sum(
                        parent.get(p["base_digest"]) == p["image_digest"]
                        for p in result["pages"]
                    ),
                }
            plan = conn.execute(
                "SELECT * FROM lesson_plans WHERE revision_id=?", (rid,)
            ).fetchone()
            if not plan:
                return result
            result["plan"] = json.loads(plan["payload"])
            result["plan_id"] = plan["id"]
            result["vocabulary"] = []
            for word in result["plan"]["vocabulary"]:
                matches = conn.execute(
                    "SELECT id FROM words WHERE lemma=?", (word["lemma"],)
                ).fetchall()
                result["vocabulary"].append(
                    {**word, "word_id": matches[0]["id"] if len(matches) == 1 else None}
                )
            for row in conn.execute(
                "SELECT * FROM lesson_tasks WHERE plan_id=? ORDER BY position",
                (plan["id"],),
            ):
                task = {
                    "id": row["id"],
                    "position": row["position"],
                    **json.loads(row["payload"]),
                }
                draft = conn.execute(
                    "SELECT * FROM lesson_drafts WHERE profile_id=? AND task_id=?",
                    (profile_id, row["id"]),
                ).fetchone()
                task["draft"] = dict(draft) if draft else {"answer": "", "revision": 0}
                attempts = [
                    dict(a)
                    for a in conn.execute(
                        "SELECT * FROM lesson_attempts WHERE profile_id=? AND task_id=? ORDER BY created_at,rowid",
                        (profile_id, row["id"]),
                    )
                ]
                for a in attempts:
                    a["feedback"] = json.loads(a["feedback"]) if a["feedback"] else None
                task["attempts"] = attempts
                task["checked"] = any(a["state"] == "checked" for a in attempts)
                result["tasks"].append(task)
            result["checked"] = sum(t["checked"] for t in result["tasks"])
            result["complete"] = bool(result["tasks"]) and result["checked"] == len(
                result["tasks"]
            )
            return result

    def task(self, task_id, lesson_id):
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT t.*,p.revision_id FROM lesson_tasks t JOIN lesson_plans p ON p.id=t.plan_id JOIN lesson_revisions r ON r.id=p.revision_id WHERE t.id=? AND r.lesson_id=?",
                (task_id, lesson_id),
            ).fetchone()
            if not row:
                raise LearningError("not_found", "This exercise was not found.", 404)
            return {**dict(row), "task": json.loads(row["payload"])}

    def save_draft(self, profile_id, lesson_id, task_id, answer, revision):
        task = self.task(task_id, lesson_id)
        if (
            not isinstance(answer, str)
            or len(answer) > 4000
            or type(revision) is not int
            or revision < 0
        ):
            raise LearningError(
                "lesson_input", "Keep your answer under 4,000 characters."
            )
        with transaction(self.db_path, write=True) as conn:
            row = conn.execute(
                "SELECT * FROM lesson_drafts WHERE profile_id=? AND task_id=?",
                (profile_id, task_id),
            ).fetchone()
            if row and row["answer"] == answer:
                return row["revision"]
            if (row["revision"] if row else 0) != revision:
                raise LearningError(
                    "lesson_conflict",
                    "A newer draft was saved in another tab. Copy your answer before reloading.",
                    409,
                )
            conn.execute(
                "INSERT INTO lesson_drafts VALUES (?,?,?,?,?) ON CONFLICT(profile_id,task_id) DO UPDATE SET answer=excluded.answer,revision=excluded.revision,updated_at=excluded.updated_at",
                (profile_id, task_id, answer, revision + 1, timestamp()),
            )
            first = conn.execute(
                "SELECT base_digest FROM lesson_pages WHERE revision_id=? AND number=1",
                (task["revision_id"],),
            ).fetchone()
            conn.execute(
                "INSERT INTO lesson_progress VALUES (?,?,?,1,?,?,?) ON CONFLICT(profile_id,lesson_id) DO UPDATE SET task_id=excluded.task_id,updated_at=excluded.updated_at",
                (
                    profile_id,
                    lesson_id,
                    task["revision_id"],
                    first["base_digest"] if first else None,
                    task_id,
                    timestamp(),
                ),
            )
            return revision + 1

    def bookmark(self, profile_id, lesson_id, revision_id, page, task_id=None):
        self.revision(revision_id, lesson_id)
        if task_id and self.task(task_id, lesson_id)["revision_id"] != revision_id:
            raise LearningError(
                "lesson_input", "This exercise belongs to another lesson version."
            )
        with transaction(self.db_path, write=True) as conn:
            p = conn.execute(
                "SELECT base_digest FROM lesson_pages WHERE revision_id=? AND number=?",
                (revision_id, page),
            ).fetchone()
            if not p:
                raise LearningError("lesson_input", "Choose a page from this lesson.")
            conn.execute(
                "INSERT INTO lesson_progress VALUES (?,?,?,?,?,?,?) ON CONFLICT(profile_id,lesson_id) DO UPDATE SET revision_id=excluded.revision_id,page=excluded.page,base_digest=excluded.base_digest,task_id=COALESCE(excluded.task_id,lesson_progress.task_id),updated_at=excluded.updated_at",
                (
                    profile_id,
                    lesson_id,
                    revision_id,
                    page,
                    p["base_digest"],
                    task_id,
                    timestamp(),
                ),
            )

    def assess(
        self, profile_id, lesson_id, task_id, answer, draft_revision, submission_key
    ):
        task = self.task(task_id, lesson_id)
        clean(answer, 4000, "answer")
        if not isinstance(submission_key, str) or not re.fullmatch(
            "[a-zA-Z0-9_-]{16,80}", submission_key
        ):
            raise LearningError("lesson_input", "Reload the exercise before checking.")
        with transaction(self.db_path, write=True) as conn:
            old = conn.execute(
                "SELECT * FROM lesson_attempts WHERE profile_id=? AND submission_key=?",
                (profile_id, submission_key),
            ).fetchone()
            if old and (old["answer"] != answer or old["task_id"] != task_id):
                raise LearningError(
                    "lesson_conflict",
                    "This submission has already been used for another answer.",
                    409,
                )
            if old and old["state"] == "checked":
                return json.loads(old["feedback"])
            if old and old["lease_until"] > timestamp():
                raise LearningError(
                    "lesson_busy",
                    "This answer is still being checked. Please wait.",
                    409,
                )
        self.save_draft(profile_id, lesson_id, task_id, answer, draft_revision)
        # Recheck the command inside a writer transaction after saving the draft.
        with transaction(self.db_path, write=True) as conn:
            old = conn.execute(
                "SELECT * FROM lesson_attempts WHERE profile_id=? AND submission_key=?",
                (profile_id, submission_key),
            ).fetchone()
            if old and (old["answer"] != answer or old["task_id"] != task_id):
                raise LearningError(
                    "lesson_conflict",
                    "This submission has already been used for another answer.",
                    409,
                )
            if old and old["state"] == "checked":
                return json.loads(old["feedback"])
            if old and old["lease_until"] > timestamp():
                raise LearningError(
                    "lesson_busy",
                    "This answer is still being checked. Please wait.",
                    409,
                )
            attempt_id = old["id"] if old else identifier()
            lease_until = timestamp() + 180
            conn.execute(
                "INSERT INTO lesson_attempts VALUES (?,?,?,?,?,'checking',NULL,?,?,?) ON CONFLICT(id) DO UPDATE SET state='checking',lease_until=excluded.lease_until",
                (
                    attempt_id,
                    profile_id,
                    task_id,
                    submission_key,
                    answer,
                    self.ai.model,
                    lease_until,
                    timestamp(),
                ),
            )
            previous = [
                r["answer"]
                for r in conn.execute(
                    "SELECT answer FROM lesson_attempts WHERE profile_id=? AND task_id=? AND state='checked' ORDER BY created_at DESC LIMIT 3",
                    (profile_id, task_id),
                )
            ]
        try:
            pages = self.evidence(task["revision_id"])
            page_ids = {e["page"] for e in task["task"]["evidence"]}
            result = self.ai.assess(
                task["task"],
                answer,
                [p for p in pages if p["page"] in page_ids],
                previous,
            )
        except Exception:
            with transaction(self.db_path, write=True) as conn:
                conn.execute(
                    "UPDATE lesson_attempts SET state='failed',lease_until=0 WHERE id=? AND lease_until=?",
                    (attempt_id, lease_until),
                )
            raise
        with transaction(self.db_path, write=True) as conn:
            # A lesson completes when every task in this saved plan has a
            # checked attempt. Rechecking an already completed plan is practice,
            # not another lesson completion.
            pending_sql = """SELECT COUNT(*) FROM lesson_tasks t WHERE t.plan_id=?
                AND NOT EXISTS (SELECT 1 FROM lesson_attempts a WHERE a.task_id=t.id
                    AND a.profile_id=? AND a.state='checked')"""
            pending_before = conn.execute(pending_sql, (task['plan_id'], profile_id)).fetchone()[0]
            if not conn.execute(
                "UPDATE lesson_attempts SET state='checked',feedback=?,lease_until=0 WHERE id=? AND lease_until=?",
                (encoded(result), attempt_id, lease_until),
            ).rowcount:
                raise LearningError(
                    "lesson_busy",
                    "This answer was resumed elsewhere. Reload to see its feedback.",
                    409,
                )
            if pending_before and conn.execute(pending_sql, (task['plan_id'], profile_id)).fetchone()[0] == 0:
                from services.progression import award
                title = conn.execute('SELECT title FROM lessons WHERE id=?', (lesson_id,)).fetchone()[0]
                award(conn, profile_id, activity='lessons', content_key=f'lesson:{task["revision_id"]}',
                      source_key=f'lesson-completion:{attempt_id}', title=title,
                      evidence={'lesson_id': lesson_id, 'revision_id': task['revision_id'],
                                'plan_id': task['plan_id'], 'completion': 'all_tasks_checked'})
        return result
