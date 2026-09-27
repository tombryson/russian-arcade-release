from pathlib import Path
import card_providers as providers
import os
import requests
from openai import OpenAI
import shutil
import logging
import json
from card_providers import OPENAI_API_KEY as openai_API_key
import random
import re
import pymorphy3  # Added for Russian morphology

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# Initialize pymorphy2
morph = pymorphy3.MorphAnalyzer()

# API keys


# Initialize OpenAI client
client = providers.provider().client
logger.info("OpenAI client initialized")

# Anki media directory
media_dir = str(Path.home() / 'Library/Application Support/Anki2/User 1/collection.media')
os.makedirs(media_dir, exist_ok=True)
logger.info(f"Anki media directory ensured: {media_dir}")

# AnkiConnect wrapper
class AnkiConnect:
    def __init__(self):
        self.url = "http://localhost:8765"
        self.ensure_deck("Russian")

    def add_note(self, note):
        payload = {"action": "addNote", "version": 6, "params": {"note": note}}
        response = requests.post(self.url, json=payload)
        return response.json()

    def ensure_deck(self, deck_name):
        payload = {"action": "createDeck", "version": 6, "params": {"deck": deck_name}}
        response = requests.post(self.url, json=payload)
        if response.json()['error'] is None:
            logger.info(f"Deck '{deck_name}' ensured")
        else:
            logger.error(f"Failed to create deck '{deck_name}': {response.json()['error']}")

anki = AnkiConnect()
logger.info("AnkiConnect initialized")

# Read vocab list
vocab_file = str(Path(__file__).resolve().parents[1] / 'vocab-list.txt')
with open(vocab_file, "r", encoding="utf-8") as f:
    russian_words = [line.strip() for line in f if line.strip()]
logger.info(f"Loaded {len(russian_words)} words from {vocab_file}")

# Load sentence tracking
sentences_file = str(Path(__file__).resolve().parents[1] / 'russian_sentences.json')
if os.path.exists(sentences_file):
    with open(sentences_file, "r", encoding="utf-8") as f:
        sentence_counts = json.load(f)
else:
    sentence_counts = {word: 0 for word in russian_words}
    with open(sentences_file, "w", encoding="utf-8") as f:
        json.dump(sentence_counts, f, ensure_ascii=False, indent=2)
logger.info(f"Loaded sentence counts for {len(sentence_counts)} words")

# Generate sentence
def generate_sentence(russian_word):
    return providers.sentence(russian_word)

# Format cloze with morphological analysis
def format_cloze(sentence, word, sentence_count):
    logger.info(f"Formatting cloze for word: {word} with sentence count: {sentence_count}")
    # Split sentence into words and find an inflected form of the lemma
    words = sentence.split()
    exact_word = None
    for w in words:
        parsed = morph.parse(w)[0]
        if parsed.normal_form == word.strip():  # Check if this is an inflected form of the lemma
            exact_word = w
            break
    
    if exact_word:
        # Create cloze with the exact form found in the sentence
        link = f'<a href="https://en.openrussian.org/ru/{word.strip()}" target="_blank">{{{{c1::{exact_word}}}}}</a>'
        cloze_sentence = sentence.replace(exact_word, link, 1)  # Replace the first occurrence
    else:
        logger.warning(f"No form of '{word}' found in sentence '{sentence}'")
        cloze_sentence = sentence  # Fallback, will be caught by validation
    
    unique_suffix = f"<!-- cloze{sentence_count + 1} -->"
    cloze_sentence_with_unique = f"{cloze_sentence} {unique_suffix}"
    logger.debug(f"Cloze sentence with unique identifier: {cloze_sentence_with_unique}")
    return cloze_sentence_with_unique

# Get single-word translation in context
def get_word_translation(russian_word, sentence):
    return providers.meaning(russian_word, sentence)

# Translate full sentence
def translate_sentence(text, target_lang="ru-en"):
    return providers.translation(text)

