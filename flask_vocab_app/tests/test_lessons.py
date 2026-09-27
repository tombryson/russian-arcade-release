"""Lesson continuity, original evidence and retry contracts; no provider network."""
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from tests.support import isolated_app
from repositories.learning_repository import LearningError, transaction, timestamp
from services.lesson_ai import LessonAI
from services.lesson_files import LessonFiles, digest
from services.lesson_service import LessonService
from services.learning_backup import backup_learning_store
from services.learning_assets import LocalAssetStore

TEXT = "Анна живёт в новых городах. Анна думает о своей семье."


def copy(text):
    return {"en": text, "ru": text}


def picture(colour="white"):
    out = io.BytesIO()
    Image.new("RGB", (160, 120), colour).save(out, "PNG")
    return out.getvalue()


def annotated_pdf(ink=True):
    # A small original PDF with real ink, not a screenshot substituted for annotations.
    stream = b"BT /F1 18 Tf 20 120 Td (Lesson) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 150] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R"
        + (b" /Annots [6 0 R]" if ink else b"")
        + b" >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Annot /Subtype /Ink /Rect [15 15 185 85] /InkList [[20 20 80 80 180 20]] /C [0 0 1] /BS << /W 4 >> >>",
    ]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    start = len(data)
    data += b"xref\n0 7\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return (
        data
        + b"trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n"
        + str(start).encode()
        + b"\n%%EOF"
    )


class FakeAI:
    model = "lesson-test"
    POLICY = "test-v1"

    def __init__(self):
        self.extract_calls = 0
        self.assess_calls = 0
        self.fail = False
        self.prepare_calls = 0

    def extract(self, images):
        self.extract_calls += 1
        return [
            {
                "text": TEXT + " " + TEXT,
                "annotations": "Blue ink: в новый городах (author unknown).",
                "uncertainty": "The arrow does not establish a grade.",
            }
            for _ in images
        ]

    def prepare(self, title, description, pages, words):
        self.prepare_calls += 1
        tasks = [
            {
                "objective": i // 2 + 1,
                "kind": "phrase",
                "instruction": copy("Use the plural."),
                "prompt": "Анна живёт в … (новый город).",
                "hint": copy("Check agreement."),
                "sample_answer": "Анна живёт в новых городах.",
                "rubric": copy("Accept valid equivalents."),
                "evidence": [{"page": 1, "quote": "Анна живёт в новых городах."}],
            }
            for i in range(6)
        ]
        return {
            "title": copy("A lesson"),
            "introduction": copy("Read and practise."),
            "preparation": copy("Remember location phrases."),
            "objectives": [
                copy("Describe places."),
                copy("Read for meaning."),
                copy("Identify the owner."),
            ],
            "tasks": tasks,
            "vocabulary": [
                {
                    "lemma": "новый",
                    "surface": "новых",
                    "context": "Анна живёт в новых городах.",
                    "meaning": copy("new"),
                    "page": 1,
                }
            ],
            "notes": copy(""),
        }

    def validate(self, plan, pages):
        return plan

    def assess(self, task, answer, pages, previous):
        self.assess_calls += 1
        self.received = (task, answer, pages, previous)
        if self.fail:
            raise LearningError("lesson_provider", "Unavailable", 503)
        return {
            "outcome": "correct",
            "feedback": copy("That works. <script>bad()</script>"),
            "corrections": [],
            "model_answer": task["sample_answer"],
        }


