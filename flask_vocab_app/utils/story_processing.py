from models.database import connect_db
import json
import logging
import re
import sqlite3
import unicodedata

import pymorphy3

logger = logging.getLogger(__name__)
_morph = None


def get_morph():
    global _morph
    if _morph is None:
        _morph = pymorphy3.MorphAnalyzer()
    return _morph


def process_story_words(story_text, db_path, drive_service, added_lemmas=None):
    # Russian compounds are one selectable surface: selecting only "повара"
    # from "шеф-повара" would lose its actual lemma and fail source validation.
    words = re.findall(r"[А-Яа-яЁё][А-Яа-яЁё\u0301]*(?:-[А-Яа-яЁё][А-Яа-яЁё\u0301]*)*|\w+|\s+|[^\w\s]", story_text, re.UNICODE)
    word_objs = []
    # A Drive capture can still be awaiting sync. Only SQLite entries count as
    # saved here, so the story's Add action can complete their lexical data.
    added_lemmas = set()
    try:
        with connect_db(db_path) as conn:
            added_lemmas = {row[0].lower() for row in conn.execute("SELECT lemma FROM words")}
    except sqlite3.Error:
        logger.exception("Could not read saved vocabulary for story highlighting")

    def sanitize(value):
        if value is None:
            return None
        value = unicodedata.normalize("NFKC", value)
        value = "".join(c for c in value if c.isprintable() and c not in '"\'\\')
        return value.encode("utf-8").decode("utf-8")

    for word in words:
        if not re.match(r"\w+", word, re.UNICODE):
            word_objs.append({"word": word, "lemma": None, "added": False})
            continue
        parsed = get_morph().parse(word.replace('\u0301', ''))[0]
        lemma = parsed.normal_form if parsed.normal_form else None
        word = sanitize(word)
        lemma = sanitize(lemma)
        added = lemma.lower() in added_lemmas if lemma else False
        word_obj = {"word": word, "lemma": lemma, "added": added}
        logger.debug("Word obj: %s", word_obj)
        word_objs.append(word_obj)

    try:
        json.dumps(word_objs, ensure_ascii=False)
    except ValueError as e:
        logger.error("JSON serialization error in word_objs: %s, raw_data: %s", str(e), word_objs[:5])
        word_objs = [{"word": "Error", "lemma": None, "added": False}]

    return word_objs
