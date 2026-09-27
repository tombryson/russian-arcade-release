import json
import os
import sqlite3
import tempfile
import unittest

from tests.support import isolated_app
from repositories import SentenceRepository, StoryRepository


class RouteSmokeTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']

    def test_metrics_returns_dashboard_json(self):
        response = self.client.get("/metrics")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data["total_words"], int)
        self.assertIn("flashcard_total", data)
        self.assertIn("difficulty_distribution", data)
        self.assertIn("topic_distribution", data)

    def test_vocab_json_contract(self):
        response = self.client.get("/vocab", headers={"Accept": "application/json"})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("words", data)
        self.assertIsInstance(data["words"], list)
        self.assertEqual(data["source"], "db")
        self.assertIn("total_pages", data)

    def test_full_pages_use_single_shared_shell(self):
        self.client.set_cookie('ui_navigation', 'sidebar')
        with self.client.session_transaction() as session:
            session.pop('ui_navigation', None)
        for path, expected_page in [
            ("/tools/anki/", "flashcards"),
            ("/vocab", "vocab"),
            ("/comprehension", "comprehension"),
            ("/writing", "writing"),
            ("/lessons", "lessons"),
            ("/word_jumble", "word_jumble"),
            ("/sentences", "sentences"),
            ("/sentences/saved", "sentences_saved"),
        ]:
            with self.subTest(path=path):
                response = self.client.get(path)
                html = response.get_data(as_text=True)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(html.count("<!DOCTYPE html>"), 1)
                self.assertEqual(html.count('id="sidebar"'), 1)
                self.assertEqual(html.count('id="mainContent"'), 1)
                self.assertRegex(html, r'<main class="main-content(?: [^"]*)?" id="mainContent"')
                self.assertIn('/static/css/style.css?', html)
                self.assertEqual(html.count('/static/js/app_shell.js?'), 1)
                self.assertIn(f'data-page="{expected_page}"', html)

    def test_htmx_sidebar_navigation_returns_swappable_main_content(self):
        self.client.set_cookie('ui_navigation', 'sidebar')
        with self.client.session_transaction() as session:
            session.pop('ui_navigation', None)
        for path, expected_page in [
            ("/vocab", "vocab"),
            ("/tools/anki/", "flashcards"),
            ("/comprehension", "comprehension"),
            ("/writing", "writing"),
            ("/lessons", "lessons"),
            ("/word_jumble", "word_jumble"),
            ("/sentences", "sentences"),
        ]:
            with self.subTest(path=path):
                response = self.client.get(
                    path,
                    headers={
                        "HX-Request": "true",
                        "HX-Target": "mainContent",
                    },
                )
                html = response.get_data(as_text=True)

                self.assertEqual(response.status_code, 200)
                self.assertIn('id="mainContent"', html)
                self.assertRegex(html, r'<main class="main-content(?: [^"]*)?" id="mainContent"')
                self.assertIn(f'data-page="{expected_page}"', html)
                self.assertNotIn("<!DOCTYPE html>", html)
                self.assertNotIn('id="sidebar"', html)

    def test_missing_comprehension_story_returns_stable_error(self):
        response = self.client.get(
            "/comprehension/load/999999",
            headers={"HX-Request": "true"},
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 404)
        self.assertIn("История не найдена", html)

    def test_comprehension_controls_are_visible_in_shell_and_partial(self):
        for headers in [{}, {"HX-Request": "true", "HX-Target": "mainContent"}]:
            with self.subTest(headers=headers):
                response = self.client.get("/comprehension", headers=headers)
                html = response.get_data(as_text=True)

                self.assertEqual(response.status_code, 200)
                self.assertIn('id="new-story"', html)
                self.assertIn('id="saved-stories"', html)
                self.assertIn('id="comprehension-form"', html)
                self.assertIn('name="custom_story"', html)
                self.assertIn("Create Story", html)

    def test_system_ui_language_can_switch_between_english_and_russian(self):
        english = self.client.get("/comprehension").get_data(as_text=True)
        self.assertIn("Comprehension", english)
        self.assertIn("Create Story", english)
        self.assertIn('value="en"', english)
        self.assertIn('aria-pressed="true"', english)

        response = self.client.post(
            "/ui-language",
            data={"lang": "ru", "next": "/comprehension"},
            follow_redirects=True,
        )
        russian = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Понимание текста", russian)
        self.assertIn("Создать историю", russian)
        self.assertIn('value="ru"', russian)
        self.assertIn('aria-pressed="true"', russian)

        response = self.client.post(
            "/ui-language",
            data={"lang": "en", "next": "/comprehension"},
            follow_redirects=True,
        )
        english_again = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Comprehension", english_again)
        self.assertIn("Create Story", english_again)

    def test_sidebar_navigation_sequence_preserves_main_content_contract(self):
        self.client.set_cookie('ui_navigation', 'sidebar')
        with self.client.session_transaction() as session:
            session.pop('ui_navigation', None)
        sequence = [
            ("/tools/anki/", "flashcards", 0),
            ("/comprehension", "comprehension", 1),
            ("/vocab", "vocab", 0),
            ("/comprehension", "comprehension", 1),
        ]

        for index, (path, expected_page, expected_panels) in enumerate(sequence):
            headers = {}
            if index:
                headers = {"HX-Request": "true", "HX-Target": "mainContent"}

            with self.subTest(path=path, index=index):
                response = self.client.get(path, headers=headers)
                html = response.get_data(as_text=True)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(html.count('id="mainContent"'), 1)
                self.assertIn(f'data-page="{expected_page}"', html)
                self.assertEqual(html.count("comprehension-panel"), expected_panels)
                self.assertEqual(html.count('id="comprehension-form"'), expected_panels)
                self.assertNotIn("comprehension-controls", html)
                self.assertNotIn("rightSidebar", html)
                self.assertNotIn("debug-story-data", html)
                self.assertNotIn("debug-story-log", html)
                if index:
                    self.assertNotIn("<!DOCTYPE html>", html)
                    self.assertNotIn('id="sidebar"', html)

    def test_flashcard_form_controls_have_accessible_labels(self):
        response = self.client.get("/tools/anki/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for token in [
            'for="case-filter"',
            'id="case-filter"',
            'for="topics-filter"',
            'id="topics-filter"',
            'for="max_sentences"',
            'id="max_sentences"',
            'for="batch_size"',
            'id="batch_size"',
        ]:
            self.assertIn(token, html)

    def test_legacy_right_sidebar_hooks_are_removed(self):
        root = os.path.dirname(os.path.dirname(__file__))
        checked_files = [
            os.path.join(root, "static", "js", "app_shell.js"),
            os.path.join(root, "static", "css", "style.css"),
            os.path.join(root, "templates", "comprehension.html"),
        ]
        forbidden = [
            "rightSidebar",
            "rightSidebarToggle",
            "right-sidebar",
            "right-sidebar-hidden",
            "comprehension-controls",
            "data-page-artifact",
        ]

        for file_path in checked_files:
            with self.subTest(file_path=file_path):
                with open(file_path, encoding="utf-8") as source_file:
                    source = source_file.read()
                for token in forbidden:
                    self.assertNotIn(token, source)