# Generate audio
def generate_audio(sentence, idx):
    return providers.audio(sentence, f"sentence_{idx}.mp3", media_dir)

# Generate image
def generate_image_url(sentence, word):
    return providers.image(sentence, word)

def download_image(image_url, filename):
    return providers.download(image_url, filename, media_dir)

# Process a batch of words
def process_batch(words, start_idx, batch_size, max_sentences_per_word):
    logger.info(f"Starting batch processing for words {start_idx} to {start_idx + batch_size - 1}")
    for idx, russian_word in enumerate(words[start_idx:start_idx + batch_size], start=start_idx):
        if sentence_counts[russian_word] < max_sentences_per_word:
            logger.info(f"Processing word: {russian_word} (index: {idx}, sentence count: {sentence_counts[russian_word]})")

            sentence = generate_sentence(russian_word)
            if sentence is None:
                continue
            cloze_sentence = format_cloze(sentence, russian_word, sentence_counts[russian_word])

            # Ensure the cloze sentence is valid (contains {{ and }})
            if "{{" not in cloze_sentence or "}}" not in cloze_sentence:
                logger.error(f"Invalid cloze sentence for '{russian_word}': {cloze_sentence}")
                continue

            word_translation = get_word_translation(russian_word, sentence)
            if word_translation is None:
                continue

            sentence_translation = translate_sentence(sentence)
            if sentence_translation is None:
                continue

            audio_file = generate_audio(sentence, idx)
            if audio_file is None:
                audio_file = ""

            image_url = generate_image_url(sentence, russian_word)
            image_file = download_image(image_url, f"{idx}_{russian_word}_{sentence_counts[russian_word]}.png") if image_url else ""

            image_tag = f'<img src="{image_file}">' if image_file else ""
            note = {
                "deckName": "Russian",
                "modelName": "Cloze",
                "fields": {
                    "Text": cloze_sentence,
                    "Translation": word_translation,
                    "Extra": f"{sentence_translation}<br>{image_tag}<br>[sound:{audio_file}]" if audio_file else f"{sentence_translation}<br>{image_tag}"
                },
                "options": {"allowDuplicate": True}
            }
            try:
                result = anki.add_note(note)
                if result['error'] is not None:
                    raise Exception(f"AnkiConnect error: {result['error']}")
                logger.info(f"Successfully added flashcard for {russian_word} with note ID: {result['result']}")
                sentence_counts[russian_word] += 1
                with open(sentences_file, "w", encoding="utf-8") as f:
                    json.dump(sentence_counts, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Failed to add flashcard for {russian_word}: {str(e)}")
        else:
            logger.info(f"Skipping {russian_word} - already has {sentence_counts[russian_word]} sentences")
    logger.info(f"Completed batch processing for words {start_idx} to {start_idx + batch_size - 1}")

# Main loop with batching
logger.info("Starting flashcard generation process")
max_sentences_per_word = 1
batch_size = 5
start_idx = 0

while start_idx < len(russian_words):
    process_batch(russian_words, start_idx, batch_size, max_sentences_per_word)
    remaining_words = len(russian_words) - start_idx - batch_size
    if remaining_words > 0:
        user_input = input(f"Queue 5 more cards? ({remaining_words} words remaining) [y/n]: ").strip().lower()
        if user_input == 'y':
            start_idx += batch_size
        elif user_input == 'n':
            logger.info("User chose to stop. Saving progress and exiting.")
            with open(sentences_file, "w", encoding="utf-8") as f:
                json.dump(sentence_counts, f, ensure_ascii=False, indent=2)
            break
        else:
            logger.warning(f"Invalid input '{user_input}'. Assuming 'n' and stopping.")
            with open(sentences_file, "w", encoding="utf-8") as f:
                json.dump(sentence_counts, f, ensure_ascii=False, indent=2)
            break
    else:
        logger.info("Processed all words in the list.")
        break

logger.info("Flashcard generation process completed")