"""Presentation fields for legacy stories; stored titles are never rewritten."""
import json
from services.curriculum import LEVELS, level_options
from utils.activity_display import topic_label


def present_story(story, language="ru"):
    title = (story.get("title") or "").strip()
    topic = (story.get("topic") or "").strip()
    level = (story.get("difficulty") or "").strip().lower()
    known_level = level in {"beginner", "intermediate", "advanced"}
    # Older generators appended these exact fields to the title, sometimes twice.
    suffix = f" ({topic}, {level})"
    if known_level and topic:
        while title.endswith(suffix):
            title = title[:-len(suffix)].rstrip()
    english_title = (story.get("title_en") or "").strip()
    use_english = language == "en" and bool(english_title)
    questions = story.get("questions") or []
    if isinstance(questions, str):
        try:
            questions = json.loads(questions)
        except (ValueError, TypeError):
            questions = None
    return {
        **story,
        "display_title": english_title if use_english else title,
        "display_title_lang": "en" if use_english else "ru",
        "display_topic": topic_label(topic, language) if topic.lower() not in {"", "any"} else "",
        "level_label": next((item["label"] for item in level_options(language) if item["value"] == level.upper()), "") if level.upper() in LEVELS else "",
        "level_key": f"comprehension.{level}" if known_level else "",
        "question_count": len(questions) if isinstance(questions, list) else None,
    }
