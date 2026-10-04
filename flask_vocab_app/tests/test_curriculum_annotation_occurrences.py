"""A contextual gloss belongs to one occurrence, not every homograph in a text."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from services import curriculum_situation_content as content
from services.curriculum_passage_language import unfamiliar_content, validate_language_support, support_entries
from services.curriculum_units import DATA_DIR
from tests.test_curriculum_situation_expansion import fixture_request, fixture_wire


def annotated_fixture():
    seed = 'extension-contract'
    base = fixture_request('present-actions-v1', seed, 'reading')
    unit = json.loads((DATA_DIR / 'present-actions-v1.json').read_text())
    request = content.build_request(unit, seed, mode='reading', vocabulary=[
        *base['vocabulary'], {'lemma': 'хотеть'}, {'lemma': 'идти'}, {'lemma': 'видеть'}])
    return request, fixture_wire(request)


def checked(request, wire):
    return content.validate_output(request, content.resolve_source_references(request, wire))


def annotation(lemma, sentence_id, meaning, pos='NOUN'):
    return {'lemma': lemma, 'pos': pos, 'sentence_id': sentence_id, 'meaning_en': meaning}


class AnnotationOccurrenceTests(unittest.TestCase):
    def test_repeated_homograph_in_one_sentence_cannot_get_an_unlocated_gloss(self):
        request, wire = annotated_fixture()
        wire['sentences'].append('Там печь, и Анна хочет печь.')
        wire['new_vocabulary'] = [annotation('печь', 's4', 'oven')]
        with self.assertRaisesRegex(ValueError, 'unambiguous occurrence'):
            checked(request, wire)

    def test_noun_annotation_does_not_cover_a_later_infinitive_of_the_same_spelling(self):
        request, wire = annotated_fixture()
        wire['sentences'].extend(['Там печь.', 'Анна хочет печь.'])
        wire['new_vocabulary'] = [annotation('печь', 's4', 'oven')]
        with self.assertRaisesRegex(ValueError, 'Unfamiliar.*печь'):
            checked(request, wire)
        wire['new_vocabulary'].append(annotation('печь', 's5', 'to bake', 'INFN'))
        original = deepcopy(request)
        document = checked(request, wire)
        words = [row for row in support_entries(request, document['response']) if row['kind'] == 'word']
        self.assertEqual([(row['meaning_en'], row['sentence']) for row in words],
                         [('oven', 'Там печь.'), ('to bake', 'Анна хочет печь.')])
        self.assertEqual(request, original)

    def test_case_forms_need_their_own_context_but_count_as_one_new_lemma(self):
        request, wire = annotated_fixture()
        wire['sentences'].extend(['Анна в библиотеке.', 'Олег идёт в библиотеку.'])
        wire['new_vocabulary'] = [annotation('библиотека', 's4', 'library')]
        with self.assertRaisesRegex(ValueError, 'Unfamiliar.*библиотеку'):
            checked(request, wire)
        wire['new_vocabulary'].append(annotation('библиотека', 's5', 'library'))
        document = checked(request, wire)
        self.assertEqual([row['form'] for row in document['response']['new_vocabulary']],
                         ['библиотеке', 'библиотеку'])

    def test_one_occurrence_cannot_be_given_two_incompatible_readings(self):
        request, wire = annotated_fixture()
        wire['sentences'].append('Там печь.')
        wire['new_vocabulary'] = [annotation('печь', 's4', 'oven'), annotation('печь', 's4', 'to bake', 'INFN')]
        with self.assertRaisesRegex(ValueError, 'only once'):
            checked(request, wire)

    def test_four_distinct_unknown_lemmas_still_exceed_the_allowance(self):
        request, wire = annotated_fixture()
        nouns = [('дельфин', 'dolphin'), ('маяк', 'lighthouse'), ('комета', 'comet'), ('фонтан', 'fountain')]
        for lemma, meaning in nouns:
            self.assertNotIn(lemma, request['known_lemmas'])
            wire['sentences'].append(f'Там {lemma}.')
            wire['new_vocabulary'].append(annotation(lemma, 's' + str(len(wire['sentences'])), meaning))
        with self.assertRaisesRegex(ValueError, 'distinct unfamiliar-lemma'):
            checked(request, wire)

    def test_context_rows_are_bounded_separately_from_lemma_count(self):
        request, wire = annotated_fixture()
        self.assertEqual(content.provider_schema(request)['properties']['new_vocabulary']['maxItems'], 8)
        wire['new_vocabulary'] = [annotation('печь', 's1', 'oven')] * 9
        with self.assertRaisesRegex(ValueError, 'invalid length'):
            content.resolve_source_references(request, wire)
        # Eight separately grounded occurrences of three lemmas are admissible
        # support. A ninth exceeds the visible support cap even for one lemma.
        sentences = ['Там печь.', 'Это печь.', 'Здесь печь.', 'Там маяк.', 'Это маяк.',
                     'Здесь маяк.', 'Там фонтан.', 'Это фонтан.']
        rows = [{'lemma': sentence.split()[-1].rstrip('.'), 'form': sentence.split()[-1].rstrip('.'),
                 'pos': 'NOUN', 'sentence': sentence, 'meaning_en': 'fixture meaning'} for sentence in sentences]
        policy = {'known_lemmas': [], 'language_plan': {'supported_phrases': []}}
        payload = {'text': ' '.join(sentences), 'new_vocabulary': rows}
        validate_language_support(policy, payload)
        payload['text'] += ' Здесь фонтан.'
        payload['new_vocabulary'].append({'lemma': 'фонтан', 'form': 'фонтан', 'pos': 'NOUN',
                                         'sentence': 'Здесь фонтан.', 'meaning_en': 'fountain'})
        with self.assertRaisesRegex(ValueError, 'eight'):
            validate_language_support(policy, payload)

    def test_sentence_substring_cannot_bind_an_annotation_to_two_occurrences(self):
        policy = {'known_lemmas': [], 'language_plan': {'supported_phrases': []}}
        payload = {'text': 'Там печь. Анна говорит: «Там печь.»', 'new_vocabulary': [
            {'lemma': 'печь', 'form': 'печь', 'pos': 'NOUN', 'sentence': 'Там печь.', 'meaning_en': 'oven'}]}
        with self.assertRaisesRegex(ValueError, 'unambiguous source sentence'):
            unfamiliar_content(policy, payload)

    def test_frozen_function_words_use_the_same_yo_normalization_as_morphology(self):
        policy = {'known_lemmas': [], 'language_plan': {'supported_phrases': []},
                  'support_policy': {'function_words': ['об', 'учёба']}}
        self.assertEqual(unfamiliar_content(policy, {'text': 'Об учёбе.', 'new_vocabulary': []}), [])

    def test_frozen_v5_schema_prompt_and_document_remain_identical(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/curriculum_source_v5.json').read_text())
        provider = MagicMock()
        provider.flashcard_model = 'existing-model'
        provider.client.with_options.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(refusal=None,
                          content=json.dumps(fixture['provider_response'])))])
        self.assertEqual(content.provider_schema(fixture['request']), fixture['schema'])
        self.assertEqual(content.prompt_for(fixture['request']), fixture['prompt'])
        self.assertEqual(content.generate(fixture['request'], provider), fixture['document'])


if __name__ == '__main__':
    unittest.main()
