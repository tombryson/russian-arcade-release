"""Server-owned attempts and shared effects, without provider calls or SRS.

The choice adapter proves the transaction contract. Native review will add its
scheduler transition to this boundary in Stage 2, not infer recall from choices.
"""
from datetime import datetime, timezone
import json
from urllib.parse import quote
from zoneinfo import ZoneInfo

from flask import has_request_context, session

from contracts.learning import fields, key, revision, reject, assess_activity_answer, activity_answer_text
from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, require_access, timestamp, transaction
from services.learning_content import child_item, published_version
from services.learning_listening import (
    item_support, current_item_support, capture_shared_transcript,
    feedback_is_deferred, record_support, verify_audio,
)


ASSESSMENT_POLICY = 'reviewed-choice-v1'
CONTROLLED_TEXT_POLICY = 'authored-controlled-form-v1'
LISTENING_POLICY = 'authored-listening-choice-v1'
REWARD_POLICY = 'practice-participation-v1'


def award_participation(conn, profile, attempt_id, content_id, now):
    """Pilot game policy: 3 coins/activity/day, at most 12 game coins/day.

Called only after validated completion, inside the attempt's write transaction.
The ledger is the balance authority; no separate total can drift out of sync.
"""
    from services.progression import award
    return award(conn,profile['id'],activity='activity',content_key=content_id,
                 source_key=attempt_id,title='Practice activity',now=now)


