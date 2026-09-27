from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import pickle
import os
import io
import logging
import time
import requests
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import GOOGLE_DRIVE_AUTO_AUTH

logger = logging.getLogger('GoogleDriveService')

APP_ROOT = Path(__file__).resolve().parent.parent

class GoogleDriveService:
    SCOPES = ['https://www.googleapis.com/auth/drive']
    CREDENTIALS_FILE = APP_ROOT / 'credentials.json'
    TOKEN_FILE = APP_ROOT / 'token.json'
    FILE_ID = '12O28VK4QwFxA5j1bGBXLNWyoBiWxdB_Y'
    CACHE_FILE = APP_ROOT / 'vocab_list_cache.txt'
    CACHE_TIMEOUT = 3600

    def __init__(self, auto_auth=GOOGLE_DRIVE_AUTO_AUTH, file_id=None,
                 credentials_file=None, token_file=None, cache_file=None):
        self.auto_auth = auto_auth
        self.service = None
        self.FILE_ID = file_id or self.FILE_ID
        self.CREDENTIALS_FILE = Path(credentials_file or self.CREDENTIALS_FILE)
        self.TOKEN_FILE = Path(token_file or self.TOKEN_FILE)
        self.CACHE_FILE = Path(cache_file or self.CACHE_FILE)
        self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_service(self):
        if self.service is None:
            self.service = self._get_service()
        return self.service

    def _get_service(self):
        logger.debug("Initializing Google Drive service")
        creds = None
        if os.path.exists(self.TOKEN_FILE):
            logger.debug(f"Found {self.TOKEN_FILE}")
            try:
                with open(self.TOKEN_FILE, 'rb') as token:
                    creds = pickle.load(token)
                    expiry_str = creds.expiry.isoformat() if creds.expiry else "None"
                    logger.debug(f"Token details: Valid={creds.valid}, Expiry={expiry_str}, Scope={creds.scopes}")
            except Exception as e:
                logger.error(f"Failed to load token: {str(e)}")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.debug("Attempting to refresh token")
                try:
                    session = requests.Session()
                    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
                    session.mount('https://', HTTPAdapter(max_retries=retries))
                    creds.refresh(Request(session=session))
                    logger.debug("Token refreshed")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {str(e)}")
                    creds = None

            if not creds:
                if not self.auto_auth:
                    raise Exception(
                        "Google Drive credentials are unavailable. "
                        "Set GOOGLE_DRIVE_AUTO_AUTH=true to run the browser OAuth flow."
                    )
                logger.debug(f"No valid credentials, running OAuth flow with {self.CREDENTIALS_FILE}")
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(self.CREDENTIALS_FILE, self.SCOPES)
                    creds = flow.run_local_server(port=0)
                    expiry_str = creds.expiry.isoformat() if creds.expiry else "None"
                    logger.debug(f"OAuth flow completed. Token details: Valid={creds.valid}, Expiry={expiry_str}, Scope={creds.scopes}")
                except Exception as e:
                    logger.error(f"OAuth flow failed: {str(e)}")
                    raise Exception(f"Failed to initialize Google Drive service: {str(e)}")

            try:
                with open(self.TOKEN_FILE, 'wb') as token:
                    pickle.dump(creds, token)
                    logger.debug(f"Saved new token to {self.TOKEN_FILE}")
            except Exception as e:
                logger.error(f"Failed to save token: {str(e)}")

        try:
            service = build('drive', 'v3', credentials=creds, cache_discovery=False)
            logger.debug("Google Drive service initialized")
            return service
        except Exception as e:
            logger.error(f"Failed to build Google Drive service: {str(e)}")
            raise Exception(f"Error initializing Google Drive service: {str(e)}")

    def download_vocab_list(self, max_retries=3, backoff_factor=1, *, force_refresh=False, allow_stale=True):
        logger.debug(f"Attempting to download vocab_list.txt, file ID: {self.FILE_ID}")
        if not force_refresh and os.path.exists(self.CACHE_FILE):
            cache_mtime = os.path.getmtime(self.CACHE_FILE)
            if time.time() - cache_mtime < self.CACHE_TIMEOUT:
                try:
                    with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                        content = f.read()
                        logger.debug(f"Using cached vocab list: {content[:50]}...")
                        return content
                except Exception as e:
                    logger.warning(f"Failed to read cache: {str(e)}")

        for attempt in range(max_retries):
            try:
                service = self._ensure_service()
                request = service.files().get_media(fileId=self.FILE_ID)
                file = io.BytesIO()
                downloader = MediaIoBaseDownload(file, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")
                file.seek(0)
                content = file.read().decode('utf-8')
                logger.debug(f"Downloaded content: {content[:50]}...")
                try:
                    with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.debug(f"Cached vocab list to {self.CACHE_FILE}")
                except Exception as e:
                    logger.warning(f"Failed to cache vocab list: {str(e)}")
                return content
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor * (2 ** attempt)
                    logger.debug(f"Retrying after {sleep_time} seconds")
                    time.sleep(sleep_time)
                else:
                    if allow_stale and os.path.exists(self.CACHE_FILE):
                        try:
                            with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                                content = f.read()
                                logger.debug(f"Falling back to cached vocab list: {content[:50]}...")
                                return content
                        except Exception as e:
                            logger.error(f"Failed to read cache: {str(e)}")
                    raise Exception(f"Error downloading vocab_list.txt: {str(e)}")

    def add_word(self, new_word):
        logger.debug(f"Adding word: {new_word}")
        try:
            content = self.download_vocab_list(force_refresh=True, allow_stale=False)
            words = [w.strip() for w in content.split('\n') if w.strip()]
            if not new_word.strip():
                logger.debug("Empty word provided")
                return False
            if new_word in words:
                logger.debug(f"Word {new_word} already exists")
                return False
            words.append(new_word.strip())
            self._upload_words(words)
            logger.debug(f"Added {new_word}")
            try:
                with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(words) + '\n')
                logger.debug(f"Updated cache with new word")
            except Exception as e:
                logger.warning(f"Failed to update cache: {str(e)}")
            return True
        except Exception as e:
            logger.error(f"Add failed: {str(e)}")
            raise

    def update_word(self, old_word, new_word):
        logger.debug(f"Updating word: {old_word} to {new_word}")
        try:
            content = self.download_vocab_list(force_refresh=True, allow_stale=False)
            words = [w.strip() for w in content.split('\n') if w.strip()]
            if old_word not in words:
                logger.debug(f"Word {old_word} not found")
                return False
            if new_word.strip() in words and new_word != old_word:
                logger.debug(f"Word {new_word} already exists")
                return False
            if not new_word.strip():
                logger.debug("Empty word provided")
                return False
            words = [new_word.strip() if w == old_word else w for w in words]
            self._upload_words(words)
            logger.debug(f"Updated {old_word} to {new_word}")
            try:
                with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(words) + '\n')
                logger.debug(f"Updated cache with updated word")
            except Exception as e:
                logger.warning(f"Failed to update cache: {str(e)}")
            return True
        except Exception as e:
            logger.error(f"Update failed: {str(e)}")
            raise

    def delete_word(self, word):
        logger.debug(f"Deleting word: {word}")
        try:
            content = self.download_vocab_list(force_refresh=True, allow_stale=False)
            words = [w.strip() for w in content.split('\n') if w.strip()]
            if word not in words:
                logger.debug(f"Word {word} not found")
                return False
            words.remove(word)
            self._upload_words(words)
            logger.debug(f"Deleted {word}")
            try:
                with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(words) + '\n')
                logger.debug(f"Updated cache after deletion")
            except Exception as e:
                logger.warning(f"Failed to update cache: {str(e)}")
            return True
        except Exception as e:
            logger.error(f"Delete failed: {str(e)}")
            raise

    def append_words(self, new_words):
        logger.debug(f"Appending {len(new_words)} words")
        try:
            content = self.download_vocab_list(force_refresh=True, allow_stale=False)
            words = [w.strip() for w in content.split('\n') if w.strip()]
            added = []
            for word in new_words:
                if word.strip() and word not in words:
                    words.append(word.strip())
                    added.append(word)
            if added:
                self._upload_words(words)
                logger.info(f"Appended words to cloud: {added}")
                try:
                    with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(words) + '\n')
                    logger.debug(f"Updated cache with appended words")
                except Exception as e:
                    logger.warning(f"Failed to update cache: {str(e)}")
            else:
                logger.debug("No new words to append")
            return True
        except Exception as e:
            logger.error(f"Append failed: {str(e)}")
            raise

    def _upload_words(self, words):
        logger.debug(f"Uploading {len(words)} words")
        try:
            content = '\n'.join(words) + '\n'
            file = io.BytesIO(content.encode('utf-8'))
            media = MediaIoBaseUpload(file, mimetype='text/plain')
            service = self._ensure_service()
            service.files().update(fileId=self.FILE_ID, media_body=media).execute()
            logger.debug("Upload completed")
        except Exception as e:
            logger.error(f"Upload failed: {str(e)}")
            raise Exception(f"Error uploading vocab_list.txt: {str(e)}")

    def update_vocab_list(self, content):
        logger.debug("Updating vocab_list.txt")
        try:
            words = [w.strip() for w in content.split('\n') if w.strip()]
            self._upload_words(words)
            logger.debug("vocab_list.txt updated")
            try:
                with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(words) + '\n')
                logger.debug(f"Updated cache with new vocab list")
            except Exception as e:
                logger.warning(f"Failed to update cache: {str(e)}")
            return True
        except Exception as e:
            logger.error(f"Update vocab list failed: {str(e)}")
            raise
