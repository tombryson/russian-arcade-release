"""Local implementation of the asset boundary; metadata stays in SQLite."""
import hashlib
import io
import os
from pathlib import Path
import re
import tempfile
import wave

from PIL import Image, UnidentifiedImageError
from pydub import AudioSegment

from contracts.learning import text, reject
from repositories.learning_repository import LearningError, identifier, timestamp, transaction


class LocalAssetStore:
    MAX_BYTES = 10 * 1024 * 1024

    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, storage_key):
        if not re.fullmatch(r'[0-9a-f]{64}', storage_key):
            raise LearningError('invalid_asset', 'Invalid asset key.', 404)
        path = (self.root / storage_key[:2] / storage_key).resolve()
        if not path.is_relative_to(self.root):
            raise LearningError('invalid_asset', 'Invalid asset path.', 404)
        return path

    def put(self, data):
        if not data or len(data) > self.MAX_BYTES:
            reject('Assets must contain at most 10 MB.')
        media_type = self._media_type(data)
        digest = hashlib.sha256(data).hexdigest()
        target = self.path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.upload-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {'storage_key': digest, 'sha256': digest, 'byte_size': len(data), 'media_type': media_type}

    @staticmethod
    def _media_type(data):
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('PNG','JPEG','WEBP') or image.width * image.height > 16_000_000:
                    reject('Use a PNG, JPEG or WebP image up to 16 megapixels.')
                mime = Image.MIME[image.format]
                image.verify()
                return mime
        except Image.DecompressionBombError:
            reject('The image dimensions are too large.')
        except (UnidentifiedImageError, OSError):
            pass
        if data.startswith(b'ID3') or (len(data)>1 and data[0]==255 and data[1]&224==224):
            try:
                audio = AudioSegment.from_file(io.BytesIO(data), format='mp3', parameters=['-t','181'])
                if audio.channels not in (1,2) or audio.frame_rate < 8000 or not 0 < len(audio) <= 180000:
                    reject('Audio must be a valid recording of at most three minutes.')
                return 'audio/mpeg'
            except LearningError:
                raise
            except Exception:
                reject('The MP3 file could not be decoded.')
        try:
            with wave.open(io.BytesIO(data)) as audio:
                if audio.getnchannels() not in (1,2) or audio.getframerate() < 8000 or not 0 < audio.getnframes() / audio.getframerate() <= 180:
                    reject('Audio must be a short, valid mono/stereo WAV file.')
                expected = audio.getnframes() * audio.getnchannels() * audio.getsampwidth()
                if len(audio.readframes(audio.getnframes())) != expected:
                    reject('The WAV file is incomplete.')
                return 'audio/wav'
        except (wave.Error, EOFError):
            reject('Use a validated PNG, JPEG, WebP, MP3 or WAV file.')


def import_asset(db_path, store, data, source):
    source = text(source, 'Asset source', 500)
    metadata = store.put(data)
    with transaction(db_path, write=True) as conn:
        existing = conn.execute('SELECT id FROM learning_assets WHERE storage_key=?', (metadata['storage_key'],)).fetchone()
        if existing:
            return existing['id']
        asset_id = identifier()
        conn.execute('INSERT INTO learning_assets(id,storage_key,sha256,byte_size,media_type,source,created_at) VALUES (?,?,?,?,?,?,?)',
                     (asset_id, metadata['storage_key'], metadata['sha256'], metadata['byte_size'], metadata['media_type'], source, timestamp()))
    return asset_id
