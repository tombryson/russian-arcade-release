"""Small presentation helpers shared by vocabulary-based activities."""
from datetime import datetime

from utils.i18n import translate_ui


def topic_label(topic, language='en'):
    key = 'topic.' + (topic or 'any')
    label = translate_ui(key, language)
    return (topic or '').replace('_', ' ').capitalize() if label == key else label


def readable_date(value, language='en'):
    try:
        date = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return ''
    months = ('янв фев мар апр май июн июл авг сен окт ноя дек' if language == 'ru'
              else 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec').split()
    return f'{date.day} {months[date.month - 1]} {date.year}'
