"""Source-backed lesson clozes, reusing native generation, media and schedules."""
import json
import logging
import re
from functools import lru_cache

from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, transaction
from services.card_metadata import GRAMMAR, metadata_for
from services.learning_content import normalize_form
from utils.story_processing import get_morph
from utils.pos_case import POS_MAP

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _local_vocabulary_pipeline():
    """Reuse the morphology pipeline without configuring external providers."""
    from services.sync_service import SyncService
    return SyncService(db_path=None, drive_service=object(), api_key='', config={})


def normal(value):
    return ' '.join(normalize_form(value).split())


def lesson_link(lesson_id, revision_id=None, page=None, view='flashcards'):
    return f'/lessons/load/{lesson_id}?view={view}' + (f'&revision={revision_id}' if revision_id else '') + (f'&page={page}' if page else '')


def batch_source(conn, batch_id):
    row = conn.execute('SELECT r.*,l.title FROM lesson_card_requests r JOIN lessons l ON l.id=r.lesson_id WHERE r.batch_id=?', (batch_id,)).fetchone()
    if not row:
        return None
    return {'lesson_id': row['lesson_id'], 'title': row['title'],
            'url': lesson_link(row['lesson_id'], row['revision_id']),
            'first_page': row['first_page'], 'last_page': row['last_page'],
            'report': json.loads(row['report'])}


def card_sources(conn, card_id):
    rows = conn.execute('SELECT DISTINCT r.lesson_id,s.revision_id,s.page,l.title,i.selection FROM lesson_card_sources s '
                        'JOIN lesson_card_requests r ON r.id=s.request_id JOIN lessons l ON l.id=r.lesson_id '
                        'JOIN native_card_generation_items i ON i.id=s.item_id JOIN card_versions cv ON cv.content_version_id=i.version_id '
                        'WHERE cv.card_id=? ORDER BY r.created_at DESC,s.page', (card_id,)).fetchall()
    return [{'lesson_id': r['lesson_id'], 'title': r['title'], 'page': r['page'], 'origin':json.loads(r['selection']).get('lesson_source',{}).get('origin','source'),
             'url': lesson_link(r['lesson_id'], r['revision_id'], r['page'], 'materials')} for r in rows]


