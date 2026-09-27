"""One activity menu for the Flask pages and native activity workspace."""
from utils.i18n import translate_ui

NAVIGATION_LAYOUTS = frozenset({'top', 'sidebar'})
NAVIGATION_COOKIE = 'ui_navigation'


def normalize_navigation_layout(value):
    """A browser preference, independent of the selected learning profile."""
    return value if isinstance(value, str) and value in NAVIGATION_LAYOUTS else 'top'


def browser_navigation_layout():
    """Keep appearance after the shorter learning session expires."""
    from flask import request, session

    saved = session.get('ui_navigation')
    if isinstance(saved, str) and saved in NAVIGATION_LAYOUTS:
        return saved
    return normalize_navigation_layout(request.cookies.get(NAVIGATION_COOKIE))


def activity_navigation(language="en"):
    def link(page, href, key, boost=True):
        return {"page": page, "href": href, "label": translate_ui(key, language), "boost": boost}

    def labelled(page, href, english, russian, boost=True):
        return {"page": page, "href": href, "label": russian if language == 'ru' else english, "boost": boost}

    return {
        "title": translate_ui("nav.activity_tools", language),
        "more": translate_ui("nav.more_tools", language),
        "main": [
            link("home", "/#home", "nav.home", False),
            labelled("activities", "/#activities", "All activities", "Все занятия", False),
            link("vocab", "/vocab", "nav.my_words"),
        ],
        "activities": [
            link("native_flashcards", "/#flashcards", "nav.flashcards", False),
            link("comprehension", "/comprehension", "nav.comprehension"),
            labelled("speaking", "/#speaking", "Speaking", "Разговорная практика", False),
            link("writing", "/writing", "nav.writing"),
            link("lessons", "/lessons", "nav.lessons"),
            link("word_jumble", "/word_jumble", "nav.word_jumble"),
            link("sentences", "/sentences", "nav.sentences"),
            labelled("curriculum", "/curriculum", "Curriculum", "Учебная программа", False),
        ],
        "tools": [
            link("flashcards", "/tools/anki/", "nav.anki_tools"),
            link("sentences_saved", "/sentences/saved", "sentences.saved_title", False),
        ],
    }
