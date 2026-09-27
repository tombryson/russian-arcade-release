from pathlib import Path
import sqlite3
import logging
import requests
import json
from datetime import datetime
from fuzzywuzzy import fuzz, process

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

class AnkiCardsSync:
    def __init__(self, db_path: str, anki_connect_url: str = "http://localhost:8765"):
        self.db_path = db_path
        self.anki_connect_url = anki_connect_url
        logger.debug(f"Initialized AnkiCardsSync with db_path={db_path}, anki_connect_url={anki_connect_url}")

    def anki_connect_request(self, action: str, params: dict = None) -> dict:
        """Send request to AnkiConnect."""
        payload = {"action": action, "version": 6, "params": params or {}}
        try:
            logger.debug(f"Sending AnkiConnect request: action={action}, params={json.dumps(params, ensure_ascii=False)}")
            response = requests.post(self.anki_connect_url, json=payload)
            response.raise_for_status()
            result = response.json()
            logger.debug(f"AnkiConnect response for {action}: {json.dumps(result, ensure_ascii=False)}")
            if result.get("error"):
                logger.error(f"AnkiConnect error for action {action}: {result['error']}")
                return None
            return result.get("result")
        except requests.RequestException as e:
            logger.error(f"AnkiConnect network error for action {action}: {str(e)}", exc_info=True)
            return None
        except json.JSONDecodeError as e:
            logger.error(f"AnkiConnect response parsing error for action {action}: {str(e)}", exc_info=True)
            return None

    def get_russian_card_ids(self) -> list:
        """Fetch card IDs from the 'Russian' deck."""
        result = self.anki_connect_request("findCards", {"query": "deck:Russian"})
        if result is None:
            logger.error("Failed to fetch card IDs for Russian deck")
            return []
        logger.info(f"Fetched {len(result)} card IDs from Russian deck: {result}")
        return result

    def get_card_info(self, card_ids: list) -> list:
        """Fetch card metadata using cardsInfo."""
        result = self.anki_connect_request("cardsInfo", {"cards": card_ids})
        if result is None:
            logger.error("Failed to fetch card info")
            return []
        logger.info(f"Fetched info for {len(result)} cards")
        for card in result:
            logger.debug(f"Card ID {card['cardId']}: fields={card.get('fields', {}).keys()}, tags={card.get('tags', [])}")
        return result

    def clean_form(self, form: str) -> str:
        """Clean form by removing punctuation and normalizing."""
        if not form:
            return ""
        return form.strip(",.?! ").lower()

    def find_form_and_word_id(self, card: dict) -> tuple:
        """Map Anki card to form_id and word_id using fields and tags."""
        card_id = card.get("cardId")
        fields = card.get("fields", {})
        tags = card.get("tags", [])
        logger.debug(f"Card ID {card_id}: Processing fields={fields.keys()}, tags={tags}")

        # Extract fields
        text = fields.get("Text", {}).get("value", "")
        translation = fields.get("Translation", {}).get("value", "")
        hint = fields.get("Hint", {}).get("value", "")
        logger.debug(f"Card ID {card_id}: Text='{text}', Translation='{translation}', Hint='{hint}'")

        # Extract cloze word from Text
        cloze_word = None
        if "{{c1::" in text:
            try:
                cloze_word = text.split("{{c1::")[1].split("}}")[0]
                logger.debug(f"Card ID {card_id}: Extracted cloze word='{cloze_word}'")
            except IndexError:
                logger.warning(f"Card ID {card_id}: Failed to parse cloze word from Text")

        # Clean candidates
        candidates = [cloze_word, translation, hint]
        candidates = [self.clean_form(c) for c in candidates if c]
        logger.debug(f"Card ID {card_id}: Cleaned candidates={candidates}")

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Fetch all forms and words for matching
                cursor.execute("SELECT f.id, f.form, f.word_id, w.lemma, w.pos FROM forms f JOIN words w ON f.word_id = w.id")
                forms_words = cursor.fetchall()
                form_list = [(row[1].lower(), row[0], row[2], row[3].lower(), row[4]) for row in forms_words]
                logger.debug(f"Card ID {card_id}: Loaded {len(form_list)} forms for matching")

                # Try exact and fuzzy matching
                best_form_id, best_word_id, best_score = None, None, 0
                best_candidate = None
                for candidate in candidates:
                    if not candidate:
                        continue
                    # Exact match on form or lemma
                    cursor.execute(
                        """
                        SELECT f.id, f.word_id, w.lemma
                        FROM forms f
                        JOIN words w ON f.word_id = w.id
                        WHERE LOWER(f.form) = ? OR LOWER(w.lemma) = ?
                        """,
                        (candidate, candidate)
                    )
                    result = cursor.fetchone()
                    if result:
                        form_id, word_id, lemma = result
                        logger.debug(f"Card ID {card_id}: Exact match for '{candidate}' -> form_id={form_id}, word_id={word_id}, lemma='{lemma}'")
                        return form_id, word_id

                    # Fuzzy match
                    matches = process.extract(candidate, [f[0] for f in form_list], scorer=fuzz.ratio, limit=1)
                    if matches and matches[0][1] >= 90:
                        matched_form, score = matches[0][0], matches[0][1]
                        for form, form_id, word_id, lemma, pos in form_list:
                            if form == matched_form:
                                logger.debug(
                                    f"Card ID {card_id}: Fuzzy match for '{candidate}' -> "
                                    f"form='{form}', form_id={form_id}, word_id={word_id}, lemma='{lemma}', score={score}"
                                )
                                if score > best_score:
                                    best_form_id, best_word_id, best_score, best_candidate = form_id, word_id, score, candidate

                # Refine with tags if fuzzy match
                if best_form_id and best_score < 100:
                    pos_tags = [tag for tag in tags if tag in ['NOUN', 'VERB', 'ADJ', 'ADVB', 'PREP', 'CONJ', 'NPRO', 'NUMR', 'PART', 'COMP', 'PRED']]
                    case_tags = [tag.split(':')[1] for tag in tags if tag.startswith('case:')]
                    logger.debug(f"Card ID {card_id}: Refining match for '{best_candidate}' with pos={pos_tags}, case={case_tags}")
                    
                    query = """
                        SELECT f.id, f.word_id, w.lemma
                        FROM forms f
                        JOIN words w ON f.word_id = w.id
                        WHERE f.id = ?
                    """
                    params = [best_form_id]
                    if pos_tags:
                        query += " AND w.pos IN ({})".format(','.join('?' for _ in pos_tags))
                        params.extend(pos_tags)
                    if case_tags:
                        query += " AND f.tags LIKE ?"
                        params.append('%' + ' OR '.join(f'"case":"{c}"' for c in case_tags) + '%')
                    
                    cursor.execute(query, params)
                    result = cursor.fetchone()
                    if result:
                        form_id, word_id, lemma = result
                        logger.debug(f"Card ID {card_id}: Tag-refined match -> form_id={form_id}, word_id={word_id}, lemma='{lemma}'")
                        return form_id, word_id

                if best_form_id:
                    logger.info(f"Card ID {card_id}: Selected best fuzzy match for '{best_candidate}' -> form_id={best_form_id}, word_id={best_word_id}, score={best_score}")
                    return best_form_id, best_word_id

                logger.warning(f"Card ID {card_id}: No match found for candidates={candidates}, tags={tags}")
                return None, None
        except sqlite3.Error as e:
            logger.error(f"Database error finding form/word for card ID {card_id}: {str(e)}", exc_info=True)
            return None, None

    def sync_anki_cards(self):
        """Sync anki_cards table with Russian deck metadata."""
        try:
            logger.info("Starting anki_cards sync")
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='anki_cards'")
                if not cursor.fetchone():
                    logger.error("anki_cards table does not exist in database")
                    return 0, ["anki_cards table not found"]

            card_ids = self.get_russian_card_ids()
            if not card_ids:
                logger.error("No cards found in Russian deck")
                return 0, ["No cards found in Russian deck"]

            cards_info = self.get_card_info(card_ids)
            if not cards_info:
                logger.error("No card info retrieved")
                return 0, ["No card info retrieved"]

            cards_added = 0
            errors = []

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM anki_cards")
                existing_count = cursor.fetchone()[0]
                logger.debug(f"Current anki_cards table count: {existing_count}")

                for card in cards_info:
                    card_id = card.get("cardId")
                    logger.debug(f"Processing card ID {card_id}")

                    cursor.execute("SELECT card_id FROM anki_cards WHERE card_id = ?", (card_id,))
                    if cursor.fetchone():
                        logger.debug(f"Card ID {card_id} already in anki_cards, skipping")
                        continue

                    form_id, word_id = self.find_form_and_word_id(card)
                    if not form_id or not word_id:
                        errors.append(f"Card ID {card_id}: Could not map to form_id or word_id")
                        continue

                    interval = card.get("interval", 0)
                    lapses = card.get("lapses", 0)
                    reps = card.get("reps", 0)
                    created_at = datetime.fromtimestamp(card.get("mod", 0)).strftime("%Y-%m-%d %H:%M:%S")
                    rewarded = 0

                    logger.debug(
                        f"Card ID {card_id}: interval={interval}, lapses={lapses}, reps={reps}, "
                        f"form_id={form_id}, word_id={word_id}, created_at={created_at}, rewarded={rewarded}"
                    )

                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO anki_cards (card_id, form_id, word_id, interval, lapses, reps, rewarded, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (card_id, form_id, word_id, interval, lapses, reps, rewarded, created_at)
                    )
                    conn.commit()
                    if cursor.rowcount > 0:
                        cards_added += 1
                        logger.info(f"Added card ID {card_id} to anki_cards")
                    else:
                        logger.debug(f"Card ID {card_id} already exists or was skipped")

            logger.info(f"Sync completed: Added {cards_added} cards, {len(errors)} errors")
            return cards_added, errors
        except sqlite3.Error as e:
            logger.error(f"Database error syncing anki_cards: {str(e)}", exc_info=True)
            return 0, [str(e)]
        except Exception as e:
            logger.error(f"Unexpected error syncing anki_cards: {str(e)}", exc_info=True)
            return 0, [str(e)]

if __name__ == "__main__":
    db_path = str(Path(__file__).resolve().parents[1] / 'flask_vocab_app/vocab.db')
    sync = AnkiCardsSync(db_path)
    cards_added, errors = sync.sync_anki_cards()
    print(f"Sync completed: {cards_added} cards added, {len(errors)} errors")
    if errors:
        print("Errors:", errors)