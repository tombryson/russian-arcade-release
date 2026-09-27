import re
import json
import logging
from typing import Dict, List, Optional
from .pos_case import get_pos_tag
from models.database import get_db
from utils.logging import setup_logging

logger = setup_logging()

def format_cloze(sentence, word_id, lemma, sentence_count, target_case=None, db_path=None):
    logger.info(f"Formatting cloze for lemma: {lemma}, word_id: {word_id}, sentence count: {sentence_count}, target_case: {target_case}")
    words = sentence.split()
    exact_form = None
    form_tags = None

    cursor = get_db(db_path).cursor()
    query = "SELECT form, tags FROM forms WHERE word_id = ?"
    params = [word_id]
    if target_case:
        query += " AND tags LIKE ?"
        params.append(f'%\"case\":\"{target_case}\"%')
    
    cursor.execute(query, params)
    valid_forms = {row['form']: json.loads(row['tags']) for row in cursor.fetchall()}
    
    clean_words = [re.sub(r'[^\w-]', '', w) for w in words]
    logger.debug(f"Cleaned sentence words: {clean_words}, Valid forms: {list(valid_forms.keys())}")
    
    for i, clean_w in enumerate(clean_words):
        clean_w_lower = clean_w.lower()
        for form, tags in valid_forms.items():
            if clean_w_lower == form.lower():
                if target_case and tags.get("case") == target_case:
                    exact_form = words[i]
                    form_tags = tags
                    break
                elif not target_case:
                    exact_form = words[i]
                    form_tags = tags
                    break
        if exact_form:
            break
    
    if exact_form:
        link = f'<a href="https://en.openrussian.org/ru/{lemma}" target="_blank">{{{{c1::{exact_form}}}}}</a>'
        cloze_sentence = sentence.replace(exact_form, link, 1)
        unique_suffix = f"<!-- cloze{sentence_count + 1} -->"
        cloze_sentence_with_unique = f"{cloze_sentence} {unique_suffix}"
        return cloze_sentence_with_unique, exact_form, form_tags
    else:
        logger.warning(f"No valid form of '{lemma}' found in sentence '{sentence}'{' matching case ' + target_case if target_case else ''}")
        return None, None, None

def format_anki_tags(tags: Dict, pos: str, difficulty: int, topic: Optional[List[str]] = None) -> List[str]:
    from utils.pos_case import get_pos_tag
    tag_list = [get_pos_tag(pos)]
    if tags:
        if 'case' in tags:
            tag_list.append(tags['case'].lower())
        if 'tense' in tags:
            tag_list.append(tags['tense'].lower())
        if 'mood' in tags:
            tag_list.append(tags['mood'].lower())
        if 'pos' in tags and tags['pos'] in ['conjunction', 'particle', 'preposition']:
            tag_list.append(tags['pos'])
    tag_list.append(f"difficulty_{difficulty}")
    if topic:
        tag_list.extend(t.lower().replace(' ', '_') for t in topic if t)
    return tag_list