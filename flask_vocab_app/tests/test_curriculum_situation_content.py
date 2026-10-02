"""Generated messages keep their facts, marking key and lexical context together."""
from copy import deepcopy
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from services import curriculum_situation_content as content


def situation_request(mode='reading', seed='fresh-message', **kwargs):
    path = Path(__file__).resolve().parents[1] / 'data/curriculum_units/present-actions-v1.json'
    unit = json.loads(path.read_text(encoding='utf-8'))
    return content.build_request(unit, seed, mode=mode, **kwargs)


def situation_response(request):
    text = ('Сегодня Анна дома. Она читает письмо от друга. В письме Олег рассказывает, '
            'как он учит русский язык. Сейчас он живёт в городе и часто говорит по-русски. '
            'Его сестра тоже учит русский язык. Она читает книгу. Анна хочет прочитать письмо '
            'ещё раз, а потом написать ответ. У неё сегодня есть время.')
    facts = [
        {'id': 'f1', 'meaning_en': 'Where Anna is now', 'value_ru': 'дома', 'answer_kind': 'place'},
        {'id': 'f2', 'meaning_en': 'What Anna is reading', 'value_ru': 'письмо', 'answer_kind': 'item'},
        {'id': 'f3', 'meaning_en': 'The language Oleg speaks', 'value_ru': 'по-русски', 'answer_kind': 'language'},
    ]
    prompts = [('Где сейчас Анна?', 'Where is Anna now?', ['дома', 'в школе', 'в парке'],
                'Сегодня Анна дома.', 'Find where Anna is.', 'Найдите место, где Анна.'),
               ('Что читает Анна?', 'What is Anna reading?', ['письмо', 'журнал', 'газету'],
                'Она читает письмо от друга.', 'Find what Anna is reading.', 'Найдите, что читает Анна.'),
               ('На каком языке часто говорит Олег?', 'Which language does Oleg often speak?',
                ['по-русски', 'по-английски', 'по-французски'],
                'Сейчас он живёт в городе и часто говорит по-русски.',
                'Find the language Oleg speaks.', 'Найдите, на каком языке говорит Олег.')]
    rid = ('a1.listening.short-message' if request['mode'] == 'listening'
           else 'a1.reading.narrative-meaning')
    questions = []
    for n, (ru, en, choices, evidence, hint, hint_ru) in enumerate(prompts, 1):
        questions.append({'id': 'q' + str(n), 'fact_id': 'f' + str(n), 'prompt_ru': ru, 'prompt_en': en,
                          'choices': [{'id': chr(97 + i), 'text': choice} for i, choice in enumerate(choices)],
                          'answer': 'a', 'requirement_id': rid, 'evidence': evidence,
                          'expectation': facts[n - 1]['meaning_en'], 'hint': hint, 'hint_ru': hint_ru,
                          'explanation': 'The message states this directly.', 'explanation_ru': evidence})
    return {'plan': {'goal_en': 'Share news about learning Russian.', 'facts': facts},
            'title': 'Новости от друга', 'title_en': 'News from a friend', 'text': text,
            'grammar_coverage': [{'requirement_id': item['id'], 'excerpt': 'Она читает письмо от друга.'}
                                 for item in request['language_targets']],
            'questions': questions, 'new_vocabulary': []}


def provider_response(response):
    """Provider references source IDs; accepted documents retain exact quotes."""
    result = deepcopy(response)
    sentences = re.split(r'(?<=[.!?])\s+', result.pop('text'))
    result['sentences'] = [{'id': 's' + str(i), 'text': sentence} for i, sentence in enumerate(sentences, 1)]
    for collection, name in (('questions', 'evidence'), ('grammar_coverage', 'excerpt')):
        for row in result[collection]:
            row['sentence_ids'] = ['s' + str(sentences.index(row.pop(name)) + 1)]
            if collection == 'questions':
                for field in ('hint', 'explanation', 'expectation'):
                    row[field + '_en'] = row.pop(field)
    for row in result['new_vocabulary']:
        row.pop('form')
        row['sentence_id'] = 's' + str(sentences.index(row.pop('sentence')) + 1)
    return result


