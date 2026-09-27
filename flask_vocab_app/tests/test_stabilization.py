import base64
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

from tests.support import isolated_app
from pathlib import Path

APP_ROOT = str(Path(__file__).resolve().parents[1])
from blueprints.comprehension import create_comprehension_blueprint
from blueprints.sentences import create_sentences_blueprint
from filters import register_filters
from services.word_jumble_service import WordJumbleService


class FakeDriveService:
    def download_vocab_list(self):
        return ""


class FakeComprehensionService:
    def __init__(self):
        self.image_calls = 0

    def get_topics(self):
        return []

    async def generate_story(self, topic, difficulty):
        return {"title": "Привет, мир!", "title_en": "Hello, World!", "text": "Привет мир.", "questions": ["Что случилось?"], "image_url": "/static/media/story.png"}

    def generate_image(self, story_text):
        self.image_calls += 1
        return "/static/media/fallback.png"

    def generate_audio(self, story_text):
        return "/static/media/story.mp3"


class FakeSentenceService:
    def __init__(self, sentence_id=101):
        self.sentence_id = sentence_id
        self.saved_payloads = []

    def assess_translation(self, sentence, english, user_response, language="en"):
        return {"score": 3, "strength": "Your meaning is clear.", "next_step": "Check the ending.", "example": "Привет!"}

    def generate_audio(self, sentence):
        return "/static/media/sentence.mp3"

    def save_sentence(self, **kwargs):
        self.saved_payloads.append(kwargs)
        return self.sentence_id


class FakeUserService:
    def __init__(self):
        self.update_calls = 0

    def update_user_stats(self, **kwargs):
        self.update_calls += 1
        return {"lingocoins_earned": 30, "elo_change": 8}


class FakeWritingService:
    def __init__(self):
        self.payload = None

    def assess_writing(self, **kwargs):
        self.payload = kwargs
        return {"score": 8, "strength": "Clear and relevant.", "next_step": "Add detail.", "example": "Моя мама дома."}


def make_db(tables):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    with sqlite3.connect(db_path) as conn:
        for statement in tables:
            conn.execute(statement)
    return db_path


class StabilizationTests(unittest.TestCase):
    def test_word_jumble_uses_lemma_difficulty_column(self):
        db_path = make_db([
            """
            CREATE TABLE words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lemma TEXT,
                topic TEXT,
                lemma_difficulty INTEGER
            )
            """,
            """
            INSERT INTO words (lemma, topic, lemma_difficulty)
            VALUES ('кофе', '["food"]', 1), ('чай', '["food"]', 2)
            """,
        ])
        try:
            service = WordJumbleService(db_path, openai_service=None, api_key="test-key")

            words = service.get_words("food", "easy", 2)

            self.assertEqual(set(words), {"кофе", "чай"})
        finally:
            os.unlink(db_path)

    def test_writing_assess_route_uses_existing_service(self):
        writing_service = FakeWritingService()
        app = isolated_app(self, {"WritingService": writing_service})
        from repositories.writing_repository import WritingRepository
        repository = WritingRepository(app.config['DB_PATH'])
        exercise_id = repository.create(dict(title='Моя семья',title_en='My family',task='Напишите о семье',
            task_en='Write about your family.',required_words=['мама','семья','дом']), 'family', 'beginner',30)
        client = app.test_client()
        csrf = client.get('/api/v1/user-session').json['csrf_token']
        response = client.post('/writing/assess', data={
            'exercise_id': exercise_id, 'revision':0, 'user_response':'Моя мама дома.',
        }, headers={'Accept':'application/json', 'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 200)
        self.assertIn('8/10', response.json['feedback'])
        self.assertEqual(writing_service.payload["response"], "Моя мама дома.")

    def test_comprehension_reuses_generated_story_image(self):
        service = FakeComprehensionService()
        app = isolated_app(self, {'ComprehensionService': service})
        client = app.test_client()
        csrf = client.get('/api/v1/user-session').json['csrf_token']
        response = client.post('/comprehension',
            data={'topic': 'any', 'difficulty': 'beginner', 'visibility': 'revealed'},
            headers={'HX-Request': 'true', 'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(service.image_calls, 0)
        self.assertIn('/static/media/story.png', response.get_data(as_text=True))

    def test_obsolete_client_supplied_grades_cannot_award_progress(self):
        service = FakeSentenceService()
        app = isolated_app(self, {'SentenceService': service})
        client = app.test_client()
        csrf = client.get('/api/v1/user-session').json['csrf_token']
        payload = {'sentence': 'Привет!', 'english': 'Hi!', 'user-response': 'Hi!',
                   'topic': 'greetings', 'difficulty': '5', 'score': '4'}
        for path in ['/sentence/assess', '/sentence/save']:
            response = client.post(path, data=payload, headers={'Accept': 'application/json', 'X-CSRF-Token': csrf})
            self.assertEqual(response.status_code, 404)
        with sqlite3.connect(app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM reward_events').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sentences').fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