class StoryRepositoryTests(unittest.TestCase):
    def test_load_story_decodes_json_fields(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE saved_stories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        topic TEXT,
                        difficulty TEXT,
                        text TEXT,
                        audio_url TEXT,
                        image_url TEXT,
                        questions TEXT,
                        answers TEXT,
                        feedback TEXT,
                        score REAL,
                        owner_profile_id TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO saved_stories
                        (title, topic, difficulty, text, audio_url, image_url, questions, answers, feedback, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "Story",
                        "family",
                        "beginner",
                        "Текст",
                        "",
                        "",
                        json.dumps(["Вопрос?"]),
                        json.dumps(["Ответ"]),
                        json.dumps(["Good"]),
                        8.0,
                    ),
                )

            story = StoryRepository(db_path).load(1)

            self.assertEqual(story["title"], "Story")
            self.assertEqual(story["questions"], ["Вопрос?"])
            self.assertEqual(story["answers"], ["Ответ"])
            self.assertEqual(story["feedback"], ["Good"])
            self.assertEqual(story["score"], 8.0)
        finally:
            os.unlink(db_path)


class SentenceRepositoryTests(unittest.TestCase):
    def test_load_sentence_returns_saved_sentence(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE sentences (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sentence TEXT,
                        english TEXT,
                        score INTEGER,
                        topic TEXT,
                        difficulty INTEGER,
                        audio_url TEXT,
                        created_at TEXT,
                        owner_profile_id TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO sentences
                        (sentence, english, score, topic, difficulty, audio_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("Привет!", "Hi!", 4, "greetings", 1, "/static/media/test.mp3", "2026-05-27"),
                )

            sentence = SentenceRepository(db_path).load(1)

            self.assertEqual(sentence["sentence"], "Привет!")
            self.assertEqual(sentence["english"], "Hi!")
            self.assertEqual(sentence["score"], 4)
            self.assertEqual(sentence["audio_url"], "/static/media/test.mp3")
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
