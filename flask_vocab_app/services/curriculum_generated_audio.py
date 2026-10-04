"""Prepare private curriculum speech from an already validated, frozen transcript.

The caller persists the plan and owns claims/retries. This boundary makes one
budgeted speech request, decodes its result, then publishes immutable files. It
never searches another workspace or substitutes a stock recording.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import tempfile

from pydub import AudioSegment

from repositories.learning_repository import LearningError
from services.elevenlabs_service import ElevenLabsService, voice_settings_for_model

VERSION = 'curriculum-generated-audio-v1'
DIRECTORY = 'curriculum-audio'
MAX_BYTES = 10 * 1024 * 1024
_DESCRIPTOR_FIELDS = {'kind', 'storage_key', 'sha256', 'transcript_sha256', 'spec_sha256', 'duration_ms', 'size_bytes'}
_SPEC_FIELDS = {'version', 'text', 'transcript_sha256', 'provider', 'model', 'voice_id', 'voice_settings'}


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def transcript_hash(transcript):
    if (not isinstance(transcript, str) or not 1 <= len(transcript) <= 4000
            or not transcript.strip() or '\x00' in transcript):
        raise ValueError('A recording needs its exact, bounded transcript.')
    return _digest(transcript.encode('utf-8'))


def _validate_spec(spec):
    if (not isinstance(spec, dict) or set(spec) != _SPEC_FIELDS
            or spec['version'] != VERSION or spec['provider'] != 'elevenlabs'
            or spec['voice_settings'] != voice_settings_for_model(spec['model'])
            or spec['transcript_sha256'] != transcript_hash(spec['text'])):
        raise ValueError('The frozen recording plan has changed.')
    for name in ('model', 'voice_id'):
        if not isinstance(spec[name], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', spec[name]):
            raise ValueError('The recording plan needs a configured voice and model.')
    return spec


def plan_audio(transcript, speech_provider):
    """Choose from the existing voice list once, before saving the durable job."""
    config = speech_provider.config
    voices = tuple(getattr(speech_provider, 'voice_ids', None) or config.get('ELEVENLABS_VOICE_IDS') or ())
    if not voices:
        raise ValueError('Audio playback is currently unavailable. Please try again later.')
    model = getattr(speech_provider, 'model', None) or config.get('ELEVENLABS_MODEL') or 'eleven_v4'
    return _validate_spec({'version': VERSION, 'text': transcript, 'transcript_sha256': transcript_hash(transcript),
                          'provider': 'elevenlabs', 'model': model, 'voice_id': random.choice(voices),
                          'voice_settings': voice_settings_for_model(model)})


def upgrade_pending_audio_spec(spec, speech_provider):
    """Move an unrecorded plan to v4 without choosing another voice or text.

    Published and staged recordings retain their original spec and hash. The
    caller must persist this replacement before attempting speech generation.
    """
    _validate_spec(spec)
    model = (getattr(speech_provider, 'model', None)
             or speech_provider.config.get('ELEVENLABS_MODEL') or 'eleven_v4')
    if model == 'eleven_v4' and spec['model'] != model:
        return _validate_spec({**spec, 'model': model, 'voice_settings': voice_settings_for_model(model)})
    return spec


def validate_descriptor(audio, transcript):
    """Validate the private reference without requiring its workspace on import."""
    if not isinstance(audio, dict) or set(audio) != _DESCRIPTOR_FIELDS or audio['kind'] != 'generated':
        raise ValueError('The recording needs its saved generation identity.')
    for field in ('storage_key', 'sha256', 'transcript_sha256', 'spec_sha256'):
        if not isinstance(audio[field], str) or not re.fullmatch(r'[a-f0-9]{64}', audio[field]):
            raise ValueError('The recording needs its immutable file identity.')
    if (audio['transcript_sha256'] != transcript_hash(transcript)
            or audio['storage_key'] != _digest((audio['spec_sha256'] + ':' + audio['sha256']).encode())
            or type(audio['duration_ms']) is not int or not 1000 <= audio['duration_ms'] <= 180000
            or type(audio['size_bytes']) is not int or not 0 < audio['size_bytes'] <= MAX_BYTES):
        raise ValueError('The recording does not match its frozen transcript or duration.')
    return audio


def _root(media_root):
    # No fallback into the source tree: runtime speech belongs to one workspace.
    if media_root is None:
        raise ValueError('A workspace media directory is required.')
    root = Path(media_root).resolve()
    private = root / DIRECTORY
    if not private.resolve().is_relative_to(root):
        raise ValueError('The recording directory is outside this workspace.')
    return root, private


def _paths(media_root, storage_key):
    if not isinstance(storage_key, str) or not re.fullmatch(r'[a-f0-9]{64}', storage_key):
        raise ValueError('Invalid recording storage key.')
    root, private = _root(media_root)
    path = private / storage_key[:2] / (storage_key + '.mp3')
    manifest = path.with_suffix('.json')
    if any(not candidate.resolve().is_relative_to(root) for candidate in (path, manifest)):
        raise ValueError('The recording is outside this workspace.')
    return path, manifest


def _atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.curriculum-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _decoded_duration(path):
    try:
        decoded = AudioSegment.from_file(path, format='mp3', parameters=['-t', '181'])
        duration_ms = len(decoded)
        if (not 1000 <= duration_ms <= 180000 or decoded.channels not in (1, 2)
                or decoded.frame_rate < 8000 or not math.isfinite(decoded.dBFS)):
            raise ValueError('The recording needs playable speech lasting 1–180 seconds.')
        return duration_ms
    except Exception:
        raise ValueError('This recording could not be checked. Please retry.') from None


def generate_audio(spec, speech_provider, media_root):
    """One explicit generation attempt, outside any database transaction."""
    _validate_spec(spec)
    if upgrade_pending_audio_spec(spec, speech_provider) != spec:
        raise ValueError('Save the updated recording plan before preparing its audio.')
    root, _ = _root(media_root)
    # The new instance retains the configured billing wrappers and credentials,
    # while the persisted voice/model stay fixed if configuration later changes.
    config = speech_provider.config
    api_key = getattr(speech_provider, 'api_key', None) or config.get('ELEVENLABS_API_KEY')
    if not api_key:
        raise ValueError('Audio playback is currently unavailable. Please try again later.')
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.curriculum-speech-', dir=root) as directory:
        service = ElevenLabsService(api_key, directory, voice_ids=(spec['voice_id'],),
                                    model=spec['model'], config=config)
        result = service.generate_audio(spec['text'], 'recording.mp3')
        path = Path(directory) / 'recording.mp3'
        if result != 'recording.mp3' or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise ValueError('This recording could not be prepared. Please retry.')
        data = path.read_bytes()
        if not (data.startswith(b'ID3') or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224)):
            raise ValueError('The recording was not returned as MP3 audio.')
        duration_ms = _decoded_duration(path)
    audio_hash, spec_hash = _digest(data), _digest(_json(spec))
    audio = {'kind': 'generated', 'storage_key': _digest((spec_hash + ':' + audio_hash).encode()),
             'sha256': audio_hash, 'transcript_sha256': spec['transcript_sha256'], 'spec_sha256': spec_hash,
             'duration_ms': duration_ms, 'size_bytes': len(data)}
    validate_descriptor(audio, spec['text'])
    target, manifest = _paths(root, audio['storage_key'])
    target.parent.mkdir(parents=True, exist_ok=True)
    target, manifest = _paths(root, audio['storage_key'])
    metadata = _json({'version': VERSION, 'spec': spec, 'audio': audio})
    # A content-addressed identity cannot silently replace different saved bytes.
    for path, expected in ((target, data), (manifest, metadata)):
        if path.exists() and path.read_bytes() != expected:
            raise ValueError('This saved recording has changed. Start another practice activity.')
    if not target.exists():
        _atomic_write(target, data)
    if not manifest.exists():
        _atomic_write(manifest, metadata)
    return audio


def verify_generated_audio(audio, transcript, media_root, *, check_duration=False):
    """Check the frozen descriptor, transcript and bytes before owned playback."""
    try:
        validate_descriptor(audio, transcript)
        path, manifest_path = _paths(media_root, audio['storage_key'])
        if (not path.is_file() or path.stat().st_size != audio['size_bytes']
                or not manifest_path.is_file() or manifest_path.stat().st_size > 25000):
            raise ValueError('Missing recording.')
        metadata = json.loads(manifest_path.read_text('utf-8'))
        if (set(metadata) != {'version', 'spec', 'audio'} or metadata['version'] != VERSION
                or metadata['audio'] != audio):
            raise ValueError('Changed recording metadata.')
        spec = _validate_spec(metadata['spec'])
        if (spec['text'] != transcript or _digest(_json(spec)) != audio['spec_sha256']
                or _digest(path.read_bytes()) != audio['sha256']):
            raise ValueError('Changed recording.')
        if check_duration and _decoded_duration(path) != audio['duration_ms']:
            raise ValueError('Changed recording duration.')
        return path
    except (OSError, ValueError, KeyError, TypeError):
        raise LearningError('audio_unavailable', 'This recording is unavailable. Try again or read the transcript.', 409) from None


def validate_saved_generated_audio(conn, media_root=None, *, require_audio=True):
    """Collect published and staged runtime recordings for backup/import.

    Only database references count. In-flight temporary provider files are never
    copied. An accepted recording awaiting publication still belongs to the
    frozen job and must survive a retry or account import.
    """
    files = {}

    def collect(audio, transcript, voice=None):
        validate_descriptor(audio, transcript)
        if voice is not None:
            _validate_spec(voice)
            if voice['text'] != transcript or _digest(_json(voice)) != audio['spec_sha256']:
                raise ValueError('The prepared recording no longer matches its saved voice plan.')
        if require_audio:
            path = verify_generated_audio(audio, transcript, media_root, check_duration=True)
            manifest = path.with_suffix('.json')
            files[str(path)] = audio['sha256']
            files[str(manifest)] = _digest(manifest.read_bytes())

    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='learning_content_versions'").fetchone():
        for row in conn.execute('SELECT payload FROM learning_content_versions'):
            pack = json.loads(row[0])
            for item in pack.get('items', []):
                audio = item.get('audio')
                if item.get('type') == 'listening_choice' and isinstance(audio, dict) and audio.get('kind') == 'generated':
                    collect(audio, item.get('transcript'))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='curriculum_situations'").fetchone():
        for row in conn.execute('SELECT audio_json,document_json,voice_json FROM curriculum_situations WHERE audio_json IS NOT NULL'):
            if not row[1] or not row[2]:
                raise ValueError('The prepared recording has no saved transcript or voice plan.')
            collect(json.loads(row[0]), json.loads(row[1])['response']['text'], json.loads(row[2]))
    return files