class LessonsTests(unittest.TestCase):
    def setUp(self):
        self.ai = FakeAI()
        self.app = isolated_app(self, {"LessonAI": self.ai})
        self.app.config["LESSON_BACKGROUND_ENABLED"] = False
        self.comp = self.app.extensions["learning"]["lessons"]
        self.db = self.app.config["DB_PATH"]
        self.client = self.app.test_client()
        self.client.get("/lessons")
        self.profile = "personal-learning"

    def lesson(self, data=None):
        material = self.comp.files.receive(data or picture(), "notes.png")
        lid, rid, _ = self.comp.create(
            "Tutor lesson", "Prepositional phrases", [material]
        )
        return lid, rid, material

    def ready(self):
        lid, rid, m = self.lesson()
        self.comp.process(rid)
        self.assertEqual(self.comp.revision(rid)["state"], "ready")
        return lid, rid, self.comp.snapshot(lid, self.profile)["tasks"][0]

    def test_duplicate_upload_and_revision_keep_lesson_identity(self):
        lid, rid, m = self.lesson()
        self.assertEqual(
            self.comp.create("Different filename/title", "", [m]), (lid, rid, True)
        )
        self.assertEqual(self.comp.revise(lid, [m]), rid)
        changed = self.comp.files.receive(picture("red"), "more-notes.png")
        next_id = self.comp.revise(lid, [changed])
        self.assertNotEqual(next_id, rid)
        row = self.comp.revision(next_id)
        self.assertEqual((row["parent_id"], row["number"]), (rid, 2))
        self.assertEqual(self.comp.files.path(m["digest"]).read_bytes(), picture())
        self.assertEqual(self.comp.adopt_legacy(lid), next_id)

    def test_preparation_retains_annotations_and_validates_source(self):
        lid, rid, task = self.ready()
        page = self.comp.evidence(rid)[0]
        self.assertIn("в новый городах", page["annotations"])
        self.assertEqual(page["text"], TEXT + " " + TEXT)
        self.assertEqual(len(self.comp.snapshot(lid, self.profile)["tasks"]), 6)
        self.comp.process(rid)
        self.assertEqual(self.ai.prepare_calls, 1)
        plan = self.ai.prepare("", "", [], [])
        plan["tasks"][0]["evidence"][0]["quote"] = "Not in the source"
        with self.assertRaises(LearningError):
            self.comp.validate_plan(plan, [{"page": 1, "text": TEXT}])

    def test_failed_preparation_reuses_extracted_pages(self):
        lid, rid, _ = self.lesson()
        with patch.object(
            self.ai, "validate", side_effect=LearningError("bad", "Retry")
        ):
            self.comp.process(rid)
        self.assertEqual(self.comp.revision(rid)["state"], "failed")
        self.comp.process(rid)
        self.assertEqual(self.comp.revision(rid)["state"], "ready")
        self.assertEqual(self.ai.extract_calls, 1)

    def test_expired_preparation_can_resume_without_duplicate_tasks(self):
        lid, rid, _ = self.lesson()
        with transaction(self.db, write=True) as conn:
            conn.execute(
                "UPDATE lesson_revisions SET state='processing',lease_until=?,lease_token='gone' WHERE id=?",
                (timestamp() + 30, rid),
            )
        self.comp.process(rid)
        self.assertEqual(self.ai.extract_calls, 0)
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE lesson_revisions SET lease_until=0 WHERE id=?", (rid,))
        html = self.client.get(f"/lessons/load/{lid}").get_data(as_text=True)
        self.assertNotIn("data-lesson-poll=", html)
        self.assertIn("Retry preparation", html)
        self.comp.process(rid)
        self.assertEqual(self.comp.revision(rid)["state"], "ready")

    def test_unknown_view_falls_back_to_lesson_overview(self):
        lid, rid, task = self.ready()
        html = self.client.get(f"/lessons/load/{lid}?view=unknown").get_data(
            as_text=True
        )
        self.assertIn("What you’ll practise", html)

    def test_draft_conflicts_and_profile_isolation(self):
        lid, rid, task = self.ready()
        tid = task["id"]
        self.assertEqual(
            self.comp.save_draft(self.profile, lid, tid, "Мой ответ", 0), 1
        )
        with self.assertRaises(LearningError) as context:
            self.comp.save_draft(self.profile, lid, tid, "Stale", 0)
        self.assertEqual(context.exception.status, 409)
        with transaction(self.db, write=True) as conn:
            conn.execute(
                "INSERT INTO learning_profiles VALUES ('other','Other','cat','UTC',0,NULL,?)",
                (timestamp(),),
            )
        self.assertEqual(
            self.comp.snapshot(lid, "other")["tasks"][0]["draft"]["answer"], ""
        )
        self.assertEqual(
            self.comp.snapshot(lid, self.profile)["progress"]["task_id"], tid
        )

    def test_answer_is_saved_before_provider_failure_and_retry_is_idempotent(self):
        lid, rid, task = self.ready()
        self.ai.fail = True
        answer = "Анна живёт в новых городах."
        with self.assertRaises(LearningError):
            self.comp.assess(
                self.profile, lid, task["id"], answer, 0, "submission-00000001"
            )
        self.assertEqual(
            self.comp.snapshot(lid, self.profile)["tasks"][0]["draft"]["answer"], answer
        )
        self.ai.fail = False
        a = self.comp.assess(
            self.profile, lid, task["id"], answer, 0, "submission-00000001"
        )
        self.assertEqual(
            self.comp.assess(
                self.profile, lid, task["id"], answer, 0, "submission-00000001"
            ),
            a,
        )
        self.assertEqual(self.ai.assess_calls, 2)
        self.assertEqual(self.ai.received[2][0]["text"], TEXT + " " + TEXT)
        self.assertEqual(
            len(self.comp.snapshot(lid, self.profile)["tasks"][0]["attempts"]), 1
        )
        with self.assertRaises(LearningError):
            self.comp.assess(
                self.profile, lid, task["id"], "Changed", 1, "submission-00000001"
            )

    def test_marking_endpoint_escapes_feedback_and_hides_sample_before_attempt(self):
        lid, rid, task = self.ready()
        url = f"/lessons/load/{lid}?view=practice"
        html = self.client.get(url).get_data(as_text=True)
        self.assertNotIn("One possible answer", html)
        self.assertIn("Show a hint", html)
        self.assertNotIn('<details class="lesson-hint" open', html)
        r = self.client.post(
            f"/lessons/{lid}/check",
            data={
                "task_id": task["id"],
                "answer": "Мой ответ",
                "draft_revision": 0,
                "submission_key": "submission-00000001",
            },
            headers={"Accept": "application/json", "X-CSRF-Token": self.token()},
        )
        self.assertEqual(r.status_code, 200)
        html = self.client.get(r.json["url"]).get_data(as_text=True)
        self.assertNotIn("<script>bad()", html)
        self.assertIn("&lt;script&gt;bad()", html)
        self.assertIn("Next exercise", html)
        self.client.post("/ui-language", data={"lang": "ru", "next": url}, headers={"X-CSRF-Token": self.token()})
        self.assertIn("Ваш ответ", self.client.get(url).get_data(as_text=True))

    def token(self):
        with self.client.session_transaction() as s:
            return s["household_csrf"]

    def test_endpoints_reject_cross_lesson_task_and_revision(self):
        lid, rid, task = self.ready()
        m = self.comp.files.receive(picture("blue"), "another.png")
        other, other_rid, _ = self.comp.create("Other", "", [m])
        with self.assertRaises(LearningError):
            self.comp.task(task["id"], other)
        self.assertEqual(
            self.client.get(f"/lessons/{other}/page/{rid}/1").status_code, 404
        )
        self.assertEqual(
            self.client.get(f"/lessons/{other}/source/0?revision={rid}").status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/lessons/{lid}/draft",
                data={"task_id": task["id"], "answer": "x", "draft_revision": 0},
            ).status_code,
            403,
        )

    def test_bookmark_follows_reordered_page_and_prior_answers_survive(self):
        a = self.comp.files.receive(picture("white"), "a.png")
        b = self.comp.files.receive(picture("blue"), "b.png")
        lid, rid, _ = self.comp.create("Two pages", "", [a, b])
        self.comp.process(rid)
        task = self.comp.snapshot(lid, self.profile)["tasks"][0]
        self.comp.assess(
            self.profile, lid, task["id"], "My response", 0, "submission-00000001"
        )
        self.comp.bookmark(self.profile, lid, rid, 2, task["id"])
        changed = self.comp.revise(lid, [b, a])
        self.comp.process(changed)
        state = self.comp.snapshot(lid, self.profile)
        self.assertEqual(state["progress"]["page"], 1)
        self.assertEqual(state["changes"]["unchanged"], 2)
        self.assertEqual(state["checked"], 0)
        old = self.comp.snapshot(lid, self.profile, rid)
        self.assertEqual(old["checked"], 1)
        self.assertEqual(old["tasks"][0]["attempts"][0]["answer"], "My response")
        self.assertEqual(self.ai.extract_calls, 1)

    def test_legacy_schema_is_read_without_modifying_original_json(self):
        raw = json.dumps(
            [
                {"question": "Вопрос?", "answer": "Ответ"},
                {"id": "prompt_1", "prompt": "Two"},
                {"id": "prompt_1", "prompt": "Three"},
            ]
        )
        with transaction(self.db, write=True) as conn:
            conn.execute(
                "INSERT INTO lessons(id,title,prompts,created_at) VALUES ('old','Old',?,'2025-01-01')",
                (raw,),
            )
        legacy = self.app.extensions["services"]["LessonService"]
        lesson = legacy.get_lesson("old")
        self.assertEqual(len({p["id"] for p in lesson["prompts"]}), 3)
        self.assertEqual(lesson["prompts"][0]["prompt"], "Вопрос?")
        self.assertEqual(lesson["prompts"][0]["reference_answer"], "Ответ")
        with transaction(self.db) as conn:
            self.assertEqual(
                conn.execute("SELECT prompts FROM lessons WHERE id='old'").fetchone()[
                    0
                ],
                raw,
            )
        self.assertIn(
            "Вопрос?", self.client.get("/lessons/load/old").get_data(as_text=True)
        )

    def test_legacy_file_routes_and_backup_restore_are_portable(self):
        root = Path(self.app.config["UPLOAD_FOLDER"])
        (root / "pdfs").mkdir(parents=True, exist_ok=True)
        path = root / "pdfs/old.pdf"
        data = annotated_pdf()
        path.write_bytes(data)
        with transaction(self.db, write=True) as conn:
            conn.execute(
                "INSERT INTO lessons(id,title,pdf_path,created_at) VALUES ('old','Old',?,'2025-01-01')",
                (str(path),),
            )
        response = self.client.get("/lessons/old/source/0")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, data)
        response.close()
        self.ready()
        destination = root.parent / "backup"
        manifest = backup_learning_store(
            self.db,
            LocalAssetStore(self.app.config["WORD_POST_ASSET_DIR"]),
            destination,
            str(root),
        )
        self.assertGreater(len(manifest["lesson_files"]), 1)
        with sqlite3.connect(destination / "vocab.db") as conn:
            reference = conn.execute(
                "SELECT pdf_path FROM lessons WHERE id='old'"
            ).fetchone()[0]
        path.unlink()
        self.assertEqual(
            LessonFiles(str(destination / "vocab.db")).legacy(reference).read_bytes(),
            data,
        )
        with transaction(self.db) as conn:
            self.assertEqual(
                conn.execute("SELECT pdf_path FROM lessons WHERE id='old'").fetchone()[
                    0
                ],
                str(path),
            )

    def test_invalid_file_does_not_create_lesson(self):
        with self.assertRaises(LearningError):
            self.comp.files.receive(b"Not a pdf", "file.pdf")
        with self.assertRaises(LearningError):
            self.comp.files.legacy("/etc/passwd")
        with self.assertRaises(LearningError):
            self.comp.files.legacy("../../../../etc/passwd")

    @unittest.skipUnless(
        shutil.which("pdftoppm"), "Poppler required for PDF rendering test"
    )
    def test_real_pdf_ink_is_visible_and_does_not_change_base_page_identity(self):
        annotated = self.comp.files.receive(annotated_pdf(), "notes.pdf")
        plain = self.comp.files.receive(annotated_pdf(False), "plain.pdf")
        a = self.comp.files.render(annotated)[0]
        b = self.comp.files.render(plain)[0]
        self.assertNotEqual(digest(a[0]), digest(b[0]))
        self.assertEqual(a[1], b[1])
        image = Image.open(io.BytesIO(a[0])).convert("RGB")
        blue = sum(
            1 for r, g, b in image.getdata() if b > 120 and b > r * 1.5 and b > g * 1.5
        )
        self.assertGreater(blue, 100)

    def test_model_correction_must_quote_the_actual_answer(self):
        ai = LessonAI({"OPENAI_API_KEY": "fake"})
        bad = {
            "outcome": "revise",
            "feedback": copy("Change it"),
            "model_answer": "x",
            "corrections": [
                {"original": "invented", "replacement": "x", "why": copy("wrong")}
            ],
        }
        with patch.object(ai, "_call", return_value=bad):
            with self.assertRaises(LearningError):
                ai.assess({}, "Original response", [], [])

    def test_empty_extraction_cannot_generate_questions(self):
        lid, rid, _ = self.lesson()
        with patch.object(
            self.ai,
            "extract",
            return_value=[{"text": "", "annotations": "", "uncertainty": "Unreadable"}],
        ):
            self.comp.process(rid)
        self.assertEqual(self.comp.revision(rid)["state"], "failed")
        self.assertEqual(self.ai.prepare_calls, 0)

    def test_no_new_coins_or_card_schedule_changes_from_upload_or_practice(self):
        with transaction(self.db) as conn:
            before = list(conn.execute("SELECT * FROM learner_card_state"))
            coins = conn.execute(
                "SELECT COUNT(*) FROM learning_reward_entries"
            ).fetchone()[0]
        self.ready()
        with transaction(self.db) as conn:
            self.assertEqual(
                list(conn.execute("SELECT * FROM learner_card_state")), before
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM learning_reward_entries").fetchone()[
                    0
                ],
                coins,
            )
