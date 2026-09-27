import random
import base64
import json
import os
import re
import requests
import shutil
import sqlite3
from typing import List, Optional
from .openai_service import OpenAIService
from .yandex_service import YandexService
from .elevenlabs_service import ElevenLabsService
from .anki_connect import AnkiConnect
from models.words import get_word_by_id, update_word_count
from models.forms import get_form_by_word_id, get_all_forms, update_form_count
from models.database import get_db
from utils.formatters import format_cloze, format_anki_tags
from utils.pos_case import POS_MAP
import logging

logger = logging.getLogger(__name__)

class FlashcardService:
    def __init__(self, db_path, openai_service, yandex_service, elevenlabs_service, anki_connect):
        self.db_path = db_path
        self.openai_service = openai_service
        self.yandex_service = yandex_service
        self.elevenlabs_service = elevenlabs_service
        self.anki_connect = anki_connect
        self.client = openai_service.client

    def get_mnemonic(self, word_id):
        """Fetch mnemonic for a word by ID from the words table."""
        try:
            logger.debug(f"Attempting to fetch mnemonic for word_id={word_id}")
            db = get_db(self.db_path)
            cursor = db.cursor()
            cursor.execute("SELECT mnemonic FROM words WHERE id = ?", (word_id,))
            result = cursor.fetchone()
            mnemonic = result['mnemonic'] if result and result['mnemonic'] else ''
            logger.debug(f"Fetched mnemonic for word_id={word_id}: {mnemonic}")
            return mnemonic
        except sqlite3.Error as e:
            logger.error(f"Database error fetching mnemonic for word_id={word_id}: {str(e)}")
            return ''
        except Exception as e:
            logger.error(f"Unexpected error fetching mnemonic for word_id={word_id}: {str(e)}")
            return ''

    def generate_flashcard(self, word_id, lemma, pos, target_form, form_tags, form_id, topic, target_case=None, form_difficulty=None):
        logger.debug(f"Starting generate_flashcard for word_id={word_id}, lemma={lemma}, pos={pos}, target_form={target_form}, form_id={form_id}, topic={topic}, target_case={target_case}, form_difficulty={form_difficulty}")
        errors = []
        try:
            word = get_word_by_id(self.db_path, word_id)
            if not word:
                error_msg = f"Word with ID {word_id} not found"
                logger.error(error_msg)
                errors.append(error_msg)
                return False, errors
            logger.debug(f"Retrieved word data for word_id={word_id}: {word}")
            # Use form_difficulty if provided, else fallback to lemma_difficulty
            difficulty = form_difficulty if form_difficulty is not None else word['lemma_difficulty']

            form = get_form_by_word_id(self.db_path, word_id, target_case)
            if not form:
                error_msg = f"Form with word_id={word_id} and case={target_case} not found"
                logger.error(error_msg)
                errors.append(error_msg)
                return False, errors
            logger.debug(f"Retrieved form data for word_id={word_id} and case={target_case}: {dict(form)}")

            content = self.openai_service.generate_native_card(
                {"lemma": lemma, "form": target_form, "pos": pos, "tags": form_tags}, "ru-cloze")
            sentence = content.get("sentence", "").strip()
            word_translation = content.get("english", "").strip()
            sentence_translation = content.get("sentence_english", "").strip()
            if not all((sentence, word_translation, sentence_translation)):
                errors.append(f"Card generation returned incomplete content for {lemma}")
                return False, errors
            cloze_sentence, exact_form, form_tags = format_cloze(sentence, word_id, lemma, word['count'], target_case, self.db_path)
            if not cloze_sentence:
                errors.append(f"Cloze formatting failed for {lemma} (form: {target_form})")
                return False, errors

            audio_filename = f"word{word_id}_form{form_id}.mp3"
            image_filename = f"word{word_id}_form{form_id}.png"
            media_dir = self.elevenlabs_service.media_dir

            logger.debug(f"Attempting to generate audio for {lemma} (form: {target_form}, filename: {audio_filename})")
            audio_file = self.elevenlabs_service.generate_audio(sentence, audio_filename) or ""
            if not audio_file:
                logger.warning(f"Audio generation failed for {lemma} (form: {target_form}, filename: {audio_filename})")
            else:
                audio_path = os.path.join(media_dir, audio_file)
                if not os.path.exists(audio_path):
                    logger.warning(f"Audio file {audio_file} not found at {audio_path}")
                    audio_file = ""

            logger.debug(f"Attempting to generate image for {lemma} (form: {target_form}, filename: {image_filename})")
            image_url = self.openai_service.generate_image_url(sentence, exact_form)
            image_file = self.download_image(image_url, image_filename) if image_url else ""
            if not image_file:
                logger.warning(f"Image generation/download failed for {lemma} (form: {target_form}, filename: {image_filename})")
            else:
                image_path = os.path.join(media_dir, image_file)
                if not os.path.exists(image_path):
                    logger.warning(f"Image file {image_file} not found at {image_path}")
                    image_file = ""

            if not image_file and not audio_file:
                errors.append(f"No media files generated for {lemma} (form: {target_form})")
                return False, errors

            # Construct Extra field correctly
            extra_content = sentence_translation  # Start with the translation string
            if image_file:
                extra_content += f"<br><img src='{image_file}'>"
            if audio_file:
                extra_content += f"<br>[sound:{audio_file}]"

            note = {
                "deckName": "Russian",
                "modelName": "Cloze",
                "fields": {
                    "Text": cloze_sentence,
                    "Back Extra": "",
                    "Extra": extra_content,
                    "Translation": word_translation,
                    "Hint": self.get_mnemonic(word_id)
                },
                "tags": format_anki_tags(form_tags, pos, difficulty, topic),
                "options": {"allowDuplicate": True}
            }
            logger.debug(f"Constructed note for {lemma} (form: {target_form}: {json.dumps(note, ensure_ascii=False)}")

            # Log the full AnkiConnect request packet
            request_data = {
                "action": "addNote",
                "version": 6,
                "params": {
                    "note": note
                }
            }
            logger.debug(f"Sending AnkiConnect request packet: {json.dumps(request_data, ensure_ascii=False)}")

            logger.debug(f"Attempting to add note to Anki for {lemma} (form: {target_form})")
            try:
                result = self.anki_connect.add_note(note)
                logger.debug(f"AnkiConnect raw response for {lemma} (form: {target_form}): {result}")
                if result.get('error'):
                    error_msg = f"AnkiConnect error for {lemma} (form: {target_form}): {result['error']}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    return False, errors
                if not isinstance(result, dict) or 'result' not in result or not isinstance(result['result'], int) or result['result'] <= 0:
                    error_msg = f"AnkiConnect unexpected response for {lemma} (form: {target_form}): {result}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    return False, errors
                logger.info(f"Successfully added note for {lemma} (form: {target_form}) with result: {result}")
            except requests.RequestException as e:
                error_msg = f"AnkiConnect network error for {lemma} (form: {target_form}): {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                return False, errors
            except json.JSONDecodeError as e:
                error_msg = f"AnkiConnect response parsing error for {lemma} (form: {target_form}): {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                return False, errors
        except Exception as e:
            error_msg = f"AnkiConnect unexpected error for {lemma} (form: {target_form}): {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)
            return False, errors

        try:
            logger.debug(f"Attempting database updates for word_id={word_id} and form_id={form_id}")
            update_word_count(self.db_path, word_id)
            logger.debug(f"Updated word count for word_id={word_id}")
            if exact_form:
                db = get_db(self.db_path)
                cursor = db.cursor()
                cursor.execute("SELECT id FROM forms WHERE id = ?", (form_id,))
                form = cursor.fetchone()
                logger.debug(f"Form ID validation for {lemma} (form_id: {form_id}, form: {target_form}): {form}")
                if form:
                    logger.debug(f"Updating form count for form_id: {form_id}")
                    update_form_count(self.db_path, form_id)
                else:
                    errors.append(f"No form found for {lemma} with form_id {form_id}")
        except sqlite3.Error as e:
            errors.append(f"Database error for {lemma} (form: {target_form}): {str(e)}")
            return False, errors
        except Exception as e:
            errors.append(f"Unexpected database error for {lemma} (form: {target_form}): {str(e)}")
            return False, errors

        logger.info(f"Completed generate_flashcard for form_id={form_id} successfully")
        return True, errors

    def process_batch(self, start_idx, difficulty, pos, case, topics: Optional[List[str]], max_sentences, batch_size):
        logger.debug(f"Starting process_batch: start_idx={start_idx}, difficulty={difficulty}, pos={pos}, case={case}, topics={topics}, max_sentences={max_sentences}, batch_size={batch_size}")
        db = get_db(self.db_path)
        cursor = db.cursor()
        query, params = self.build_query(difficulty, pos, case, topics, max_sentences, batch_size)
        logger.debug(f"Built query: {query}")
        logger.debug(f"Query params: {params}")
        cursor.execute(query, params)
        batch_words = cursor.fetchall()
        logger.debug(f"Fetched batch_words: {[(row['id'], row['lemma'], row['pos'], row['topic']) for row in batch_words]}")
        cards_added = 0
        errors = []
        
        for idx, word in enumerate(batch_words, start=start_idx):
            word_id, lemma, pos, topic = word['id'], word['lemma'], word['pos'], json.loads(word['topic'] or '[]')
            logger.debug(f"Processing word {idx}: word_id={word_id}, lemma={lemma}, pos={pos}, topic={topic}")
            form_query = "SELECT id, form, tags, form_difficulty FROM forms WHERE word_id = ?"
            form_params = [word_id]
            if case:
                form_query += " AND tags LIKE ?"
                form_params.append(f'%\"case\":\"{case}\"%')
            if difficulty and difficulty != ['any']:
                form_query += " AND form_difficulty IN ({})".format(','.join('?' for _ in difficulty))
                form_params.extend(map(int, difficulty))
            form_query += " ORDER BY RANDOM() LIMIT 1"
            logger.debug(f"Form query for word_id={word_id}: {form_query}")
            logger.debug(f"Form query params: {form_params}")
            cursor.execute(form_query, form_params)
            form_row = cursor.fetchone()
            if not form_row:
                error_msg = f"No valid forms found for {lemma}{' in case ' + case if case else ''}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
            logger.debug(f"Fetched form_row for word_id={word_id}: {dict(form_row)}")
            form_id, target_form, form_tags, form_difficulty = form_row['id'], form_row['form'], json.loads(form_row['tags']), form_row['form_difficulty']

            success, form_errors = self.generate_flashcard(word_id, lemma, pos, target_form, form_tags, form_id, topic, case, form_difficulty)
            if success:
                cards_added += 1
                logger.info(f"Successfully generated flashcard for word_id={word_id}, form_id={form_id}")
            errors.extend(form_errors)
            logger.debug(f"Word {idx} result: success={success}, errors={form_errors}")

        logger.info(f"Completed process_batch: cards_added={cards_added}, total_words={len(batch_words)}, errors={errors}")
        return cards_added, len(batch_words), errors

    def process_word_forms(self, word_id, lemma, pos):
        logger.debug(f"Starting process_word_forms: word_id={word_id}, lemma={lemma}, pos={pos}")
        db = get_db(self.db_path)
        cursor = db.cursor()
        cards_added = 0
        errors = []
        
        cursor.execute("SELECT topic FROM words WHERE id = ?", (word_id,))
        topic_row = cursor.fetchone()
        topic = json.loads(topic_row['topic'] or '[]') if topic_row else []
        logger.debug(f"Retrieved topic for word_id={word_id}: {topic}")

        cursor.execute("SELECT id, form, tags, form_difficulty FROM forms WHERE word_id = ?", (word_id,))
        forms = cursor.fetchall()
        logger.debug(f"Fetched forms for word_id={word_id}: {[(row['id'], row['form'], row['tags'], row['form_difficulty']) for row in forms]}")
        if not forms:
            error_msg = f"No forms found for {lemma}"
            logger.error(error_msg)
            errors.append(error_msg)
            return 0, 1, errors
        
        for form_row in forms:
            form_id, target_form, form_tags, form_difficulty = form_row['id'], form_row['form'], json.loads(form_row['tags']), form_row['form_difficulty']
            logger.debug(f"Processing form: form_id={form_id}, target_form={target_form}, form_tags={form_tags}, form_difficulty={form_difficulty}")

            success, form_errors = self.generate_flashcard(word_id, lemma, pos, target_form, form_tags, form_id, topic, None, form_difficulty)
            if success:
                cards_added += 1
                logger.info(f"Successfully generated flashcard for word_id={word_id}, form_id={form_id}")
            errors.extend(form_errors)
            logger.debug(f"Form result for form_id={form_id}: success={success}, errors={form_errors}")

        logger.info(f"Completed process_word_forms: cards_added={cards_added}, total_forms={len(forms)}, errors={errors}")
        return cards_added, len(forms), errors

    def download_image(self, image_url, filename):
        logger.debug(f"Starting download_image: image_url={image_url}, filename={filename}")
        filepath = os.path.join(self.elevenlabs_service.media_dir, filename)
        try:
            os.makedirs(self.elevenlabs_service.media_dir, exist_ok=True)
            logger.debug(f"Ensured media directory exists: {self.elevenlabs_service.media_dir}")
            if image_url.startswith("data:image/"):
                _, encoded = image_url.split(",", 1)
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(encoded))
            else:
                response = requests.get(image_url, stream=True, timeout=30)
                response.raise_for_status()
                with open(filepath, "wb") as f:
                    shutil.copyfileobj(response.raw, f)
            logger.debug(f"Successfully downloaded image to {filepath}")
            if not os.path.exists(filepath):
                logger.error(f"Image file {filepath} not created despite successful download")
                return None
            return filename
        except Exception as e:
            logger.error(f"Image download failed for {image_url}: {str(e)}")
            return None

    def build_query(self, difficulty, pos, case, topics: Optional[List[str]], max_sentences, batch_size):
        logger.debug(f"Starting build_query: difficulty={difficulty}, pos={pos}, case={case}, topics={topics}, max_sentences={max_sentences}, batch_size={batch_size}")
        query = "SELECT w.id, w.lemma, w.pos, w.topic FROM words w"
        conditions = ["w.count < ?"]
        params = [max_sentences]
        
        if difficulty and difficulty != ['any']:
            logger.debug(f"Adding difficulty filter: {difficulty}")
            conditions.append("w.lemma_difficulty IN ({})".format(','.join('?' for _ in difficulty)))
            params.extend(map(int, difficulty))
        
        if pos and pos != ['any']:
            logger.debug(f"Adding pos filter: {pos}")
            normalized_pos = [POS_MAP.get(p, p) for p in pos]
            conditions.append("w.pos IN ({})".format(','.join('?' for _ in normalized_pos)))
            params.extend(normalized_pos)
        else:
            logger.debug("Adding default pos filter for all POS values")
            unique_pos = list(set(POS_MAP.values()))
            conditions.append("w.pos IN ({})".format(','.join('?' for _ in unique_pos)))
            params.extend(unique_pos)
        
        if case:
            query += " JOIN forms f ON w.id = f.word_id"
            logger.debug(f"Adding case filter: {case}")
            conditions.append("f.tags LIKE ?")
            params.append(f'%\"case\":\"{case}\"%')
        
        if topics and topics != ['any']:
            logger.debug(f"Adding topics filter: {topics}")
            topic_conditions = ["w.topic LIKE ?" for _ in topics]
            conditions.append("(" + " OR ".join(topic_conditions) + ")")
            params.extend(f'%"{topic}"%' for topic in topics)
        
        if conditions:
            logger.debug(f"Applying WHERE clause with conditions: {conditions}")
            query += " WHERE " + " AND ".join(conditions)
        
        logger.debug(f"Adding LIMIT: {batch_size}")
        query += " LIMIT ?"
        params.append(batch_size)
        
        logger.debug(f"Built query: {query}")
        logger.debug(f"Query params: {params}")
        return query, params
