from .trial_provider import config_snapshot, openai_client
from .ai_trial_budget import TrialDenied
from config import model_for
from contextlib import closing
from collections import Counter
from pathlib import Path
import unicodedata
from utils.lazy import LazyService
from models.database import connect_db
import sqlite3
import pymorphy3
from wordfreq import word_frequency
import math
import json
import re
import logging
import time
from openai import OpenAI
from services.google_drive_service import GoogleDriveService
from services.vocabulary_topics import TOPICS
from services.form_selection import canonical_tags
from config import OPENAI_API_KEY, OPENAI_MODEL_HIGH, OPENAI_MODEL_FAST
from datetime import datetime

logger = logging.getLogger('SyncService')


def _form_tags(tag):
    """Keep the dictionary reading, including full/short and verbal distinctions."""
    tags = {'pos': tag.POS}
    for name in ('case', 'number', 'gender', 'animacy', 'tense', 'aspect', 'mood',
                 'person', 'voice', 'transitivity', 'involvement'):
        value = getattr(tag, name, None)
        if value:
            tags[name] = value
    if tag.POS == 'COMP':
        tags['degree'] = 'comp'
    elif 'Supr' in tag:
        tags['degree'] = 'Supr'
    return tags


class VocabularyEnrichmentUnavailable(RuntimeError):
    """The account needs attention before any more enrichment calls can work."""


def _account_failure(error):
    body = getattr(error, 'body', {})
    if not isinstance(body, dict):
        body = {}
    if isinstance(body.get('error'), dict):
        body = body['error']
    codes = {getattr(error, 'code', None), body.get('code'), body.get('type')}
    if codes & {'insufficient_quota', 'credit_balance_exhausted', 'billing_hard_limit_reached'}:
        return "Vocabulary enrichment is pending: the AI account has no available credit."
    if getattr(error, 'status_code', None) in (401, 403):
        return "Vocabulary enrichment is pending: check the AI account credentials and permissions."
    return None

