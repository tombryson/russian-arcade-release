"""Learner-selected occurrences, saved before any paid card generation."""
import json

from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, transaction
from services.lesson_ocr import RUSSIAN
from services.learning_content import normalize_form


class LessonSelection:
    def __init__(self, cards, ocr):
        self.cards, self.ocr = cards, ocr
        self.db_path = cards.db_path

    def pending(self, credential, lesson_id, revision_id):
        self.cards.companion.revision(revision_id,lesson_id)
        with transaction(self.db_path) as conn:
            owner=self.cards.generator._owner(conn,credential)
            rows=conn.execute('SELECT p.*,r.state AS request_state,r.batch_id,i.status AS item_status '
                              'FROM lesson_word_picks p LEFT JOIN lesson_card_requests r ON r.id=p.request_id '
                              'LEFT JOIN native_card_generation_items i ON i.id=p.item_id '
                              'WHERE p.owner_id=? AND p.lesson_id=? AND p.revision_id=? AND p.selected=1 ORDER BY p.created_at,p.rowid',
                              (owner,lesson_id,revision_id)).fetchall()
        result=[]
        for r in rows:
            status='saved' if r['item_id'] else 'preparing' if r['request_state'] in ('pending','processing') else 'pending'
            result.append({k:r[k] for k in ('id','page','surface','context','original','error','batch_id','region_id')} | {'token_key':r['region_id'] or r['token_key'], 'status':status})
        return {'picks':result,'pending_count':sum(p['status']=='pending' for p in result)}

    def page(self, credential, lesson_id, revision_id, number):
        self.pending(credential, lesson_id, revision_id)
        data = self.ocr.page(lesson_id, revision_id, number)
        with transaction(self.db_path) as conn:
            owner = self.cards.generator._owner(conn, credential)
            rows = conn.execute('SELECT p.*,r.payload FROM lesson_word_picks p JOIN lesson_word_regions r ON r.id=p.region_id WHERE p.owner_id=? AND p.revision_id=? AND p.page=?', (owner, revision_id, number)).fetchall()
        words = {w['key']: w for w in data['words']}
        for pick in rows:
            key = pick['region_id']
            if key not in words and pick['selected']:
                words[key] = {**json.loads(pick['payload']), 'key': key}
            if key in words:
                if pick['reading_confirmed'] or not words[key].get('needs_check'):
                    words[key].update(surface=pick['surface'], context=pick['context'], needs_check=False, remembered=True)
        data['words'] = list(words.values())
        return data

    @staticmethod
    def reading(surface):
        if not isinstance(surface, str) or len(surface)>100 or not RUSSIAN.fullmatch(surface.strip()):
            raise LearningError('invalid_word', 'Enter one Russian word as it appears on the page.', 422)
        return surface.strip()

    @staticmethod
    def context(word, surface):
        return next((s['context'] for s in word.get('suggestions', []) if normalize_form(s['surface']) == normalize_form(surface)), word.get('context', ''))

    def choose(self, credential, lesson_id, revision_id, number, token, selected, *, surface=None, confirmed=False):
        if type(selected) is not bool or not isinstance(token, str) or type(confirmed) is not bool:
            raise LearningError('invalid_selection', 'Choose a word on the page.', 422)
        self.pending(credential, lesson_id, revision_id)
        with transaction(self.db_path) as conn:
            owner = self.cards.generator._owner(conn, credential)
            old = conn.execute('SELECT * FROM lesson_word_picks WHERE owner_id=? AND revision_id=? AND page=? AND (region_id=? OR token_key=?)', (owner, revision_id, number, token, token)).fetchone()
        # Removing a legacy selection never requires guessing its old location.
        word = None if old and not selected else self.ocr.region(lesson_id, revision_id, number, token)
        if selected:
            if word.get('needs_check') and not (old and old['reading_confirmed']) and not confirmed:
                raise LearningError('check_reading', 'Check this reading against the word on the page.', 409)
            value = self.reading(surface if confirmed and surface is not None else old['surface'] if old else word['surface'])
            context = self.context(word, value) if confirmed or not old else old['context']
        with transaction(self.db_path, write=True) as conn:
            owner = self.cards.generator._owner(conn, credential)
            existing = conn.execute('SELECT p.*,r.state FROM lesson_word_picks p LEFT JOIN lesson_card_requests r ON r.id=p.request_id WHERE p.owner_id=? AND p.revision_id=? AND p.page=? AND (p.region_id=? OR p.token_key=?)', (owner, revision_id, number, token, token)).fetchone()
            if existing:
                if existing['item_id'] or existing['state'] in ('pending','processing'):
                    raise LearningError('selection_in_use', 'This word already belongs to a card set. Open the set to continue.', 409)
                conn.execute('UPDATE lesson_word_picks SET selected=? WHERE id=?', (int(selected), existing['id']))
                if selected and confirmed:
                    conn.execute('UPDATE lesson_word_picks SET surface=?,context=?,reading_confirmed=1,request_id=NULL,error=NULL WHERE id=?', (value, context, existing['id']))
            elif selected:
                count = conn.execute('SELECT COUNT(*) FROM lesson_word_picks WHERE owner_id=? AND lesson_id=? AND selected=1 AND item_id IS NULL', (owner,lesson_id)).fetchone()[0]
                if count >= 100:
                    raise LearningError('selection_full', 'Create some of your pending cards before adding more words.', 409)
                conn.execute('INSERT INTO lesson_word_picks(id,owner_id,lesson_id,revision_id,page,token_key,surface,context,original,created_at,region_id,reading_confirmed) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                             (identifier(),owner,lesson_id,revision_id,number,token,value,context,word['ocr'],self.cards.clock(),token,int(confirmed)))
        return self.pending(credential, lesson_id, revision_id)

    def edit(self, credential, lesson_id, revision_id, pick_id, surface):
        surface=self.reading(surface)
        with transaction(self.db_path,write=True) as conn:
            owner=self.cards.generator._owner(conn,credential)
            row=conn.execute('SELECT p.*,r.state FROM lesson_word_picks p LEFT JOIN lesson_card_requests r ON r.id=p.request_id WHERE p.id=? AND p.owner_id=? AND p.lesson_id=? AND p.revision_id=?',
                             (pick_id,owner,lesson_id,revision_id)).fetchone()
            if not row:
                raise LearningError('not_found','This selected word was not found.',404)
            if row['item_id'] or row['state'] in ('pending','processing'):
                raise LearningError('selection_in_use','This word is already being made into a card.',409)
            region=conn.execute('SELECT payload FROM lesson_word_regions WHERE id=?',(row['region_id'],)).fetchone()
            context=self.context(json.loads(region['payload']),surface) if region else row['context']
            conn.execute('UPDATE lesson_word_picks SET surface=?,context=?,reading_confirmed=1,request_id=NULL,error=NULL WHERE id=?',(surface,context,pick_id))
        return self.pending(credential,lesson_id,revision_id)

    def create(self, credential, lesson_id, revision_id):
        revision=self.cards.companion.revision(revision_id,lesson_id)
        if revision['state']!='ready':
            raise LearningError('lesson_not_ready','Prepare this lesson before making cards.',409)
        with transaction(self.db_path,write=True) as conn:
            owner=self.cards.generator._owner(conn,credential)
            rows=conn.execute('SELECT p.* FROM lesson_word_picks p LEFT JOIN lesson_card_requests r ON r.id=p.request_id '
                              "WHERE p.owner_id=? AND p.lesson_id=? AND p.revision_id=? AND p.selected=1 AND p.item_id IS NULL AND (r.id IS NULL OR r.state IN ('failed','ready')) ORDER BY p.created_at,p.rowid LIMIT 10",
                              (owner,lesson_id,revision_id)).fetchall()
            if not rows:
                # A double click/reload resumes the request that claimed the picks.
                old=conn.execute("SELECT r.id FROM lesson_card_requests r JOIN lesson_word_picks p ON p.request_id=r.id WHERE p.owner_id=? AND p.lesson_id=? AND p.revision_id=? AND p.selected=1 AND r.selection IS NOT NULL ORDER BY r.created_at DESC LIMIT 1",(owner,lesson_id,revision_id)).fetchone()
                if old:return old['id']
                raise LearningError('no_selection','Select some words on the lesson first.',422)
            picks=[{k:r[k] for k in ('id','page','surface','context','original','region_id')} for r in rows]
            fingerprint=payload_hash(picks)
            old=conn.execute('SELECT id FROM lesson_card_requests WHERE owner_id=? AND revision_id=? AND selection_key=?',(owner,revision_id,fingerprint)).fetchone()
            request_id=old['id'] if old else identifier()
            if not old:
                conn.execute('INSERT INTO lesson_card_requests(id,owner_id,lesson_id,revision_id,first_page,last_page,quantity,selection_key,selection,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                             (request_id,owner,lesson_id,revision_id,min(p['page'] for p in picks),max(p['page'] for p in picks),len(picks),fingerprint,encoded(picks),self.cards.clock()))
            for p in picks:
                conn.execute('UPDATE lesson_word_picks SET request_id=?,error=NULL WHERE id=?',(request_id,p['id']))
        return request_id
