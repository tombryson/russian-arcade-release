"""Audio practice keeps owned playback/support receipts and frozen criteria."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch

from contracts.learning import validate_pack
from migrations import upgrade_database
from repositories.learning_repository import LearningError, encoded
from services.account_import import ImportConflict, build_account_import, digest
from services.activity_evidence import validate_saved_evidence
from services.curriculum_units import get_unit, _pack, _practice_contract, _questions
from tests.support import isolated_app


UNIT = 'location-destination-v1'
PATH = '/curriculum/units/' + UNIT
ROOT = Path(__file__).resolve().parents[1]


class CurriculumUnitListeningTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.state = self.client.get('/api/v1/user-session').json
        self.headers = {'X-CSRF-Token': self.state['csrf_token']}
        self.sequence = 0

    def start_response(self, stage='listening', request_id=None):
        self.sequence += 1
        return self.client.post(PATH + '/' + stage, data={
            'profile_id': self.state['profile']['id'],
            'request_id': request_id or f'start-{self.sequence}'}, headers=self.headers)

    def start(self, stage='listening'):
        response = self.start_response(stage)
        self.assertEqual(response.status_code, 303, response.text)
        response = self.client.get('/api/v1/learning-sessions/' + response.location.rsplit('/', 1)[1])
        self.assertEqual(response.status_code, 200, response.text)
        return response.json

    def path(self, saved):
        return '/api/v1/learning-sessions/' + saved['id']

    def body(self, saved, answer=None):
        self.sequence += 1
        result = {'submission_id': f'command-{self.sequence}', 'expected_revision': saved['revision'],
                  'item_id': saved['item']['id']}
        if answer is not None:
            result['answer'] = answer
        return result

    def command(self, saved, action, answer=None):
        response = self.client.post(self.path(saved) + '/' + action,
                                    json=self.body(saved, answer), headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json

    def item(self, saved):
        with sqlite3.connect(self.db) as conn:
            pack = json.loads(conn.execute('SELECT payload FROM learning_content_versions WHERE id=?',
                                           (saved['version_id'],)).fetchone()[0])
        return next(item for item in pack['items'] if item['id'] == saved['item']['id'])

    def assert_no_transcript(self, saved, item):
        self.assertNotIn(item['transcript'], json.dumps(saved, ensure_ascii=False))
        self.assertFalse(saved['item'].get('transcript'))
        for secret in ('answer', 'accepted_answers', 'explanation'):
            self.assertNotIn(secret, saved['item'])

    def test_new_item_hides_transcript_and_rejects_answer_until_playback(self):
        saved = self.start()
        item = self.item(saved)
        self.assertEqual(saved['item']['type'], 'listening_choice')
        self.assertFalse(saved['item']['listened'])
        self.assert_no_transcript(saved, item)
        response = self.client.post(self.path(saved) + '/attempts',
            json=self.body(saved, {'choice_id': item['answer']}), headers=self.headers)
        self.assertEqual(response.status_code, 409, response.text)
        restored = self.client.get(self.path(saved)).json
        self.assertEqual(restored['revision'], saved['revision'])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_commands').fetchone()[0], 0)
        listened = self.command(saved, 'listened')
        self.assertTrue(listened['item']['listened'])
        self.assert_no_transcript(listened, item)
        self.assertEqual(self.client.get(self.path(saved)).json['item'], listened['item'])

    def test_support_is_saved_exactly_and_does_not_leak_into_next_item(self):
        saved = self.start()
        item = self.item(saved)
        saved = self.command(saved, 'transcript')
        self.assertEqual(saved['item']['transcript'], item['transcript'])
        self.assertFalse(saved['item']['listened'])
        saved = self.command(saved, 'help')
        self.assertEqual(saved['item']['hint'], item['hint'])
        self.assertEqual(self.client.get(self.path(saved)).json['item'], saved['item'])
        saved = self.command(saved, 'listened')
        answered = self.command(saved, 'attempts', {'choice_id': item['answer']})
        self.assertTrue(answered['attempts'][-1]['assisted'])
        self.assertFalse(answered['item']['listened'])
        self.assertFalse(answered['item'].get('transcript'))
        self.assertNotIn('hint', answered['item'])
        with sqlite3.connect(self.db) as conn:
            receipt = conn.execute('SELECT listened_at,transcript_at,hint_at,audio_sha256 FROM learning_item_support '
                                   'WHERE session_id=? AND item_id=?', (saved['id'], item['id'])).fetchone()
            self.assertTrue(all(value is not None for value in receipt[:3]))
            self.assertEqual(receipt[3], item['audio']['sha256'])
            report = conn.execute('SELECT report_json,support_json FROM activity_criterion_reports').fetchone()
            self.assertEqual(json.loads(report[1]), ['hint', 'transcript'])
            self.assertEqual(json.loads(report[0])['judgements'][0]['outcome'], 'satisfied')
            changes = conn.total_changes
            validate_saved_evidence(conn)
            self.assertEqual(conn.total_changes, changes)

    def test_retry_is_exact_and_new_stale_wrong_item_and_changed_operation_are_rejected(self):
        saved = self.start()
        body = self.body(saved)
        first = self.client.post(self.path(saved) + '/listened', json=body, headers=self.headers)
        self.assertEqual(first.status_code, 200, first.text)
        for _ in range(2):
            retry = self.client.post(self.path(saved) + '/listened', json=body, headers=self.headers)
            self.assertEqual(retry.json, first.json)
        changed = self.client.post(self.path(saved) + '/transcript', json=body, headers=self.headers)
        self.assertEqual(changed.status_code, 409, changed.text)
        stale = self.client.post(self.path(saved) + '/transcript', json=self.body(saved), headers=self.headers)
        self.assertEqual(stale.status_code, 409, stale.text)
        wrong = self.body(first.json)
        wrong['item_id'] = 'another-item'
        denied = self.client.post(self.path(saved) + '/transcript', json=wrong, headers=self.headers)
        self.assertEqual(denied.status_code, 409, denied.text)
        current = first.json
        item = self.item(current)
        answer = self.body(current, {'choice_id': item['answer']})
        result = self.client.post(self.path(saved) + '/attempts', json=answer, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        for _ in range(2):
            retry = self.client.post(self.path(saved) + '/attempts', json=answer, headers=self.headers)
            self.assertEqual(retry.json, result.json)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_commands').fetchone()[0], 2)
            self.assertIsNone(conn.execute('SELECT transcript_at FROM learning_item_support WHERE session_id=? AND item_id=?',
                                          (saved['id'], item['id'])).fetchone()[0])

    def test_profile_switch_cannot_read_support_or_replay_cached_receipt(self):
        saved = self.start()
        body = self.body(saved)
        self.assertEqual(self.client.post(self.path(saved) + '/transcript', json=body, headers=self.headers).status_code, 200)
        changed = self.client.post('/api/v1/user-session/profiles', json={'display_name': 'Other listener'}, headers=self.headers)
        self.assertEqual(changed.status_code, 201, changed.text)
        headers = {'X-CSRF-Token': changed.json['csrf_token']}
        self.assertEqual(self.client.get(self.path(saved)).status_code, 404)
        for action in ('transcript', 'listened', 'help'):
            response = self.client.post(self.path(saved) + '/' + action, json=body, headers=headers)
            self.assertEqual(response.status_code, 404, response.text)

    def test_listening_commands_reject_choice_and_forms_without_changing_them(self):
        for stage in ('practice', 'forms'):
            with self.subTest(stage=stage):
                saved = self.start(stage)
                for action in ('listened', 'transcript'):
                    response = self.client.post(self.path(saved) + '/' + action,
                                                json=self.body(saved), headers=self.headers)
                    self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(self.client.get(self.path(saved)).json, saved)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_item_support').fetchone()[0], 0)

    def test_answer_evidence_failure_rolls_back_attempt_and_keeps_support(self):
        saved = self.command(self.start(), 'listened')
        item = self.item(saved)
        with patch('services.curriculum_units.save_report', side_effect=RuntimeError('evidence unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'evidence unavailable'):
                self.client.post(self.path(saved) + '/attempts',
                    json=self.body(saved, {'choice_id': item['answer']}), headers=self.headers)
        self.assertEqual(self.client.get(self.path(saved)).json, {k: v for k, v in saved.items() if k not in ('coins_earned', 'feedback')})
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_commands').fetchone()[0], 1)

    def test_all_three_items_need_own_receipt_and_only_existing_participation_is_awarded(self):
        saved = self.start()
        while saved['status'] == 'active':
            self.assertFalse(saved['item']['listened'])
            item = self.item(saved)
            saved = self.command(saved, 'listened')
            saved = self.command(saved, 'attempts', {'choice_id': item['answer']})
        self.assertEqual(saved['coins_earned'], 3)
        self.assertEqual(len(saved['attempts']), 3)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_item_support WHERE listened_at IS NOT NULL').fetchone()[0], 3)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 3)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT DISTINCT support_json FROM activity_criterion_reports').fetchall(), [('[]',)])

    def test_old_published_packs_and_contract_hashes_stay_byte_identical(self):
        unit = get_unit(UNIT)
        expected = {
            'practice': ('f69c783ceab3424b9c9c26f424803c41902b5fc992972681bfe90c0d15830ddb', [
                '26363eecd98b3204b0397d666f8fb972feae28cfdab71f59f653b41b9571eac0',
                '7bc5298935925d7f4914581f29563af4823aaf073b8760630efc58f8e0867bab',
                '02d33d37c1641f7752e50d16a935d583a9863bb0f2df0bb313527e5d173e66c4',
                'e68c53d3a5c9974713c25daa61d692e65912bb85b2c0face6e0a2b7b99273939']),
            'forms': ('26c5095d7996901290e791c2097b25a683b6363acdc2ea6e88670c3a66e246e9', [
                'cb66c8c2d3d48430a60fb4afb9ec998213905da09699d11c7a8b5fa41e0bba3a',
                '3f8a510b96ee9ddc77260b78a4a116d48200b19436b4b37424dbba86a872282a',
                '31a6957dac2b65bb4442bf45c0fd56f01c5af127ebc0b7c079de32d23f379193'])}
        for stage, (payload_hash, hashes) in expected.items():
            pack = _pack(unit, stage)
            self.assertEqual(hashlib.sha256(encoded(pack).encode()).hexdigest(), payload_hash)
            self.assertEqual([_practice_contract(unit, item, question, 'validation')['contract_sha256']
                              for item, question in zip(pack['items'], _questions(unit, stage))], hashes)
            saved = self.start(stage)
            for field in ('audio', 'listened', 'transcript', 'has_transcript'):
                self.assertNotIn(field, saved['item'])

    def test_listening_schema_rejects_missing_audio_and_cross_mode_metadata(self):
        pack = _pack(get_unit(UNIT), 'listening')
        validate_pack(pack)
        mutations = [
            lambda item: item.pop('audio'),
            lambda item: item.pop('transcript'),
            lambda item: item.update(word_id=1),
            lambda item: item.update(accepted_answers=['магазин']),
            lambda item: item['audio'].update(url='https://example.com/message.mp3'),
            lambda item: item['audio'].update(sha256='g' * 64),
            lambda item: item['audio'].update(duration_ms=True),
            lambda item: item.update(type='choice'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = deepcopy(pack)
                mutate(changed['items'][0])
                with self.assertRaises(LearningError):
                    validate_pack(changed)

    def test_missing_audio_blocks_new_start_and_receipt_but_retains_transcript_fallback(self):
        saved = self.start()
        item = self.item(saved)
        target = (ROOT / 'static' / item['audio']['url'].removeprefix('/static/')).resolve()
        exists = Path.is_file

        def available(path):
            return False if path.resolve() == target else exists(path)

        with patch.object(Path, 'is_file', available):
            # Start-or-continue must still resume the saved activity so the
            # learner can choose its supported transcript fallback.
            self.assertEqual(self.start_response().status_code, 303)
            response = self.client.post('/api/v1/learning-sessions', json={
                'profile_id': self.state['profile']['id'], 'version_id': saved['version_id'],
                'submission_id': 'new-session-missing-audio'}, headers=self.headers)
            self.assertIn(response.status_code, (409, 503), response.text)
            receipt = self.client.post(self.path(saved) + '/listened', json=self.body(saved), headers=self.headers)
            self.assertIn(receipt.status_code, (409, 503), receipt.text)
            fallback = self.command(saved, 'transcript')
            self.assertEqual(fallback['item']['transcript'], item['transcript'])
            self.assertFalse(fallback['item']['listened'])
            answered = self.command(fallback, 'attempts', {'choice_id': item['answer']})
            self.assertTrue(answered['attempts'][-1]['assisted'])
            self.assertFalse(answered['attempts'][-1]['feedback']['listened'])

    def test_offline_import_preserves_listening_support_and_rejects_tampering(self):
        saved = self.command(self.start(), 'transcript')
        saved = self.command(saved, 'listened')
        item = self.item(saved)
        self.command(saved, 'attempts', {'choice_id': item['answer']})
        directory = Path(self.db).parent
        hosted, output = directory / 'empty-hosted.db', directory / 'listening-import.db'
        upgrade_database(hosted, backup=False)
        before = (digest(self.db), digest(hosted))
        build_account_import(self.db, hosted, output)
        self.assertEqual((digest(self.db), digest(hosted)), before)
        with sqlite3.connect(output) as conn, sqlite3.connect(self.db) as original:
            for table in ('learning_item_support', 'activity_task_contracts', 'activity_criterion_reports', 'activity_attempts'):
                self.assertEqual(conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall(),
                                 original.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall())
            validate_saved_evidence(conn)
        # Support may not be erased during import to turn supported listening
        # into an independent response; both source files remain unchanged.
        with sqlite3.connect(self.db) as conn:
            conn.execute('UPDATE learning_item_support SET transcript_at=NULL WHERE session_id=? AND item_id=?',
                         (saved['id'], item['id']))
        tampered = directory / 'tampered-import.db'
        before = (digest(self.db), digest(hosted))
        with self.assertRaises(ImportConflict):
            build_account_import(self.db, hosted, tampered)
        self.assertFalse(tampered.exists())
        self.assertEqual((digest(self.db), digest(hosted)), before)

    def test_receipts_without_reports_still_require_the_exact_saved_item_and_audio(self):
        saved = self.command(self.start(), 'transcript')
        item = self.item(saved)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 0)
            validate_saved_evidence(conn)
            conn.execute('UPDATE learning_item_support SET audio_sha256=? WHERE session_id=?', ('0' * 64, saved['id']))
            with self.assertRaises(ValueError):
                validate_saved_evidence(conn)
            conn.execute('UPDATE learning_item_support SET audio_sha256=?,item_id=? WHERE session_id=?',
                         (item['audio']['sha256'], 'not-a-published-item', saved['id']))
            with self.assertRaises(ValueError):
                validate_saved_evidence(conn)

    def test_import_audit_rejects_future_item_and_impossible_support_timestamps(self):
        saved = self.command(self.start(), 'transcript')
        item = self.item(saved)
        with sqlite3.connect(self.db) as conn:
            payload, started = conn.execute('SELECT v.payload,s.created_at FROM learning_sessions s '
                'JOIN learning_content_versions v ON v.id=s.version_id WHERE s.id=?', (saved['id'],)).fetchone()
            next_item = json.loads(payload)['items'][1]
            original = conn.execute('SELECT transcript_at FROM learning_item_support WHERE session_id=?', (saved['id'],)).fetchone()[0]
            conn.execute('UPDATE learning_item_support SET item_id=?,audio_sha256=? WHERE session_id=?',
                         (next_item['id'], next_item['audio']['sha256'], saved['id']))
            with self.assertRaises(ValueError):
                validate_saved_evidence(conn)
            conn.execute('UPDATE learning_item_support SET item_id=?,audio_sha256=? WHERE session_id=?',
                         (item['id'], item['audio']['sha256'], saved['id']))
            for invalid in (started - 1, 'not-a-timestamp', None):
                with self.subTest(timestamp=invalid):
                    conn.execute('UPDATE learning_item_support SET transcript_at=? WHERE session_id=?', (invalid, saved['id']))
                    with self.assertRaises(ValueError):
                        validate_saved_evidence(conn)
            conn.execute('UPDATE learning_item_support SET transcript_at=? WHERE session_id=?', (original, saved['id']))
        self.command(saved, 'attempts', {'choice_id': item['answer']})
        with sqlite3.connect(self.db) as conn:
            answered = conn.execute('SELECT created_at FROM activity_attempts WHERE session_id=?', (saved['id'],)).fetchone()[0]
            conn.execute('UPDATE learning_item_support SET transcript_at=? WHERE session_id=?', (answered + 1, saved['id']))
            with self.assertRaises(ValueError):
                validate_saved_evidence(conn)


class PublicListeningTests(unittest.TestCase):
    def setUp(self):
        from hosted import create_hosted_app
        from public_demo import prepare_demo
        environment = patch.dict(os.environ, {'PUBLIC_DEMO': 'true',
            'FLASK_SECRET_KEY': 'synthetic-test-secret-' * 3, 'HOSTED_HOSTNAME': 'arcade.example',
            'HOSTED_TRIAL_ROOT': '', 'AI_TRIAL_ENABLED': 'false', 'HOSTED_ACCOUNTS_ENABLED': 'false'})
        environment.start()
        self.addCleanup(environment.stop)
        root = prepare_demo()
        self.addCleanup(shutil.rmtree, root)
        self.app = create_hosted_app()
        self.a, self.b = self.app.test_client(), self.app.test_client()
        self.base = 'https://arcade.example'
        provider = patch('utils.lazy.LazyService._get', side_effect=AssertionError('Authored listening cannot call a provider'))
        self.provider = provider.start()
        self.addCleanup(provider.stop)

    def test_demo_can_listen_and_use_transcript_but_another_visitor_cannot(self):
        a = self.a.get('/api/v1/user-session', base_url=self.base).json
        b = self.b.get('/api/v1/user-session', base_url=self.base).json
        headers = {'X-CSRF-Token': a['csrf_token']}
        response = self.a.post(PATH + '/listening', data={
            'profile_id': a['profile']['id'], 'request_id': 'demo-listening'}, headers=headers, base_url=self.base)
        self.assertEqual(response.status_code, 303, response.text)
        path = '/api/v1/learning-sessions/' + response.location.rsplit('/', 1)[1]
        saved = self.a.get(path, base_url=self.base).json
        media = self.a.get(saved['item']['audio']['url'], base_url=self.base)
        self.assertEqual(media.status_code, 200)
        media.close()
        for action in ('transcript', 'listened'):
            body = {'submission_id': f'demo-{action}', 'expected_revision': saved['revision'], 'item_id': saved['item']['id']}
            other = self.b.post(path + '/' + action, json=body,
                headers={'X-CSRF-Token': b['csrf_token']}, base_url=self.base)
            self.assertEqual(other.status_code, 404, other.text)
            self.assertEqual(self.a.post(path + '/' + action, json=body, base_url=self.base).status_code, 403)
            response = self.a.post(path + '/' + action, json=body, headers=headers, base_url=self.base)
            self.assertEqual(response.status_code, 200, response.text)
            saved = response.json
        self.assertTrue(saved['item']['listened'])
        self.assertTrue(saved['item']['transcript'])
        self.assertEqual(self.b.get(path, base_url=self.base).status_code, 404)
        self.provider.assert_not_called()


class HouseholdListeningTests(unittest.TestCase):
    def test_child_can_play_only_authored_public_audio_and_save_owned_support(self):
        app = isolated_app(self)
        app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='household-test-' * 4)
        app.extensions['learning']['household'].configure('Listening household', '246810')
        adult = app.test_client()

        def post(client, path, body):
            token = client.get('/api/v1/household').json['csrf_token']
            return client.post(path, json=body, headers={'X-CSRF-Token': token})

        self.assertEqual(post(adult, '/api/v1/household/unlock', {'pin': '246810'}).status_code, 200)
        profile = post(adult, '/api/v1/grownups/profiles', {'display_name': 'Listener', 'study_timezone': 'Australia/Melbourne'}).json['id']
        child = app.test_client()
        self.assertEqual(post(child, '/api/v1/household/unlock', {'pin': '246810'}).status_code, 200)
        selected = post(child, f'/api/v1/grownups/profiles/{profile}/select', {})
        self.assertEqual(selected.status_code, 200)
        self.assertFalse(selected.json['adult'])
        token = child.get('/api/v1/household').json['csrf_token']
        headers = {'X-CSRF-Token': token}
        response = child.post(PATH + '/listening', data={'profile_id': profile, 'request_id': 'child-listening'}, headers=headers)
        self.assertEqual(response.status_code, 303, response.text)
        path = '/api/v1/learning-sessions/' + response.location.rsplit('/', 1)[1]
        saved = child.get(path).json
        response = child.get(saved['item']['audio']['url'])
        self.assertEqual(response.status_code, 200)
        response.close()
        # A narrowly added authored clip must not expose other static media.
        self.assertIn(child.get('/static/audio/private-family-recording.mp3').status_code, (302, 403, 404))
        receipt = child.post(path + '/listened', json={'submission_id': 'child-listened',
            'expected_revision': saved['revision'], 'item_id': saved['item']['id']}, headers=headers)
        self.assertEqual(receipt.status_code, 200, receipt.text)
        self.assertEqual(receipt.json['profile_id'], profile)
        self.assertTrue(receipt.json['item']['listened'])


if __name__ == '__main__':
    unittest.main()