class SyncService:
    def __init__(self, db_path, drive_service=None, api_key=None, config=None):
        self.db_path = db_path
        self.drive_service = drive_service if drive_service is not None else GoogleDriveService()
        self.morph = pymorphy3.MorphAnalyzer()
        self.api_key = OPENAI_API_KEY if api_key is None else api_key
        self.config = config_snapshot(config)
        self.openai_client = LazyService("OpenAI sync client", lambda: openai_client(config=self.config, factory=OpenAI, api_key=self.api_key, timeout=60.0, max_retries=0))
        self.TOPICS = list(TOPICS)

    def is_valid_russian_word(self, word):
        logger.debug(f"Validating word: {word}")
        if not word or len(word) < 2:
            return False, "Word is too short"
        if not re.match(r'^[А-Яа-яЁё-]+$', word):
            return False, "Contains non-Cyrillic characters"
        try:
            parsed = self.morph.parse(word)[0]
            if not parsed.tag.POS:
                return False, "No valid POS tag"
            return True, ""
        except TrialDenied:
            raise
        except Exception as e:
            logger.error(f"Validation error for '{word}': {str(e)}")
            return False, f"Parse error: {str(e)}"

    def get_lemma(self, word, conn, cursor):
        logger.debug(f"Getting lemma for: {word}")
        cursor.execute("""
            SELECT w.lemma, w.pos
            FROM forms f
            JOIN words w ON f.word_id = w.id
            WHERE f.form = ?
        """, (word,))
        result = cursor.fetchone()
        if result:
            logger.debug(f"Found lemma in DB: {result[0]} ({result[1]})")
            return result[0], result[1], f"Form of '{result[0]}' ({result[1]})"
        
        parses = self.morph.parse(word)
        pos_map = {
            'NOUN': 'NOUN', 'VERB': 'VERB', 'INFN': 'VERB', 'GRND': 'VERB', 'ADJF': 'ADJ', 'ADJS': 'ADJ',
            'PRTF': 'ADJ', 'PRTS': 'ADJ', 'ADVB': 'ADVB', 'NUMR': 'NUMR', 'NPRO': 'NPRO',
            'CONJ': 'CONJ', 'COMP': 'COMP', 'PRCL': 'PART', 'PRED': 'PRED', 'PREP': 'PREP'
        }
        for parse in parses:
            pos_tag = parse.tag.POS
            logger.debug(f"Parse for '{word}': POS={pos_tag}, Score={parse.score}, Normal Form={parse.normal_form}")
            if not pos_tag:
                continue
            lemma = parse.normal_form
            # Handle participles (e.g., газированный)
            if pos_tag == 'PRTF' and lemma.endswith(('ать', 'еть', 'ить')):
                verb_parse = self.morph.parse(lemma)[0]
                if verb_parse.tag.POS == 'INFN':
                    pos = 'VERB'
                    logger.debug(f"Corrected participle '{word}' to lemma '{lemma}' (VERB)")
                    return lemma, pos, f"Normalized to lemma '{lemma}' (VERB)"
            pos = pos_map.get(pos_tag, pos_tag)
            if parse.normal_form:
                logger.debug(f"Normalized to lemma: {lemma} ({pos})")
                return lemma, pos, f"Normalized to lemma '{lemma}'"
        pos = pos_map.get(parses[0].tag.POS, parses[0].tag.POS) if parses else 'ADJ'
        logger.debug(f"No lemma change: {word} ({pos})")
        return word, pos, ""

    def process_word(self, lemma, conn, cursor, *, parsed=None, word_id=None):
        """Import a lemma, or add missing lexical data to an explicit reading.

        A supplied dictionary parse keeps a context-verified reading instead of
        reranking homographs. Supplying a word ID backfills that row in place;
        existing forms, counts, enrichment and nonzero difficulty are retained.
        The caller owns the transaction, including any rollback on failure.
        """
        logger.debug(f"Processing word: {lemma}")
        try:
            explicit = parsed is not None or word_id is not None
            existing_word = None
            if word_id is not None:
                existing_word = cursor.execute(
                    'SELECT id, lemma, pos, lemma_difficulty FROM words WHERE id=?', (word_id,)
                ).fetchone()
                if not existing_word or self.normalize_capture(existing_word[1]) != self.normalize_capture(lemma):
                    logger.warning('Cannot backfill a missing or mismatched vocabulary ID')
                    return False
            if not explicit:
                if cursor.execute("SELECT 1 FROM words WHERE lemma = ?", (lemma,)).fetchone():
                    return True
                cursor.execute("""
                    SELECT w.lemma, w.pos
                    FROM forms f
                    JOIN words w ON f.word_id = w.id
                    WHERE f.form = ?
                """, (lemma,))
                existing_form = cursor.fetchone()
                if existing_form:
                    logger.info(f"Skipping '{lemma}' as it is a form of lemma '{existing_form[0]}' ({existing_form[1]})")
                    return True

            pos_map = {
                'NOUN': 'NOUN', 'VERB': 'VERB', 'INFN': 'VERB', 'GRND': 'VERB', 'ADJF': 'ADJ', 'ADJS': 'ADJ',
                'PRTF': 'ADJ', 'PRTS': 'ADJ', 'ADVB': 'ADVB', 'NUMR': 'NUMR', 'NPRO': 'NPRO',
                'CONJ': 'CONJ', 'COMP': 'COMP', 'PRCL': 'PART', 'PRED': 'PRED', 'PREP': 'PREP'
            }

            def matching_pos(tag_pos):
                if not existing_word:
                    return True
                stored_pos = str(existing_word[2]).upper()
                # Contextual captures historically use PART for participles and
                # PRCL for particles; preserve those stored labels as well.
                return (stored_pos in {tag_pos, pos_map.get(tag_pos, tag_pos)}
                        or (stored_pos == 'PART' and tag_pos in ('PRTF', 'PRTS')))

            if parsed is not None:
                if (not parsed.tag.POS or not parsed.is_known
                        or self.normalize_capture(parsed.normal_form) != self.normalize_capture(lemma)
                        or not matching_pos(parsed.tag.POS)):
                    logger.warning('The supplied dictionary reading does not match the vocabulary entry')
                    return False
                parses = [parsed]
            else:
                parses = self.morph.parse(lemma)

            scored_parses = []
            for parse in parses:
                pos = parse.tag.POS
                logger.debug(f"Parse for '{lemma}': POS={pos}, Score={parse.score}, Normal Form={parse.normal_form}")
                if not pos or (explicit and (not matching_pos(pos)
                        or self.normalize_capture(parse.normal_form) != self.normalize_capture(lemma))):
                    continue
                freq = word_frequency(parse.normal_form, 'ru')
                score = parse.score + (freq * 1e6 if freq > 0 else 0)
                scored_parses.append((parse, pos, score))

            if not scored_parses:
                logger.warning(f"No valid parses for '{lemma}'")
                return False

            scored_parses.sort(key=lambda x: x[2], reverse=True)
            parsed, pos_tag, score = scored_parses[0]
            pos = pos_map.get(pos_tag, pos_tag)
            logger.debug(f"Selected POS: {pos}, Score: {score}")

            if explicit:
                if existing_word is None:
                    existing_word = cursor.execute(
                        'SELECT id, lemma, pos, lemma_difficulty FROM words WHERE lemma=? AND pos=?', (lemma, pos)
                    ).fetchone()
                if existing_word:
                    word_id, pos = existing_word[0], existing_word[2]
            else:
                cursor.execute("SELECT id, pos FROM words WHERE lemma = ?", (lemma,))
                existing = cursor.fetchall()
                if existing:
                    existing_pos = [row[1] for row in existing]
                    if pos in existing_pos:
                        logger.info(f"Skipping duplicate lemma '{lemma}' with POS '{pos}'")
                        return True
                    # Another reading of this spelling is a separate entry.
                    # Never relabel a saved word or delete forms linked to cards.

            forms = set()
            form_counts = Counter()
            valid_noun_cases = {'nomn', 'gent', 'datv', 'accs', 'ablt', 'loct'}
            valid_adj_cases = {'nomn', 'gent', 'datv', 'accs', 'ablt', 'loct'}
            max_noun_forms = 12
            max_adj_forms = 24
            freq_threshold = 6e-7
            participle_freq_threshold = 2e-6

            for form in parsed.lexeme:
                if not form.word or not form.tag.POS:
                    continue
                try:
                    freq = word_frequency(form.word, 'ru')
                    if form.tag.POS in ('PRTF', 'PRTS') and freq < participle_freq_threshold:
                        continue
                    if form.tag.POS in ('VERB', 'INFN') and freq == 0:
                        continue
                    if form.tag.POS in ('ADJF', 'ADJS', 'COMP') and freq == 0:
                        continue
                    if form.tag.POS in ('ADJF', 'ADJS') and 'Supr' in form.tag and freq < 1e-7:
                        continue
                    if form.tag.POS == "NOUN":
                        if form.tag.case not in valid_noun_cases or form.tag.number not in {'sing', 'plur'} or freq < freq_threshold:
                            continue
                        if form.tag.gender == 'neut' and form.word.endswith('ь') and form.word != lemma:
                            continue
                    elif form.tag.POS == 'ADJF':
                        if form.tag.case not in valid_adj_cases:
                            continue
                    # Short adjectives/participles have no case. Keep their
                    # actual POS and agreement instead of inventing a case.
                    tags = _form_tags(form.tag)
                    candidate = (form.word, canonical_tags(tags))
                    limit = {'NOUN': max_noun_forms, 'ADJF': max_adj_forms}.get(form.tag.POS)
                    if candidate in forms or (limit is not None and form_counts[form.tag.POS] >= limit):
                        continue
                    forms.add(candidate)
                    form_counts[form.tag.POS] += 1
                    # Continue through the lexeme: its short/comparative forms
                    # can follow the capped full-adjective forms.
                except AttributeError:
                    continue

            freq = word_frequency(lemma, 'ru')
            rarity = 5 if freq == 0 else max(1, min(5, round(5 - math.log10(freq * 1e6))))
            rarity_component = (rarity / 5) * 2.5
            length_component = min(2.5, len(lemma) / 4)
            lemma_difficulty = max(1, min(5, round(rarity_component + length_component)))
            current_date = datetime.now().strftime("%Y-%m-%d")

            logger.debug(f"Generated forms: {[f[0] for f in forms]}")
            try:
                if explicit and existing_word:
                    if existing_word[3] is None or existing_word[3] == 0:
                        cursor.execute('UPDATE words SET lemma_difficulty=? WHERE id=?', (lemma_difficulty, word_id))
                    else:
                        lemma_difficulty = existing_word[3]
                else:
                    cursor.execute(
                        "INSERT OR IGNORE INTO words (lemma, pos, count, lemma_difficulty, date_added) VALUES (?, ?, ?, ?, ?)",
                        (lemma, pos, 0, lemma_difficulty, current_date)
                    )
                    cursor.execute("SELECT id FROM words WHERE lemma = ? AND pos = ?", (lemma, pos))
                    inserted_word = cursor.fetchone()
                    if not inserted_word:
                        logger.error(f"Failed to insert or find '{lemma}' with POS '{pos}'")
                        return False
                    word_id = inserted_word[0]

                existing_forms = {}
                if explicit:
                    for form_id, surface, stored_tags, difficulty in cursor.execute(
                            'SELECT id, form, tags, form_difficulty FROM forms WHERE word_id=?', (word_id,)).fetchall():
                        try:
                            decoded = json.loads(stored_tags)
                            signature = (surface, canonical_tags(decoded))
                        except (TypeError, ValueError):
                            continue
                        existing_forms.setdefault(signature, []).append((form_id, difficulty))

                # Insert forms with form_difficulty
                for form, tags_json in sorted(forms):
                    tags = json.loads(tags_json)
                    modifier = 0
                    if tags.get('pos') in ('PRTF', 'PRTS', 'GRND'):
                        modifier += 2
                    if 'plur' in tags.get('number', ''):  # Plural declensions
                        modifier += 1
                    form_difficulty = min(8, lemma_difficulty + modifier)  # Cap at 8
                    logger.debug(f"Form '{form}' (POS: {tags.get('pos', '')}, Tags: {tags}): Lemma {lemma_difficulty}, Modifier {modifier}, Form {form_difficulty}")
                    stored = existing_forms.get((form, tags_json), [])
                    # Older complete readings may lack only the newly explicit
                    # POS field. Reuse their IDs without rewriting their tags.
                    # Missing case/gender/etc. does not qualify as equivalence.
                    if explicit and not stored:
                        legacy_tags = {name: value for name, value in tags.items() if name != 'pos'}
                        stored = existing_forms.get((form, canonical_tags(legacy_tags)), [])
                    if explicit and stored:
                        for form_id, difficulty in stored:
                            if difficulty is None or difficulty == 0:
                                cursor.execute('UPDATE forms SET form_difficulty=? WHERE id=?', (form_difficulty, form_id))
                        continue
                    try:
                        cursor.execute(
                            "INSERT INTO forms (word_id, form, count, tags, form_difficulty) VALUES (?, ?, ?, ?, ?)",
                            (word_id, form, 0, tags_json, form_difficulty)
                        )
                    except sqlite3.IntegrityError as e:
                        logger.warning(f"Skipping duplicate form '{form}' for lemma '{lemma}': {str(e)}")
                        if explicit or not cursor.execute(
                                'SELECT 1 FROM forms WHERE word_id=? AND form=? AND tags=?',
                                (word_id, form, tags_json)).fetchone():
                            raise
                        # A retry must not overwrite a stored reading's score,
                        # or all syncretic readings sharing this spelling.
                logger.info(f"Processed lemma '{lemma}' with POS '{pos}', {len(forms)} forms")
                return True
            except sqlite3.Error as e:
                logger.error(f"Database error for '{lemma}': {str(e)}")
                return False
        except TrialDenied:
            raise
        except Exception as e:
            logger.error(f"Failed to process '{lemma}': {str(e)}")
            return False

    def assign_mnemonics(self, words):
        logger.debug(f"Assigning mnemonics to {len(words)} words")
        word_list = "\n".join([f"- {word['lemma']} (part of speech: {word['pos']})" for word in words])
        prompt = (
            f"You are a Russian language learning expert. Create a short, memorable English mnemonic for each Russian word below "
            f"to help learners recall the word by linking its pronunciation to its meaning. "
            f"The mnemonic must be a concise phrase (max 7 words) that: "
            f"1. Includes the Russian word or a close phonetic approximation (e.g., 'Go-lad' for 'голод'). "
            f"2. Uses shocking, silly or cartoonish imagery to stick in your memory. (e.g., a shopping card for 'карточка'). "
            f"3. Matches the part of speech (verbs for actions, nouns for objects, adjectives for descriptions). "
            f"4. Avoids generic or abstract phrases. "
            f"Return only a JSON object with each word as a key and a mnemonic string as the value, e.g:\n"
            "{\n"
            "  \"голод\": \"Go-lad, you're hungry!\",\n"
            "  \"карточка\": \"Kartochka saves 10% off!\"\n"
            "}\n"
            "Do not include extra text or markdown outside the JSON object.\n\n"
            "Words:\n" + word_list
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.debug(f"Mnemonic assignment attempt {attempt + 1}/{max_retries}")
                response = self.openai_client.chat.completions.create(
                    model=self.config.get("OPENAI_MODEL_HIGH") or model_for("OPENAI_MODEL_HIGH"),
                    messages=[
                        {"role": "system", "content": "You are a precise mnemonic generator."},
                        {"role": "user", "content": prompt}
                    ],

                    max_completion_tokens=4096, reasoning_effort="low"
                )

                raw_content = response.choices[0].message.content.strip()
                # Strip markdown code blocks
                if raw_content.startswith('```json'):
                    raw_content = raw_content[7:].rstrip('```').strip()
                elif raw_content.startswith('```'):
                    raw_content = raw_content[3:].rstrip('```').strip()
                logger.debug(f"Cleaned mnemonic response: {raw_content}")

                result = json.loads(raw_content)
                if not isinstance(result, dict):
                    logger.warning(f"Invalid mnemonic response format, not a dict: {raw_content}")
                    continue
                # Validate response includes all words
                if set(word['lemma'] for word in words) != set(result.keys()):
                    logger.warning(f"Mnemonic response missing lemmas: {raw_content}")
                    continue
                valid_result = {}
                for lemma, mnemonic in result.items():
                    if isinstance(mnemonic, str) and mnemonic.strip() and len(mnemonic.split()) <= 7:
                        valid_result[lemma] = mnemonic
                    else:
                        logger.warning(f"Invalid mnemonic for '{lemma}': {mnemonic} (length: {len(mnemonic.split()) if isinstance(mnemonic, str) else 'N/A'})")
                if valid_result:
                    logger.info(f"Assigned mnemonics to {len(valid_result)} words")
                    return valid_result
                logger.warning("No valid mnemonics assigned, retrying")

            except TrialDenied:
                raise
            except Exception as e:
                account_failure = _account_failure(e)
                if account_failure:
                    raise VocabularyEnrichmentUnavailable(account_failure) from e
                logger.error(f"Mnemonic assignment error on attempt {attempt + 1}: {str(e)}, raw response: {raw_content if 'raw_content' in locals() else 'N/A'}")
                time.sleep(2 ** attempt)  # Exponential backoff

        logger.error("All mnemonic assignment attempts failed")
        return {}

    @staticmethod
    def _missing_topics(value):
        """Legacy empty and fallback labels must remain eligible for enrichment."""
        try:
            topics = json.loads(value) if isinstance(value, str) else value
        except (TypeError, ValueError):
            return True
        return not (isinstance(topics, list) and any(topic in TOPICS for topic in topics))

    @staticmethod
    def _missing_mnemonic(value, lemma):
        return (not isinstance(value, str) or not value.strip()
                or value.strip() == f"Recall {lemma} phonetically.")

    def enrich_words(self, word_ids=None, *, batch_size=20):
        """Complete saved vocabulary through the importer's AI enrichment.

        Call after the capture transaction commits. Provider calls run without a
        database connection; each short write transaction rechecks the row so
        edits made while generation runs are not overwritten. Missing values
        stay missing on failure and can be retried by selecting the same IDs.
        Existing topics, mnemonics, forms and history are retained.
        """
        if not isinstance(batch_size, int) or not 1 <= batch_size <= 100:
            raise ValueError("Enrich between 1 and 100 words per batch.")
        if word_ids is not None:
            word_ids = list(dict.fromkeys(word_ids))
            if any(type(word_id) is not int or word_id <= 0 for word_id in word_ids):
                raise ValueError("Vocabulary IDs must be positive integers.")
        result = {"updated": [], "completed": [], "pending": [], "warnings": []}
        if word_ids == []:
            return result
        with connect_db(self.db_path) as conn:
            query = 'SELECT id,lemma,pos,topic,mnemonic FROM words'
            args = []
            if word_ids is not None:
                query += ' WHERE id IN (' + ','.join('?' for _ in word_ids) + ')'
                args = word_ids
            rows = [dict(zip(('id', 'lemma', 'pos', 'topic', 'mnemonic'), row))
                    for row in conn.execute(query + ' ORDER BY id', args)]
        incomplete = []
        for word in rows:
            if (self._missing_topics(word['topic'])
                    or self._missing_mnemonic(word['mnemonic'], word['lemma'])):
                incomplete.append(word)
            else:
                result['completed'].append(word['id'])
        if not self.api_key:
            result['pending'] = [word['id'] for word in incomplete]
            return result

        # Provider output is keyed by lemma. Separate homographs with different
        # readings instead of asking a JSON object to represent duplicate keys.
        batches = []
        for word in incomplete:
            if (not batches or len(batches[-1]) >= batch_size
                    or any(other['lemma'] == word['lemma'] for other in batches[-1])):
                batches.append([])
            batches[-1].append(word)
        for batch_index, batch in enumerate(batches):
            halted = False
            topic_words = [word for word in batch if self._missing_topics(word['topic'])]
            mnemonic_words = [word for word in batch
                              if self._missing_mnemonic(word['mnemonic'], word['lemma'])]
            topics, mnemonics = {}, {}
            for kind, words, assign in (
                    ('topics', topic_words, self.assign_topics),
                    ('mnemonics', mnemonic_words, self.assign_mnemonics)):
                if not words:
                    continue
                try:
                    assigned = assign(words)
                    if isinstance(assigned, dict):
                        if kind == 'topics':
                            topics = assigned
                        else:
                            mnemonics = assigned
                except TrialDenied:
                    raise
                except VocabularyEnrichmentUnavailable as error:
                    result['warnings'].append(str(error))
                    halted = True
                    break
                except Exception:
                    logger.exception('Vocabulary %s enrichment failed', kind)
                    result['warnings'].append(f"Some {kind} could not be generated. Retry enrichment.")
            with connect_db(self.db_path) as conn:
                conn.execute('BEGIN IMMEDIATE')
                for word in batch:
                    current = conn.execute('SELECT lemma,pos,topic,mnemonic FROM words WHERE id=?',
                                           (word['id'],)).fetchone()
                    if not current or current[:2] != (word['lemma'], word['pos']):
                        result['pending'].append(word['id'])
                        continue
                    topic_value, mnemonic = current[2:]
                    updates = {}
                    candidate_topics = topics.get(word['lemma'])
                    if (self._missing_topics(topic_value) and isinstance(candidate_topics, list)
                            and 1 <= len(candidate_topics) <= 2
                            and all(topic in TOPICS for topic in candidate_topics)):
                        topic_value = json.dumps(list(dict.fromkeys(candidate_topics)))
                        updates['topic'] = topic_value
                    candidate_mnemonic = mnemonics.get(word['lemma'])
                    if (self._missing_mnemonic(mnemonic, word['lemma'])
                            and isinstance(candidate_mnemonic, str)
                            and not self._missing_mnemonic(candidate_mnemonic, word['lemma'])
                            and len(candidate_mnemonic.split()) <= 7):
                        mnemonic = candidate_mnemonic.strip()
                        updates['mnemonic'] = mnemonic
                    if updates:
                        conn.execute('UPDATE words SET ' + ','.join(f'{key}=?' for key in updates)
                                     + ' WHERE id=?', [*updates.values(), word['id']])
                        result['updated'].append(word['id'])
                    complete = (not self._missing_topics(topic_value)
                                and not self._missing_mnemonic(mnemonic, word['lemma']))
                    result['completed' if complete else 'pending'].append(word['id'])
            if halted:
                result['pending'].extend(word['id'] for remaining in batches[batch_index + 1:]
                                         for word in remaining)
                break
        return result

    def preview_sync(self, cloud_only):
        logger.debug(f"Previewing sync for {len(cloud_only)} cloud-only words")
        try:
            with connect_db(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT lemma, pos FROM words")
                db_lemmas = {(row[0], row[1]) for row in cursor.fetchall()}
                cursor.execute("SELECT form FROM forms")
                db_forms = {row[0] for row in cursor.fetchall()}
                preview = {"to_add": [], "rejected": []}
                seen_lemmas = set()

                for word in cloud_only:
                    is_valid, reason = self.is_valid_russian_word(word)
                    if not is_valid:
                        logger.debug(f"Rejected '{word}': {reason}")
                        preview["rejected"].append({"word": word, "reason": reason})
                        continue

                    if word in db_forms:
                        logger.debug(f"Rejected '{word}': Already a form in database")
                        preview["rejected"].append({"word": word, "reason": "Already a form in database"})
                        continue

                    lemma, pos, lemma_reason = self.get_lemma(word, conn, cursor)
                    logger.debug(f"Word '{word}' → lemma '{lemma}', POS '{pos}'")

                    lemma_pos = (lemma, pos)
                    if lemma_pos in seen_lemmas:
                        logger.debug(f"Duplicate lemma '{lemma}' ({pos})")
                        preview["rejected"].append({"word": word, "reason": f"Duplicate lemma '{lemma}' ({pos})"})
                        continue

                    if lemma_pos in db_lemmas:
                        logger.debug(f"Lemma '{lemma}' ({pos}) already in DB")
                        preview["rejected"].append({"word": word, "reason": f"Lemma '{lemma}' ({pos}) already in database"})
                        continue

                    seen_lemmas.add(lemma_pos)
                    preview["to_add"].append({
                        "word": word,
                        "lemma": lemma,
                        "pos": pos,
                        "reason": lemma_reason
                    })

            logger.info(f"Preview: {len(preview['to_add'])} to add, {len(preview['rejected'])} rejected")
            return preview, None
        except TrialDenied:
            raise
        except Exception as e:
            logger.error(f"Preview sync error: {str(e)}")
            return {"to_add": [], "rejected": []}, str(e)

    def sanitize_vocab_list(self):
        logger.debug("Sanitizing vocab_list.txt")
        try:
            conn = connect_db(self.db_path)
            cursor = conn.cursor()
            cloud_content = self.drive_service.download_vocab_list(force_refresh=True, allow_stale=False)
            cloud_words = sorted(set(w.strip() for w in cloud_content.split() if w.strip()))
            logger.debug(f"Cloud words: {cloud_words}")

            sanitization = {"to_remove": []}
            to_keep = []
            seen_lemmas = set()
            pos_map = {
                'NOUN': 'NOUN', 'VERB': 'VERB', 'INFN': 'VERB', 'GRND': 'VERB', 'ADJF': 'ADJ', 'ADJS': 'ADJ',
                'PRTF': 'ADJ', 'PRTS': 'ADJ', 'ADVB': 'ADVB', 'NUMR': 'NUMR', 'NPRO': 'NPRO',
                'CONJ': 'CONJ', 'COMP': 'COMP', 'PRCL': 'PART', 'PRED': 'PRED', 'PREP': 'PREP'
            }

            for word in cloud_words:
                is_valid, reason = self.is_valid_russian_word(word)
                if not is_valid:
                    sanitization["to_remove"].append({"word": word, "reason": reason})
                    continue

                if word == 'газированный':
                    logger.debug(f"Parsing 'газированный': {[(p.normal_form, p.tag.POS, p.score) for p in self.morph.parse(word)]}")

                cursor.execute("SELECT lemma, pos FROM words WHERE lemma = ?", (word,))
                lemma_in_db = cursor.fetchone()
                if lemma_in_db:
                    lemma, pos = lemma_in_db
                    lemma_pos = (lemma, pos)
                    if lemma_pos in seen_lemmas:
                        sanitization["to_remove"].append({
                            "word": word,
                            "reason": f"Duplicate lemma '{lemma}' ({pos})"
                        })
                        continue
                    seen_lemmas.add(lemma_pos)
                    to_keep.append({"word": word, "lemma": lemma, "pos": pos})
                    logger.debug(f"Keeping '{word}' as lemma '{lemma}' ({pos}) from DB")
                    continue

                cursor.execute("""
                    SELECT w.lemma, w.pos
                    FROM forms f
                    JOIN words w ON f.word_id = w.id
                    WHERE f.form = ? AND w.lemma != ?
                """, (word, word))
                existing_form = cursor.fetchone()
                if existing_form:
                    sanitization["to_remove"].append({
                        "word": word,
                        "reason": f"Non-lemma form of '{existing_form[0]}' ({existing_form[1]})"
                    })
                    continue

                if word == 'счастье' or word == 'счастие':
                    lemma, pos = 'счастье', 'NOUN'
                    lemma_pos = (lemma, pos)
                    if lemma_pos in seen_lemmas:
                        sanitization["to_remove"].append({
                            "word": word,
                            "reason": f"Duplicate lemma '{lemma}' ({pos})"
                        })
                        continue
                    seen_lemmas.add(lemma_pos)
                    to_keep.append({"word": word, "lemma": lemma, "pos": pos})
                    logger.debug(f"Hardcoding '{word}' as lemma 'счастье' (NOUN)")
                    continue

                parses = self.morph.parse(word)
                valid_parses = []
                for parse in parses:
                    pos_tag = parse.tag.POS
                    if not pos_tag or parse.score < 0.1:
                        continue
                    lemma = parse.normal_form
                    freq = word_frequency(lemma, 'ru')
                    score = parse.score + (freq * 1e6 if freq > 0 else 0)
                    if pos_tag == 'NOUN' and parse.tag.number == 'sing' and parse.tag.case == 'nomn':
                        score += 0.5
                    valid_parses.append((parse, pos_tag, score, lemma))

                if not valid_parses:
                    sanitization["to_remove"].append({"word": word, "reason": "No valid parses"})
                    continue

                lemma_pos_candidates = {}
                for parse, pos_tag, score, lemma in sorted(valid_parses, key=lambda x: x[2], reverse=True):
                    pos = pos_map.get(pos_tag, 'ADJ')
                    if pos_tag == 'PRTF' and lemma.endswith(('ать', 'еть', 'ить')):
                        verb_parse = self.morph.parse(lemma)[0]
                        if verb_parse.tag.POS == 'INFN':
                            pos = 'VERB'
                            logger.debug(f"Corrected participle '{word}' to lemma '{lemma}' (VERB)")
                    if pos_tag == 'ADJS':
                        adj_parses = [p for p in self.morph.parse(word) if p.tag.POS == 'ADJF']
                        if adj_parses and adj_parses[0].normal_form != word:
                            lemma = adj_parses[0].normal_form
                            pos = 'ADJ'
                    if pos_tag == 'NOUN' and parse.tag.number == 'plur' and word == lemma:
                        singular_parses = [p for p in parses if p.tag.POS == 'NOUN' and p.tag.number == 'sing']
                        if not singular_parses:
                            pos = 'NOUN'
                    lemma_pos = (lemma, pos)
                    if lemma_pos not in lemma_pos_candidates:
                        lemma_pos_candidates[lemma_pos] = (parse, pos_tag, score, lemma)

                for (lemma, pos), (parse, pos_tag, score, lemma) in lemma_pos_candidates.items():
                    if pos == 'NOUN' and word_frequency(lemma, 'ru') < 1e-8:
                        sanitization["to_remove"].append({
                            "word": word,
                            "reason": f"Invalid lemma '{lemma}' ({pos}, low frequency)"
                        })
                        continue

                    lemma_pos_key = (lemma, pos)
                    if lemma_pos_key in seen_lemmas:
                        sanitization["to_remove"].append({
                            "word": word,
                            "reason": f"Duplicate lemma '{lemma}' ({pos})"
                        })
                        continue

                    if word != lemma and pos_tag not in ('ADVB', 'ADJF', 'ADJS'):
                        sanitization["to_remove"].append({
                            "word": word,
                            "reason": f"Non-lemma form, variant of '{lemma}' ({pos})"
                        })
                        if lemma_pos_key not in seen_lemmas:
                            seen_lemmas.add(lemma_pos_key)
                            to_keep.append({
                                "word": lemma,
                                "lemma": lemma,
                                "pos": pos
                            })
                        continue

                    seen_lemmas.add(lemma_pos_key)
                    to_keep.append({
                        "word": word,
                        "lemma": lemma,
                        "pos": pos
                    })
                    logger.debug(f"Keeping '{word}' as lemma '{lemma}' ({pos}), score={score}")

            conn.close()
            logger.debug(f"To keep: {to_keep}")
            logger.info(f"Sanitization: {len(sanitization['to_remove'])} to remove, {len(to_keep)} to keep")
            return sanitization, to_keep, None
        except TrialDenied:
            raise
        except Exception as e:
            logger.error(f"Sanitize vocab error: {str(e)}")
            return {"to_remove": []}, [], str(e)

    def apply_sanitization(self, to_keep):
        logger.debug("Applying sanitization")
        try:
            content = "\n".join(entry["word"] for entry in to_keep)
            self.drive_service.update_vocab_list(content)
            logger.info("Sanitization applied to vocab_list.txt")
            return None
        except TrialDenied:
            raise
        except Exception as e:
            logger.error(f"Apply sanitization error: {str(e)}")
            return str(e)

    def assign_topics(self, words):
        logger.debug(f"Assigning topics to {len(words)} words")
        word_list = "\n".join([f"- {word['lemma']} ({word['pos']})" for word in words])
        prompt = (
            f"You are a Russian language expert. Assign 1-2 topics to each Russian word below "
            f"from this exact list only:\n\n{', '.join(self.TOPICS)}\n\n"
            f"Use only the topics listed above, verbatim, without synonyms or related terms"
            f"For pronouns, prepositions, conjunctions, and adverbs, prioritize 'grammar' unless a specific thematic topic applies "
            "(e.g., 'привет' to 'greetings'). For nouns, verbs, and adjectives, assign thematic topics based on natural contexts for language learning, "
            "e.g., 'гулять' (VERB) to 'daily_activities', 'красивый' (ADJ) to 'colors' or 'feelings'. "
            "Return only a JSON object with each word as a key and a topic array as the value, e.g:\n"
            "{\n  \"песок\": [\"places\"],\n  \"море\": [\"places\", \"nature\"],\n  \"что\": [\"grammar\"]\n}\n"
            "Do not include extra text or explanations.\n\n"
            "For each word, select the most relevant topics based on its part of speech and meaning. "
            "Return a JSON object mapping each word to its topics, e.g., "
            f"{{\"песок\": [\"places\", \"nature\"], \"что\": [\"grammar\"]}}.\n\n"
            f"Words:\n{word_list}"
        )

        max_retries = 2
        for attempt in range(max_retries):
            try:
                logger.debug(f"Topic assignment attempt {attempt + 1}/{max_retries}")
                response = self.openai_client.chat.completions.create(
                    model=self.config.get("OPENAI_MODEL_FAST") or model_for("OPENAI_MODEL_FAST"),
                    messages=[
                        {"role": "system", "content": "You are a precise topic classifier."},
                        {"role": "user", "content": prompt}
                    ],

                    max_completion_tokens=4096, reasoning_effort="low"
                )

                raw_content = response.choices[0].message.content
                logger.debug(f"Raw response content: {raw_content}")

                # Strip Markdown code block
                cleaned_content = re.sub(r'^```json\n|\n```$', '', raw_content.strip())
                logger.debug(f"Cleaned content: {cleaned_content}")

                result = json.loads(cleaned_content)
                logger.debug(f"Parsed JSON result: {result}")

                valid_result = {}
                for lemma, topics in result.items():
                    if isinstance(topics, list) and all(t in self.TOPICS for t in topics) and 1 <= len(topics) <= 2:
                        valid_result[lemma] = topics
                    else:
                        logger.warning(f"Invalid topics for '{lemma}': {topics}")
                if valid_result:
                    logger.info(f"Assigned topics to {len(valid_result)} words")
                    return valid_result
                logger.warning("No valid topics assigned, retrying")

            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error on attempt {attempt + 1}: {str(e)}")
                logger.error(f"Raw content: {raw_content}")
            except TrialDenied:
                raise
            except Exception as e:
                account_failure = _account_failure(e)
                if account_failure:
                    raise VocabularyEnrichmentUnavailable(account_failure) from e
                logger.error(f"OpenAI error on attempt {attempt + 1}: {str(e)}")
            
            if attempt < max_retries - 1:
                time.sleep(1)  # 1s delay before retry

        logger.error("All topic assignment attempts failed")
        return {}

    @staticmethod
    def normalize_capture(word):
        return unicodedata.normalize("NFC", word.strip()).lower()

    def compare_vocab(self):
        """Read latest captures without changing schema, files, or learning data."""
        try:
            cloud_content = self.drive_service.download_vocab_list(force_refresh=True, allow_stale=False)
            cloud_words = {self.normalize_capture(w) for w in cloud_content.split() if w.strip()}
            with connect_db(self.db_path) as conn:
                db_words = {row[0] for row in conn.execute('SELECT DISTINCT lemma FROM words')}
            return sorted(db_words - cloud_words), sorted(cloud_words - db_words), None
        except TrialDenied:
            raise
        except Exception as error:
            logger.exception("Could not compare vocabulary")
            return [], [], str(error)

    def sync_vocab(self, captures):
        """Import selected Drive captures, then enrich and export without holding a DB lock.

        Drive captures and structured vocabulary are complementary stores. Absence
        from Drive never deletes a SQLite word or its learning history.
        """
        if not isinstance(captures, list) or any(not isinstance(w, str) or not w.strip() for w in captures):
            raise ValueError("Select a list of non-empty words to sync.")
        if len(captures) > 500:
            raise ValueError("Sync at most 500 captures at a time.")
        captures = sorted({self.normalize_capture(w) for w in captures})
        cloud = self.drive_service.download_vocab_list(force_refresh=True, allow_stale=False)
        current = {self.normalize_capture(w) for w in cloud.split() if w.strip()}
        missing = set(captures) - current
        if missing:
            raise ValueError("Drive changed since preview. Refresh the preview before syncing: " + ", ".join(sorted(missing)))
        preview, error = self.preview_sync(captures)
        if error:
            raise ValueError(error)
        result = {"imported": [], "skipped": preview["rejected"], "failed": [],
                  "enrichment_pending": [], "exported": [], "warnings": []}
        # Back up immediately before importing, never merely for opening a preview.
        backup_path = str(self.db_path) + '_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.bak'
        with closing(connect_db(self.db_path)) as source, closing(sqlite3.connect(backup_path)) as target:
            source.backup(target)
        with connect_db(self.db_path) as conn:
            cursor = conn.execute("INSERT INTO sync_runs(status, summary) VALUES ('running', '{}')")
            run_id = cursor.lastrowid
        result["run_id"] = run_id
        result["backup_path"] = backup_path
        import_committed = False
        try:
            with connect_db(self.db_path) as conn:
                conn.execute('BEGIN IMMEDIATE')
                cursor = conn.cursor()
                for entry in preview["to_add"]:
                    lemma = entry["lemma"]
                    if cursor.execute('SELECT 1 FROM words WHERE lemma = ?', (lemma,)).fetchone():
                        result["skipped"].append({"word": entry["word"], "reason": "Already imported"})
                        continue
                    conn.execute('SAVEPOINT import_word')
                    if self.process_word(lemma, conn, cursor):
                        conn.execute('RELEASE import_word')
                        if cursor.execute('SELECT 1 FROM words WHERE lemma = ?', (lemma,)).fetchone():
                            result["imported"].append(lemma)
                        else:
                            result["skipped"].append({"word": entry["word"], "reason": "Already represented by an existing form"})
                    else:
                        conn.execute('ROLLBACK TO import_word')
                        conn.execute('RELEASE import_word')
                        result["failed"].append(entry["word"])
            import_committed = True
            # Enrichment is shared by every capture path and happens after the
            # import commits. Re-selecting an incomplete capture can retry it.
            selected = sorted(set(captures) | set(result["imported"]))
            with connect_db(self.db_path) as conn:
                selected_ids = []
                if selected:
                    placeholders = ','.join('?' for _ in selected)
                    selected_ids = [row[0] for row in conn.execute(
                        f"SELECT DISTINCT w.id FROM words w LEFT JOIN forms f ON f.word_id=w.id "
                        f"WHERE w.lemma IN ({placeholders}) OR f.form IN ({placeholders})",
                        selected + selected)]
            enrichment = self.enrich_words(selected_ids)
            if enrichment["pending"]:
                with connect_db(self.db_path) as conn:
                    placeholders = ','.join('?' for _ in enrichment["pending"])
                    result["enrichment_pending"] = [row[0] for row in conn.execute(
                        f"SELECT DISTINCT lemma FROM words WHERE id IN ({placeholders}) ORDER BY lemma",
                        enrichment["pending"])]
            result["warnings"].extend(enrichment["warnings"])
            with connect_db(self.db_path) as conn:
                db_words = {row[0] for row in conn.execute('SELECT DISTINCT lemma FROM words')}
            to_export = sorted(db_words - current)
            if to_export:
                try:
                    if not self.drive_service.append_words(to_export):
                        raise RuntimeError("Drive did not confirm the vocabulary export.")
                    result["exported"] = to_export
                except TrialDenied:
                    raise
                except Exception:
                    logger.exception("Imported vocabulary, but Drive export failed")
                    result["warnings"].append("Words were retained in SQLite, but export to Drive failed. Retry sync.")
            result["status"] = "partial" if result["failed"] or result["enrichment_pending"] or result["warnings"] else "completed"
        except TrialDenied:
            raise
        except Exception:
            logger.exception("Sync interrupted after run %s started", run_id)
            result["status"] = "failed"
            if not import_committed:
                result["imported"] = []
            result["warnings"].append("Sync was interrupted. Imported words remain safe; refresh preview before retrying.")
            raise
        finally:
            with connect_db(self.db_path) as conn:
                conn.execute("UPDATE sync_runs SET status=?, summary=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                             (result.get("status", "failed"), json.dumps(result, ensure_ascii=False), run_id))
        return result
