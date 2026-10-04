"""Optional passage support is owned, explicit, durable and assistance-aware."""
from copy import deepcopy
import json
import unittest
from uuid import uuid4

from contracts.learning import validate_pack
from repositories.learning_repository import LearningError, transaction
from services.curriculum_units import _pack
from services.learning_content import child_item
from services.learning_listening import validate_saved_support
from tests import test_learning as learning_tests


class PassageSupportTests(unittest.TestCase):
    setUp = learning_tests.LearningTests.setUp
    post = learning_tests.LearningTests.post
    unlock = learning_tests.LearningTests.unlock
    learner = learning_tests.LearningTests.learner
    publish = learning_tests.LearningTests.publish
    start = learning_tests.LearningTests.start

    def pack(self, listening=False, support=True):
        pack = learning_tests.choice_pack('passage-support-test', count=3)
        if listening:
            sample = _pack({'id': 'location-destination-v1'}, 'listening')['items'][0]
            text = sample['transcript']
        else:
            text = 'Анна стоит перед аптекой. Потом она идёт домой.'
        for item in pack['items']:
            item.pop('word_id', None)
            if listening:
                item.update(type='listening_choice', transcript=text, audio=deepcopy(sample['audio']))
            else:
                item['passage'] = text
            if support:
                # This is a transport/assistance fixture, not lesson content.
                token = text.split()[0].strip('—.,!?')
                item['passage_support'] = [{'kind': 'word', 'text': token,
                    'meaning_en': 'Fixture contextual meaning', 'sentence': text}]
        return pack

    def command(self, child, saved, action, *, body=None, status=200):
        body = body or {'submission_id': uuid4().hex, 'expected_revision': saved['revision'],
                        'item_id': saved['item']['id']}
        if action == 'attempts':
            body['answer'] = {'choice_id': 'coffee'}
        result = self.post(child, '/api/v1/learning-sessions/' + saved['id'] + '/' + action, body)
        self.assertEqual(result.status_code, status, result.get_data(as_text=True))
        return result.json

    def test_reading_disclosure_persists_and_preserves_previous_answers(self):
        child, profile = self.learner()
        pack = self.pack()
        state = self.start(child, profile, self.publish(pack))
        self.assertTrue(state['item']['has_passage_support'])
        self.assertNotIn('passage_support', state['item'])
        self.assertNotIn('Fixture contextual meaning', json.dumps(state))
        state = self.command(child, state, 'attempts')
        self.assertFalse(state['attempts'][0]['assisted'])
        body = {'submission_id': uuid4().hex, 'expected_revision': state['revision'], 'item_id': state['item']['id']}
        opened = self.command(child, state, 'passage-help', body=body)
        self.assertEqual(opened, self.command(child, state, 'passage-help', body=body))
        self.assertEqual(opened['item']['passage_support'], pack['items'][1]['passage_support'])
        self.assertNotIn('hint', opened['item'])
        reloaded = child.get('/api/v1/learning-sessions/' + state['id']).json
        self.assertEqual(reloaded['item'], opened['item'])
        answered = self.command(child, reloaded, 'attempts')
        self.assertEqual([bool(a['assisted']) for a in answered['attempts']], [False, True])
        self.assertEqual(answered['item']['passage_support'], opened['item']['passage_support'])
        completed = self.command(child, answered, 'attempts')
        self.assertEqual([bool(a['assisted']) for a in completed['attempts']], [False, True, True])
        with transaction(self.db) as conn:
            frozen = json.loads(conn.execute('SELECT payload FROM learning_content_versions WHERE id=?', (state['version_id'],)).fetchone()[0])
        self.assertEqual(frozen, pack)

    def test_listening_support_requires_transcript_and_records_assistance(self):
        child, profile = self.learner()
        state = self.start(child, profile, self.publish(self.pack(listening=True)))
        self.assertNotIn('has_passage_support', state['item'])
        self.assertNotIn('passage_support', state['item'])
        error = self.command(child, state, 'passage-help', status=409)
        self.assertEqual(error['error']['code'], 'transcript_required')
        played = self.command(child, state, 'listened')
        self.assertNotIn('has_passage_support', played['item'])
        prior = self.command(child, played, 'attempts')
        self.assertFalse(prior['attempts'][0]['assisted'])
        revealed = self.command(child, prior, 'transcript')
        self.assertTrue(revealed['item']['has_passage_support'])
        self.assertNotIn('passage_support', revealed['item'])
        opened = self.command(child, revealed, 'passage-help')
        self.assertTrue(opened['item']['passage_support'])
        answered = self.command(child, opened, 'attempts')
        self.assertEqual([bool(a['assisted']) for a in answered['attempts']], [False, True])
        self.assertTrue(answered['item']['passage_support'])
        complete = self.command(child, answered, 'attempts')
        self.assertEqual([bool(a['assisted']) for a in complete['attempts']], [False, True, True])
        with transaction(self.db) as conn:
            validate_saved_support(conn)

    def test_owned_revision_csrf_and_frozen_old_pack_boundaries(self):
        child, profile = self.learner()
        state = self.start(child, profile, self.publish(self.pack()))
        path = '/api/v1/learning-sessions/' + state['id'] + '/passage-help'
        body = {'submission_id': uuid4().hex, 'expected_revision': state['revision'], 'item_id': state['item']['id']}
        self.assertEqual(child.post(path, json=body).status_code, 403)
        other, _ = self.learner('Another person')
        self.assertEqual(self.post(other, path, body).status_code, 404)
        self.assertEqual(self.post(child, path, {**body, 'expected_revision': 12}).status_code, 409)
        self.assertEqual(self.post(child, path, {**body, 'item_id': 'coffee-2'}).status_code, 409)
        oldpack = self.pack(support=False)
        oldpack['id'] = 'old-pack'
        old = self.start(child, profile, self.publish(oldpack), key='start-old')
        self.assertEqual(old['item'], child_item(oldpack['items'][0]))
        self.command(child, old, 'passage-help', status=404)


class PassageSupportContractTests(unittest.TestCase):
    def test_pack_rejects_context_not_in_passage_and_bounded_support(self):
        pack = learning_tests.choice_pack()
        item = pack['items'][0]
        item['passage'] = 'Анна стоит перед аптекой.'
        row = {'kind': 'word', 'text': 'аптекой', 'meaning_en': 'pharmacy', 'sentence': item['passage']}
        item['passage_support'] = [row]
        self.assertEqual(validate_pack(pack), pack)
        for changed in ([{**row, 'sentence': 'Это магазин.'}], [{**row, 'text': 'магазин'}], [row] * 9, []):
            with self.subTest(changed=changed):
                invalid = deepcopy(pack)
                invalid['items'][0]['passage_support'] = changed
                with self.assertRaises(LearningError):
                    validate_pack(invalid)
