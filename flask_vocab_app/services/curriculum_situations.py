"""Durable, owned preparation of variable unit reading and listening practice.

GETs never generate. Each explicit advance claims one bounded provider stage;
refreshing an uncertain claim cannot silently spend again. Accepted text and the
selected voice survive an audio failure. Publication uses the existing player.
"""
import json

from contracts.learning import key, validate_pack
from contracts.curriculum import freeze_task_contract
from repositories.learning_repository import (LearningError, encoded, identifier,
    payload_hash, require_access, timestamp, transaction)
from services.ai_trial_budget import TrialDenied

PREFIX = 'curriculum-unit:situation-v1:'
LEASE_SECONDS = 180
MAX_ATTEMPTS = 3


def origin(pack):
    if not pack['id'].startswith(PREFIX):
        return None
    unit_id, _ = pack['id'][len(PREFIX):].rsplit(':', 1)
    return {'href': '/curriculum/units/' + unit_id, 'title': pack['title'], 'explanations': {}}


def freeze(conn, profile_id, session_id, pack, document):
    from services.curriculum_units import _criterion, _spec
    from services.activity_evidence import save_contract
    unit = document['request']['unit']
    for item, question in zip(pack['items'], document['response']['questions']):
        criterion = _criterion(question['requirement_id'], item['id'],
            'unit.' + unit['id'] + '.situation', question['expectation'])
        content = {'item': item, 'unit_id': unit['id'], 'title_en': unit['title'],
                   'title_ru': unit['title_ru'], 'explanation': question['explanation'],
                   'explanation_ru': question['explanation_ru'],
                   'item_locale_ru': {'prompt': question['prompt_ru'],
                                      'hint': question['hint_ru']}}
        spec = _spec(unit, session_id + ':' + item['id'], 'curriculum_unit', content, [criterion])
        spec.update(content_version=pack['id'], rubric_version='generated-source-choice-v1')
        if item['type'] == 'listening_choice':
            spec['support'] = {'allowed': ['hint', 'transcript'], 'independence_breakers': ['hint', 'transcript']}
        save_contract(conn, profile_id, 'curriculum_unit', session_id + ':' + item['id'], freeze_task_contract(spec))


