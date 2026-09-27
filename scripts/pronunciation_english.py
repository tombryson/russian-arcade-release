from pathlib import Path
import subprocess
from openai import OpenAI

def standardize_and_concatenate(speech_path, silence_path, output_path):
    # Standardize the speech file to 44100 Hz, mono
    standardized_speech_path = speech_path.with_suffix('.standardized.mp3')
    subprocess.run(["ffmpeg", "-i", str(speech_path), "-ar", "44100", "-ac", "1", "-y", str(standardized_speech_path)])

    # Concatenate with the silence file
    concatenated_path = speech_path.with_suffix('.concatenated.mp3')
    subprocess.run(["ffmpeg", "-i", f"concat:{silence_path}|{standardized_speech_path}", "-c", "copy", "-y", str(concatenated_path)])

    # Reduce the volume by 25%
    subprocess.run(["ffmpeg", "-i", str(concatenated_path), "-filter:a", "volume=0.75", "-y", str(output_path)])

    # Clean up temporary files
    standardized_speech_path.unlink()
    concatenated_path.unlink()

def get_english_pronunciation(english_translation, client):
    speech_file_path = Path(str(Path(__file__).resolve().parents[1] / 'anki_audio_english/')) / f"{english_translation}.mp3"
    local_directory = Path(str(Path.home() / 'Library/Application Support/Anki2/User 1/collection.media')) / f"{english_translation}.mp3"
    silence_file_path = Path(str(Path(__file__).resolve().parents[1] / 'anki_audio_english/silence.mp3'))

    # Generate the audio file using OpenAI's API
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice="alloy",
        input=f"{english_translation}"
    )
    response.stream_to_file(speech_file_path)

    # Standardize and concatenate
    standardize_and_concatenate(speech_file_path, silence_file_path, speech_file_path)

    # Copy the file to the local directory
    local_modified_path = local_directory.parent / f"{english_translation}.mp3"
    subprocess.run(["cp", str(speech_file_path), str(local_modified_path)])

    return speech_file_path, local_modified_path