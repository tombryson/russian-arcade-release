import requests
import os
import shutil
from pathlib import Path
from pydub import AudioSegment
import numpy as np

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

api_key = os.environ.get("FORVO_API_KEY", "")
if not api_key:
    raise RuntimeError("FORVO_API_KEY not set. Add it to .env at the repo root.")
language = "ru"  # You can change this to any language code supported by Forvo (e.g., "es" for Spanish)
word = "Яблоко"
url = f"https://apifree.forvo.com/action/word-pronunciations/format/json/word/{word}/language/{language}/key/{api_key}"
filepath = str(Path(__file__).resolve().parents[1] / 'anki_audio')
response = requests.get(url)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:96.0) Gecko/20100101 Firefox/96.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Pragma': 'no-cache',
    'Cache-Control': 'no-cache',
}


def download_audio_file(url, filename, target_directory="anki_audio"):
    os.makedirs(target_directory, exist_ok=True)
    response = requests.get(url, headers=headers)
    file_path = os.path.join(target_directory, filename)
    with open(file_path, 'wb') as f:
        f.write(response.content)
    return file_path

def calculate_snr(audio_data):
    signal = np.mean(np.abs(audio_data))
    noise = np.std(audio_data)
    if noise == 0:
        return float('inf')
    return signal / noise

def analyze_audio_files(files):
    best_snr = float('-inf')
    best_file = None

    for file in files:
        audio = AudioSegment.from_mp3(file)
        samples = np.array(audio.get_array_of_samples())
        snr = calculate_snr(samples)
        print(f"{file}: SNR = {snr}")
        if snr > best_snr:
            best_snr = snr
            best_file = file
    
    return best_file

if response.status_code == 200:
    pronunciations = response.json()["items"]
    if pronunciations:
        downloaded_files = []
        for i, pronunciation in enumerate(pronunciations):
            file_url = pronunciation["pathmp3"]
            filename = f"{word}_{i}.mp3"
            file_path = download_audio_file(file_url, filename, filepath)
            downloaded_files.append(file_path)

        best_file = analyze_audio_files(downloaded_files)
        print(f"Best file: {best_file}")

        for file in downloaded_files:
            if file != best_file:
                os.remove(file)

    else:
        print("No Pronunciations Found.")
else:
    print(f"Error: {response.status_code}")
