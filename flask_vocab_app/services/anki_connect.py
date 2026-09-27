import requests
import json
import os
import logging

logger = logging.getLogger(__name__)

class AnkiConnect:
    def __init__(self, url='http://localhost:8765', default_deck='Default'):
        self.url = url
        self.default_deck = default_deck
        self.media_dir = None

    def set_media_dir(self, media_dir):
        self.media_dir = media_dir
        logger.debug(f"Set media_dir to {media_dir}")

    def add_note(self, note):
        deck_name = note.get('deckName', self.default_deck)
        payload = {
            "action": "addNote",
            "version": 6,
            "params": {
                "note": note
            }
        }
        try:
            logger.debug(f"Sending AnkiConnect request: {json.dumps(payload, ensure_ascii=False)}")
            response = requests.post(self.url, json=payload, timeout=15)
            response.raise_for_status()
            result = response.json()
            logger.debug(f"AnkiConnect response: {result}")
            return result
        except requests.RequestException as e:
            logger.error(f"AnkiConnect request failed: {str(e)}")
            return {"error": str(e), "result": None}