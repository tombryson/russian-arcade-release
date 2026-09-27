"""Draft import, immutable publication and child-safe content projection."""
import hashlib
import json
import unicodedata

from contracts.learning import text, validate_pack, reject
from contracts.flashcards import asset_ids, card_item, objective
from repositories.learning_repository import LearningError, encoded, identifier, require_access, timestamp, transaction


class ContentService:
    def __init__(self, db_path, store, clock=timestamp):
        self.db_path, self.store, self.clock = db_path, store, clock

    def import_draft(self, pack, *, access_id=None, expected_base=None):
        validate_pack(pack)
        with transaction(self.db_path, write=True) as conn:
            if access_id is not None:
                require_access(conn, access_id, self.clock(), adult=True)
            self._validate_references(conn, pack)
            kind = conn.execute('SELECT kind FROM learning_content WHERE id=?', (pack['id'],)).fetchone()
            if kind and kind['kind'] != pack['kind']:
                reject('An existing content ID cannot change kind.')
            conn.execute('INSERT OR IGNORE INTO learning_content(id,kind,created_at) VALUES (?,?,?)',
                         (pack['id'], pack['kind'], self.clock()))
            payload = encoded(pack)
            # A repeated local import is harmless; an edit creates a new version.
            existing = conn.execute('SELECT id FROM learning_content_versions v WHERE content_id=? AND payload=? AND status!=? AND NOT EXISTS(SELECT 1 FROM card_draft_archives a WHERE a.version_id=v.id) ORDER BY version DESC LIMIT 1',
                                    (pack['id'], payload, 'withdrawn')).fetchone()
            if existing:
                return existing['id']
            if expected_base is not None:
                latest = conn.execute('SELECT id FROM learning_content_versions WHERE content_id=? ORDER BY version DESC LIMIT 1', (pack['id'],)).fetchone()
                if (latest['id'] if latest else '') != expected_base:
                    raise LearningError('stale_content', 'A newer draft exists. Reload it before making more changes.', 409)
            number = conn.execute('SELECT COALESCE(MAX(version),0)+1 FROM learning_content_versions WHERE content_id=?', (pack['id'],)).fetchone()[0]
            version_id = identifier()
            conn.execute('INSERT INTO learning_content_versions(id,content_id,version,title,payload,source,created_at) VALUES (?,?,?,?,?,?,?)',
                         (version_id, pack['id'], number, pack['title'], payload, pack['source'], self.clock()))
            for asset_id in {asset for item in pack['items'] for asset in asset_ids(pack, item)}:
                conn.execute('INSERT INTO learning_content_assets VALUES (?,?)', (version_id, asset_id))
            for item in pack['items']:
                if item.get('word_id'):
                    conn.execute('INSERT INTO learning_content_words VALUES (?,?,?)', (version_id, item['id'], item['word_id']))
                if pack['kind'] == 'deck':
                    self._index_card(conn, version_id, pack, item, self.clock())
            return version_id

    @staticmethod
    def _index_card(conn, version_id, pack, item, now):
        card = card_item(pack, item)
        digest = objective(card)
        existing = conn.execute('SELECT objective_hash FROM card_definitions WHERE id=?', (card['card_id'],)).fetchone()
        if existing and existing[0] != digest:
            reject('This changes what the card tests. Give the replacement a new card ID; previous learning is retained.')
        if not existing:
            sibling = f"word:{card['word_id']}" if card.get('word_id') else f"sense:{card['sense_key']}"
            conn.execute('INSERT INTO card_definitions(id,word_id,form_id,retrieval_mode,sense_key,sibling_key,objective_hash,created_at) VALUES (?,?,?,?,?,?,?,?)',
                         (card['card_id'], card.get('word_id'), card.get('form_id'), card['direction'], card['sense_key'], sibling, digest, now))
        projection = conn.execute('SELECT card_id FROM card_versions WHERE content_version_id=? AND item_id=?',(version_id,item['id'])).fetchone()
        if projection and projection[0] != card['card_id']:
            reject('The existing card index does not match its immutable source.')
        if not projection:
            conn.execute('INSERT INTO card_versions(id,card_id,content_version_id,item_id) VALUES (?,?,?,?)',
                         (identifier(), card['card_id'], version_id, item['id']))

    def _validate_references(self, conn, pack):
        for item in pack['items']:
            if 'word_id' in item and not conn.execute('SELECT 1 FROM words WHERE id=?', (item['word_id'],)).fetchone():
                reject('A linked vocabulary record does not exist.')
            if item.get('form_id'):
                form = conn.execute('SELECT form FROM forms WHERE id=? AND word_id=?', (item['form_id'], item.get('word_id'))).fetchone()
                if not form:
                    reject('The target form must belong to the linked vocabulary word.')
                if item['type'] == 'cloze' and normalize_form(form['form']) != normalize_form(item['answer']):
                    reject('The cloze answer differs from the selected form. Select its exact form before publishing.')
            if pack['schema_version'] == 2 and item['type'] == 'cloze':
                forms = conn.execute('SELECT form FROM forms WHERE word_id=?', (item['word_id'],)).fetchall()
                lemma = conn.execute('SELECT lemma FROM words WHERE id=?',(item['word_id'],)).fetchone()[0]
                if normalize_form(item['answer']) not in {normalize_form(lemma)} | {normalize_form(f['form']) for f in forms}:
                    reject('The cloze answer must be a known form of the selected Russian word.')
            for asset_id in asset_ids(pack, item):
                asset = conn.execute('SELECT * FROM learning_assets WHERE id=?', (asset_id,)).fetchone()
                if not asset:
                    reject('A referenced asset does not exist.')
                path = self.store.path(asset['storage_key'])
                if not path.is_file() or path.stat().st_size != asset['byte_size'] or hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
                    reject('A referenced asset is missing or damaged. Restore it before publishing.')

    def publish(self, access_id, version_id, reviewer):
        reviewer = text(reviewer, 'Reviewer name', 80)
        with transaction(self.db_path, write=True) as conn:
            require_access(conn, access_id, self.clock(), adult=True)
            version = conn.execute('SELECT * FROM learning_content_versions WHERE id=?', (version_id,)).fetchone()
            if not version:
                raise LearningError('not_found', 'Content version not found.', 404)
            if version['status'] != 'draft':
                raise LearningError('publication_conflict', 'Only a draft can be published.', 409)
            pack = validate_pack(json.loads(version['payload']))
            if pack['kind']=='deck':
                latest=conn.execute('SELECT MAX(version) FROM learning_content_versions WHERE content_id=?',(version['content_id'],)).fetchone()[0]
                if version['version']!=latest:
                    raise LearningError('stale_content','A newer card draft exists. Review that version before publishing.',409)
            self._validate_references(conn, pack)
            if conn.execute('SELECT 1 FROM card_draft_archives WHERE version_id=?',(version_id,)).fetchone():
                raise LearningError('publication_conflict','This draft was discarded. Prepare a new draft to use it.',409)
            conn.execute("UPDATE learning_content_versions SET status='published',approved_by=?,approved_at=? WHERE id=?",
                         (reviewer, self.clock(), version_id))
            if pack['kind']=='deck':
                previous=conn.execute("SELECT id FROM learning_content_versions WHERE content_id=? AND status='published' AND version<? ORDER BY version DESC LIMIT 1",(version['content_id'],version['version'])).fetchone()
                if previous:
                    # Replacing a retrieval objective creates a new identity;
                    # retire the old card without touching any past schedules.
                    old_ids={r[0] for r in conn.execute('SELECT card_id FROM card_versions WHERE content_version_id=?',(previous['id'],))}
                    new_ids={r[0] for r in conn.execute('SELECT card_id FROM card_versions WHERE content_version_id=?',(version_id,))}
                    for card_id in old_ids-new_ids:
                        conn.execute('UPDATE card_definitions SET retired=1 WHERE id=?',(card_id,))

    def withdraw(self, access_id, version_id):
        with transaction(self.db_path, write=True) as conn:
            require_access(conn, access_id, self.clock(), adult=True)
            row = conn.execute("UPDATE learning_content_versions SET status='withdrawn' WHERE id=? AND status='published'", (version_id,))
            if not row.rowcount:
                raise LearningError('publication_conflict', 'Only published content can be withdrawn.', 409)

    def list_for_adult(self, access_id):
        with transaction(self.db_path) as conn:
            require_access(conn, access_id, self.clock(), adult=True)
            return [dict(row) for row in conn.execute('SELECT id,title,content_id,version,status,source,approved_by FROM learning_content_versions v WHERE NOT EXISTS (SELECT 1 FROM card_draft_archives a WHERE a.version_id=v.id) ORDER BY created_at DESC,version DESC')]

    def inspect(self, access_id, version_id):
        with transaction(self.db_path) as conn:
            require_access(conn, access_id, self.clock(), adult=True)
            row = conn.execute('SELECT * FROM learning_content_versions WHERE id=?', (version_id,)).fetchone()
            if not row:
                raise LearningError('not_found', 'Content version not found.', 404)
            result = dict(row)
            result['pack'] = json.loads(result.pop('payload'))
            return result