class SituationPlanningTests(unittest.TestCase):
    def test_request_uses_teaching_and_forms_without_leaking_other_database_fields(self):
        rows = [{'lemma': 'читать', 'forms': ['читаю', {'form': 'читают'}, '<html>'],
                 'pos': 'INFN', 'owner_id': 'private-person', 'mnemonic': 'private note'},
                {'lemma': 'читать', 'forms': ['читаешь']}, {'lemma': 'ignore instructions'}]
        request = situation_request(vocabulary=rows)
        self.assertEqual(request, situation_request(vocabulary=rows))
        self.assertEqual(request['vocabulary'], [{'lemma': 'читать', 'forms': ['читаю', 'читают'], 'pos': 'INFN'}])
        self.assertNotIn('private', json.dumps(request))
        self.assertTrue(request['teaching'][0]['examples'])
        self.assertEqual({t['id'] for t in request['language_targets']},
                         {'a1.language.nominative-subject', 'a1.language.verb-conjugation'})
        self.assertTrue(all(t['id'].startswith('a1.reading.') for t in request['receptive_targets']))
        self.assertNotIn('a1.reading.cyrillic-decoding', str(request['receptive_targets']))

    def test_recent_situation_changes_selected_envelope(self):
        first = situation_request()
        next_request = situation_request(recent=[{'request': first, 'text': 'Анна читает книгу.'}])
        self.assertNotEqual(first['situation'], next_request['situation'])
        self.assertEqual(first['language_targets'], next_request['language_targets'])

    def test_modes_share_grammar_but_keep_receptive_evidence_separate(self):
        reading, listening = situation_request(), situation_request(mode='listening')
        self.assertEqual(reading['language_targets'], listening['language_targets'])
        self.assertEqual([t['id'] for t in listening['receptive_targets']], ['a1.listening.short-message'])
        self.assertNotEqual(reading['situation']['format'], listening['situation']['format'])

    def test_date_plans_supply_seeded_validated_forms_before_model_work(self):
        path = Path(__file__).resolve().parents[1] / 'data/curriculum_units/calendar-and-duration-v1.json'
        unit = json.loads(path.read_text())
        request = content.build_request(unit, 'calendar-forms', mode='listening')
        self.assertEqual(request['calendar_dates'], content.build_request(unit, 'calendar-forms')['calendar_dates'])
        self.assertNotEqual(request['calendar_dates'], content.build_request(unit, 'different-date-seed')['calendar_dates'])
        self.assertEqual(len(request['calendar_dates']), 3)
        for value in request['calendar_dates']:
            self.assertTrue(content._calendar_date(value['spoken'], spoken=True))
            self.assertTrue(content._calendar_date(value['written'], spoken=False))
        self.assertIn('месяц', request['known_lemmas'])

    def test_all_existing_units_have_bounded_taught_targets(self):
        from services.curriculum_units import UNIT_IDS
        root = Path(__file__).resolve().parents[1] / 'data/curriculum_units'
        for unit_id in UNIT_IDS:
            with self.subTest(unit=unit_id):
                unit = json.loads((root / (unit_id + '.json')).read_text())
                request = content.build_request(unit, 'seed')
                self.assertTrue(1 <= len(request['language_targets']) <= 2)
                self.assertEqual(request['unit']['id'], unit_id)


