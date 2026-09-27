"""Native recall sessions sharing household ownership, commands and attempts."""
from datetime import datetime, timezone
import json
from urllib.parse import quote
from zoneinfo import ZoneInfo

from contracts.learning import fields, key, revision, reject, text
from repositories.card_repository import active_cards, learner_state, load_card
from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, require_access, timestamp, transaction
from services.review_scheduler import POLICY_ID, RATINGS, ReviewScheduler
from services.lesson_cards import card_sources, lesson_link


NEW_LIMIT = 5
SCOPE_FIELDS = {'q','deck','direction','state','topic','pos','case','difficulty','sort','word_id','lesson_id'}


def dictionary_url(lemma):
    return 'https://en.openrussian.org/ru/' + quote(lemma, safe='') if lemma else None


def study_day(profile, now):
    return datetime.fromtimestamp(now, timezone.utc).astimezone(ZoneInfo(profile['study_timezone'])).date().isoformat()


def scope_value(scope):
    fields(scope, set(), SCOPE_FIELDS)
    clean = {k: text(v, k, 120) for k,v in scope.items() if v != ''}
    if clean.get('direction', '') not in ('','ru-en','en-ru','ru-cloze'):
        reject('Choose a supported practice type.')
    if clean.get('state', '') not in ('','new','due','learning','reviewing','suspended'):
        reject('Choose an available card state.')
    if clean.get('sort','due') not in ('due','alphabetical','difficulty'):
        reject('Choose an available sort order.')
    if clean.get('difficulty') and clean['difficulty'] not in tuple(str(n) for n in range(1,9)):
        reject('Choose a difficulty from 1 to 8.')
    if clean.get('word_id') and (not clean['word_id'].isascii() or not clean['word_id'].isdigit() or int(clean['word_id']) < 1):
        reject('Choose a vocabulary word.')
    return clean


