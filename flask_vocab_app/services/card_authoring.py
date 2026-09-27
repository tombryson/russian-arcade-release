"""Grown-up card preparation. Meaning belongs to a reviewed use, not a lemma."""
import copy
import json
from flask import current_app, has_app_context

from contracts.flashcards import card_item, objective
from contracts.learning import key, text, reject
from repositories.card_repository import load_card
from repositories.learning_repository import LearningError, identifier, require_access, timestamp, transaction


CASES={'nomn':'Nominative','gent':'Genitive','datv':'Dative','accs':'Accusative','ablt':'Instrumental','loct':'Prepositional'}


class CardAuthoringService:
    def __init__(self, db_path, content, clock=timestamp):
        self.db_path,self.content,self.clock=db_path,content,clock

    def workspace(self, access_id, *, query='', word_id=None, edit=None):
        with transaction(self.db_path) as conn:
            access = require_access(conn,access_id,self.clock(),adult=True)
            household = current_app.config['WORD_POST_HOUSEHOLD_ENABLED'] if has_app_context() else access['profile_id'] is None
            query=query.strip()[:120]
            words=[dict(r) for r in conn.execute('SELECT id,lemma,pos FROM words WHERE lemma LIKE ? ORDER BY lemma,id LIMIT 30',('%'+query.casefold()+'%',))] if query else []
            selected=None
            if edit:
                key(edit);meta,item=load_card(conn,edit,published=False)
                selected={'meta':meta,'item':item};word_id=item.get('word_id')
            word=conn.execute('SELECT id,lemma,pos FROM words WHERE id=?',(word_id,)).fetchone() if word_id else None
            forms=[]
            if word:
                for r in conn.execute('SELECT id,form,tags FROM forms WHERE word_id=? ORDER BY form,id LIMIT 200',(word['id'],)):
                    tags=json.loads(r['tags'] or '{}')
                    labels=[CASES.get(tags.get('case'),'')]+[{'sing':'singular','plur':'plural'}.get(tags.get('number'),'')]
                    forms.append({'id':r['id'],'label':r['form']+(' · '+', '.join(filter(None,labels)) if any(labels) else '')})
            versions=[]
            for r in conn.execute("SELECT v.*,EXISTS(SELECT 1 FROM card_draft_archives a WHERE a.version_id=v.id) AS discarded FROM learning_content_versions v JOIN learning_content c ON c.id=v.content_id WHERE c.kind='deck' AND v.version=(SELECT MAX(v2.version) FROM learning_content_versions v2 WHERE v2.content_id=v.content_id) ORDER BY v.created_at DESC,v.rowid DESC"):
                version=dict(r);pack=json.loads(version.pop('payload'))
                version['cards']=[]
                for item in pack['items']:
                    cv=conn.execute('SELECT cv.id,d.retired FROM card_versions cv JOIN card_definitions d ON d.id=cv.card_id WHERE cv.content_version_id=? AND cv.item_id=?',(r['id'],item['id'])).fetchone()
                    version['cards'].append({**card_item(pack,item),'version_id':cv['id'],'retired':bool(cv['retired'])})
                versions.append(version)
            report_scope = '' if household else ' WHERE r.profile_id=?'
            reports=[dict(r) for r in conn.execute(
                'SELECT r.reason,r.created_at,p.display_name,w.lemma,cv.id AS version_id,d.retired FROM card_reports r '
                'JOIN learning_profiles p ON p.id=r.profile_id JOIN card_versions cv ON cv.id=r.card_version_id '
                'JOIN card_definitions d ON d.id=r.card_id LEFT JOIN words w ON w.id=d.word_id' + report_scope +
                ' ORDER BY r.created_at DESC LIMIT 50', () if household else (access['profile_id'],))]
            return {'query':query,'words':words,'word':dict(word) if word else None,'forms':forms,'selected':selected,'versions':versions,'reports':reports,'draft_key':identifier()}

    def save(self, access_id, data):
        key(data.get('draft_key'),'Draft key')
        try:
            word_id=int(data.get('word_id',''))
            form_id=int(data['form_id']) if data.get('form_id') else None
        except (TypeError,ValueError):reject('Choose a vocabulary word and, optionally, a form.')
        direction=data.get('direction')
        item={'id':'card','card_id':'card-'+data['draft_key'],'word_id':word_id,'type':'cloze' if direction=='ru-cloze' else 'basic',
              'direction':direction,'sense_key':'sense-'+data['draft_key'],
              'sense_label':text(data.get('sense_label'),'Situation',160),'context':text(data.get('context'),'Russian context'),
              'prompt':text(data.get('prompt'),'Prompt'),'answer':text(data.get('answer'),'Answer')}
        for name in ('sense_label_ru','cue_en','context_meaning','explanation','explanation_ru','hint','topic'):
            if data.get(name,'').strip():item[name]=text(data[name],name,160 if name in ('sense_label_ru','topic') else 2000)
        if form_id:item['form_id']=form_id
        base='';pack={'schema_version':2,'id':'prepared-'+data['draft_key'],'kind':'deck','title':item['sense_label'],
                      'source':'Prepared in the household card workspace. Meaning is specific to this context.','items':[item]}
        if data.get('edit'):
            with transaction(self.db_path) as conn:
                require_access(conn,access_id,self.clock(),adult=True)
                meta,old=load_card(conn,key(data['edit']),published=False)
                if meta['retired']:raise LearningError('content_unavailable','This card is retired. Prepare a new card from its word.',409)
                base=meta['content_version_id']
                source=json.loads(meta['payload'])
                if source['schema_version']!=2:
                    # Preserve v1 source unchanged; explicit replacement is a new
                    # preparation. Grown-ups can retire the old card separately.
                    reject('This is a legacy pack. Prepare a new contextual card from its vocabulary word, then retire the old card.')
                pack=copy.deepcopy(source);item['id']=old['id'];item['sense_key']=old['sense_key']
                if objective(item)==objective(old):item['card_id']=old['card_id']
                if old.get('assets') and objective(item)==objective(old):item['assets']=old['assets']
                from services.card_metadata import enrich_item
                enrich_item(conn,item)
                pack['items']=[item if i['id']==old['id'] else i for i in pack['items']]
                if len(pack['items'])==1:
                    pack['title']=item['sense_label']
                    pack.pop('title_ru',None)
        if len(pack['items'])==1 and item.get('sense_label_ru'):
            pack['title_ru']=item['sense_label_ru']
        return self.content.import_draft(pack,access_id=access_id,expected_base=base)

    def discard(self, access_id, version_id):
        key(version_id)
        with transaction(self.db_path,write=True) as conn:
            require_access(conn,access_id,self.clock(),adult=True)
            row=conn.execute("SELECT v.status FROM learning_content_versions v JOIN learning_content c ON c.id=v.content_id WHERE v.id=? AND c.kind='deck'",(version_id,)).fetchone()
            if not row or row['status']!='draft':raise LearningError('publication_conflict','Only an unpublished draft can be discarded.',409)
            conn.execute('INSERT OR IGNORE INTO card_draft_archives VALUES (?,?)',(version_id,self.clock()))

    def retire(self, access_id, card_id):
        key(card_id)
        with transaction(self.db_path,write=True) as conn:
            require_access(conn,access_id,self.clock(),adult=True)
            if not conn.execute('UPDATE card_definitions SET retired=1 WHERE id=?',(card_id,)).rowcount:
                raise LearningError('not_found','Card not found.',404)