class LearningService:
    def __init__(self, db_path, clock=timestamp, native_review_enabled=True):
        self.db_path, self.clock = db_path, clock
        self.native_review_enabled = native_review_enabled

    def home(self, access_id):
        with transaction(self.db_path) as conn:
            profile = require_access(conn, access_id, self.clock())
            content = [dict(row) for row in conn.execute(
                "SELECT v.id AS version_id,v.content_id,v.title,c.kind FROM learning_content_versions v JOIN learning_content c ON c.id=v.content_id "
                "WHERE v.status='published' AND v.version=(SELECT MAX(v2.version) FROM learning_content_versions v2 WHERE v2.content_id=v.content_id AND v2.status='published') ORDER BY v.title")]
            sessions = [dict(row) for row in conn.execute(
                "SELECT s.id,s.version_id,s.revision,s.status,v.title,v.status AS content_status FROM learning_sessions s JOIN learning_content_versions v ON v.id=s.version_id WHERE s.profile_id=? ORDER BY s.updated_at DESC LIMIT 50", (profile['id'],))]
            return {'profile': {'id': profile['id'], 'display_name': profile['display_name']}, 'content': content,
                    'sessions': sessions, 'balance': self._balance(conn, profile['id']), 'native_review_available': self.native_review_enabled}

    @staticmethod
    def _balance(conn, profile_id):
        return conn.execute('SELECT COALESCE(SUM(amount),0) FROM progression_entries WHERE profile_id=?', (profile_id,)).fetchone()[0]

    def start(self, access_id, data):
        fields(data, {'profile_id','version_id','submission_id'})
        for name in data:
            key(data[name], name)
        digest = payload_hash(data)
        with transaction(self.db_path, write=True) as conn:
            now = self.clock()
            profile = require_access(conn, access_id, now, profile_id=data['profile_id'])
            version, pack = published_version(conn, data['version_id'])
            if pack['kind'] != 'activity':
                raise LearningError('use_native_review', 'Open Flashcards to practise this deck.', 409)
            if pack['id'].startswith('curriculum-unit:sequence:'):
                raise LearningError('use_lesson', 'Open this activity from its lesson.', 409)
            existing = conn.execute('SELECT * FROM learning_sessions WHERE profile_id=? AND start_key=?', (profile['id'], data['submission_id'])).fetchone()
            if existing:
                if existing['start_hash'] != digest:
                    raise LearningError('idempotency_conflict', 'That request ID was already used for different content.', 409)
                return json.loads(existing['start_result'])
            for item in pack['items']:
                if item['type'] == 'listening_choice':
                    verify_audio(item)
            session_id = identifier()
            conn.execute('INSERT INTO learning_sessions(id,profile_id,version_id,kind,start_key,start_hash,start_result,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                         (session_id, profile['id'], version['id'], pack['kind'], data['submission_id'], digest, '{}', now, now))
            from services.curriculum_units import freeze_practice
            freeze_practice(conn, profile['id'], session_id, pack)
            result = self._snapshot(conn, session_id, pack)
            conn.execute('UPDATE learning_sessions SET start_result=? WHERE id=?', (encoded(result), session_id))
            return result

    def _owned_session(self, conn, access_id, session_id):
        # Authorise before returning even a cached result or an unavailable notice.
        profile = require_access(conn, access_id, self.clock())
        saved = conn.execute('SELECT * FROM learning_sessions WHERE id=? AND profile_id=?', (session_id, profile['id'])).fetchone()
        if not saved:
            raise LearningError('not_found', 'This session is not available for the selected learner.', 404)
        version, pack = published_version(conn, saved['version_id'])
        return profile, saved, version, pack

    def read(self, access_id, session_id):
        with transaction(self.db_path) as conn:
            _, _, _, pack = self._owned_session(conn, access_id, session_id)
            return self._snapshot(conn, session_id, pack)

    def audio_path(self, access_id, session_id, item_id):
        """Serve only a recording already reached in this learner's frozen run.

        Reading the file is not a playback receipt. The player records completion
        separately, after the audio ends; neither operation changes an answer.
        """
        with transaction(self.db_path) as conn:
            _, saved, _, pack = self._owned_session(conn, access_id, session_id)
            reached = pack['items'][:saved['current_index'] + 1]
            item = next((item for item in reached if item['id'] == item_id), None)
            if item is None or item['type'] != 'listening_choice':
                raise LearningError('not_found', 'This recording is not available in this activity.', 404)
            return verify_audio(item)

    def _snapshot(self, conn, session_id, pack):
        from services.curriculum_units import practice_context
        origin = practice_context(pack)
        russian_ui = has_request_context() and session.get('ui_lang') == 'ru'
        title = pack['title']
        saved = conn.execute('SELECT * FROM learning_sessions WHERE id=?', (session_id,)).fetchone()
        attempts = [dict(row) for row in conn.execute('SELECT id,item_id,answer,assisted,outcome FROM activity_attempts WHERE session_id=? ORDER BY created_at,rowid', (session_id,))]
        items = {item['id']: item for item in pack['items']}
        for attempt in attempts:
            attempt['answer'] = json.loads(attempt['answer'])
            item = items[attempt['item_id']]
            attempt['prompt'] = item['prompt']
            # Reconstruct the structured choice feedback from the immutable
            # answer policy; reload must retain the correction, not only a mark.
            answer_text = activity_answer_text(item)
            attempt['feedback'] = {'outcome': attempt['outcome'], 'answer': answer_text, 'assisted': bool(attempt['assisted'])}
            if item['type'] == 'controlled_text':
                attempt['feedback']['response_text'] = attempt['answer']['text']
            if item['type'] == 'listening_choice':
                attempt['feedback'].update(item_support(conn, session_id, item), transcript=item['transcript'])
                attempt['feedback']['response_text'], _ = assess_activity_answer(item, attempt['answer'])
            if origin or pack['id'].startswith('curriculum-unit:sequence:'):
                from services.activity_evidence import load_contract
                contract = load_contract(conn, saved['profile_id'], 'curriculum_unit', session_id + ':' + attempt['item_id'])
                content = contract['content']
                attempt['feedback']['explanation'] = content.get('explanation_ru', content['explanation']) if russian_ui else content['explanation']
                if russian_ui:
                    title = content.get('title_ru', title)
                    attempt['prompt'] = content.get('item_locale_ru', {}).get('prompt', attempt['prompt'])
                if pack['id'].startswith('curriculum-unit:sequence:'):
                    report = conn.execute('SELECT r.support_json FROM activity_criterion_reports r JOIN activity_task_contracts c ON c.id=r.contract_id '
                                          'WHERE r.profile_id=? AND c.activity=? AND r.source_key=?',
                                          (saved['profile_id'], 'curriculum_unit', attempt['id'])).fetchone()
                    if report:
                        attempt['feedback']['support'] = json.loads(report[0])
            if item['type'] == 'listening_choice' and feedback_is_deferred(pack, saved['current_index'], item):
                # The answer key (even a binary correctness mark) can resolve a
                # later question about this same message. Keep only the reply.
                response_text, _ = assess_activity_answer(item, attempt['answer'])
                previous = attempt['feedback']
                attempt['feedback'] = {'deferred': True, 'outcome': 'deferred',
                    'response_text': response_text, 'assisted': previous['assisted'],
                    'support': previous.get('support', []), 'listened': previous.get('listened', False)}
                if 'transcript' in previous.get('support', []):
                    attempt['feedback']['transcript'] = item['transcript']
                attempt.pop('outcome', None)
        current = None
        if saved['status'] == 'active':
            item = pack['items'][saved['current_index']]
            support = current_item_support(conn, session_id, item, pack, saved['current_index']) if item['type'] == 'listening_choice' else {'listened': False, 'support': []}
            current = child_item(item, help_used=bool(saved['help_used']), listened=support['listened'],
                                 transcript_used='transcript' in support['support'])
            if item['type'] == 'listening_choice':
                # Shared static requests use the anonymous hosted application.
                # Keep the immutable asset reference in the pack, and expose an
                # owned route that works in personal and /demo workspaces.
                current['audio'] = {**current['audio'], 'url':
                    f"/api/v1/learning-sessions/{quote(session_id, safe='')}/items/{quote(item['id'], safe='')}/audio"}
            if russian_ui and pack['id'].startswith('curriculum-unit:sequence:'):
                from services.activity_evidence import load_contract
                content = load_contract(conn, saved['profile_id'], 'curriculum_unit', session_id + ':' + item['id'])['content']
                title = content.get('title_ru', title)
                for name in ('prompt', 'hint'):
                    # Only translate fields already exposed by the player.
                    # A localized hint must not bypass the help receipt.
                    if name in current and name in content.get('item_locale_ru', {}):
                        current[name] = content['item_locale_ru'][name]
        from services.curriculum_sequences import practice_context as sequence_context
        sequence = sequence_context(conn, saved['profile_id'], session_id)
        draft = None
        if current and current.get('type') == 'controlled_text':
            row = conn.execute('SELECT response_json,revision FROM learning_session_drafts WHERE session_id=? AND item_id=?',
                               (session_id, current['id'])).fetchone()
            draft = {'response': json.loads(row[0]), 'revision': row[1]} if row else {'response': {'text': ''}, 'revision': 0}
        return {'id': saved['id'], 'profile_id': saved['profile_id'], 'version_id': saved['version_id'],
                'title': title, 'revision': saved['revision'], 'status': saved['status'],
                'completed_items': saved['current_index'], 'total_items': len(pack['items']),
                'item': current,
                'attempts': attempts, 'balance': self._balance(conn, saved['profile_id']),
                **({'origin': {'href': origin['href'], 'title': origin['title']}} if origin else {}),
                **({'draft_enabled': True, 'draft': draft} if draft is not None else {}),
                **({'sequence': sequence} if sequence else {})}

    def save_draft(self, access_id, session_id, data):
        fields(data, {'submission_id', 'item_id', 'expected_revision', 'expected_draft_revision', 'response'})
        key(data['submission_id']); key(data['item_id'])
        revision(data['expected_revision']); revision(data['expected_draft_revision'])
        fields(data['response'], {'text'})
        text = data['response']['text']
        if not isinstance(text, str) or len(text) > 200 or '\x00' in text:
            reject('Keep this answer under 200 characters.')
        digest = payload_hash({'operation': 'draft', **data})
        with transaction(self.db_path, write=True) as conn:
            _, saved, _, pack = self._owned_session(conn, access_id, session_id)
            cached = conn.execute('SELECT payload_hash,result FROM learning_commands WHERE session_id=? AND submission_id=?',
                                  (session_id, data['submission_id'])).fetchone()
            if cached:
                if cached[0] != digest:
                    raise LearningError('idempotency_conflict', 'This request was used for another answer.', 409)
                return json.loads(cached[1])
            if saved['status'] != 'active' or saved['revision'] != data['expected_revision']:
                raise LearningError('stale_revision', 'This activity changed. Your unsaved text is still here.', 409)
            item = pack['items'][saved['current_index']]
            if item['type'] != 'controlled_text' or item['id'] != data['item_id']:
                raise LearningError('wrong_item', 'This answer belongs to another question.', 409)
            old = conn.execute('SELECT revision FROM learning_session_drafts WHERE session_id=? AND item_id=?',
                               (session_id, item['id'])).fetchone()
            old_revision = old[0] if old else 0
            if old_revision != data['expected_draft_revision']:
                raise LearningError('stale_draft', 'A newer draft is saved in another tab. Copy your text before reloading.', 409)
            now = self.clock()
            conn.execute('INSERT INTO learning_session_drafts VALUES (?,?,?,?,?) ON CONFLICT(session_id,item_id) '
                         'DO UPDATE SET response_json=excluded.response_json,revision=excluded.revision,updated_at=excluded.updated_at',
                         (session_id, item['id'], encoded(data['response']), old_revision + 1, now))
            result = {'draft': {'response': data['response'], 'revision': old_revision + 1}}
            conn.execute('INSERT INTO learning_commands VALUES (?,?,?,?,?)',
                         (session_id, data['submission_id'], digest, encoded(result), now))
            return result

    def command(self, access_id, session_id, operation, data):
        required = {'submission_id','expected_revision','item_id'} | ({'answer'} if operation == 'answer' else set())
        fields(data, required)
        key(data['submission_id'], 'Submission ID')
        key(data['item_id'], 'Item ID')
        revision(data['expected_revision'])
        if operation not in ('answer','help','listened','transcript'):
            reject('Unsupported learning operation.')
        if operation == 'answer':
            if not isinstance(data['answer'], dict):
                reject('Provide an answer for this activity.')
        digest = payload_hash({'operation': operation, **data})
        with transaction(self.db_path, write=True) as conn:
            now = self.clock()
            profile, saved, version, pack = self._owned_session(conn, access_id, session_id)
            cached = conn.execute('SELECT * FROM learning_commands WHERE session_id=? AND submission_id=?', (session_id, data['submission_id'])).fetchone()
            if cached:
                if cached['payload_hash'] != digest:
                    raise LearningError('idempotency_conflict', 'That submission ID was already used for another answer.', 409)
                return json.loads(cached['result'])
            if saved['revision'] != data['expected_revision']:
                raise LearningError('stale_revision', 'A newer answer is saved. Reload the current session before continuing.', 409,
                                    {'current_session': self._snapshot(conn, session_id, pack)})
            if saved['status'] != 'active':
                raise LearningError('session_complete', 'This session is already complete.', 409)
            item = pack['items'][saved['current_index']]
            if data['item_id'] != item['id']:
                raise LearningError('wrong_item', 'Please answer the current item.', 409)
            capture_shared_transcript(conn, session_id, pack, now)
            coins, feedback = 0, None
            if operation == 'help':
                if not item.get('hint'):
                    reject('This item has no saved hint.')
                conn.execute('UPDATE learning_sessions SET help_used=1,revision=revision+1,updated_at=? WHERE id=?', (now, session_id))
                if pack['id'].startswith('curriculum-unit:sequence:'):
                    conn.execute('INSERT OR IGNORE INTO learning_hint_usage VALUES (?,?)', (session_id, item['id']))
                if item['type'] == 'listening_choice':
                    record_support(conn, session_id, item, operation, now)
            elif operation in ('listened', 'transcript'):
                record_support(conn, session_id, item, operation, now)
                conn.execute('UPDATE learning_sessions SET revision=revision+1,updated_at=? WHERE id=?', (now, session_id))
            else:
                listening = item['type'] == 'listening_choice'
                support = item_support(conn, session_id, item) if listening else {
                    'listened': False, 'support': ['hint'] if saved['help_used'] else []}
                if listening and not support['listened'] and 'transcript' not in support['support']:
                    raise LearningError('listen_required', 'Listen to the message or open its transcript before answering.', 409)
                if pack['id'].startswith('curriculum-unit:sequence:'):
                    from services.curriculum_sequences import capture_prior_feedback, practice_support
                    capture_prior_feedback(conn, profile['id'], session_id, item['id'])
                    support['support'] = practice_support(conn, profile['id'], session_id, item['id'], support['support'])
                assisted = bool(support['support'])
                response_text, correct = assess_activity_answer(item, data['answer'])
                outcome = 'correct' if correct else 'incorrect'
                policy = LISTENING_POLICY if listening else CONTROLLED_TEXT_POLICY if item['type'] == 'controlled_text' else ASSESSMENT_POLICY
                attempt_id = identifier()
                conn.execute('INSERT INTO activity_attempts(id,session_id,item_id,submission_id,answer,assisted,outcome,policy_version,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                             (attempt_id, session_id, item['id'], data['submission_id'], encoded(data['answer']), int(assisted), outcome, policy, now))
                if item.get('word_id'):
                    conn.execute('INSERT INTO learner_word_evidence VALUES (?,?,?,?,?,?)',
                                 (attempt_id, profile['id'], item['word_id'], 'supported_recognition' if saved['help_used'] else 'recognition', outcome, now))
                from services.curriculum_units import observe_answer
                observe_answer(conn, profile['id'], session_id, pack, item, attempt_id,
                               data['answer'], assisted, support=support['support'])
                complete = saved['current_index'] + 1 == len(pack['items'])
                conn.execute('UPDATE learning_sessions SET current_index=current_index+1,revision=revision+1,help_used=0,status=?,updated_at=? WHERE id=?',
                             ('completed' if complete else 'active', now, session_id))
                capture_shared_transcript(conn, session_id, pack, now)
                if complete:
                    from services.curriculum_sequences import award_practice, binding_for_task
                    binding = binding_for_task(conn, profile['id'], 'curriculum_unit', session_id)
                    coins = award_practice(conn, profile, binding, attempt_id, version['content_id'], now)
                answer_text = activity_answer_text(item)
                feedback = {'outcome': outcome, 'answer': answer_text, 'assisted': assisted}
                if listening:
                    feedback.update(support, transcript=item['transcript'])
                if item['type'] == 'controlled_text':
                    feedback['response_text'] = response_text
            result = self._snapshot(conn, session_id, pack)
            if feedback is not None and result['attempts']:
                feedback = result['attempts'][-1]['feedback']
            result.update(coins_earned=coins, feedback=feedback)
            conn.execute('INSERT INTO learning_commands VALUES (?,?,?,?,?)', (session_id, data['submission_id'], digest, encoded(result), now))
            return result

    def progress(self, access_id):
        with transaction(self.db_path) as conn:
            profile = require_access(conn, access_id, self.clock())
            evidence = [dict(row) for row in conn.execute('SELECT e.attempt_id,e.word_id,w.lemma,e.evidence_type,e.outcome,e.created_at FROM learner_word_evidence e JOIN words w ON w.id=e.word_id LEFT JOIN review_reversals r ON r.attempt_id=e.attempt_id WHERE e.profile_id=? AND r.id IS NULL ORDER BY e.created_at DESC LIMIT 200', (profile['id'],))]
            rewards = [dict(row) for row in conn.execute('SELECT id,event_id AS attempt_id,amount,study_day,category,policy_version FROM progression_entries WHERE profile_id=? ORDER BY created_at DESC,rowid DESC LIMIT 200', (profile['id'],))]
            return {'profile_id': profile['id'], 'evidence': evidence, 'balance': self._balance(conn, profile['id']), 'rewards': rewards}
