import requests
import os
import shutil
from pathlib import Path
from pydub import AudioSegment
import numpy as np
import shutil
import librosa

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.134 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-User': '?1',
    'Sec-Fetch-Dest': 'document',
    'Referer': 'https://www.google.com/',
}

api_key = os.environ.get("FORVO_API_KEY", "")
if not api_key:
    raise RuntimeError("FORVO_API_KEY not set. Add it to .env at the repo root.")

def calculate_thd(y, sr):
    # Calculate the harmonic components of the signal
    harmonics = librosa.effects.harmonic(y)

    # Calculate the power of the original signal and its harmonic components
    signal_power = np.sum(np.abs(y) ** 2)
    harmonics_power = np.sum(np.abs(harmonics) ** 2)

    # Calculate the THD as the ratio of the powers
    if signal_power == 0:
        return float('inf')
    return (harmonics_power / signal_power)

def get_pronunciation(word):
    print(word)
    best_file_src = None
    url = f"https://apifree.forvo.com/key/{api_key}/format/json/action/word-pronunciations/word/{word}/language/ru"
    try:
        response = requests.get(url, headers=headers)
        print(response)
    except requests.RequestException as e:
        print(f"An error occurred: {e}")

    def download_audio_file(url, filename, target_directory):
        os.makedirs(target_directory, exist_ok=True)
        response = requests.get(url, headers=headers)
        file_path = os.path.join(target_directory, filename)
        with open(file_path, 'wb') as f:
            f.write(response.content)
        return file_path

    def calculate_snr(audio_data): # Code which uses the pydub library to analysis SNR of audio source
        signal = np.mean(np.abs(audio_data))
        noise = np.std(audio_data)
        if noise == 0:
            return float('inf')
        return signal / noise

    def analyze_audio_files(files):
        snr_list = []

        for file in files:
            audio = AudioSegment.from_mp3(file)
            samples = np.array(audio.get_array_of_samples())
            snr = calculate_snr(samples)
            print(f"{file}: SNR = {snr}")
            snr_list.append((snr, file))

        snr_list.sort(reverse=True)

        y, sr = librosa.load(f"{snr_list[0][1]}")         # Load the audio file using Librosa and calculate THD
        thd = calculate_thd(y, sr)
        print(f"THD = {thd}")
        
        if thd > 0.7 and len(snr_list) > 1:
            best_file = snr_list[1][1] # Pick the second file
        else:
            best_file = snr_list[0][1] # Pick the first file

        return best_file

    def download_file(pronunciation, word, i): # Downloads and names a new pronunciation
        filepath = str(Path(__file__).resolve().parents[1] / 'anki_audio')
        file_url = pronunciation["pathmp3"]
        filename = f"{word}_{i}.mp3"
        file_path = download_audio_file(file_url, filename, filepath)
        downloaded_files.append(file_path)
        print(filename)

    if response.status_code == 200:
        pronunciations = response.json()["items"]
        downloaded_files = []
        if pronunciations:
            max_votes = 0
            upvoted_file = None
            for pronunciation in reversed(pronunciations):
                if pronunciation["num_positive_votes"] >= max_votes: # If there is a highly favoured pronunciation, download this and skip the audio analysis
                    max_votes = pronunciation["num_positive_votes"]
                    upvoted_file = pronunciation
            download_file(upvoted_file, word, 0)
                
            if upvoted_file is None: # If there is no favoured pronunciation, download 5 pronunciations
                download_count = 0
                for i, pronunciation in enumerate(pronunciations):
                    if download_count >= 5:
                        break
                    download_file(pronunciation, word, i)
                    download_count += 1

            if len(downloaded_files) > 1: # and choose the best based on SNR and distortion analysis
                best_file = analyze_audio_files(downloaded_files)
            else:
                best_file = downloaded_files[0]

            # Copy the file to the Anki Directory
            destination_directory = str(Path.home() / 'Library/Application Support/Anki2/User 1/collection.media')
            os.makedirs(destination_directory, exist_ok=True)
            destination_path = os.path.join(destination_directory, os.path.basename(best_file))
            shutil.copy(best_file, destination_path)
            best_file_src = os.path.basename(best_file)

            for file in downloaded_files:
                if file != best_file:
                    os.remove(file)

        else:
            print("No Pronunciations Found.")
            best_file_src = None
    else:
        print(f"Error: {response.status_code}")

    return best_file_src
