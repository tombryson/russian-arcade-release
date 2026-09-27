"""Convert an explicitly selected personal native batch using its saved content.

Dry run by default. No provider, Anki, lexical or review-history writes. Applying
creates a backed-up, atomic replacement with fresh card identities/schedules.
"""
import argparse
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask_vocab_app'))
from contracts.learning import validate_pack
from repositories.card_repository import load_card
from repositories.learning_repository import encoded, identifier, timestamp, transaction
from services.card_generation import CardGenerationService
from services.learning_assets import LocalAssetStore
from services.learning_content import ContentService


def convert(db_path, asset_root, batch_id, *, apply=False):
    backup = None
    if apply:
        backup = str(db_path) + '.pre-cloze-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.bak'
        with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
    content = ContentService(db_path, LocalAssetStore(asset_root))
    content_id = 'cloze-batch-' + batch_id
    with transaction(db_path, write=apply) as conn:
        existing = conn.execute('SELECT id,payload FROM learning_content_versions WHERE content_id=? AND status=?', (content_id,'published')).fetchone()
        if existing:
            return {'applied':True,'already_converted':True,'content_id':content_id,'cards':len(json.loads(existing['payload'])['items']),'backup':backup}
        batch = conn.execute('SELECT * FROM native_card_batches WHERE id=?', (batch_id,)).fetchone()
        if not batch or batch['owner_id']=='household':
            raise ValueError('Choose a saved personal generation batch.')
        rows = conn.execute('SELECT * FROM native_card_generation_items WHERE batch_id=? ORDER BY position', (batch_id,)).fetchall()
        if not rows or any(row['status']!='saved' for row in rows):
            raise ValueError('Every item in this batch must be saved before conversion.')
        items, replacements = [], []
        for row in rows:
            original = conn.execute('SELECT card_id FROM card_versions WHERE content_version_id=?', (row['version_id'],)).fetchone()
            latest = conn.execute('SELECT cv.id FROM card_versions cv JOIN learning_content_versions v ON v.id=cv.content_version_id WHERE cv.card_id=? ORDER BY v.created_at DESC,v.rowid DESC LIMIT 1', (original['card_id'],)).fetchone()
            meta, old = load_card(conn,latest['id'])
            selected, response = json.loads(row['selection']), json.loads(row['response'])
            if (old['direction']!='ru-en' or old['context']!=response['sentence'].strip()
                    or old['answer']!=response['english'] or old.get('context_meaning')!=response['sentence_english']
                    or old.get('form_id')!=selected.get('form_id')):
                raise ValueError('A card differs from the saved recognition example. Review that card before converting it.')
            item = CardGenerationService.pack(row['id'],selected,{'kind':'ru-cloze'},response)['items'][0]
            if {a.get('kind') for a in old.get('assets',[])} != {'image','word_audio','sentence_audio'}:
                raise ValueError('Every source card needs its picture, word audio and sentence audio.')
            item['assets'] = [{**a,'role':'prompt' if a['kind']=='image' else 'answer'} for a in old['assets']]
            for field in ('metadata','hint','explanation','explanation_ru','topic'):
                if field in old:
                    item[field] = old[field]
            item['id'] = 'card-' + str(row['position']+1)
            items.append(item)
            replacements.append({'old_card_id':meta['card_id'],'new_card_id':item['card_id'],'form':item['answer'],'cue_en':item['cue_en']})
        pack = {'schema_version':2,'id':content_id,'kind':'deck','title':'Sentence clozes','title_ru':'Пропуски в предложениях',
                'source':'Converted from personal generation batch '+batch_id+'. Reuses its saved sentences, contextual cues, pictures and recordings. Original cards and reviews retained in history.', 'items':items}
        validate_pack(pack)
        content._validate_references(conn,pack)
        old_ids = [r['old_card_id'] for r in replacements]
        slots = ','.join('?' for _ in old_ids)
        sessions = [r[0] for r in conn.execute('SELECT DISTINCT s.id FROM learning_sessions s JOIN review_session_cards q ON q.session_id=s.id WHERE s.status=? AND q.card_id IN ('+slots+')', ('active',*old_ids))]
        if apply:
            now, version = timestamp(), identifier()
            conn.execute('INSERT INTO learning_content(id,kind,created_at) VALUES (?,?,?)', (content_id,'deck',now))
            conn.execute('INSERT INTO learning_content_versions(id,content_id,version,title,payload,status,source,created_at,approved_by,approved_at) VALUES (?,?,1,?,?,?,?,?,?,?)',
                         (version,content_id,pack['title'],encoded(pack),'published',pack['source'],now,'Me',now))
            for item in items:
                content._index_card(conn,version,pack,item,now)
                conn.execute('INSERT INTO learning_content_words VALUES (?,?,?)', (version,item['id'],item['word_id']))
            for asset in {a['id'] for i in items for a in i['assets']}:
                conn.execute('INSERT INTO learning_content_assets VALUES (?,?)', (version,asset))
            conn.execute('UPDATE card_definitions SET retired=1 WHERE id IN ('+slots+')',old_ids)
            # Closing an obsolete queue records no rating and changes no schedule.
            for session in sessions:
                conn.execute('UPDATE learning_sessions SET status=?,revision=revision+1,updated_at=? WHERE id=?', ('completed',now,session))
                conn.execute('UPDATE review_sessions SET phase=?,current_occurrence_id=NULL WHERE session_id=?', ('completed',session))
            if conn.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Conversion failed its foreign-key check; no changes committed.')
        return {'applied':apply,'content_id':content_id,'cards':len(items),'replacements':replacements,'closed_sessions':sessions if apply else [],'backup':backup}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True)
    parser.add_argument('--assets',required=True)
    parser.add_argument('--batch',required=True)
    parser.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    print(json.dumps(convert(args.db,args.assets,args.batch,apply=args.apply),ensure_ascii=False,indent=2))
