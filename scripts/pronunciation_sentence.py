from pathlib import Path
from openai import OpenAI
import os
from API_key import openai_API_key
import argparse
import requests

# API key for Yandex.Translate
yandex_api_key = os.environ["YANDEX_API_KEY"]
def get_pronunciation_sentence(russian_response, russian_word):
    folder_id = Path("./anki_sentence_audio")

    # Ensure the directory exists
    folder_id.mkdir(parents=True, exist_ok=True)

    # Define the path to the audio file within that directory
    speech_file_path = folder_id / f"{russian_word}.mp3"

    url = 'https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize'
    headers = {
        'Authorization': 'Api-Key ' + yandex_api_key,
    }

    data = {
        'text': russian_response,
        'lang': 'ru-RU',
        'voice': 'filipp',
        'speed': "0.9",
        'format': 'mp3',
        'folderId': str(folder_id)
    }

    with requests.post(url, headers=headers, data=data, stream=True) as resp:
        if resp.status_code != 200:
            raise RuntimeError("Invalid response received: code: %d, message: %s" % (
                resp.status_code, resp.text))

        with open(speech_file_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=None):
                f.write(chunk)

    return russian_response


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--word", required=True, help="Word for filename")
    parser.add_argument("--text", required=True, help="Text for synthesize")
    parser.add_argument("--output", required=True, help="Output file name")
    args = parser.parse_args()

    get_pronunciation_sentence(args.text, args.word)

# def get_pronunciation_sentence(russian_response, russian_word):

#     # Define the path to the 'anki_sentence_audio' directory
#     audio_directory = Path("./anki_sentence_audio")

#     # Ensure the directory exists
#     audio_directory.mkdir(parents=True, exist_ok=True)

#     # Define the path to the audio file within that directory
#     speech_file_path = audio_directory / f"{russian_word}.mp3"

#     response = client.audio.speech.create(
#         model="tts-1-hd",
#         voice="nova",
#         input=f"{russian_response}"
#     )

#     response.stream_to_file(speech_file_path)

#     return russian_response
