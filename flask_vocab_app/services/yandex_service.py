import requests
import logging
import pymorphy3
from .trial_provider import config_snapshot, yandex_call
from .ai_trial_budget import TrialDenied

logger = logging.getLogger(__name__)

class YandexService:
    def __init__(self, api_key, config=None):
        self.config = config_snapshot(config)
        self.api_key = api_key
        self.url = "https://translate.api.cloud.yandex.net/translate/v2/translate"
        self.morph = pymorphy3.MorphAnalyzer()

    def translate(self, text, target_lang="en"):
        """Translate text from Russian to target language (default: English)."""
        if not self.api_key:
            return {"translation": None, "error": "Yandex Cloud API key is missing."}
        try:
            response = yandex_call(self.config, text, target_lang, lambda: requests.post(
                self.url, headers={"Authorization": f"Api-Key {self.api_key}"},
                json={"texts": [text], "sourceLanguageCode": "ru" if target_lang != "ru" else "en",
                      "targetLanguageCode": target_lang}, timeout=20))
            response.raise_for_status()
            translation = response.json()["translations"][0]["text"]
            if not translation.strip():
                raise ValueError("Empty translation")
            return {"translation": translation}
        except TrialDenied:
            raise
        except Exception as exc:
            # Do not expose authenticated request details or manufacture a translation.
            logger.warning("Yandex translation failed (%s)", type(exc).__name__)
            return {"translation": None, "error": "Yandex translation failed. Check the Cloud API key and service access."}

    def translate_sentence(self, sentence, target_lang="en"):
        """Translate a full sentence using the translate method."""
        return self.translate(sentence, target_lang)

    def get_pos(self, word):
        """Get part of speech for a Russian word using pymorphy3."""
        try:
            parsed = self.morph.parse(word)[0]
            pos_tag = parsed.tag.POS
            pos_map = {
                'NOUN': 'noun',
                'VERB': 'verb',
                'INFN': 'verb',
                'ADJF': 'adjective',
                'ADJS': 'adjective',
                'PRTF': 'adjective',
                'PRTS': 'adjective',
                'ADVB': 'adverb',
                'NUMR': 'numeral',
                'NPRO': 'pronoun',
                'CONJ': 'conjunction',
                'COMP': 'comparative',
                'PRCL': 'particle',
                'PRED': 'predicative',
                'PREP': 'preposition'
            }
            pos = pos_map.get(pos_tag, 'unknown')
            logger.debug(f"POS for '{word}': {pos}")
            return pos
        except Exception as e:
            logger.error(f"POS tagging failed for '{word}': {str(e)}")
            return None
