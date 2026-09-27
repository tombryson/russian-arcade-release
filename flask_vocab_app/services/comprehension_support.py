"""Validate saved disclosure receipts without inventing support for old tasks."""
import json
import re

VERSION = 'comprehension-support-v1'


def receipts(conn, task):
    payload = task['payload']
    task_id = task.get('task_id', task.get('id'))
    profile_id = task['profile_id']
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='comprehension_support_receipts'").fetchone():
        if payload.get('support_version') == VERSION:
            raise ValueError('The task is missing its support store.')
        return []
    rows = conn.execute('SELECT id,profile_id,revision,request_key,kind,detail_json,created_at,inherited_from '
                        'FROM comprehension_support_receipts WHERE task_id=? ORDER BY rowid', (task_id,)).fetchall()
    if payload.get('support_version') != VERSION:
        if rows:
            raise ValueError('An older task cannot acquire new support evidence.')
        return []
    parent = payload.get('parent_task_id')
    if parent:
        row = conn.execute('SELECT profile_id,story_id,payload_json,rowid,created_at FROM comprehension_tasks WHERE id=?', (parent,)).fetchone()
        current = conn.execute('SELECT rowid FROM comprehension_tasks WHERE id=?', (task_id,)).fetchone()[0]
        if (row is None or tuple(row[:2]) != (profile_id, task['story_id']) or row[3] >= current
                or type(row[4]) is not int or row[4] > task['created_at']):
            raise ValueError('Question versions require their original preceding task.')
        previous = json.loads(row[2])
        if (previous.get('support_version') != VERSION or previous['questions'] != payload['questions'][:len(previous['questions'])]
                or any(previous.get(key) != payload.get(key) for key in ('text', 'practice_mode', 'audio'))):
            raise ValueError('Question versions cannot change the passage, mode or recording.')
    result = []
    inherited = set()
    attempts = [row[0] for row in conn.execute('SELECT created_at FROM comprehension_attempts WHERE task_id=? ORDER BY rowid', (task_id,))]
    for row in rows:
        identity, owner, revision, request_key, kind, raw, created, source_id = row
        if (owner != profile_id or type(revision) is not int or not 0 <= revision <= task['revision']
                or not re.fullmatch(r'[a-f0-9]{32}', identity) or not re.fullmatch(r'[a-f0-9]{32}', request_key)
                or type(created) is not int or created < task['created_at']):
            raise ValueError('Support does not belong to this task and revision.')
        if revision and (revision > len(attempts) or type(attempts[revision - 1]) is not int or created < attempts[revision - 1]):
            raise ValueError('Support cannot precede the earlier answer named by its revision.')
        detail = json.loads(raw)
        if kind == 'listened':
            audio = payload.get('audio')
            if payload.get('practice_mode') != 'listening' or not audio or detail != {'audio_sha256': audio['sha256']}:
                raise ValueError('Playback does not match the frozen recording.')
        elif kind == 'transcript':
            if payload.get('practice_mode') != 'listening' or detail != {}:
                raise ValueError('Transcript disclosure belongs to listening practice.')
        elif kind in ('translation', 'hint'):
            if not isinstance(detail, dict) or set(detail) != {'word'} or not isinstance(detail['word'], str):
                raise ValueError('Word support needs the disclosed word.')
            from services.game_vocabulary_discovery import _occurrences
            if not 1 <= len(detail['word']) <= 100 or not _occurrences(payload['text'], detail['word']):
                raise ValueError('Word support must refer to this passage.')
            if payload.get('practice_mode') == 'listening' and not any(item['kind'] == 'transcript' for item in result):
                raise ValueError('Listening word help requires transcript disclosure first.')
        else:
            raise ValueError('Unknown comprehension support.')
        if source_id:
            source = conn.execute('SELECT task_id,profile_id,kind,detail_json,created_at FROM comprehension_support_receipts WHERE id=?', (source_id,)).fetchone()
            if (not parent or revision != 0 or source_id in inherited or source is None
                    or tuple(source[:4]) != (parent, profile_id, kind, raw)
                    or type(source[4]) is not int or source[4] > task['created_at']):
                raise ValueError('Inherited support must retain the original disclosure.')
            inherited.add(source_id)
        result.append({'id': identity, 'revision': revision, 'kind': kind, 'created_at': created})
    if parent:
        expected = {row[0] for row in conn.execute('SELECT id FROM comprehension_support_receipts WHERE task_id=?', (parent,))}
        if inherited != expected:
            raise ValueError('A new question set must retain all earlier support.')
    initial = payload.get('initial_support', [])
    if initial not in ([], ['transcript']) or (parent and initial):
        raise ValueError('Invalid initial passage exposure.')
    if initial and not any(row['kind'] == 'transcript' and row['revision'] == 0 for row in result):
        raise ValueError('A supplied passage must retain its transcript receipt.')
    return result


def attempt_support(conn, task, ordinal, receipt_ids, *, created_at):
    expected = {'model_answer'} if task['payload']['prior_feedback'] or ordinal else set()
    rows = receipts(conn, task)
    selected = [row for row in rows if row['revision'] <= ordinal]
    if (not isinstance(receipt_ids, list) or any(not isinstance(value, str) for value in receipt_ids)
            or len(receipt_ids) != len(set(receipt_ids))
            or set(receipt_ids) != {row['id'] for row in selected}
            or any(row['created_at'] > created_at for row in selected)):
        raise ValueError('An answer must retain the exact support available at submission.')
    expected.update(row['kind'] for row in selected if row['kind'] != 'listened')
    if task['payload'].get('practice_mode') == 'listening' and not any(row['kind'] in ('listened', 'transcript') for row in selected):
        raise ValueError('Listening answers require playback or a disclosed transcript.')
    return sorted(expected)