class LessonCards:
    def __init__(self, companion, generator):
        self.companion, self.generator = companion, generator
        self.db_path, self.clock = generator.db_path, generator.clock

    def create(self, credential, lesson_id, revision_id, first, last, quantity):
        revision = self.companion.revision(revision_id, lesson_id)
        pages = self.companion.evidence(revision_id)
        if revision['state'] != 'ready':
            raise LearningError('lesson_not_ready', 'Prepare this lesson before making cards.', 409)
        if any(type(n) is not int for n in (first, last, quantity)) or not 1 <= quantity <= 10 or not 1 <= first <= last or last-first >= 10:
            raise LearningError('invalid_pages', 'Choose up to 10 consecutive pages and between 1 and 10 cards.', 422)
        if not set(range(first, last+1)) <= {p['page'] for p in pages}:
            raise LearningError('invalid_pages', 'Some selected pages have not been read yet.', 422)
        with transaction(self.db_path, write=True) as conn:
            owner = self.generator._owner(conn, credential)
            row = conn.execute("SELECT id FROM lesson_card_requests WHERE owner_id=? AND revision_id=? AND first_page=? AND last_page=? AND quantity=? AND selection_key='pages'", (owner, revision_id, first, last, quantity)).fetchone()
            request_id = row['id'] if row else identifier()
            if not row:
                conn.execute('INSERT INTO lesson_card_requests(id,owner_id,lesson_id,revision_id,first_page,last_page,quantity,created_at) VALUES (?,?,?,?,?,?,?,?)', (request_id, owner, lesson_id, revision_id, first, last, quantity, self.clock()))
        return request_id

    def _request(self, conn, credential, request_id, lesson_id):
        owner = self.generator._owner(conn, credential)
        row = conn.execute('SELECT * FROM lesson_card_requests WHERE id=? AND owner_id=? AND lesson_id=?', (request_id, owner, lesson_id)).fetchone()
        if not row:
            raise LearningError('not_found', 'This card request was not found.', 404)
        return dict(row)

    def read(self, credential, request_id, lesson_id):
        with transaction(self.db_path) as conn:
            row = self._request(conn, credential, request_id, lesson_id)
        return {k: row[k] for k in ('id','state','batch_id','error','first_page','last_page','quantity')}

    def history(self, credential, lesson_id):
        with transaction(self.db_path) as conn:
            owner = self.generator._owner(conn, credential)
            return [dict(r) for r in conn.execute('SELECT id,revision_id,first_page,last_page,quantity,state,batch_id FROM lesson_card_requests WHERE owner_id=? AND lesson_id=? ORDER BY created_at DESC', (owner, lesson_id))]

    @staticmethod
    def resolve(conn, candidate):
        """Verify contextual morphology before touching lemma/form tables.

        Homographs with indistinguishable morphology cannot be resolved by this
        dictionary. Their contextual meaning stays on the card, never the lemma.
        """
        lemma, surface = normal(candidate['lemma']), normal(candidate['surface'])
        if not re.fullmatch(r'[а-яё]+(?:-[а-яё]+)*', surface) or not re.fullmatch(r'[а-яё]+(?:-[а-яё]+)*', lemma):
            raise ValueError('The target must be one Russian word.')
        tags = {k: v for k, v in candidate['grammar'].items() if v}
        # OpenCorpora marks voice on participles, not finite verbs/infinitives.
        # A linguistically meaningful active/reflexive reading is not a reason
        # to reject a correctly conjugated verb for lacking that dictionary tag.
        if candidate['pos'] in ('VERB', 'INFN'):
            tags.pop('voice', None)
        parses = [p for p in get_morph().parse(surface) if p.is_known and p.normal_form == lemma and p.tag.POS == candidate['pos']
                  and all(getattr(p.tag, k, None) == v for k, v in tags.items())]
        signatures = {tuple(getattr(p.tag, k, None) for k in GRAMMAR) for p in parses}
        if len(signatures) != 1:
            raise ValueError('The word form needs a clearer grammatical context.')
        tag = parses[0].tag  # All surviving parses have the same lemma and grammar.
        tags = {k: getattr(tag, k) for k in GRAMMAR if getattr(tag, k, None)}
        pos = POS_MAP.get(candidate['pos'], candidate['pos'])
        rows = [r for r in conn.execute('SELECT * FROM words') if normal(r['lemma']) == lemma and POS_MAP.get(r['pos'], r['pos']) == pos]
        if len(rows) > 1:
            raise ValueError('More than one vocabulary entry matches this word.')
        if not rows:
            conn.execute('INSERT INTO words(lemma,pos,count,lemma_difficulty,topic,date_added) VALUES (?,?,0,0,?,date(\'now\'))', (lemma, pos, encoded([])))
            row = conn.execute('SELECT * FROM words WHERE id=last_insert_rowid()').fetchone()
            # Keep the contextual parse and row identity: parsing the lemma
            # again could choose a different homograph or part of speech.
            if not _local_vocabulary_pipeline().process_word(lemma, conn, conn.cursor(), parsed=parses[0], word_id=row['id']):
                raise ValueError('The vocabulary forms could not be prepared.')
            row = conn.execute('SELECT * FROM words WHERE id=?', (row['id'],)).fetchone()
        else:
            row = rows[0]
        forms = []
        for f in conn.execute('SELECT * FROM forms WHERE word_id=?', (row['id'],)):
            try:
                existing = json.loads(f['tags'] or '{}')
            except (ValueError, TypeError):
                continue
            if normal(f['form']) == surface and isinstance(existing, dict) and all(existing.get(k) == v for k, v in tags.items()):
                forms.append(f)
        if not forms:
            # Frequency filtering may omit the precise form in this lesson.
            # Preserve that verified form even when it is uncommon.
            difficulty = row['lemma_difficulty']
            if difficulty:
                difficulty = min(8, difficulty + (tags.get('number') == 'plur') + (2 if candidate['pos'] in ('PRTF', 'PRTS') else 0))
            conn.execute('INSERT INTO forms(word_id,form,count,tags,form_difficulty) VALUES (?,?,0,?,?)', (row['id'], surface, encoded(tags), difficulty))
            form = conn.execute('SELECT * FROM forms WHERE id=last_insert_rowid()').fetchone()
        else:
            form = forms[0]
        return {'word_id': row['id'], 'lemma': row['lemma'], 'pos': row['pos'],
                'form_id': form['id'], 'form': candidate['surface'], 'tags': tags,
                'metadata': metadata_for(row, form), 'mnemonic': row['mnemonic'] or ''}

    def recheck(self, credential, batch_id):
        with transaction(self.db_path) as conn:
            self.generator._batch(conn,credential,batch_id)
            row = conn.execute('SELECT id,lesson_id FROM lesson_card_requests WHERE batch_id=?',(batch_id,)).fetchone()
        if row:
            return self.advance(credential,row['id'],row['lesson_id'],recheck=True)

    def advance(self, credential, request_id, lesson_id, *, recheck=False):
        with transaction(self.db_path, write=True) as conn:
            row = self._request(conn, credential, request_id, lesson_id)
            if (row['state'] == 'ready' and not recheck) or row['lease_until'] > self.clock():
                return self.read(credential, request_id, lesson_id)
            token = identifier()
            conn.execute("UPDATE lesson_card_requests SET state='processing',lease_token=?,lease_until=?,error=NULL WHERE id=?", (token, self.clock()+300, request_id))
        try:
            selections=json.loads(row['selection']) if row.get('selection') else None
            pages = [p for p in self.companion.evidence(row['revision_id']) if (p['page'] in {s['page'] for s in selections} if selections else row['first_page'] <= p['page'] <= row['last_page'])]
            response = json.loads(row['response']) if row['response'] else {
                **(self.companion.ai.selected_flashcards(pages,selections) if selections else self.companion.ai.flashcards(pages, row['quantity'])),
                'model': str(self.companion.ai.model), 'policy': 'lesson-selected-clozes-v1' if selections else 'lesson-clozes-v1',
            }
            with transaction(self.db_path, write=True) as conn:
                self._request(conn, credential, request_id, lesson_id)
                if not conn.execute('UPDATE lesson_card_requests SET response=? WHERE id=? AND lease_token=?', (encoded(response), request_id, token)).rowcount:
                    raise LearningError('request_changed', 'Another request is preparing these cards.', 409)
            self._materialize(credential, row, response, pages, token)
        except Exception as error:
            log.warning('Lesson card preparation failed (%s)', type(error).__name__)
            from services.ai_trial_budget import TrialDenied
            message = str(error) if isinstance(error, (LearningError, TrialDenied)) else 'These cards could not be prepared. Your lesson and existing cards are kept. Please retry.'
            with transaction(self.db_path, write=True) as conn:
                conn.execute("UPDATE lesson_card_requests SET state='failed',lease_until=0,error=? WHERE id=? AND lease_token=?", (message, request_id, token))
                if isinstance(error, LearningError) and error.code == 'no_lesson_cards':
                    conn.execute('UPDATE lesson_card_requests SET response=NULL WHERE id=? AND lease_token=?', (request_id,token))
            if isinstance(error, TrialDenied):
                raise
        return self.read(credential, request_id, lesson_id)

    def _materialize(self, credential, row, response, pages, token):
        printed = {p['page']: normal(p['text']) for p in pages}
        picks={p['id']:p for p in json.loads(row.get('selection') or '[]')}
        with transaction(self.db_path, write=True) as conn:
            current = self._request(conn, credential, row['id'], row['lesson_id'])
            if current['lease_token'] != token:
                raise LearningError('request_changed', 'Another request is preparing these cards.', 409)
            batch = row['batch_id'] or identifier()
            options = {'kind': 'ru-cloze', 'quantity': row['quantity'], 'audio': True, 'image': True}
            if not row['batch_id']:
                conn.execute('INSERT INTO native_card_batches VALUES (?,?,?,?,?,?)', (batch, row['owner_id'], 'lesson:'+row['id'], payload_hash(options), encoded(options), self.clock()))
            position = conn.execute('SELECT COUNT(*) FROM native_card_generation_items WHERE batch_id=?',(batch,)).fetchone()[0]
            report, added, reused, seen = [], 0, 0, set()
            for candidate in response['cards'][:row['quantity']]:
                conn.execute('SAVEPOINT candidate')
                try:
                    sentence = candidate['sentence'].strip()
                    pick=picks.get(candidate.get('pick_id')) if picks else None
                    if picks and (not pick or candidate['page']!=pick['page'] or normal(candidate['surface'])!=normal(pick['surface'])):
                        raise ValueError('The proposed card did not use your selected word.')
                    is_example=bool(pick and candidate.get('origin')=='example')
                    if not sentence or len(sentence) > 1000 or (not is_example and normal(sentence) not in printed.get(candidate['page'], '')):
                        raise ValueError('The sentence could not be matched to the printed page.')
                    if pick and not is_example and normal(sentence) not in normal(pick['context']):
                        raise ValueError('The sentence did not match the context you selected.')
                    word = self.resolve(conn, candidate)
                    answer = {k: candidate[k] for k in ('english', 'sentence', 'sentence_english', 'notes')}
                    identity = payload_hash({'lemma': normal(word['lemma']), 'pos': word['pos'], 'tags': word['tags'], 'surface': normal(word['form']), 'context': normal(sentence)})
                    if identity in seen:
                        if pick:
                            linked=conn.execute('SELECT item_id FROM lesson_card_targets WHERE owner_id=? AND lesson_id=? AND identity=?',(row['owner_id'],row['lesson_id'],identity)).fetchone()
                            if linked:conn.execute('UPDATE lesson_word_picks SET item_id=?,error=NULL WHERE id=?',(linked['item_id'],pick['id']))
                        continue
                    seen.add(identity)
                    old = conn.execute('SELECT t.item_id,i.batch_id FROM lesson_card_targets t JOIN native_card_generation_items i ON i.id=t.item_id WHERE t.owner_id=? AND t.lesson_id=? AND t.identity=?', (row['owner_id'], row['lesson_id'], identity)).fetchone()
                    if old:
                        item_id = old['item_id']
                        if old['batch_id']==batch:
                            added += 1
                        else:
                            reused += 1
                    else:
                        item_id = identifier()
                        # Validate the full native cloze before committing new lexical rows.
                        from contracts.learning import validate_pack
                        validate_pack(self.generator.pack(item_id, word, options, answer))
                        word['lesson_source'] = {'lesson_id': row['lesson_id'], 'revision_id': row['revision_id'], 'page': candidate['page'], 'model': response.get('model','not recorded'), 'policy': response.get('policy','not recorded'), 'origin':'example' if is_example else 'source'}
                        conn.execute('INSERT INTO native_card_generation_items(id,batch_id,position,selection,response) VALUES (?,?,?,?,?)', (item_id, batch, position, encoded(word), encoded(answer)))
                        conn.execute('INSERT INTO lesson_card_targets VALUES (?,?,?,?)', (row['owner_id'], row['lesson_id'], identity, item_id))
                        added += 1
                        position += 1
                    conn.execute('INSERT OR IGNORE INTO lesson_card_sources VALUES (?,?,?,?)', (row['id'], item_id, row['revision_id'], candidate['page']))
                    if pick:
                        conn.execute('UPDATE lesson_word_picks SET item_id=?,error=NULL WHERE id=?',(item_id,pick['id']))
                except (ValueError, LearningError) as error:
                    conn.execute('ROLLBACK TO candidate')
                    report.append({'page': candidate.get('page'), 'surface': candidate.get('surface', ''), 'reason': str(error)})
                finally:
                    conn.execute('RELEASE candidate')
            if not added and not reused:
                raise LearningError('no_lesson_cards', 'No cards could be made for these readings. Check your selected words and try again.' if picks else 'No suitable complete sentences were found in these pages. Try a reading section or a different page range.', 422)
            report.insert(0, {'added': added, 'reused': reused, 'requested': row['quantity']})
            if picks:
                conn.execute("UPDATE lesson_word_picks SET error='No card was made for this reading. Check the word or try again.' WHERE request_id=? AND item_id IS NULL",(row['id'],))
            conn.execute("UPDATE lesson_card_requests SET batch_id=?,report=? WHERE id=?", (batch, encoded(report), row['id']))
        # Lexical rows and source evidence must commit before paid enrichment.
        # Freeze their completed metadata only after the shared importer returns.
        self.generator.enrich_batch(credential, batch)
        with transaction(self.db_path, write=True) as conn:
            if not conn.execute("UPDATE lesson_card_requests SET state='ready',lease_until=0 WHERE id=? AND lease_token=?", (row['id'], token)).rowcount:
                raise LearningError('request_changed', 'Another request is preparing these cards.', 409)
