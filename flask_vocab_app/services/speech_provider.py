"""Explicit speech providers. Recognition hypotheses are never grammar-corrected here."""
import base64
import json
import logging
import subprocess
import time
import tempfile
import wave
from pathlib import Path

import requests
from .trial_provider import config_snapshot, openai_client, elevenlabs_call, mai_call, trial_enabled
from .ai_trial_budget import TrialDenied

logger = logging.getLogger(__name__)


class SpeechError(ValueError):
    """A safe message without provider response bodies or credentials."""


def _response(response, label):
    if not response.ok:
        logger.warning('%s request failed: HTTP %s', label, response.status_code)
        raise SpeechError('Audio processing is currently unavailable. Please try again later.')
    return response


def audio_info(path):
    try:
        header = Path(path).read_bytes()[:16]
        if not (header.startswith((b'RIFF', b'ID3', b'OggS', b'\x1aE\xdf\xa3')) or header[4:8] == b'ftyp' or (len(header)>1 and header[0]==255 and header[1]&224==224)):
            raise ValueError()
        if header.startswith(b'RIFF') and header[8:12]==b'WAVE':
            with wave.open(str(path)) as audio:
                duration = audio.getnframes() / audio.getframerate()
                if not 0.2 <= duration <= 90:
                    raise ValueError()
                expected = audio.getnframes() * audio.getnchannels() * audio.getsampwidth()
                if len(audio.readframes(audio.getnframes())) != expected:
                    raise ValueError()
                return duration
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                 'format=duration:stream=codec_type', '-of', 'json', str(path)],
                                capture_output=True, timeout=30, check=True)
        info = json.loads(result.stdout)
        raw_duration = info.get('format', {}).get('duration')
        if raw_duration is None or raw_duration == 'N/A':
            # MediaRecorder's streaming WebM often has no container duration.
            with tempfile.TemporaryDirectory() as tmp:
                decoded = Path(tmp) / 'duration.wav'
                subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-t','91',
                                '-vn','-ac','1','-ar','16000',str(decoded)],
                               capture_output=True,timeout=30,check=True)
                with wave.open(str(decoded)) as audio:
                    duration = audio.getnframes() / audio.getframerate()
        else:
            duration = float(raw_duration)
        if not 0.2 <= duration <= 90 or not any(s['codec_type'] == 'audio' for s in info['streams']):
            raise ValueError()
        return duration
    except subprocess.TimeoutExpired:
        raise SpeechError('Audio processing took too long. Your recording is unchanged; please try sending it again.') from None
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, wave.Error, EOFError):
        raise SpeechError('Use a playable audio recording between 0.2 and 90 seconds.') from None


def wav_copy(source, destination):
    """Keep original bytes; no trimming, denoising, or silence removal."""
    audio_info(source)
    try:
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source),
                        '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(destination)],
                       capture_output=True, timeout=15, check=True)
    except (OSError, subprocess.SubprocessError):
        raise SpeechError('The recording could not be converted. Try recording again.') from None


class SpeechProvider:
    def __init__(self, config):
        self.config = config_snapshot(config)

    def transcribe(self, path, *, provider='mai', style='verbatim'):
        if provider not in ('mai', 'openai') or style not in ('verbatim', 'clean'):
            raise SpeechError('Unsupported transcription setting.')
        path = Path(path)
        started = time.monotonic()
        try:
            if provider == 'mai':
                key = self.config.get('OPENROUTER_API_KEY')
                if not key:
                    logger.warning('MAI transcription unavailable: OPENROUTER_API_KEY is not configured')
                    raise SpeechError('Speech recognition is currently unavailable. Your recording is saved.')
                model = self.config.get('CONVERSATION_TRANSCRIPTION_MODEL', 'microsoft/mai-transcribe-2')
                options = {'response_format': 'verbose_json', 'timestamp_granularities': ['word'],
                           'provider': {'options': {'azure': {'enhancedMode': {'modelOptions': {'transcribeStyle': style}}}}}}
                if trial_enabled(self.config):
                    options['provider']['allow_fallbacks'] = False
                response = mai_call(self.config, path, model, options,
                    lambda: requests.post('https://openrouter.ai/api/v1/audio/transcriptions',
                    headers={'Authorization': 'Bearer ' + key},
                    json={'model': model, 'input_audio': {'data': base64.b64encode(path.read_bytes()).decode(),
                                                        'format': path.suffix[1:]}, **options}, timeout=(10, 60)))
                raw = _response(response, 'MAI transcription').json()
            else:
                import openai
                key = self.config.get('OPENAI_API_KEY')
                if not key:
                    logger.warning('OpenAI transcription unavailable: OPENAI_API_KEY is not configured')
                    raise SpeechError('Speech recognition is currently unavailable. Your recording is saved.')
                model = self.config.get('CONVERSATION_COMPARISON_MODEL', 'gpt-transcribe')
                options = {'prompt': 'Transcribe the Russian speech literally. Preserve incorrect endings, conjugations, repetitions and self-corrections. Do not improve grammar.'}
                client = openai_client(config=self.config, api_key=key, timeout=60, max_retries=0)
                with path.open('rb') as audio:
                    raw = client.audio.transcriptions.create(model=model, file=audio, **options).model_dump(mode='json')
            if not isinstance(raw, dict) or not isinstance(raw.get('text'), str) or not raw['text'].strip():
                raise SpeechError('No speech was recognised. Please try again closer to the microphone.')
            return {'provider': provider, 'model': model, 'style': style if provider == 'mai' else 'literal_prompt',
                    'settings': options, 'text': raw['text'], 'words': raw.get('words', []),
                    'raw': raw, 'latency_ms': round((time.monotonic() - started) * 1000)}
        except (SpeechError, TrialDenied):
            raise
        except Exception:
            raise SpeechError('Transcription could not finish. Your recording is kept; try again.') from None

    def speak(self, text, voice_id):
        key = self.config.get('ELEVENLABS_API_KEY')
        if not key:
            logger.warning('Speech playback unavailable: ELEVENLABS_API_KEY is not configured')
            raise SpeechError('Audio playback is currently unavailable. You can still read the dialogue.')
        try:
            model = self.config.get('ELEVENLABS_MODEL', 'eleven_multilingual_v2')
            response = elevenlabs_call(self.config, text, model, voice_id,
                lambda: requests.post(f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}',
                headers={'xi-api-key': key}, json={'text': text,
                    'model_id': model,
                    'voice_settings': {'stability': 0.8, 'similarity_boost': 0.85, 'style': 0.0}}, timeout=(10, 60)))
            data = _response(response, 'Speech playback').content
            with tempfile.TemporaryDirectory() as tmp:
                audio = Path(tmp) / 'reply.mp3'
                audio.write_bytes(data)
                audio_info(audio)
            return data
        except (SpeechError, TrialDenied):
            raise
        except Exception:
            raise SpeechError('Speech playback could not be prepared. You can still read the reply.') from None
