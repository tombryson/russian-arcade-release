from pathlib import Path
import os
import re
from openai import OpenAI
from API_key import openai_API_key
from pronunciation_english import get_english_pronunciation

client = OpenAI(api_key=openai_API_key)
original_cards_path = str(Path(__file__).resolve().parents[1] / 'anki_flashcards.txt')
temp_cards_path = str(Path(__file__).resolve().parents[1] / 'anki_flashcards_temp.txt')

def get_english_translation(line):
    match = re.search(r"alt='([^']+)'", line)
    return match.group(1).strip() if match else None

def update_cards_with_english_audio(original_path, temp_path):
    with open(original_path, "r", encoding="utf-8") as original_file, \
         open(temp_path, "w", encoding="utf-8") as temp_file:
        for line in original_file:
            parts = line.strip().split("\t")
            if len(parts) < 3:
                # If the line doesn't have enough parts, it's likely malformed or missing crucial content.
                temp_file.write(line)  # Write the original line to the temp file.
                continue
            
            russian_word = parts[0].strip()
            html_content = parts[1].strip()
            audio_content = parts[2].strip()

            # Count the number of .mp3 occurrences in the audio content
            mp3_count = audio_content.count('.mp3')

            if mp3_count == 1:  # Only Russian audio exists, need to add English audio
                english_translation = get_english_translation(html_content)
                print(f"Generating English audio for: {english_translation}, {russian_word}")
                english_audio_file, local_audio_file = get_english_pronunciation(english_translation, client)
                english_audio_filename = os.path.basename(english_audio_file).strip()

                # Append the new English audio to the audio content
                audio_content += f" <audio controls='' autoplay><source src='{english_audio_filename}' type='audio/mpeg'>audio</audio>"
            else:
                print(f"Both Russian and English audio already exist for: {russian_word}")

            # Write updated content to temp file, ensuring all segments are tab-separated
            updated_line = f"{russian_word}\t{html_content}\t{audio_content}\n"
            temp_file.write(updated_line)

    # Replace the original file with the updated content after verification
    os.replace(temp_path, original_path)

update_cards_with_english_audio(original_cards_path, temp_cards_path)