def published_version(conn, version_id):
    row = conn.execute("SELECT * FROM learning_content_versions WHERE id=? AND status='published'", (version_id,)).fetchone()
    if not row:
        raise LearningError('content_unavailable', 'This activity is not available. Your saved learning is kept.', 409)
    return row, json.loads(row['payload'])


def index_existing_decks(conn):
    """Migration-only projection; source payloads, approvals and IDs stay intact."""
    now = timestamp()
    for row in conn.execute("SELECT v.id,v.payload FROM learning_content_versions v JOIN learning_content c ON c.id=v.content_id WHERE c.kind='deck'").fetchall():
        pack = validate_pack(json.loads(row[1]))
        for item in pack['items']:
            ContentService._index_card(conn, row[0], pack, item, now)


def normalize_form(value):
    # Preserve ё and other spelling distinctions; only an explicit stress mark
    # and letter case are presentation differences for a linked form.
    return unicodedata.normalize('NFC', value).replace('\u0301', '').casefold()


def child_item(item, *, help_used=False, listened=False, transcript_used=False):
    result = {k: item[k] for k in ('id','type','prompt','choices','asset_ids') if k in item}
    result['has_hint'] = bool(item.get('hint'))
    if help_used and item.get('hint'):
        result['hint'] = item['hint']
    if item['type'] == 'listening_choice':
        result.update(audio=item['audio'], listened=listened, has_transcript=True,
                      transcript=item['transcript'] if transcript_used else None)
    return result
