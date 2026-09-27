import os
import random
import tempfile
import math
from config import ELEVENLABS_MODEL, ELEVENLABS_VOICE_IDS
import requests
import logging
from .trial_provider import config_snapshot, elevenlabs_call
from .ai_trial_budget import TrialDenied
from pydub import AudioSegment

logger = logging.getLogger(__name__)

class ElevenLabsService:
    def __init__(self, api_key, media_dir, voice_ids=ELEVENLABS_VOICE_IDS, model=ELEVENLABS_MODEL, config=None):
        self.config = config_snapshot(config)
        self.api_key = api_key
        self.media_dir = media_dir
        self.voice_ids = tuple(voice_ids)
        if not self.voice_ids:
            raise ValueError("Configure at least one ElevenLabs voice.")
        self.model = model

    def generate_audio(self, sentence, filename):
        voice_id = random.choice(self.voice_ids)
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        data = {
            "text": sentence,
            "model_id": self.model,
            "voice_settings": {"stability": 0.8, "similarity_boost": 0.85, "style": 0.0}
        }
        logger.info(f"Generating audio for sentence: {sentence} with filename: {filename}")
        try:
            response = elevenlabs_call(self.config, sentence, self.model, voice_id,
                lambda: requests.post(url, json=data, headers=headers, timeout=60))
            response.raise_for_status()
            audio_file = os.path.join(self.media_dir, filename)
            os.makedirs(os.path.dirname(audio_file), exist_ok=True)
            # Publish only a complete, decoded MP3; preserve any previous good file.
            fd, temporary = tempfile.mkstemp(suffix=".mp3", dir=os.path.dirname(audio_file))
            os.close(fd)
            try:
                with open(temporary, "wb") as stream:
                    stream.write(response.content)
                audio = AudioSegment.from_file(temporary, format="mp3")
                if math.isfinite(audio.dBFS):
                    audio = audio.apply_gain(-20.0 - audio.dBFS)
                audio.export(temporary, format="mp3")
                os.replace(temporary, audio_file)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

            return os.path.basename(audio_file)
        except TrialDenied:
            raise
        except Exception as e:
            logger.error(f"Audio generation failed: {str(e)}")
            return None
