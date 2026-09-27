from pathlib import Path
import card_providers as providers
from pronunciation import get_pronunciation
from pronunciation_english import get_english_pronunciation
from urllib.request import urlretrieve
import os
import requests
import sys
import time
from openai import OpenAI
from card_providers import OPENAI_API_KEY as openai_API_key

client = providers.provider().client







def get_prompt(word, russian_word):
    text = providers.sentence(russian_word)
    return f"Illustrate: {text}", text

def generate_image_url(english_translation, russian_word):
    text = providers.sentence(russian_word)
    return providers.image(text, russian_word), text

# Ensure the directory to store the images exists
image_directory = str(Path.home() / 'Library/Application Support/Anki2/User 1/collection.media')
os.makedirs(image_directory, exist_ok=True)

def download_image(image_url, image_filename, target_directory):
    return providers.download(image_url, image_filename, target_directory)

# Read the vocab-list.txt file & remove newline characters from each word and ignore any empty lines
with open(str(Path(__file__).resolve().parents[1] / 'vocab-list.txt'), "r", encoding="utf-8") as f:
    russian_words = [line.strip() for line in f if line.strip()]


# Read existing translations from the anki_flashcards.txt file
existing_translations = {}

try:
    with open(str(Path(__file__).resolve().parents[1] / 'anki_flashcards.txt'), "r", encoding="utf-8") as flashcard_file:
        for line in flashcard_file:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                russian_word = parts[0].split("<")[0].strip()  # Extract the Russian word before the HTML tag
                html_content = parts[1]
                english_translation = html_content.split("'>", 1)[1].split("<audio", 1)[0].strip() if len(parts) > 1 else ""
                existing_translations[russian_word] = english_translation
                print(f"Existing translation: {russian_word} -> {english_translation}")
except FileNotFoundError:
    print("Anki flashcards file not found.")


# Open the flashcard file, Iterate through the existing vocab, determine newly added vocab and output a new line of input
with open(str(Path(__file__).resolve().parents[1] / 'anki_flashcards.txt'), "a", encoding="utf-8") as flashcard_file:
    for idx, russian_word in enumerate(russian_words):
        if russian_word not in existing_translations:
            # 1. Make a GET request to the Yandex.Translate API with the Russian word and return the English translation
            english_translation = providers.card(russian_word)["english"]
            print(f"Word in english: {english_translation.title()}")

            # Generate the image URL for the English translation
            image_url, russian_response = generate_image_url(
                english_translation, russian_word)
            print(f"New Word Acquired! : {russian_word}")

            # Download the image and save it locally -> Anki Directory
            image_filename = f"{idx}_{english_translation}.png"
            download_image(image_url, image_filename, image_directory)

            # Download the image and save it -> anki_images folder
            anki_image_path = "../anki_images"
            download_image(image_url, image_filename, anki_image_path)

            # Download the russian pronunciation and save it locally + in the Anki folder + get HTML output
            forvo_audio_file = get_pronunciation(russian_word) or 'dummy_audio.mp3'
            print(f"Pronunciation generated @ {forvo_audio_file}")

            # Download the English pronunciation and save it locally + in the Anki folder + get HTML output
            english_audio_file, local_audio_file = get_english_pronunciation(english_translation, client)
            print(f"English pronunciation generated @ {english_audio_file}")

            # Create an HTML string with the image tag and English translation
            html_string = f"<img src='{image_filename}'alt=' {english_translation} '>{english_translation.title()}	<audio controls='' autoplay> <source src='{forvo_audio_file}' type='audio/mpeg'>audio</audio> <audio controls='' autoplay> <source src='{english_translation}.mp3' type='audio/mpeg'>"

            # Format the Russian word and its English translation as an Anki flashcard
            flashcard = f"{russian_word}\t{html_string}\n"

            # Write the Anki flashcard to the file
            flashcard_file.write(flashcard)
