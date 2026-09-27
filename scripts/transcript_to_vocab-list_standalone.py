from pathlib import Path
import re
import pymorphy2
import nltk
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Download required NLTK data
try:
    nltk.download('punkt', quiet=True)
except Exception as e:
    logger.warning(f"Failed to download NLTK data: {e}")

# Initialize pymorphy2
morph = pymorphy2.MorphAnalyzer()

# Prompt the user for the input file
file_path = input("What is the location of your new vocab transcript?: ")

# Load the transcript
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        transcript = f.read()
    logger.info(f"Loaded transcript from {file_path}")
except FileNotFoundError:
    logger.error(f"File not found: {file_path}")
    exit(1)
except Exception as e:
    logger.error(f"Error reading file {file_path}: {e}")
    exit(1)

# Tokenize the transcript into words
words = nltk.word_tokenize(transcript)

# Normalize to lemma forms
lemmas = []
for word in words:
    try:
        parsed = morph.parse(word)[0]
        lemmas.append(parsed.normal_form)
    except Exception as e:
        logger.warning(f"Could not parse word '{word}': {e}")

# Filter out non-alphabetic characters and short words
filtered_words = []
for word in lemmas:
    cleaned = re.sub(r'[^А-Яа-яЁё-]+', '', word.lower().rstrip('.'))
    if len(cleaned) > 2:
        filtered_words.append(cleaned)

# Deduplicate while preserving order
filtered_words = list(dict.fromkeys(filtered_words))

# Load existing learned words
vocab_filename = str(Path(__file__).resolve().parents[1] / 'vocab-list.txt')
learned_words = set()
if os.path.exists(vocab_filename):
    try:
        with open(vocab_filename, 'r', encoding='utf-8') as f:
            learned_words = set(line.strip() for line in f if line.strip())
        logger.info(f"Loaded {len(learned_words)} existing words from {vocab_filename}")
    except Exception as e:
        logger.error(f"Error reading {vocab_filename}: {e}")

# Identify new words
new_words = []
for word in filtered_words:
    if word and word not in learned_words:
        logger.info(f"New word found: {word}")
        new_words.append(word)
        learned_words.add(word)

# Append new words to vocab_list.txt
if new_words:
    try:
        with open(vocab_filename, 'a', encoding='utf-8') as f:
            f.write('\n'.join(new_words) + '\n')
        logger.info(f"Appended {len(new_words)} new words to {vocab_filename}")
    except Exception as e:
        logger.error(f"Error appending to {vocab_filename}: {e}")
        exit(1)
else:
    logger.info("No new words to append")

# Compute complexity scores
complexity_scores = {word: len(word) for word in learned_words}

# Sort words by complexity
sorted_words = sorted(complexity_scores, key=complexity_scores.get, reverse=True)

# Print results
print("\nSorted words by complexity:")
for word in sorted_words:
    print(f"{word} {complexity_scores[word]}")

if new_words:
    print("\nNew words appended:")
    for word in new_words:
        print(word)
else:
    print("\nNo new words found.")
