"""Keep saved activity media behind the same local profile as its activity.

Lesson sources and the common card/vocabulary library remain shared. Old media
URLs are retained; this read check does not rename or rewrite existing files.
"""
import json
import posixpath
from pathlib import Path
from urllib.parse import unquote, urlsplit

from flask import abort, current_app, session

from repositories.learning_repository import transaction
from utils.household_access import active_profile_id


def _matches(reference, bucket, filename):
    if not isinstance(reference, str) or not reference:
        return False
    try:
        path = unquote(urlsplit(reference).path)
    except ValueError:
        return False
    prefix = f'/static/{bucket}/'
    if path.startswith(prefix):
        relative = path[len(prefix):]
    elif bucket == 'uploads' and prefix in path:
        relative = path.split(prefix, 1)[1]
    elif bucket == 'uploads' and Path(path).is_absolute():
        try:
            relative = Path(path).relative_to(current_app.config['UPLOAD_FOLDER']).as_posix()
        except ValueError:
            return False
    else:
        return False
    return posixpath.normpath(relative) == posixpath.normpath(filename)


def require_activity_media(bucket, filename):
    # The global route boundary already requires an unlocked household adult.
    if current_app.config['WORD_POST_HOUSEHOLD_ENABLED']:
        return
    with transaction(current_app.config['DB_PATH']) as conn:
        profile = active_profile_id(conn)
        owners = set()
        for row in conn.execute('SELECT owner_profile_id,audio_url,image_url FROM saved_stories'):
            if any(_matches(row[field], bucket, filename) for field in ('audio_url','image_url')):
                owners.add(row['owner_profile_id'] or 'personal-learning')
        for row in conn.execute('SELECT owner_profile_id,audio_url FROM sentences'):
            if _matches(row['audio_url'], bucket, filename):
                owners.add(row['owner_profile_id'] or 'personal-learning')
        # A file deliberately used as a shared lesson source remains available
        # through the existing URL as well as the lesson source endpoint.
        for row in conn.execute('SELECT pdf_path,images FROM lessons'):
            try:
                images = json.loads(row['images'] or '[]')
            except (ValueError, TypeError):
                images = []
            references = [row['pdf_path'], *(images if isinstance(images,list) else [])]
            if any(_matches(value,bucket,filename) for value in references):
                return
        # A submitted activity URL cannot grant access to somebody else's
        # existing private file. Ambiguous private references fail closed.
        if owners - {profile}:
            abort(404)
        if owners:
            return
        # Reading can be generated before Save. Its preview media belongs to
        # the current session until a persisted story provides the owner link.
        if bucket == 'media' and Path(filename).name.startswith(('story_','sentence_')):
            preview = session.get('generated_story_media')
            if isinstance(preview,list) and any(_matches(value,bucket,filename) for value in preview):
                return
            abort(404)
        # Non-activity media (for example shared vocabulary/card illustrations)
        # keeps its existing authenticated shared-library behavior.
