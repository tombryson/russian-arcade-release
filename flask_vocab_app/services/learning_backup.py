"""Consistent SQLite snapshot plus the local Word Post asset set."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time

from repositories.learning_repository import LearningError


def backup_learning_store(db_path, store, destination, lesson_upload_folder=None):
    destination = Path(destination).resolve()
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    marker = destination / 'INCOMPLETE'
    marker.write_text('Do not restore this backup until its manifest has been verified.\n')
    database = destination / 'vocab.db'
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(database)) as snapshot:
            source.backup(snapshot)
            snapshot.row_factory = sqlite3.Row
            if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or snapshot.execute('PRAGMA foreign_key_check').fetchone():
                raise LearningError('backup_invalid', 'Database integrity checks failed; the backup is incomplete.')
            assets = [dict(row) for row in snapshot.execute('SELECT id,storage_key,sha256,byte_size,media_type FROM learning_assets ORDER BY id')]
            recordings = []
            live_recordings = []
            step_recordings = []
            lesson_files = []
            legacy_lessons = []
            if snapshot.execute("SELECT 1 FROM sqlite_master WHERE name='lesson_files'").fetchone():
                if snapshot.execute("SELECT 1 FROM lesson_revisions WHERE state='processing' AND lease_until>?",(int(time.time()),)).fetchone() or snapshot.execute("SELECT 1 FROM lesson_attempts WHERE state='checking' AND lease_until>?",(int(time.time()),)).fetchone():
                    raise LearningError('backup_busy', 'Let lesson preparation and answer checking finish before backing up.')
                lesson_files = [dict(row) for row in snapshot.execute('SELECT * FROM lesson_files')]
            if snapshot.execute("SELECT 1 FROM sqlite_master WHERE name='lessons'").fetchone():
                legacy_lessons = [dict(row) for row in snapshot.execute('SELECT id,pdf_path,images FROM lessons')]
            if snapshot.execute("SELECT 1 FROM sqlite_master WHERE name='live_conversation_recordings'").fetchone():
                if snapshot.execute("SELECT 1 FROM live_conversation_recordings WHERE state='capturing' OR lease_until>?", (int(time.time()),)).fetchone() or snapshot.execute("SELECT 1 FROM live_conversation_sessions WHERE state IN ('connecting','live','ending')").fetchone():
                    raise LearningError('backup_busy', 'End live conversations and let their recordings finish before backing up.')
                live_recordings = [row[0] for row in snapshot.execute('SELECT filename FROM live_conversation_recordings')]
            if snapshot.execute("SELECT 1 FROM sqlite_master WHERE name='conversation_turns'").fetchone():
                if snapshot.execute('SELECT 1 FROM conversation_turns WHERE lease_until>?', (int(time.time()),)).fetchone():
                    raise LearningError('backup_busy', 'Wait for conversation processing to finish before backing up recordings.')
                for row in snapshot.execute('SELECT audio_filename,reply_audio_filename FROM conversation_turns'):
                    recordings.extend(name for name in row if name)
                audio_root = Path(db_path).resolve().parent / 'conversation-audio'
                for row in snapshot.execute('SELECT id FROM conversation_sessions'):
                    greeting = row['id'] + '-greeting.mp3'
                    if (audio_root / greeting).is_file(): recordings.append(greeting)
            if snapshot.execute("SELECT 1 FROM sqlite_master WHERE name='step_conversation_sessions'").fetchone():
                if snapshot.execute("SELECT 1 FROM step_conversation_sessions WHERE state='preparing' AND lease_until>?", (int(time.time()),)).fetchone():
                    raise LearningError('backup_busy', 'Let step-through dialogue preparation finish before backing up.')
                step_root = Path(db_path).resolve().parent / 'step-conversation-audio'
                for row in snapshot.execute('SELECT id,dialogue_json FROM step_conversation_sessions WHERE dialogue_json IS NOT NULL'):
                    for turn in json.loads(row['dialogue_json'])['turns']:
                        for kind in ('npc', 'reply'):
                            filename = f'{row["id"]}-{turn["id"]}-{kind}.mp3'
                            if Path(filename).name != filename:
                                raise LearningError('backup_invalid', 'Invalid step-through recording path in the database.')
                            if (step_root / filename).is_file():
                                step_recordings.append(filename)
    for asset in assets:
        source = store.path(asset['storage_key'])
        target = destination / 'assets' / asset['storage_key'][:2] / asset['storage_key']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if target.stat().st_size != asset['byte_size'] or hashlib.sha256(target.read_bytes()).hexdigest() != asset['sha256']:
            raise LearningError('backup_invalid', 'An asset failed its checksum; the backup is incomplete.')
    audio_manifest = []
    for name in sorted(set(recordings)):
        if Path(name).name != name:
            raise LearningError('backup_invalid', 'Invalid conversation recording path in the database.')
        source = Path(db_path).resolve().parent / 'conversation-audio' / name
        target = destination / 'conversation-audio' / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            shutil.copyfile(source, target)
        except OSError:
            raise LearningError('backup_invalid', 'A conversation recording is missing; the backup is incomplete.') from None
        audio_manifest.append({'file': 'conversation-audio/'+name, 'sha256':hashlib.sha256(target.read_bytes()).hexdigest(), 'byte_size':target.stat().st_size})
    live_manifest = []
    for name in sorted(set(live_recordings)):
        if Path(name).name != name:
            raise LearningError('backup_invalid', 'Invalid live recording path in the database.')
        source = Path(db_path).resolve().parent / 'live-conversation-audio' / name
        target = destination / 'live-conversation-audio' / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            shutil.copyfile(source,target)
        except OSError:
            raise LearningError('backup_invalid', 'A live recording is missing; the backup is incomplete.') from None
        live_manifest.append({'file':'live-conversation-audio/'+name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'byte_size':target.stat().st_size})
    from services.lesson_files import LessonFiles, digest
    step_manifest = []
    for name in sorted(set(step_recordings)):
        source = Path(db_path).resolve().parent / 'step-conversation-audio' / name
        target = destination / 'step-conversation-audio' / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            shutil.copyfile(source, target)
        except OSError:
            raise LearningError('backup_invalid', 'A step-through recording is missing; the backup is incomplete.') from None
        step_manifest.append({'file': 'step-conversation-audio/' + name,
                              'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'byte_size': target.stat().st_size})
    lesson_store = LessonFiles(db_path, lesson_upload_folder)
    lesson_manifest = {}

    def copy_lesson(data, key, expected_size=None):
        if digest(data)!=key or (expected_size is not None and len(data)!=expected_size):
            raise LearningError('backup_invalid','A lesson file failed its checksum; the backup is incomplete.')
        target = destination / 'lesson-assets' / key[:2] / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        lesson_manifest[key] = {'file':str(target.relative_to(destination)),'sha256':key,'byte_size':len(data)}

    for item in lesson_files:
        try: data=lesson_store.path(item['digest']).read_bytes()
        except OSError: raise LearningError('backup_invalid','A lesson source or page is missing; the backup is incomplete.') from None
        copy_lesson(data,item['digest'],item['byte_size'])
    # Make legacy source references portable in the snapshot only. Live rows,
    # original files and historical prompt/response arrays are never changed.
    with closing(sqlite3.connect(database)) as snapshot:
        for lesson in legacy_lessons:
            def portable(reference):
                if not reference:return reference
                data=lesson_store.legacy(reference).read_bytes()
                key=digest(data)
                copy_lesson(data,key)
                return 'lesson-asset:'+key
            pdf=portable(lesson['pdf_path'])
            images=[portable(path) for path in json.loads(lesson['images'] or '[]')]
            snapshot.execute('UPDATE lessons SET pdf_path=?,images=? WHERE id=?',(pdf,json.dumps(images),lesson['id']))
        snapshot.commit()
        if snapshot.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or snapshot.execute('PRAGMA foreign_key_check').fetchone():
            raise LearningError('backup_invalid','The lesson snapshot failed its integrity checks.')
    manifest = {'schema': 1, 'database': {'file': 'vocab.db', 'sha256': hashlib.sha256(database.read_bytes()).hexdigest()},
                'assets': assets, 'conversation_audio': audio_manifest, 'live_conversation_audio': live_manifest,
                'step_conversation_audio': step_manifest,
                'lesson_files':list(lesson_manifest.values()),
                'scope': 'Application SQLite database, Word Post assets, lesson originals/pages and private conversation recordings. Other legacy media, external Anki and Drive are separate backups.'}
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    marker.unlink()
    return manifest
