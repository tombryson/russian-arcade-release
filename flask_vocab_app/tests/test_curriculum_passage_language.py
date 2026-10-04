"""Unknown central words are supported without guessing homograph senses."""
from copy import deepcopy
import unittest

from services.curriculum_passage_language import unfamiliar_content, validate_language_support, support_entries


class PassageLanguageTests(unittest.TestCase):
    def request(self, known=(), phrases=()):
        return {'known_lemmas': list(known), 'language_plan': {'supported_phrases': list(phrases)}}

    def response(self, text, annotations=()):
        return {'text': text, 'new_vocabulary': list(annotations)}

    def test_missing_central_word_cannot_pass_with_empty_annotations(self):
        request = self.request(('быть',))
        payload = self.response('Анна была в библиотеке.')
        self.assertEqual(unfamiliar_content(request, payload), [{'form': 'библиотеке', 'possible_lemmas': ['библиотека']}])
        with self.assertRaisesRegex(ValueError, 'библиотеке'):
            validate_language_support(request, payload)
        payload['new_vocabulary'] = [{'lemma': 'библиотека', 'form': 'библиотеке', 'pos': 'NOUN',
            'sentence': payload['text'], 'meaning_en': 'library'}]
        validate_language_support(request, payload)
        self.assertEqual(support_entries(request, payload)[0]['text'], 'библиотеке')

    def test_support_covers_actual_phrase_not_other_forms_of_its_lemmas(self):
        request = self.request(('рассказать',), ({'ru': 'читала книгу', 'en': 'was reading a book'},))
        payload = self.response('Анна читала книгу. Она рассказала о книге.')
        self.assertEqual([row['form'] for row in unfamiliar_content(request, payload)], ['книге'])
        self.assertEqual(support_entries(request, payload), [{'kind': 'phrase', 'text': 'читала книгу', 'meaning_en': 'was reading a book'}])

    def test_phrase_support_retains_actual_surface_and_hides_unused_variant(self):
        request = self.request((), ({'ru': 'читал книгу / читала книгу', 'en': 'read a book; completion is not asserted'},))
        payload = self.response('Читала книгу Анна.')
        entries = support_entries(request, payload)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['text'], 'Читала книгу')
        self.assertIn(entries[0]['text'], payload['text'])
        validate_language_support(request, payload)

    def test_lowercase_common_noun_does_not_escape_as_a_proper_name(self):
        request = self.request(('видеть',))
        payload = self.response('Олег видит мир.')
        self.assertIn('мир', [row['form'] for row in unfamiliar_content(request, payload)])

    def test_known_homograph_does_not_claim_a_contextual_sense(self):
        payload = self.response('Анна хочет печь.')
        request = self.request(('хотеть', 'печь'))
        validate_language_support(request, payload)
        self.assertEqual(support_entries(request, payload), [])

    def test_annotation_does_not_mutate_learner_vocabulary_or_teaching(self):
        request = self.request(('быть',))
        before = deepcopy(request)
        payload = self.response('Анна в парке.', ({'lemma':'парк', 'form':'парке', 'pos':'NOUN', 'meaning_en':'park', 'sentence':'Анна в парке.'},))
        validate_language_support(request, payload)
        self.assertEqual(request, before)