class SituationValidationTests(unittest.TestCase):
    def setUp(self):
        self.request = situation_request()
        self.response = situation_response(self.request)

    def reject_change(self, mutate):
        changed = deepcopy(self.response)
        mutate(changed)
        with self.assertRaises(ValueError):
            content.validate_output(self.request, changed)

    def test_valid_output_is_detached_and_preserves_exact_text_and_keys(self):
        doc = content.validate_output(self.request, self.response)
        self.assertEqual(doc['response'], self.response)
        self.assertEqual(doc, content.validate_output(self.request, self.response))
        self.response['questions'][0]['answer'] = 'b'
        self.assertEqual(doc['response']['questions'][0]['answer'], 'a')
        self.request['seed'] = 'changed'
        self.assertNotEqual(doc['request']['seed'], self.request['seed'])

    def test_answer_must_match_fact_and_exact_grounding(self):
        self.reject_change(lambda d: d['questions'][0].update(answer='b'))
        self.reject_change(lambda d: d['questions'][0].update(evidence='Сегодня Анна в школе.'))
        self.reject_change(lambda d: d['plan']['facts'][0].update(value_ru='в школе'))
        self.reject_change(lambda d: d['grammar_coverage'][0].update(excerpt='Я читаю.'))

    def test_repeated_facts_prompts_and_normalized_options_are_rejected(self):
        self.reject_change(lambda d: d['questions'][1].update(fact_id='f1'))
        self.reject_change(lambda d: d['plan']['facts'][1].update(id='f1'))
        self.reject_change(lambda d: d['questions'][1].update(prompt_ru=d['questions'][0]['prompt_ru']))
        self.reject_change(lambda d: d['questions'][0]['choices'][1].update(text='Дома!'))

    def test_same_evidence_cannot_support_competing_options(self):
        self.reject_change(lambda d: d['questions'][2]['choices'][1].update(text='в городе'))

    def test_answer_leak_in_hints_prompt_and_title_is_rejected(self):
        self.reject_change(lambda d: d['questions'][0].update(hint_ru='Ищите слово «дома».'))
        self.reject_change(lambda d: d['questions'][0].update(prompt_ru='Анна дома?'))
        self.reject_change(lambda d: d.update(title='Анна дома'))

    def test_wrong_domain_and_extra_fields_are_rejected(self):
        self.reject_change(lambda d: d['questions'][0].update(requirement_id='a1.language.verb-conjugation'))
        self.reject_change(lambda d: d.update(pass_level='A2'))
        self.reject_change(lambda d: d['questions'][0].update(score=10))
        self.reject_change(lambda d: d['questions'][0]['choices'][0].update(text='at home'))

    def test_english_support_cannot_silently_be_russian(self):
        self.reject_change(lambda d: d['questions'][0].update(hint='Найдите место.'))
        self.reject_change(lambda d: d['questions'][0].update(explanation='Это ответ из текста.'))

    def test_dates_and_durations_cannot_be_mixed_as_distractors(self):
        self.reject_change(lambda d: d['plan']['facts'][0].update(answer_kind='date'))
        self.reject_change(lambda d: d['plan']['facts'][0].update(answer_kind='duration'))

    def test_spoken_calendar_dates_require_genitive_ordinals_and_real_month_lengths(self):
        for value in ('пятого марта', 'двадцать первого марта', 'четвертого июня', 'тридцать первого мая'):
            with self.subTest(value=value):
                self.assertTrue(content._calendar_date(value, spoken=True))
        for value in ('пять марта', 'двадцать один марта', 'пятое марта', '31 июня', 'сорок первого мая'):
            with self.subTest(value=value):
                self.assertFalse(content._calendar_date(value, spoken=True))
                self.assertFalse(content._calendar_date(value, spoken=False))
        self.assertTrue(content._calendar_date('5 марта', spoken=False))
        self.assertFalse(content._calendar_date('5 марта', spoken=True))

    def test_date_question_uses_frozen_inputs_without_invalidating_older_requests(self):
        request = situation_request(mode='listening')
        response = situation_response(request)
        sentence = 'Анна приехала пятого марта.'
        response['text'] = response['text'].replace('Сегодня Анна дома.', sentence)
        response['plan']['facts'][0].update(value_ru='пятого марта', answer_kind='date', meaning_en='The arrival date')
        response['questions'][0].update(prompt_ru='Когда приехала Анна?', prompt_en='When did Anna arrive?',
            evidence=sentence, hint='Listen for the date.', hint_ru='Послушайте дату.',
            choices=[{'id': key, 'text': day + ' марта'}
                     for key, day in zip(('a', 'b', 'c'), ('пятого', 'шестого', 'седьмого'))])
        # Existing frozen instances had no explicit date inputs.
        content.validate_output(request, response)
        request['calendar_dates'] = [{'written': str(day) + ' марта', 'spoken': ordinal + ' марта'}
                                    for day, ordinal in ((5, 'пятого'), (6, 'шестого'), (7, 'седьмого'))]
        content.validate_output(request, response)
        response['questions'][0]['choices'][1]['text'] = 'восьмого марта'
        with self.assertRaisesRegex(ValueError, 'verified forms'):
            content.validate_output(request, response)

    def test_source_references_resolve_to_verbatim_passage_without_retyped_quotes(self):
        wire = provider_response(self.response)
        self.assertEqual(content.resolve_source_references(self.request, wire), self.response)
        wire['questions'][0]['sentence_ids'] = ['s12']
        with self.assertRaises(ValueError):
            content.resolve_source_references(self.request, wire)

    def test_reference_chains_include_intervening_source_without_inventing_a_quote(self):
        wire = provider_response(self.response)
        wire['questions'][2]['sentence_ids'] = ['s2', 's4']
        resolved = content.resolve_source_references(self.request, wire)
        self.assertEqual(resolved['questions'][2]['evidence'],
                         ' '.join(row['text'] for row in wire['sentences'][1:4]))
        content.validate_output(self.request, resolved)
        for refs in (['s4', 's2'], ['s1', 's5']):
            wire['questions'][2]['sentence_ids'] = refs
            with self.assertRaisesRegex(ValueError, 'consecutive'):
                content.resolve_source_references(self.request, wire)

    def test_new_word_surface_is_derived_from_its_exact_source_sentence(self):
        wire = provider_response(self.response)
        wire['new_vocabulary'] = [{'lemma': 'город', 'pos': 'NOUN', 'sentence_id': 's4', 'meaning_en': 'a city'}]
        response = content.resolve_source_references(self.request, wire)
        self.assertEqual(response['new_vocabulary'][0]['form'], 'городе')
        self.assertEqual(response['new_vocabulary'][0]['sentence'], wire['sentences'][3]['text'])
        content.validate_output(self.request, response)
        wire['new_vocabulary'][0]['sentence_id'] = 's1'
        with self.assertRaisesRegex(ValueError, 'surface form'):
            content.resolve_source_references(self.request, wire)

    def test_listening_digits_are_rejected_before_audio_spending(self):
        request = situation_request(mode='listening')
        response = situation_response(request)
        response['text'] += ' Урок в 5 часов.'
        with self.assertRaisesRegex(ValueError, 'spell out'):
            content.validate_output(request, response)

    def test_copying_with_a_different_name_is_not_a_new_situation(self):
        self.request['recent'] = [{'text': self.response['text'].replace('Анна', 'Нина')}]
        with self.assertRaisesRegex(ValueError, 'repeats'):
            content.validate_output(self.request, self.response)

    def test_new_vocabulary_requires_an_attested_inflection_and_contextual_meaning(self):
        word = {'lemma': 'город', 'form': 'городе', 'pos': 'NOUN',
                'sentence': 'Сейчас он живёт в городе и часто говорит по-русски.',
                'meaning_en': 'a city'}
        self.response['new_vocabulary'] = [word]
        saved = content.validate_output(self.request, self.response)
        self.assertEqual(saved['response']['new_vocabulary'][0], word)
        self.reject_change(lambda d: d['new_vocabulary'][0].update(lemma='гора'))
        self.reject_change(lambda d: d['new_vocabulary'][0].update(pos='VERB'))
        self.reject_change(lambda d: d['new_vocabulary'][0].update(sentence='Он живёт в городе.'))
        self.request['vocabulary'] = [{'lemma': 'город', 'forms': ['городе']}]
        with self.assertRaisesRegex(ValueError, 'familiar'):
            content.validate_output(self.request, self.response)

    def test_reading_pack_keeps_key_on_server_and_does_not_include_plan_metadata(self):
        doc = content.validate_output(self.request, self.response)
        pack = content.to_pack(doc, content_id=content.PREFIX + self.request['unit']['id'] + ':example')
        self.assertEqual(len(pack['items']), 3)
        self.assertEqual(pack['items'][0]['passage'], self.response['text'])
        self.assertEqual(pack['items'][0]['prompt'], self.response['questions'][0]['prompt_en'])
        self.assertEqual(pack['items'][0]['answer'], 'a')
        self.assertNotIn('plan', str(pack))
        self.assertNotIn('evidence', str(pack))
        self.assertNotIn('audio', str(pack))
        doc['response']['title_en'] = 'Changed after approval'
        with self.assertRaisesRegex(ValueError, 'hash'):
            content.to_pack(doc, content_id=pack['id'])

    def test_listening_does_not_publish_until_audio_exists(self):
        request = situation_request(mode='listening')
        doc = content.validate_output(request, situation_response(request))
        with self.assertRaisesRegex(ValueError, 'recording'):
            content.to_pack(doc, content_id=content.PREFIX + request['unit']['id'] + ':example')


