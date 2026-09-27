import os
import re
import pymorphy3
from openai import OpenAI

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flask_vocab_app"))
from config import OPENAI_API_KEY
client = OpenAI(api_key=OPENAI_API_KEY, timeout=120, max_retries=1)
from pydub import AudioSegment


# Set your OpenAI API key


# Get the path to your M4A file
file_path = input("Enter the path to your M4A file: ")

# Convert the M4A file to MP3 format
audio_file_path = file_path.replace(".m4a", ".mp3")
AudioSegment.from_file(file_path).export(audio_file_path, format="mp3")

# Load the MP3 audio file
audio = AudioSegment.from_mp3(audio_file_path)

# Define segment duration in milliseconds
segment_duration_ms = 20 * 60 * 1000

# Split audio into segments
segments = [audio[i:i + segment_duration_ms] for i in range(0, len(audio), segment_duration_ms)]

# Initialize variables
morph = pymorphy3.MorphAnalyzer()
vocab_filename = "vocab-list.txt"
learned_words = set()

# Load existing learned words from 'vocab_list.txt' or create an empty set
if os.path.exists(vocab_filename):
    with open(vocab_filename, "r", encoding="utf-8") as f:
        learned_words = set(line.strip() for line in f)

# Process each segment
for i, segment in enumerate(segments):
    # Save segment as MP3 file
    segment_path = f"segment_{i}.mp3"
    segment.export(segment_path, format="mp3")

    # Transcribe segment using OpenAI API
    with open(segment_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file, language="ru")

    # Tokenize the Russian transcript into individual norminative form words
    words = [morph.parse(word)[0].normal_form for word in transcript.text.split()]

    # Filter out any non-alphabetic characters from the list of words using a regular expression
    filtered_words = [re.sub(r'[^А-Яа-яЁё-]+', "", word.lower().rstrip(".")) for word in words if len(re.sub(r'[^А-Яа-яЁё]+', "", word.lower().rstrip("."))) > 2]
    filtered_words = [morph.parse(word)[0].normal_form for word in filtered_words]

    # Update the set of learned words with the new filtered words
    for word in filtered_words:
        if word not in learned_words:
            print(f"New word added!: {word}")
            learned_words.add(word)

    # Delete the MP3 segment file
    os.remove(segment_path)

# Compute a measure of word complexity for each word in the filtered list
complexity_scores = {word: len(word) for word in learned_words}

# Sort the list of words based on their complexity scores
sorted_words = sorted(complexity_scores, key=complexity_scores.get, reverse=True)

# Write the updated list of learned words to 'vocab_list.txt'
with open(vocab_filename, "w", encoding="utf-8") as f:
    f.write("\n".join(sorted(learned_words)))

# Print the sorted list of words and their complexity scores
for word in sorted_words:
    print(f"{word} {complexity_scores[word]}")
