"""Late vocabulary enrichment reaches published cards without rewriting them."""
import json
import unittest

from repositories.card_repository import load_card
from repositories.learning_repository import transaction
from tests import test_native_flashcards as fixtures


class CardMnemonicProjectionTests(unittest.TestCase):
    setUp = fixtures.NativeFlashcardTests.setUp
    post = fixtures.NativeFlashcardTests.post
    unlock = fixtures.NativeFlashcardTests.unlock
    learner = fixtures.NativeFlashcardTests.learner
    credential = staticmethod(fixtures.NativeFlashcardTests.credential)
    publish = fixtures.NativeFlashcardTests.publish
    begin = fixtures.NativeFlashcardTests.begin
    move = fixtures.NativeFlashcardTests.move
    rows = fixtures.NativeFlashcardTests.rows

    @staticmethod
    def cloze():
        pack = fixtures.deck()
        item = pack['items'][0]
        item.pop('hint')
        item.update(type='cloze', direction='ru-cloze',
                    prompt='Я пью [[blank]].', answer='кофе',
                    context='Я пью кофе.', cue_en='coffee', form_id=1)
        return pack

    def set_mnemonic(self, value):
        with transaction(self.db) as conn:
            conn.execute('UPDATE words SET mnemonic=? WHERE id=1', (value,))

    def projected_card(self):
        with transaction(self.db) as conn:
            version_id = conn.execute('SELECT id FROM card_versions').fetchone()[0]
            return load_card(conn, version_id)[1]

    def test_late_enrichment_supplies_hint_without_changing_published_content(self):
        self.publish(self.cloze())
        original = self.rows('learning_content_versions')
        self.set_mnemonic('Imagine a coffee cup with a big K on it.')

        item = self.projected_card()

        self.assertEqual(item['hint'], 'Imagine a coffee cup with a big K on it.')
        self.assertEqual(item['cue_en'], 'coffee')
        self.assertEqual(self.rows('learning_content_versions'), original)
        self.assertNotIn('hint', json.loads(original[0]['payload'])['items'][0])

    def test_explicit_card_hint_takes_precedence_over_word_mnemonic(self):
        pack = self.cloze()
        pack['items'][0]['hint'] = 'The hint written specifically for this card.'
        self.publish(pack)
        self.set_mnemonic('A general word mnemonic.')

        self.assertEqual(self.projected_card()['hint'], pack['items'][0]['hint'])

    def test_empty_and_legacy_fallbacks_are_not_presented_as_hints(self):
        self.publish(self.cloze())
        for value in (None, '', '   ', 'Recall кофе phonetically.'):
            with self.subTest(value=value):
                self.set_mnemonic(value)
                self.assertNotIn('hint', self.projected_card())

    def test_legacy_card_placeholder_uses_real_word_mnemonic(self):
        pack = self.cloze()
        pack['items'][0]['hint'] = 'Recall кофе phonetically.'
        self.publish(pack)
        self.set_mnemonic('A useful memory association.')

        self.assertEqual(self.projected_card()['hint'], 'A useful memory association.')

    def test_database_hint_stays_hidden_until_requested(self):
        self.publish(self.cloze())
        self.set_mnemonic('Picture your favourite coffee cup.')
        client, profile = self.learner()

        saved = self.begin(client, profile)

        self.assertTrue(saved['item']['has_hint'])
        self.assertEqual(saved['item']['cue_en'], 'coffee')
        self.assertNotIn('hint', saved['item'])
        self.assertNotIn('answer', saved['item'])
        self.assertNotIn('dictionary_url', saved['item'])
        self.assertNotIn('Picture your favourite coffee cup.', json.dumps(saved))

        saved = self.move(client, saved, 'help')

        self.assertTrue(saved['item']['assisted'])
        self.assertEqual(saved['item']['hint'], 'Picture your favourite coffee cup.')
        self.assertNotIn('answer', saved['item'])
        self.assertNotIn('dictionary_url', saved['item'])

    def test_enrichment_does_not_change_existing_schedule_or_review_history(self):
        self.publish(self.cloze())
        client, profile = self.learner()
        saved = self.move(client, self.begin(client, profile), 'reveal')
        self.move(client, saved, 'reviews', rating='good')
        tables = ('card_versions', 'learning_content_versions', 'review_events',
                  'activity_attempts', 'learner_card_state')
        original = {table: self.rows(table) for table in tables}

        self.set_mnemonic('A mnemonic generated after the first review.')
        self.assertEqual(self.projected_card()['hint'],
                         'A mnemonic generated after the first review.')

        self.assertEqual({table: self.rows(table) for table in tables}, original)


if __name__ == '__main__':
    unittest.main()