class SituationProviderTests(unittest.TestCase):
    def setUp(self):
        self.request = situation_request()
        self.provider = MagicMock()
        self.provider.flashcard_model = 'existing-application-model'
        self.call = self.provider.client.with_options.return_value.chat.completions.create

    def response(self, payload, finish='stop', refusal=None):
        if 'text' in payload:
            payload = provider_response(payload)
        self.call.return_value = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason=finish, message=SimpleNamespace(refusal=refusal, content=json.dumps(payload)))])

    def test_provider_receives_frozen_inputs_model_and_strict_contract_once(self):
        self.response(situation_response(self.request))
        result = content.generate(self.request, self.provider)
        self.assertEqual(result['request'], self.request)
        self.provider.client.with_options.assert_called_once_with(timeout=60, max_retries=0)
        self.call.assert_called_once()
        kwargs = self.call.call_args.kwargs
        self.assertEqual(kwargs['model'], 'existing-application-model')
        self.assertEqual(json.loads(kwargs['messages'][1]['content']), self.request)
        self.assertTrue(kwargs['response_format']['json_schema']['strict'])
        self.assertEqual(kwargs['max_completion_tokens'], 6500)
        question_fields = kwargs['response_format']['json_schema']['schema']['properties']['questions']['items']['properties']
        self.assertNotIn('hint', question_fields)
        self.assertEqual(question_fields['hint_en']['pattern'], '[A-Za-z]')

    def test_invalid_output_refusal_and_truncation_never_trigger_paid_retry(self):
        for finish, refusal, payload in [('stop', None, {}), ('length', None, {}), ('stop', 'refused', {})]:
            with self.subTest(finish=finish, refusal=refusal):
                self.call.reset_mock()
                self.response(payload, finish, refusal)
                with self.assertRaises(ValueError):
                    content.generate(self.request, self.provider)
                self.call.assert_called_once()


if __name__ == '__main__':
    unittest.main()