class NativeReviewService:
    def __init__(self, db_path, clock=timestamp, scheduler=None):
        self.db_path, self.clock = db_path, clock
        self.scheduler = scheduler or ReviewScheduler()

    def _cards(self, conn, profile, scope, now, *, source=None):
        states = {r['card_id']: dict(r) for r in conn.execute('SELECT * FROM learner_card_state WHERE profile_id=?', (profile['id'],))}
        chapter_cards={row['card_id'] for row in conn.execute("SELECT DISTINCT cv.card_id FROM card_versions cv JOIN native_card_generation_items i ON i.version_id=cv.content_version_id WHERE json_extract(i.selection,'$.first_steps_source') IS NOT NULL")}
        day = study_day(profile, now)
        seen_siblings = {}
        # Only qualified ratings space siblings; an ungraded prompt must not
        # accidentally bury the rest of a word's cards for the whole day.
        for r in conn.execute('SELECT d.sibling_key,d.id FROM review_events e JOIN activity_attempts a ON a.id=e.attempt_id '
                              'JOIN learning_sessions s ON s.id=a.session_id JOIN card_definitions d ON d.id=e.card_id '
                              'LEFT JOIN review_reversals x ON x.attempt_id=e.attempt_id WHERE s.profile_id=? AND e.study_day=? AND x.id IS NULL AND d.retired=0', (profile['id'],day)):
            seen_siblings.setdefault(r['sibling_key'], set()).add(r['id'])
        result = []
        for card in active_cards(conn) if source is None else source:
            meta, item = card['meta'], card['item']
            sources = card_sources(conn, meta['card_id'])
            if scope.get('lesson_id') and scope['lesson_id'] not in {s['lesson_id'] for s in sources}:
                continue
            media_ready = (not sources and meta['card_id'] not in chapter_cards) or {'image','word_audio','sentence_audio'} <= {a.get('kind') for a in item.get('assets',[])}
            if scope.get('word_id') and str(meta['word_id']) != scope['word_id']:
                continue
            state = states.get(meta['card_id'])
            is_new = not state or state['introduced_at'] is None
            fsrs_state = json.loads(state['scheduler_state'])['state'] if state and state['scheduler_state'] else 1
            status = 'suspended' if state and state['suspended'] else 'new' if is_new else 'reviewing' if fsrs_state == 2 else 'learning'
            buried = bool(seen_siblings.get(meta['sibling_key'], set()) - {meta['card_id']})
            due = not is_new and state['due_at'] is not None and state['due_at'] <= now and status != 'suspended' and not buried
            haystack = ' '.join(str(v) for v in (meta['lemma'],item['prompt'],item['answer'],item['sense_label'],item.get('sense_label_ru',''))).casefold()
            if scope.get('q') and scope['q'].casefold() not in haystack:
                continue
            if scope.get('deck') and scope['deck'] not in {d['content_id'] for d in card['decks']}:
                continue
            if scope.get('direction') and scope['direction'] != item['direction']:
                continue
            metadata = item.get('metadata',{})
            topics = set(metadata.get('topics',[])) | ({item['topic']} if item.get('topic') else set())
            if scope.get('topic') and scope['topic'] not in topics:
                continue
            if scope.get('pos') and scope['pos'] != metadata.get('pos'):
                continue
            if scope.get('case') and scope['case'] != metadata.get('grammar',{}).get('case'):
                continue
            if scope.get('difficulty') and int(scope['difficulty']) != metadata.get('form_difficulty',metadata.get('lemma_difficulty',item.get('difficulty'))):
                continue
            if scope.get('state') and not (due if scope['state'] == 'due' else status == scope['state']):
                continue
            result.append({**card,'state':state,'status':status,'due':due,'buried':buried,'fsrs_state':fsrs_state,'sources':sources,'media_ready':media_ready})
        return result

    @staticmethod
    def _allowance(conn, profile, now):
        day = study_day(profile,now)
        used = conn.execute('SELECT COUNT(*) FROM review_introductions WHERE profile_id=? AND study_day=?', (profile['id'],day)).fetchone()[0]
        return max(0, NEW_LIMIT-used)

    def _overview(self, conn, profile, scope, now):
        source = active_cards(conn)
        cards = self._cards(conn,profile,scope,now,source=source)
        facets = {'decks':list({d['content_id']:d for c in source for d in c['decks']}.values()),
                  'topics':sorted({topic for c in source for topic in c['item'].get('metadata',{}).get('topics',[]) + ([c['item']['topic']] if c['item'].get('topic') else [])}),
                  'pos':sorted({c['item']['metadata']['pos'] for c in source if c['item'].get('metadata')}),
                  'cases':sorted({c['item']['metadata']['grammar']['case'] for c in source if c['item'].get('metadata',{}).get('grammar',{}).get('case')})}
        available = [c for c in cards if c['status'] != 'suspended' and not c['buried'] and c['media_ready']]
        new = sum(c['status']=='new' for c in available)
        allowance = self._allowance(conn,profile,now)
        due = sum(c['due'] for c in available)
        day = study_day(profile,now)
        today = conn.execute('SELECT e.card_id FROM review_events e JOIN activity_attempts a ON a.id=e.attempt_id '
                             'JOIN learning_sessions s ON s.id=a.session_id LEFT JOIN review_reversals x ON x.attempt_id=e.attempt_id '
                             'WHERE s.profile_id=? AND e.study_day=? AND x.id IS NULL', (profile['id'],day)).fetchall()
        scope_ids = {c['meta']['card_id'] for c in cards}
        today_ids = [r['card_id'] for r in today if r['card_id'] in scope_ids]
        future = [c['state']['due_at'] for c in available if c['state'] and c['state']['due_at'] and c['state']['due_at']>now]
        counts = {'media_pending':sum(not c['media_ready'] for c in cards), 'cards':len(cards), 'words':len({c['meta']['word_id'] for c in cards if c['meta']['word_id']}),
                  'new':new,'new_allowance':allowance,'due':due,'ready':due+min(new,allowance),
                  'learning':sum(c['status']=='learning' for c in cards),'reviewing':sum(c['status']=='reviewing' for c in cards),
                  'suspended':sum(c['status']=='suspended' for c in cards),'buried':sum(c['buried'] for c in cards),
                  'practised_today':len(set(today_ids)),'answers_today':len(today_ids),'next_due_at':min(future) if future else None}
        active = self._active(conn, profile['id'], scope)
        library = []
        for c in cards:
            meta,item,state = c['meta'],c['item'],c['state']
            library.append({'id':meta['card_id'],'version_id':meta['id'],'word_id':meta['word_id'],'lemma':meta['lemma'],
                            'title':item['sense_label'],'title_ru':item.get('sense_label_ru'), 'type':item['type'],'direction':item['direction'],
                            'prompt':item['prompt'],'answer':item['answer'],'context':item['context'],
                            'explanation':item.get('explanation'),'explanation_ru':item.get('explanation_ru'),
                            'media_supported':json.loads(meta['payload'])['schema_version']==2,
                            'metadata':item.get('metadata'),'context_meaning':item.get('context_meaning'),
                            'cue_en':item.get('cue_en'),'dictionary_url':dictionary_url(meta['lemma']),
                            'assets':[{**a,'media_type':conn.execute('SELECT media_type FROM learning_assets WHERE id=?',(a['id'],)).fetchone()[0]} for a in item.get('assets',[])],
                            'media_jobs':[dict(j) for j in conn.execute('SELECT kind,status,error FROM native_card_media_jobs WHERE card_id=?',(meta['card_id'],))],
                            'decks':c['decks'],'sources':c['sources'],'media_ready':c['media_ready'],'topic':item.get('topic'),'status':c['status'],'due':c['due'],'buried':c['buried'],
                            'due_at':state['due_at'] if state else None,'revision':state['revision'] if state else 0})
        library.sort(key=lambda c: (not c['due'], c['due_at'] or 2**60, (c['lemma'] or c['prompt']).casefold(),c['id']))
        if scope.get('sort')=='alphabetical':
            library.sort(key=lambda c:((c['lemma'] or c['prompt']).casefold(),c['id']))
        elif scope.get('sort')=='difficulty':
            library.sort(key=lambda c:((c.get('metadata') or {}).get('form_difficulty',(c.get('metadata') or {}).get('lemma_difficulty',9)),c['id']))
        return {'profile_id':profile['id'],'profile_name':profile['display_name'],'scope':scope,'facets':facets,'counts':counts,'cards':library,
                'active_session_id':active['id'] if active else None,'server_now':now,'new_limit':NEW_LIMIT,
                'lesson':self._lesson(conn,scope)}

    @staticmethod
    def _lesson(conn, scope):
        if not scope.get('lesson_id'):
            return None
        row = conn.execute('SELECT id,title FROM lessons WHERE id=?', (scope['lesson_id'],)).fetchone()
        if not row:
            raise LearningError('not_found','This lesson was not found.',404)
        return {'lesson_id':row['id'], 'title':row['title'], 'url':lesson_link(row['id'])}

    @staticmethod
    def _active(conn, profile_id, scope):
        for row in conn.execute("SELECT s.id,r.scope FROM learning_sessions s JOIN review_sessions r ON r.session_id=s.id WHERE s.profile_id=? AND s.status='active' ORDER BY s.updated_at DESC,s.created_at DESC", (profile_id,)):
            saved_scope=json.loads(row['scope'])
            if all(saved_scope.get(key)==value for key,value in scope.items() if value and key!='sort'):
                return row
        return None

    def overview(self, access_id, scope=None):
        scope = scope_value(scope or {})
        with transaction(self.db_path) as conn:
            profile = require_access(conn,access_id,self.clock())
            return self._overview(conn,profile,scope,self.clock())

    def _owned(self, conn, access_id, session_id):
        profile = require_access(conn,access_id,self.clock())
        saved = conn.execute('SELECT s.*,r.scope,r.target_size,r.current_occurrence_id,r.last_attempt_id,r.phase '
                             'FROM learning_sessions s JOIN review_sessions r ON r.session_id=s.id WHERE s.id=? AND s.profile_id=?', (session_id,profile['id'])).fetchone()
        if not saved:
            raise LearningError('not_found','This practice belongs to another learner or is unavailable.',404)
        return profile,saved

    def _current(self, conn, saved):
        occurrence = conn.execute('SELECT * FROM review_session_items WHERE id=? AND session_id=?', (saved['current_occurrence_id'],saved['id'])).fetchone()
        if not occurrence:
            return None,None,None
        meta,item = load_card(conn,occurrence['card_version_id'])
        return occurrence,meta,item

    def _snapshot(self, conn, profile, saved, *, include_item=True):
        total,answered,skipped = conn.execute('SELECT COUNT(*),COALESCE(SUM(answered),0),COALESCE(SUM(skipped),0) FROM review_session_cards WHERE session_id=?', (saved['id'],)).fetchone()
        result = {'id':saved['id'],'profile_id':profile['id'],'revision':saved['revision'],'status':saved['status'],'phase':saved['phase'],
                  'total_cards':total,'practised_cards':answered,'skipped_cards':skipped,'item':None,'feedback':None,'can_undo':False,'server_now':self.clock(),
                  'lesson':self._lesson(conn,json.loads(saved['scope']))}
        if include_item and saved['current_occurrence_id']:
            occurrence,meta,item = self._current(conn,saved)
            if saved['phase'] in ('front','revealed'):
                front = {'id':occurrence['id'],'card_id':meta['card_id'],'type':item['type'],'direction':item['direction'],
                         'prompt':item['prompt'],
                         'metadata':item.get('metadata'),
                         'has_hint':bool(item.get('hint') or any(a['role']=='hint' for a in item.get('assets',[]))),'assisted':bool(occurrence['assisted']), 'assets':[]}
                if item['direction']=='ru-en':
                    front['context'] = item['context']
                if item['direction']=='ru-cloze' and item.get('cue_en'):
                    # Contextual English translation identifies what to recall.
                    # The optional mnemonic is a separate hint.
                    front['cue_en'] = item['cue_en']
                if occurrence['assisted']:
                    front['hint'] = item.get('hint')
                if occurrence['revealed']:
                    front['sources'] = card_sources(conn,meta['card_id'])
                    front.update(answer=item['answer'],context=item['context'],cue_en=item.get('cue_en'),
                                 dictionary_url=dictionary_url(meta['lemma']),
                                 context_meaning=item.get('context_meaning'),hint=item.get('hint'),
                                 explanation=item.get('explanation'),explanation_ru=item.get('explanation_ru'))
                roles = {'prompt'} | ({'hint'} if occurrence['assisted'] else set()) | ({'answer'} if occurrence['revealed'] else set())
                for asset in item.get('assets',[]):
                    # A cloze's scene supplies context; its recordings reveal the
                    # missing form. Older generated cards put all three on the back.
                    if asset['role'] in roles or (item['direction']=='ru-cloze' and asset.get('kind')=='image'):
                        row = conn.execute('SELECT media_type FROM learning_assets WHERE id=?',(asset['id'],)).fetchone()
                        if row:
                            front['assets'].append({'id':asset['id'],'role':asset['role'],'media_type':row['media_type'],'kind':asset.get('kind')})
                result['item'] = front
        last = conn.execute('SELECT e.*,a.assisted FROM review_events e JOIN activity_attempts a ON a.id=e.attempt_id '
                            'LEFT JOIN review_reversals x ON x.attempt_id=e.attempt_id WHERE a.session_id=? AND x.id IS NULL ORDER BY e.rowid DESC LIMIT 1', (saved['id'],)).fetchone()
        if include_item and last and saved['phase'] in ('feedback','front','completed') and saved['last_attempt_id']==last['attempt_id']:
            after = json.loads(last['after_state'])
            current = learner_state(conn,profile['id'],last['card_id'])
            if saved['phase']=='feedback':
                _,item = load_card(conn,last['card_version_id'])
                result['feedback'] = {'attempt_id':last['attempt_id'],'rating':last['rating'],'assisted':bool(last['assisted']),'answer':item['answer'],
                                      'due_at':after['due_at'],'prompt':item['prompt']}
            result['can_undo'] = bool(current and current['revision']==after['revision'])
            if saved['phase']=='completed' and conn.execute("SELECT 1 FROM learning_sessions s JOIN review_sessions r ON r.session_id=s.id WHERE s.profile_id=? AND s.status='active' AND s.id!=?",(profile['id'],saved['id'])).fetchone():
                result['can_undo'] = False
        return result

    def read(self, access_id, session_id):
        key(session_id)
        with transaction(self.db_path) as conn:
            profile,saved = self._owned(conn,access_id,session_id)
            try:
                return self._snapshot(conn,profile,saved)
            except LearningError as error:
                if error.code=='content_unavailable':
                    error.details['current_session']=self._snapshot(conn,profile,saved,include_item=False)
                raise

    @staticmethod
    def _cached_result(conn, result, session_id, submission_id=None):
        # A completed current session does not authorize replaying an old answer
        # from a version that has since been withdrawn or retired.
        if result.get('item'):
            item=conn.execute('SELECT card_version_id FROM review_session_items WHERE id=? AND session_id=?',(result['item']['id'],session_id)).fetchone()
            if not item:raise LearningError('content_unavailable','This saved card is unavailable.',409)
            load_card(conn,item['card_version_id'])
        if result.get('feedback'):
            event=conn.execute('SELECT e.card_version_id FROM review_events e JOIN activity_attempts a ON a.id=e.attempt_id WHERE a.session_id=? AND a.id=?',(session_id,result['feedback'].get('attempt_id'))).fetchone()
            if not event:raise LearningError('content_unavailable','This saved answer is unavailable.',409)
            load_card(conn,event['card_version_id'])
        return result

    def _ensure_state(self, conn, profile, card_id, now):
        conn.execute('INSERT OR IGNORE INTO learner_card_state(profile_id,card_id,policy_version) VALUES (?,?,?)', (profile['id'],card_id,POLICY_ID))
        state = learner_state(conn,profile['id'],card_id)
        if state['introduced_at'] is None:
            if self._allowance(conn,profile,now)<1:
                return None
            initial = self.scheduler.initial(card_id,now)
            conn.execute('UPDATE learner_card_state SET introduced_at=?,due_at=?,scheduler_state=?,revision=revision+1 WHERE profile_id=? AND card_id=?', (now,now,initial,profile['id'],card_id))
            conn.execute('INSERT INTO review_introductions VALUES (?,?,?,?,?)', (profile['id'],card_id,study_day(profile,now),profile['study_timezone'],now))
        return learner_state(conn,profile['id'],card_id)

    def _issue(self, conn, profile, session_id, now):
        saved = conn.execute('SELECT * FROM review_sessions WHERE session_id=?',(session_id,)).fetchone()
        eligible = {c['meta']['card_id']:c for c in self._cards(conn,profile,{},now) if c['status']!='suspended' and not c['buried']}
        selected = conn.execute('SELECT * FROM review_session_cards WHERE session_id=? AND skipped=0 ORDER BY position',(session_id,)).fetchall()
        # Relearning may return during a longer session, but only when actually
        # due. A short session never lies about clearing later learning steps.
        ready = sorted(selected,key=lambda row: (not eligible.get(row['card_id'],{}).get('due',False),row['position']))
        for row in ready:
            card = eligible.get(row['card_id'])
            if not card:
                if not row['answered']:
                    conn.execute('UPDATE review_session_cards SET skipped=1 WHERE session_id=? AND card_id=?',(session_id,row['card_id']))
                continue
            if row['answered'] and not card['due']:
                continue
            if not row['answered'] and card['status']!='new' and not card['due']:
                continue
            # A pinned version can have been withdrawn since the queue was made.
            try:
                load_card(conn,row['card_version_id'])
            except LearningError:
                conn.execute('UPDATE review_session_cards SET skipped=1 WHERE session_id=? AND card_id=?',(session_id,row['card_id']))
                continue
            state = self._ensure_state(conn,profile,row['card_id'],now)
            if not state:
                continue
            occurrence_id = identifier()
            conn.execute('INSERT INTO review_session_items(id,session_id,card_id,card_version_id,state_revision,created_at) VALUES (?,?,?,?,?,?)',
                         (occurrence_id,session_id,row['card_id'],row['card_version_id'],state['revision'],now))
            conn.execute("UPDATE review_sessions SET current_occurrence_id=?,phase='front' WHERE session_id=?",(occurrence_id,session_id))
            return
        conn.execute("UPDATE review_sessions SET current_occurrence_id=NULL,phase='completed' WHERE session_id=?",(session_id,))
        conn.execute("UPDATE learning_sessions SET status='completed' WHERE id=?",(session_id,))

    def start(self, access_id, data):
        fields(data,{'profile_id','submission_id','scope','size'})
        key(data['profile_id']);key(data['submission_id'])
        scope = scope_value(data['scope'])
        if type(data['size']) is not int or not 1<=data['size']<=20:
            reject('Choose between 1 and 20 cards.')
        digest = payload_hash(data)
        with transaction(self.db_path,write=True) as conn:
            now = self.clock();profile = require_access(conn,access_id,now,profile_id=data['profile_id'])
            previous = conn.execute('SELECT * FROM review_start_commands WHERE profile_id=? AND submission_id=?',(profile['id'],data['submission_id'])).fetchone()
            if previous:
                if previous['payload_hash']!=digest:
                    raise LearningError('idempotency_conflict','That request was already used for different practice.',409)
                _,saved = self._owned(conn,access_id,previous['session_id'])
                self._snapshot(conn,profile,saved)  # Publication/ownership before cache.
                return self._cached_result(conn,json.loads(previous['result']),previous['session_id'])
            self._lesson(conn,scope)
            active = self._active(conn,profile['id'],scope)
            if active:
                session_id = active['id']
            else:
                cards = self._cards(conn,profile,scope,now)
                cards.sort(key=lambda c:(0 if c['due'] and c['fsrs_state']!=2 else 1 if c['due'] else 2,c['state']['due_at'] if c['state'] and c['state']['due_at'] else 2**60,c['meta']['card_id']))
                allowance = self._allowance(conn,profile,now)
                chosen, siblings = [],set()
                for c in cards:
                    if c['status']=='suspended' or c['buried'] or not c['media_ready'] or c['meta']['sibling_key'] in siblings:
                        continue
                    if c['status']=='new':
                        if not allowance:continue
                        allowance-=1
                    elif not c['due']:continue
                    chosen.append(c);siblings.add(c['meta']['sibling_key'])
                    if len(chosen)==data['size']:break
                if not chosen:
                    raise LearningError('nothing_due','No cards are ready in this selection. You can browse cards or return later.',409)
                session_id=identifier()
                conn.execute("INSERT INTO learning_sessions(id,profile_id,version_id,kind,start_key,start_hash,start_result,created_at,updated_at) VALUES (?,?,NULL,'review',?,?,?,?,?)",
                             (session_id,profile['id'],'review:'+data['submission_id'],digest,'{}',now,now))
                conn.execute("INSERT INTO review_sessions(session_id,scope,target_size,phase) VALUES (?,?,?,'front')",(session_id,encoded(scope),data['size']))
                for position,c in enumerate(chosen):
                    conn.execute('INSERT INTO review_session_cards(session_id,card_id,card_version_id,position) VALUES (?,?,?,?)',(session_id,c['meta']['card_id'],c['meta']['id'],position))
                self._issue(conn,profile,session_id,now)
            _,saved=self._owned(conn,access_id,session_id)
            result=self._snapshot(conn,profile,saved)
            conn.execute('INSERT INTO review_start_commands VALUES (?,?,?,?,?)',(profile['id'],data['submission_id'],session_id,digest,encoded(result)))
            conn.execute("UPDATE learning_sessions SET start_result=? WHERE id=? AND start_result='{}'",(encoded(result),session_id))
            return result

    def command(self, access_id, session_id, operation, data):
        if operation not in ('reveal','help','reviews','next','finish','undo','report'):
            reject('Unsupported review action.')
        required={'submission_id','expected_revision'}
        if operation in ('reveal','help','reviews','report'):required.add('item_id')
        if operation=='reviews':required.add('rating')
        if operation=='report':required.add('reason')
        fields(data,required);key(data['submission_id']);revision(data['expected_revision']);key(session_id)
        if 'item_id' in data:key(data['item_id'])
        if operation=='reviews' and (not isinstance(data['rating'],str) or data['rating'] not in RATINGS):reject('Choose Again, Hard, Good or Easy.')
        if operation=='report' and data['reason'] not in ('meaning','confusing','other'):reject('Choose a reason for setting this card aside.')
        digest=payload_hash({'operation':operation,**data})
        with transaction(self.db_path,write=True) as conn:
            now=self.clock();profile,saved=self._owned(conn,access_id,session_id)
            # Finish can always close a withdrawn queue, without serving its content.
            if operation!='finish':self._snapshot(conn,profile,saved)
            cached=conn.execute('SELECT * FROM learning_commands WHERE session_id=? AND submission_id=?',(session_id,data['submission_id'])).fetchone()
            if cached:
                if cached['payload_hash']!=digest:
                    raise LearningError('idempotency_conflict','This request ID was already used for another action.',409)
                return self._cached_result(conn,json.loads(cached['result']),session_id,data['submission_id'])
            if saved['revision']!=data['expected_revision']:
                raise LearningError('stale_revision','Practice changed in another tab. The latest saved state is shown.',409,
                                    {'current_session':self._snapshot(conn,profile,saved,include_item=operation!='finish')})
            if saved['status']!='active' and operation!='undo':
                raise LearningError('session_complete','This practice has ended. Start another when you are ready.',409)
            if operation=='finish':
                conn.execute("UPDATE learning_sessions SET status='completed' WHERE id=?",(session_id,))
                conn.execute("UPDATE review_sessions SET phase='completed',current_occurrence_id=NULL,last_attempt_id=NULL WHERE session_id=?",(session_id,))
            elif operation=='next':
                if saved['phase']!='feedback':reject('Finish the current card before moving on.')
                self._issue(conn,profile,session_id,now)
            elif operation=='undo':
                self._undo(conn,profile,saved,now)
            else:
                occurrence,meta,item=self._current(conn,saved)
                if not occurrence or occurrence['id']!=data['item_id'] or saved['phase'] not in ('front','revealed'):
                    raise LearningError('wrong_item','This card has already moved on. Reload your practice.',409)
                state=learner_state(conn,profile['id'],meta['card_id'])
                if not state or state['revision']!=occurrence['state_revision'] or state['suspended']:
                    raise LearningError('card_changed','This card changed in another tab. Finish this session and reopen your practice.',409)
                if operation=='reveal':
                    if saved['phase']!='front':reject('The answer is already open.')
                    conn.execute('UPDATE review_session_items SET revealed=1 WHERE id=?',(occurrence['id'],))
                    conn.execute("UPDATE review_sessions SET phase='revealed' WHERE session_id=?",(session_id,))
                elif operation=='help':
                    if saved['phase']!='front' or occurrence['assisted'] or not (item.get('hint') or any(a['role']=='hint' for a in item.get('assets',[]))):
                        reject('This card has no unopened hint.')
                    conn.execute('UPDATE review_session_items SET assisted=1 WHERE id=?',(occurrence['id'],))
                elif operation=='report':
                    conn.execute('INSERT OR IGNORE INTO card_reports VALUES (?,?,?,?,?,?)',(identifier(),profile['id'],meta['card_id'],meta['id'],data['reason'],now))
                    conn.execute('UPDATE learner_card_state SET suspended=1,revision=revision+1 WHERE profile_id=? AND card_id=?',(profile['id'],meta['card_id']))
                    conn.execute('UPDATE review_session_cards SET skipped=1 WHERE session_id=? AND card_id=?',(session_id,meta['card_id']))
                    conn.execute("UPDATE review_sessions SET phase='feedback',current_occurrence_id=NULL,last_attempt_id=NULL WHERE session_id=?",(session_id,))
                elif operation=='reviews':
                    if saved['phase']!='revealed' or not occurrence['revealed']:
                        reject('Show the answer before recording how it went.')
                    rating=data['rating']
                    after_state,due,log=self.scheduler.review(state['scheduler_state'],rating,now)
                    previous_fsrs=json.loads(state['scheduler_state'])
                    conn.execute('UPDATE learner_card_state SET scheduler_state=?,due_at=?,last_review_at=?,reviews=reviews+1,lapses=lapses+?,revision=revision+1,policy_version=? WHERE profile_id=? AND card_id=?',
                                 (after_state,due,now,int(rating=='again' and previous_fsrs['state']==2),POLICY_ID,profile['id'],meta['card_id']))
                    after=learner_state(conn,profile['id'],meta['card_id'])
                    prior_answered=conn.execute('SELECT answered FROM review_session_cards WHERE session_id=? AND card_id=?',(session_id,meta['card_id'])).fetchone()[0]
                    before_session={'phase':saved['phase'],'last_attempt_id':saved['last_attempt_id'],'answered':prior_answered}
                    attempt_id=identifier()
                    conn.execute('INSERT INTO activity_attempts(id,session_id,item_id,submission_id,answer,assisted,outcome,policy_version,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                                 (attempt_id,session_id,occurrence['id'],data['submission_id'],encoded({'reported_rating':data['rating'],'effective_rating':rating}),occurrence['assisted'],rating,POLICY_ID,now))
                    conn.execute('INSERT INTO review_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                 (attempt_id,occurrence['id'],meta['card_id'],meta['id'],rating,encoded(state),encoded(after),encoded(before_session),encoded(log),encoded(self.scheduler.policy),study_day(profile,now),profile['study_timezone'],now))
                    from services.progression import award
                    award(conn,profile['id'],activity='flashcards',content_key=meta['card_id'],source_key=attempt_id,title='Flashcard practice',now=now,category='review',evidence={'rating':rating,'assisted':bool(occurrence['assisted'])})
                    if meta['word_id']:
                        conn.execute('INSERT INTO learner_word_evidence VALUES (?,?,?,?,?,?)',(attempt_id,profile['id'],meta['word_id'],'supported_recall' if occurrence['assisted'] else 'self_reported_recall',rating,now))
                    conn.execute('UPDATE review_session_cards SET answered=1 WHERE session_id=? AND card_id=?',(session_id,meta['card_id']))
                    conn.execute("UPDATE review_sessions SET phase='feedback',last_attempt_id=? WHERE session_id=?",(attempt_id,session_id))
            conn.execute('UPDATE learning_sessions SET revision=revision+1,updated_at=? WHERE id=?',(now,session_id))
            _,saved=self._owned(conn,access_id,session_id)
            result=self._snapshot(conn,profile,saved,include_item=operation!='finish')
            if operation=='report':result['notice']='Card set aside. This was not recorded as a forgotten answer.'
            conn.execute('INSERT INTO learning_commands VALUES (?,?,?,?,?)',(session_id,data['submission_id'],digest,encoded(result),now))
            return result

    def _undo(self, conn, profile, saved, now):
        if saved['phase'] not in ('feedback','front','completed') or not saved['last_attempt_id']:
            raise LearningError('undo_unavailable','Undo is available before revealing the next card or finishing practice.',409)
        if saved['status']=='completed' and conn.execute("SELECT 1 FROM learning_sessions s JOIN review_sessions r ON r.session_id=s.id WHERE s.profile_id=? AND s.status='active' AND s.id!=?",(profile['id'],saved['id'])).fetchone():
            raise LearningError('undo_conflict','Another practice has started. This session cannot be reopened.',409)
        event=conn.execute('SELECT e.* FROM review_events e LEFT JOIN review_reversals x ON x.attempt_id=e.attempt_id WHERE e.attempt_id=? AND x.id IS NULL',(saved['last_attempt_id'],)).fetchone()
        if not event:
            raise LearningError('undo_unavailable','This answer has already been undone.',409)
        load_card(conn,event['card_version_id'])
        current=learner_state(conn,profile['id'],event['card_id'])
        after=json.loads(event['after_state']);before=json.loads(event['before_state']);previous=json.loads(event['before_session'])
        if not current or current['revision']!=after['revision']:
            raise LearningError('undo_conflict','Later work changed this card. Its saved progress cannot be undone here.',409)
        conn.execute('UPDATE learner_card_state SET scheduler_state=?,due_at=?,last_review_at=?,reviews=?,lapses=?,revision=revision+1,policy_version=? WHERE profile_id=? AND card_id=?',
                     (before['scheduler_state'],before['due_at'],before['last_review_at'],before['reviews'],before['lapses'],before['policy_version'],profile['id'],event['card_id']))
        conn.execute('INSERT INTO review_reversals VALUES (?,?,?,?)',(identifier(),event['attempt_id'],saved['id'],now))
        from services.progression import reverse
        reverse(conn,profile['id'],'flashcards',event['attempt_id'],now)
        original=conn.execute('SELECT * FROM review_session_items WHERE id=?',(event['occurrence_id'],)).fetchone()
        occurrence_id=identifier()
        conn.execute('INSERT INTO review_session_items(id,session_id,card_id,card_version_id,state_revision,revealed,assisted,created_at) VALUES (?,?,?,?,?,?,?,?)',
                     (occurrence_id,saved['id'],event['card_id'],event['card_version_id'],current['revision']+1,original['revealed'],original['assisted'],now))
        conn.execute('UPDATE review_session_cards SET answered=? WHERE session_id=? AND card_id=?',(previous['answered'],saved['id'],event['card_id']))
        conn.execute('UPDATE review_sessions SET phase=?,current_occurrence_id=?,last_attempt_id=? WHERE session_id=?',
                     (previous['phase'],occurrence_id,previous['last_attempt_id'],saved['id']))
        conn.execute("UPDATE learning_sessions SET status='active' WHERE id=?",(saved['id'],))

    def suspend(self, access_id, card_id, data):
        fields(data,{'profile_id','suspended','expected_revision'})
        key(card_id);key(data['profile_id']);revision(data['expected_revision'])
        if type(data['suspended']) is not bool:reject('Choose whether to set this card aside.')
        with transaction(self.db_path,write=True) as conn:
            profile=require_access(conn,access_id,self.clock(),profile_id=data['profile_id'])
            eligible={c['meta']['card_id'] for c in active_cards(conn)}
            if card_id not in eligible:raise LearningError('content_unavailable','This card is unavailable.',409)
            state=learner_state(conn,profile['id'],card_id)
            if (state['revision'] if state else 0)!=data['expected_revision']:
                raise LearningError('stale_revision','This card changed. Reload the library before changing it.',409)
            conn.execute('INSERT OR IGNORE INTO learner_card_state(profile_id,card_id,policy_version) VALUES (?,?,?)',(profile['id'],card_id,POLICY_ID))
            conn.execute('UPDATE learner_card_state SET suspended=?,revision=revision+1 WHERE profile_id=? AND card_id=?',(int(data['suspended']),profile['id'],card_id))
            return {'card_id':card_id,'suspended':data['suspended']}

    def history(self, access_id, card_id):
        key(card_id)
        with transaction(self.db_path) as conn:
            profile=require_access(conn,access_id,self.clock())
            rows=conn.execute('SELECT e.rating,e.created_at,e.after_state,a.assisted,x.id AS reversed FROM review_events e '
                              'JOIN activity_attempts a ON a.id=e.attempt_id JOIN learning_sessions s ON s.id=a.session_id '
                              'LEFT JOIN review_reversals x ON x.attempt_id=e.attempt_id WHERE s.profile_id=? AND e.card_id=? ORDER BY e.rowid DESC LIMIT 50',(profile['id'],card_id)).fetchall()
            return {'profile_id':profile['id'],'card_id':card_id,'events':[{'rating':r['rating'],'at':r['created_at'],'due_at':json.loads(r['after_state'])['due_at'],'assisted':bool(r['assisted']),'undone':bool(r['reversed'])} for r in rows]}