class CurriculumSituations:
    def __init__(self, db_path, provider, speech, config, *, clock=timestamp):
        self.db_path, self.provider, self.speech, self.config, self.clock = db_path, provider, speech, config, clock

    def available(self):
        return not self.config.get('PUBLIC_DEMO')

    def _owned(self, conn, access, sid, expected_profile_id=None):
        profile = require_access(conn, access, self.clock(), profile_id=expected_profile_id)
        row = conn.execute('SELECT * FROM curriculum_situations WHERE id=? AND profile_id=?', (sid, profile['id'])).fetchone()
        if row is None:
            raise LearningError('not_found', 'This practice is not available.', 404)
        return row

    def _public(self, row):
        expired = row['state'] == 'running' and row['lease_until'] <= self.clock()
        state = 'failed' if expired else row['state']
        attempts = row['audio_attempts'] if row['stage'] == 'audio' else row['text_attempts']
        return {'id': row['id'], 'unit_id': row['unit_id'], 'mode': row['mode'], 'state': state,
                'stage': row['stage'], 'retryable': state == 'failed' and (row['stage'] == 'publish' or attempts < MAX_ATTEMPTS),
                'error': 'preparation_interrupted' if expired else row['error_code'],
                'url': '/#practice/' + row['session_id'] if row['state'] == 'ready' else None}

    def read(self, access, sid):
        with transaction(self.db_path) as conn:
            return self._public(self._owned(conn, access, sid))

    def start(self, access, unit_id, mode, request_id, profile_id):
        from services.curriculum_units import get_unit
        from services.curriculum_situation_content import build_request
        key(request_id, 'Request ID')
        if not self.available():
            raise LearningError('practice_unavailable', 'New situations are unavailable here. You can use the saved lesson practice.', 403)
        if mode not in ('reading', 'listening'):
            raise LearningError('invalid_input', 'Choose reading or listening.')
        if unit_id == 'location-destination-v2':
            unit_id = 'location-destination-v1'
        try:
            unit = get_unit(unit_id)
        except LookupError:
            raise LearningError('not_found', 'This lesson is not available.', 404) from None
        with transaction(self.db_path, write=True) as conn:
            now = self.clock()
            profile = require_access(conn, access, now, profile_id=profile_id)
            digest = payload_hash({'unit_id': unit_id, 'mode': mode})
            receipt = conn.execute('SELECT * FROM curriculum_situation_requests WHERE profile_id=? AND request_id=?', (profile['id'], request_id)).fetchone()
            if receipt:
                if receipt['request_sha256'] != digest:
                    raise LearningError('idempotency_conflict', 'This request already belongs to another activity.', 409)
                return self._public(self._owned(conn, access, receipt['situation_id']))
            existing = conn.execute("SELECT j.* FROM curriculum_situations j LEFT JOIN learning_sessions s ON s.id=j.session_id "
                "WHERE j.profile_id=? AND j.unit_id=? AND j.mode=? AND (j.state!='ready' OR s.status='active') "
                "ORDER BY j.created_at DESC,j.rowid DESC LIMIT 1", (profile['id'], unit_id, mode)).fetchone()
            # A capped failure can be replaced by an explicit new start. A
            # partially answered or preparing situation is always resumed.
            capped_failure = existing and self._public(existing)['state'] == 'failed' and not self._public(existing)['retryable']
            if existing and not capped_failure:
                row = existing
            else:
                recent_count = conn.execute('SELECT COUNT(*) FROM curriculum_situations WHERE profile_id=? AND created_at>?', (profile['id'], now - 3600)).fetchone()[0]
                if recent_count >= 6:
                    raise LearningError('preparation_limit', 'You have prepared several situations. Continue one of them before trying again later.', 429)
                # The lexical store is intentionally shared by profiles in one
                # local workspace. It remains isolated between hosted accounts.
                words = conn.execute('SELECT id,lemma,pos FROM words ORDER BY count DESC,id LIMIT 60').fetchall()
                vocabulary = []
                for word in words:
                    forms = [dict(form) for form in conn.execute('SELECT form,tags FROM forms WHERE word_id=? ORDER BY count DESC,id LIMIT 6', (word['id'],))]
                    vocabulary.append({'lemma': word['lemma'], 'pos': word['pos'], 'forms': forms})
                # A busy profile's other lessons must not erase this unit's
                # recent semantic families. Reading/listening share exposure.
                # Accepted text awaiting audio/publication has not been issued
                # to the learner and must not count as an encountered family.
                recent = [json.loads(value[0]) for value in conn.execute(
                    "SELECT document_json FROM curriculum_situations WHERE profile_id=? AND unit_id=? "
                    "AND state='ready' AND session_id IS NOT NULL AND document_json IS NOT NULL "
                    "ORDER BY created_at DESC,rowid DESC LIMIT 12", (profile['id'], unit_id))]
                sid = identifier()
                plan = build_request(unit, sid, vocabulary, recent, mode=mode)
                conn.execute("INSERT INTO curriculum_situations(id,profile_id,unit_id,mode,request_json,state,stage,created_at,updated_at) VALUES (?,?,?,?,?,'pending','text',?,?)",
                    (sid, profile['id'], unit_id, mode, encoded(plan), now, now))
                row = self._owned(conn, access, sid)
            conn.execute('INSERT INTO curriculum_situation_requests VALUES (?,?,?,?)', (profile['id'], request_id, digest, row['id']))
            return self._public(row)

    def advance(self, access, sid, *, retry=False):
        from services.curriculum_situation_content import generate
        from services.curriculum_generated_audio import plan_audio, generate_audio
        with transaction(self.db_path, write=True) as conn:
            row = self._owned(conn, access, sid)
            if row['state'] == 'ready' or (row['state'] == 'running' and row['lease_until'] > self.clock()):
                return self._public(row)
            if row['state'] != 'pending' and not retry:
                return self._public(row)
            if not self.available():
                raise LearningError('practice_unavailable', 'Preparation is unavailable. Your saved work is kept.', 403)
            stage = row['stage']
            field = 'audio_attempts' if stage == 'audio' else 'text_attempts'
            if stage != 'publish' and row[field] >= MAX_ATTEMPTS:
                raise LearningError('preparation_limit', 'This preparation has reached its retry limit. Return to the lesson to start again.', 429)
            claim = identifier()
            increment = 0 if stage == 'publish' else 1
            conn.execute(f"UPDATE curriculum_situations SET state='running',claim_id=?,lease_until=?,{field}={field}+{increment},error_code=NULL,updated_at=? WHERE id=?",
                         (claim, self.clock() + LEASE_SECONDS, self.clock(), sid))
            plan = json.loads(row['request_json'])
            document = json.loads(row['document_json']) if row['document_json'] else None
            voice = json.loads(row['voice_json']) if row['voice_json'] else None
        try:
            if stage == 'text':
                document = generate(plan, self.provider)
                with transaction(self.db_path, write=True) as conn:
                    owned = self._claimed(conn, access, sid, claim)
                    listening = owned['mode'] == 'listening'
                    conn.execute("UPDATE curriculum_situations SET document_json=?,stage=?,state=?,claim_id=?,lease_until=?,updated_at=? WHERE id=?",
                        (encoded(document), 'audio' if listening else 'publish', 'pending' if listening else 'running',
                         None if listening else claim, 0 if listening else self.clock() + LEASE_SECONDS, self.clock(), sid))
                if not listening:
                    with transaction(self.db_path, write=True) as conn:
                        self._claimed(conn, access, sid, claim)
                        self._publish(conn, access, sid, document)
            elif stage == 'audio':
                if voice is None:
                    voice = plan_audio(document['response']['text'], self.speech)
                    with transaction(self.db_path, write=True) as conn:
                        self._claimed(conn, access, sid, claim)
                        conn.execute('UPDATE curriculum_situations SET voice_json=? WHERE id=?', (encoded(voice), sid))
                audio = generate_audio(voice, self.speech, self.config['APP_MEDIA_DIR'])
                with transaction(self.db_path, write=True) as conn:
                    self._claimed(conn, access, sid, claim)
                    conn.execute("UPDATE curriculum_situations SET audio_json=?,stage='publish' WHERE id=?", (encoded(audio), sid))
                with transaction(self.db_path, write=True) as conn:
                    self._claimed(conn, access, sid, claim)
                    self._publish(conn, access, sid, document, audio)
            else:
                with transaction(self.db_path, write=True) as conn:
                    current = self._claimed(conn, access, sid, claim)
                    self._publish(conn, access, sid, document, json.loads(current['audio_json']) if current['audio_json'] else None)
        except LearningError as error:
            if error.code == 'preparation_changed':
                raise
            self._failed(sid, claim, 'preparation_failed')
        except TrialDenied:
            self._failed(sid, claim, 'allowance_unavailable')
        except Exception:
            # Provider exceptions can contain secrets or private request data.
            self._failed(sid, claim, 'preparation_failed')
        return self.read(access, sid)

    def _claimed(self, conn, access, sid, claim):
        row = self._owned(conn, access, sid)
        if row['claim_id'] != claim:
            raise LearningError('preparation_changed', 'Preparation changed in another tab. Reopen the lesson.', 409)
        return row

    def _failed(self, sid, claim, code):
        with transaction(self.db_path, write=True) as conn:
            conn.execute("UPDATE curriculum_situations SET state='failed',error_code=?,claim_id=NULL,lease_until=0,updated_at=? WHERE id=? AND claim_id=?",
                         (code, self.clock(), sid, claim))

    def _publish(self, conn, access, sid, document, audio=None):
        from services.curriculum_situation_content import to_pack
        from services.learning_service import LearningService
        row = self._owned(conn, access, sid)
        pack = validate_pack(to_pack(document, content_id=PREFIX + row['unit_id'] + ':' + sid, audio=audio))
        version, session_id, now = identifier(), identifier(), self.clock()
        conn.execute("INSERT INTO learning_content(id,kind,created_at) VALUES (?,'activity',?)", (pack['id'], now))
        conn.execute("INSERT INTO learning_content_versions(id,content_id,version,title,payload,source,status,approved_by,approved_at,created_at) VALUES (?,?,1,?,?,?,'published','validated generated practice',?,?)",
                     (version, pack['id'], pack['title'], encoded(pack), pack['source'], now, now))
        conn.execute("INSERT INTO learning_sessions(id,profile_id,version_id,kind,start_key,start_hash,start_result,created_at,updated_at) VALUES (?,?,?,'activity',?,?,'{}',?,?)",
                     (session_id, row['profile_id'], version, 'situation-' + sid, payload_hash({'situation': sid}), now, now))
        freeze(conn, row['profile_id'], session_id, pack, document)
        service = LearningService(self.db_path, media_root=self.config['APP_MEDIA_DIR'])
        result = service._snapshot(conn, session_id, pack)
        conn.execute('UPDATE learning_sessions SET start_result=? WHERE id=?', (encoded(result), session_id))
        conn.execute("UPDATE curriculum_situations SET session_id=?,state='ready',stage='ready',claim_id=NULL,lease_until=0,error_code=NULL,updated_at=? WHERE id=?", (session_id, now, sid))
