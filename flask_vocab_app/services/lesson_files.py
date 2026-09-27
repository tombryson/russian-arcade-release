"""Portable lesson sources and annotated page renders. Originals are never edited."""
import hashlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import pdfplumber
from PIL import Image, ImageOps

from repositories.learning_repository import LearningError, timestamp, transaction


MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 40
LEGACY_ROOT = Path(__file__).resolve().parents[1] / "static/uploads"


def digest(data):
    return hashlib.sha256(data).hexdigest()


class LessonFiles:
    def __init__(self, db_path, upload_folder=None, renderer="pdftoppm", *, max_pages=MAX_PAGES):
        self.db_path = db_path
        self.root = Path(db_path).resolve().parent / "lesson-assets"
        self.upload_folder = Path(upload_folder or LEGACY_ROOT).resolve()
        self.renderer = renderer
        self.max_pages = min(MAX_PAGES, max(1, int(max_pages)))

    def path(self, key):
        if not re.fullmatch("[a-f0-9]{64}", key):
            raise LearningError("lesson_file", "This lesson file is unavailable.", 404)
        return self.root / key[:2] / key

    def put(self, data, media_type):
        if not data or len(data) > MAX_BYTES:
            raise LearningError("lesson_file", "Choose a file smaller than 25 MB.")
        key = digest(data)
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        with transaction(self.db_path, write=True) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO lesson_files VALUES (?,?,?,?)",
                (key, len(data), media_type, timestamp()),
            )
        return key

    @staticmethod
    def inspect(data, max_pages=MAX_PAGES):
        if not data or len(data) > MAX_BYTES:
            raise LearningError(
                "lesson_file", "Choose a PDF or image smaller than 25 MB."
            )
        try:
            if data.startswith(b"%PDF-"):
                with pdfplumber.open(io.BytesIO(data)) as pdf:
                    if not 1 <= len(pdf.pages) <= max_pages:
                        raise LearningError(
                            "lesson_file",
                            f"Choose up to {max_pages} pages for one lesson.",
                        )
                    return "application/pdf", len(pdf.pages)
            with Image.open(io.BytesIO(data)) as image:
                if (
                    image.format not in ("PNG", "JPEG", "WEBP")
                    or image.width * image.height > 16_000_000
                ):
                    raise ValueError()
                mime = Image.MIME[image.format]
                image.verify()
                return mime, 1
        except LearningError:
            raise
        except Exception:
            raise LearningError(
                "lesson_file",
                "This file could not be read. Choose an unlocked PDF, PNG, JPEG or WebP image.",
            ) from None

    def receive(self, data, filename):
        mime, count = self.inspect(data, self.max_pages)
        return {
            "digest": self.put(data, mime),
            "name": Path(filename).name[:200],
            "media_type": mime,
            "pages": count,
        }

    def legacy(self, reference):
        if not reference:
            raise LearningError(
                "lesson_file", "No source file was saved for this lesson.", 404
            )
        if reference.startswith("lesson-asset:"):
            path = self.path(reference.split(":", 1)[1])
            if path.is_file():
                return path
        supplied = Path(reference)
        roots = (self.upload_folder, LEGACY_ROOT.resolve())
        candidates = [supplied] if supplied.is_absolute() else []
        suffix = reference.split("static/uploads/", 1)[-1]
        candidates.extend(root / suffix for root in roots)
        for candidate in candidates:
            path = candidate.resolve()
            if any(path.is_relative_to(root) for root in roots) and path.is_file():
                return path
        raise LearningError(
            "lesson_file",
            "The original file is not available here. Upload it again to this lesson.",
            404,
        )

    def render(self, material):
        """Return annotated JPEG and base-page hashes, preserving annotations in the displayed image."""
        path = self.path(material["digest"])
        if material["media_type"] != "application/pdf":
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((1800, 1800))
                buffer = io.BytesIO()
                image.save(buffer, "JPEG", quality=92)
            data = buffer.getvalue()
            return [(data, digest(data))]
        binary = shutil.which(self.renderer)
        if not binary:
            raise LearningError(
                "lesson_renderer",
                "PDF page rendering needs Poppler (pdftoppm) installed on the server.",
                503,
            )
        with tempfile.TemporaryDirectory(prefix="lesson-render-") as temporary:
            root = Path(temporary)
            for prefix, extra in [("page", []), ("base", ["-hide-annotations"])]:
                command = [
                    binary,
                    "-scale-to",
                    "1800",
                    "-jpeg",
                    "-jpegopt",
                    "quality=92",
                    *extra,
                    str(path),
                    str(root / prefix),
                ]
                try:
                    result = subprocess.run(command, capture_output=True, timeout=120)
                except subprocess.TimeoutExpired:
                    raise LearningError(
                        "lesson_renderer",
                        "This PDF took too long to render. Try a smaller section.",
                        503,
                    ) from None
                if result.returncode:
                    raise LearningError(
                        "lesson_renderer",
                        "The PDF pages could not be rendered. The original is saved; try another PDF export.",
                        503,
                    )
            pages = sorted(root.glob("page-*.jpg"))
            bases = sorted(root.glob("base-*.jpg"))
            if len(pages) != material["pages"] or len(bases) != len(pages):
                raise LearningError(
                    "lesson_renderer",
                    "Some PDF pages are missing. Try another PDF export.",
                    503,
                )
            output = []
            for page, base in zip(pages, bases):
                with Image.open(page) as image:
                    image.verify()
                output.append((page.read_bytes(), digest(base.read_bytes())))
            return output
