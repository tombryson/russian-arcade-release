from openai import OpenAI

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flask_vocab_app"))
from config import OPENAI_API_KEY
client = OpenAI(api_key=OPENAI_API_KEY, timeout=120, max_retries=1)


# Set your OpenAI API key


# Change the path to the path of your MP4 file
with open(input("Audio file path: ").strip(), "rb") as audio_file:
    transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file, language="ru")

# Print the transcribed text
print(transcript.text)