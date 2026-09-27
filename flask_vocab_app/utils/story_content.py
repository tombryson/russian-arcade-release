"""The content contract shared by generation, saving and title migrations."""


def validate_story_title(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A story title is required.")
    title = value.strip()
    if len(title) > 100 or any(char in title for char in "\r\n<>"):
        raise ValueError("Use a plain-text story title of at most 100 characters.")
    return title


def story_schema(include_text=True, *, reading_ids=None, topic_ids=None):
    properties = {
        "title": {"type": "string", "description": "A short, meaningful Russian title, not an excerpt or opening sentence."},
        "title_en": {"type": "string", "description": "A natural English version of the Russian title, naming the same subject or event."},
        "questions": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 5},
    }
    if reading_ids:
        properties['topic_id'] = {'type': 'string', 'enum': list(topic_ids)}
        focus_properties = {
            'question_index': {'type': 'integer', 'minimum': 0, 'maximum': 3},
            'requirement_id': {'type': 'string', 'enum': list(reading_ids)},
            'passage_excerpt': {'type': 'string', 'minLength': 1, 'maxLength': 4000},
            'expectation': {'type': 'string', 'minLength': 1, 'maxLength': 1000},
        }
        properties['reading_focus'] = {'type': 'array', 'minItems': 4, 'maxItems': 4, 'items': {
            'type': 'object', 'additionalProperties': False, 'properties': focus_properties,
            'required': list(focus_properties)}}
    if include_text:
        properties["text"] = {"type": "string", "description": "The complete Russian story, without its title."}
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def validate_story_content(data, include_text=True, *, reading_ids=None, topic_ids=None, passage=None):
    if not isinstance(data, dict):
        raise ValueError("Story generation returned an invalid object.")
    title = validate_story_title(data.get("title"))
    title_en = validate_story_title(data.get("title_en"))
    questions = data.get("questions")
    if not isinstance(questions, list) or len(questions) != 5:
        raise ValueError("A story needs five comprehension questions.")
    if not all(isinstance(question, str) and question.strip() for question in questions):
        raise ValueError("Comprehension questions must be non-empty text.")
    questions = [question.strip() for question in questions]
    if len(set(questions)) != 5:
        raise ValueError("Comprehension questions must be distinct.")
    result = {"title": title, "title_en": title_en, "questions": questions}
    if include_text:
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("A story needs its complete text.")
        result["text"] = text.strip()
    if reading_ids:
        if any(len(question) > 2000 or '\x00' in question for question in questions):
            raise ValueError('Comprehension questions must be bounded plain text.')
        source_text = result['text'] if include_text else passage
        if not isinstance(source_text, str) or len(source_text) > 100_000 or '\x00' in source_text:
            raise ValueError('The comprehension passage must be bounded plain text.')
        if set(data) != set(story_schema(include_text, reading_ids=reading_ids, topic_ids=topic_ids)['properties']):
            raise ValueError('Return only the requested story fields and reading focus.')
        validate_reading_focus(data, reading_ids, topic_ids, source_text)
        from copy import deepcopy
        result.update(topic_id=data['topic_id'], reading_focus=deepcopy(data['reading_focus']))
    return result


def validate_reading_focus(data, reading_ids, topic_ids, passage):
    """Require one grounded question focus for indexes 0–3, never reflection."""
    if not isinstance(data.get('topic_id'), str) or data['topic_id'] not in topic_ids:
        raise ValueError('The story needs its actual canonical topic.')
    focus = data.get('reading_focus')
    if not isinstance(focus, list) or len(focus) != 4 or not isinstance(passage, str):
        raise ValueError('The four passage questions need explicit reading focus.')
    seen = set()
    for item in focus:
        if not isinstance(item, dict) or set(item) != {'question_index', 'requirement_id', 'passage_excerpt', 'expectation'}:
            raise ValueError('Reading focus has missing or unsupported fields.')
        index, rid = item['question_index'], item['requirement_id']
        if type(index) is not int or not 0 <= index <= 3 or index in seen:
            raise ValueError('Map each of the first four questions once; reflection is not reading evidence.')
        if not isinstance(rid, str) or rid not in reading_ids:
            raise ValueError('Use a supplied reading requirement at the selected level.')
        excerpt, expectation = item['passage_excerpt'], item['expectation']
        if (not isinstance(excerpt, str) or not excerpt.strip() or len(excerpt) > 4000
                or '\x00' in excerpt or excerpt not in passage):
            raise ValueError('Reading focus must quote its supporting passage exactly.')
        if (not isinstance(expectation, str) or not expectation.strip() or len(expectation) > 1000 or '\x00' in expectation):
            raise ValueError('Reading focus needs a bounded expected meaning.')
        seen.add(index)
    return data
