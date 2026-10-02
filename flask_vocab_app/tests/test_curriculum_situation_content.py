"""Generated messages keep their facts, marking key and lexical context together."""
from copy import deepcopy
import json
import hashlib
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
           else 'a1.reading.practical-information')
    expectation = next(row['expectation'] for row in request['receptive_targets'] if row['id'] == rid)
    questions = []
    for n, (ru, en, choices, evidence, hint, hint_ru) in enumerate(prompts, 1):
        facts[n - 1]['meaning_en'] = en
        questions.append({'id': 'q' + str(n), 'fact_id': 'f' + str(n), 'prompt_ru': ru, 'prompt_en': en,
                          'choices': [{'id': chr(97 + i), 'text': choice} for i, choice in enumerate(choices)],
                          'answer': 'a', 'requirement_id': rid, 'evidence': evidence,
                          'expectation': expectation, 'hint': hint, 'hint_ru': hint_ru,
                          'explanation': 'The message states this directly.', 'explanation_ru': evidence})
    return {'plan': {'goal_en': 'Share news about learning Russian.', 'facts': facts},
            'title': 'Новости от друга', 'title_en': 'News from a friend', 'text': text,
            'grammar_coverage': [{'requirement_id': item['id'], 'excerpt': 'Она читает письмо от друга.'}
                                 for item in request['language_targets']],
            'questions': questions, 'new_vocabulary': []}


def provider_response(response, *, legacy=False):
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
    if legacy:
        return result
    facts = {fact['id']: fact for fact in result['plan']['facts']}
    questions = []
    for question in result['questions']:
        questions.append({
            **{name: question[name] for name in ('prompt_ru', 'prompt_en', 'sentence_ids', 'hint_en', 'hint_ru',
                                                'explanation_en', 'explanation_ru')},
            'answer_kind': facts[question['fact_id']]['answer_kind'],
            'correct_ru': next(choice['text'] for choice in question['choices'] if choice['id'] == question['answer']),
            'distractors_ru': [choice['text'] for choice in question['choices'] if choice['id'] != question['answer']]})
    return {'goal_en': result['plan']['goal_en'], 'title': result['title'], 'title_en': result['title_en'],
            'sentences': [row['text'] for row in result['sentences']],
            'grammar_coverage': {row['requirement_id']: row['sentence_ids'] for row in result['grammar_coverage']},
            'questions': questions, 'new_vocabulary': result['new_vocabulary']}


def meaning_provider_response(request):
    """Small generated-wire fixture; only tests use this authored passage."""
    plan = request['language_plan']['meaning_plan']
    facts = plan['facts']
    people = {row['name_ru']: row for row in plan['participants']}
    sentences = [f"{plan['addressee']['name_ru']}, привет!",
                 'У меня есть новости для тебя, и я хочу немного рассказать о наших друзьях.']
    questions = {}
    for fact in facts:
        name, english, value, role = fact['subject_name'], fact['subject_en'], fact['value_ru'], fact['role']
        female = people[name]['gender'] == 'feminine'
        if role == 'location':
            sentence, en = f'{name} сейчас {value}.', f'Where is {english} now?'
        elif role == 'destination':
            sentence, en = f'Потом {name} идёт {value}.', f'Where is {english} going next?'
        elif role == 'duration':
            sentence, en = f"{name} {'жила' if female else 'жил'} там {value}.", f'How long did {english} stay there?'
        elif role == 'date':
            sentence, en = f"{name} {'приехала' if female else 'приехал'} {value}.", f'When did {english} arrive?'
        elif role == 'person':
            sentence, en = f"{name} тоже {'жила' if female else 'жил'} там.", 'Who else stayed there?'
        else:
            sentence = f'{name} говорит {value}.'
            en = f"{'Who' if role == 'topic_person' else 'What'} is {english} talking about?"
        sentences.append(sentence)
        questions[fact['id']] = {'prompt_ru': fact['question_frame_ru'], 'prompt_en': en,
            'sentence_ids': ['s' + str(len(sentences))],
            'hint_en': 'Find the detail about this person.', 'hint_ru': 'Найдите нужную информацию об этом человеке.',
            'explanation_en': 'The message states this fact about the named person.', 'explanation_ru': sentence}
        if request.get('generation_revision') == 'source-v4':
            for field in ('hint_en', 'hint_ru', 'explanation_en', 'explanation_ru'):
                questions[fact['id']].pop(field)
    sentences.append('Вот такие новости сегодня, напиши мне ответ, когда у тебя будет время.')
    return {'title': 'Сообщение другу', 'title_en': 'A message to a friend',
            'sentences': sentences, 'questions': questions, 'new_vocabulary': []}


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
        request = content.build_request(unit, 'calendar-forms', mode='reading')
        forms = request['language_plan']['checked_forms']
        self.assertEqual(forms, content.build_request(unit, 'calendar-forms')['language_plan']['checked_forms'])
        self.assertNotEqual(forms, content.build_request(unit, 'different-date-seed')['language_plan']['checked_forms'])
        dates = [row for row in forms if 'date_written' in row]
        self.assertEqual(len(dates), 3)
        for value in dates:
            self.assertTrue(content._calendar_date(value['date_spoken'], spoken=True))
            self.assertTrue(content._calendar_date(value['date_written'], spoken=False))
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
                         ' '.join(wire['sentences'][1:4]))
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
        self.assertEqual(response['new_vocabulary'][0]['sentence'], wire['sentences'][3])
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

    def test_frozen_generation_contract_is_checked_before_a_paid_call(self):
        self.request['generation_prompt_sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'frozen generation'):
            content.generate(self.request, self.provider)
        self.call.assert_not_called()

    def test_legacy_pending_requests_and_saved_hashes_keep_their_original_adapter(self):
        old = deepcopy(self.request)
        for name in ('generation_revision', 'generation_prompt_sha256', 'generation_schema_sha256'):
            old.pop(name)
        response = situation_response(old)
        document = content.validate_output(old, response)
        frozen = json.dumps(document, ensure_ascii=False, sort_keys=True)
        schema = content.provider_schema(old)
        self.assertEqual(schema['properties']['plan']['properties']['facts']['items']['properties']['answer_kind']['enum'],
                         list(content.LEGACY_ANSWER_KINDS))
        self.call.return_value = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(refusal=None, content=json.dumps(provider_response(response, legacy=True))))])
        regenerated = content.generate(old, self.provider)
        self.assertEqual(json.dumps(regenerated, ensure_ascii=False, sort_keys=True), frozen)
        self.assertEqual(self.call.call_args.kwargs['messages'][0]['content'], content.SYSTEM_PROMPT)
        pack = content.to_pack(document, content_id=content.PREFIX + old['unit']['id'] + ':legacy')
        self.assertEqual(pack['items'][0]['passage'], response['text'])

    def test_new_wire_has_one_correct_phrase_and_no_model_assigned_keys(self):
        question = content.provider_schema(self.request)['properties']['questions']['items']['properties']
        self.assertIn('correct_ru', question)
        self.assertIn('distractors_ru', question)
        for removed in ('id', 'fact_id', 'choices', 'answer', 'expectation_en', 'requirement_id'):
            self.assertNotIn(removed, question)
        self.assertEqual(question['prompt_en']['maxLength'], 200)
        self.assertEqual(self.request['generation_prompt_sha256'],
                         hashlib.sha256(content.prompt_for(self.request).encode()).hexdigest())


class GuidedLanguageTests(unittest.TestCase):
    def request(self, unit, mode='reading', **kwargs):
        path = Path(__file__).resolve().parents[1] / 'data/curriculum_units' / (unit + '.json')
        request = content.build_request(json.loads(path.read_text()), 'guided-source', mode=mode, **kwargs)
        # These tests exercise the retained construction adapter independently
        # of the newer, three-fact meaning plan tested below.
        request['generation_revision'] = 'source-v2'
        request.pop('writer_brief', None)
        request.pop('generation_input_sha256', None)
        request['limits'].update(minimum_words=35 if unit == 'calendar-and-duration-v1' else 30,
                                 maximum_words=80 if unit == 'calendar-and-duration-v1' else 70)
        request['generation_prompt_sha256'] = hashlib.sha256(content.prompt_for(request).encode()).hexdigest()
        request['generation_schema_sha256'] = content._hash(content.provider_schema(request))
        return request

    def topic_document(self):
        request = self.request('talking-about-topics-v1')
        response = situation_response(request)
        response['text'] = ('Сегодня Анна и Дима дома. Они пьют чай. Анна рассказывает о маме. '
            'Её мама работает в школе. Дима говорит о работе. Он работает в магазине. '
            'Потом Анна читает письмо. В письме есть новости от друга. Дима слушает Анну.')
        rows = [('topic_person', 'О ком рассказывает Анна?', 'Who is Anna talking about?',
                 ['о маме', 'о друге', 'об Анне'], 'Анна рассказывает о маме.'),
                ('topic_thing', 'О чём говорит Дима?', 'What is Dima talking about?',
                 ['о работе', 'о музыке', 'об отдыхе'], 'Дима говорит о работе.'),
                ('item', 'Что читает Анна?', 'What is Anna reading?',
                 ['письмо', 'книгу', 'газету'], 'Потом Анна читает письмо.')]
        for fact, question, (kind, ru, en, choices, evidence) in zip(response['plan']['facts'], response['questions'], rows):
            fact.update(meaning_en=en, value_ru=choices[0], answer_kind=kind)
            question.update(prompt_ru=ru, prompt_en=en, evidence=evidence,
                hint='Listen to what this person says.', hint_ru='Послушайте, что говорит этот человек.',
                choices=[{'id': letter, 'text': value} for letter, value in zip('abc', choices)])
        response['grammar_coverage'] = [{'requirement_id': 'a1.language.prepositional-topic',
                                        'excerpt': 'Анна рассказывает о маме.'}]
        return request, response

    def test_topic_question_requires_a_complete_governed_phrase(self):
        request, response = self.topic_document()
        content.validate_output(request, response)
        response['questions'][0]['choices'][1]['text'] = 'друг'
        with self.assertRaisesRegex(ValueError, 'governed answer frame'):
            content.validate_output(request, response)

    def test_exact_source_quote_alone_does_not_prove_grammar_coverage(self):
        request, response = self.topic_document()
        response['grammar_coverage'][0]['excerpt'] = 'Сегодня Анна и Дима дома.'
        with self.assertRaisesRegex(ValueError, 'taught construction'):
            content.validate_output(request, response)

    def test_supported_regular_nouns_extend_the_exemplars_without_new_grammar(self):
        request = self.request('talking-about-topics-v1', vocabulary=[{'lemma': 'проект', 'forms': ['проекте'], 'pos': 'NOUN'}])
        plan = request['language_plan']
        frame = next(frame for frame in plan['answer_frames'] if frame['role'] == 'topic_thing')
        self.assertTrue(content._allowed_frame_phrase(request, {'new_vocabulary': []}, plan, frame, 'о проекте'))
        for phrase in ('о проект', 'об проекте', 'обо мне', 'о проектах'):
            self.assertFalse(content._allowed_frame_phrase(request, {'new_vocabulary': []}, plan, frame, phrase))

    def test_location_frames_extend_examples_but_do_not_guess_prepositions(self):
        request = self.request('location-destination-v1')
        plan = request['language_plan']
        frame = next(frame for frame in plan['answer_frames'] if frame['role'] == 'location')
        extra = next(row for row in plan['extension_policy']['place_frames'] if row not in plan['checked_forms'])
        self.assertTrue(content._allowed_frame_phrase(request, {'new_vocabulary': []}, plan, frame, extra['location']))
        self.assertFalse(content._allowed_frame_phrase(request, {'new_vocabulary': []}, plan, frame, 'в почте'))

    def test_written_date_scope_does_not_become_a_spoken_ordinal_test(self):
        reading = self.request('calendar-and-duration-v1', mode='reading')
        listening = self.request('calendar-and-duration-v1', mode='listening')
        self.assertEqual([target['id'] for target in listening['language_targets']], ['a1.language.accusative-duration'])
        self.assertIn('a1.language.genitive-calendar-month', [target['id'] for target in reading['language_targets']])
        self.assertNotIn('date', [frame['role'] for frame in listening['language_plan']['answer_frames']])
        self.assertFalse(any('date_spoken' in row for row in listening['language_plan']['checked_forms']))
        self.assertEqual(reading['limits']['minimum_words'], 35)
        self.assertEqual(self.request('talking-about-topics-v1')['limits']['minimum_words'], 30)

    def test_elapsed_duration_is_not_a_start_time_or_delay(self):
        self.assertTrue(content._construction_in_quote('Я читал час.', 'час', 'elapsed-duration'))
        self.assertFalse(content._construction_in_quote('Урок в час.', 'час', 'elapsed-duration'))
        self.assertFalse(content._construction_in_quote('Урок через час.', 'час', 'elapsed-duration'))
        self.assertFalse(content._construction_in_quote('Я читаю каждый день.', 'день', 'elapsed-duration'))
        for source, bare, full in (('Урок через один час.', 'час', 'один час'),
                                  ('Урок в один час.', 'час', 'один час'),
                                  ('Он приехал на одну неделю.', 'неделю', 'одну неделю')):
            for phrase in (bare, full):
                with self.subTest(source=source, phrase=phrase):
                    self.assertFalse(content._construction_in_quote(source, phrase, 'elapsed-duration'))
        self.assertTrue(content._construction_in_quote('Я читал один час.', 'час', 'elapsed-duration'))


class MeaningBriefTests(unittest.TestCase):
    def request(self, unit='location-destination-v1', mode='reading'):
        path = Path(__file__).resolve().parents[1] / 'data/curriculum_units' / (unit + '.json')
        return content.build_request(json.loads(path.read_text()), 'meaning-test', mode=mode)

    def test_six_guided_modes_bind_answers_and_derive_coverage(self):
        for unit in ('location-destination-v1', 'calendar-and-duration-v1', 'talking-about-topics-v1'):
            for mode in ('reading', 'listening'):
                with self.subTest(unit=unit, mode=mode):
                    request = self.request(unit, mode)
                    wire = meaning_provider_response(request)
                    response = content.resolve_source_references(request, wire)
                    doc = content.validate_output(request, response)
                    self.assertEqual(doc['response'], response)
                    for planned, fact in zip(request['language_plan']['meaning_plan']['facts'], response['plan']['facts']):
                        self.assertEqual(planned['value_ru'], fact['value_ru'])
                        self.assertEqual(planned['role'], fact['answer_kind'])
                    self.assertEqual({row['requirement_id'] for row in response['grammar_coverage']},
                                     {row['id'] for row in request['language_targets']})
                    self.assertNotIn('grammar_coverage', content.provider_schema(request)['properties'])

    def test_provider_only_receives_the_frozen_compact_brief(self):
        request = self.request()
        provider = MagicMock()
        provider.flashcard_model = 'existing-model'
        call = provider.client.with_options.return_value.chat.completions.create
        call.return_value = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
            refusal=None, content=json.dumps(meaning_provider_response(request))))])
        content.generate(request, provider)
        sent = json.loads(call.call_args.kwargs['messages'][1]['content'])
        self.assertEqual(sent, request['writer_brief'])
        self.assertLess(len(json.dumps(sent)), len(json.dumps(request)) / 2)
        for private in ('source_sha256', 'language_targets', 'receptive_targets', 'extension_policy'):
            self.assertNotIn(private, sent)
        self.assertEqual(sent['known_lemmas'], request['known_lemmas'])
        self.assertEqual(content.prompt_for(request), content.SYSTEM_PROMPT_V4)
        provider.client.with_options.assert_called_once_with(timeout=60, max_retries=0)
        request['writer_brief']['purpose'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'frozen generation input'):
            content.generate(request, provider)
        self.assertEqual(call.call_count, 1)

    def test_same_span_can_contrast_two_named_actors(self):
        request = self.request()
        wire = meaning_provider_response(request)
        wire['sentences'][2] = wire['sentences'][2][:-1] + ', а ' + wire['sentences'][4]
        wire['questions']['f3']['sentence_ids'] = ['s3']
        wire['sentences'][4] = 'Сейчас всё ясно, и можно спокойно решить, что делать.'
        response = content.resolve_source_references(request, wire)
        content.validate_output(request, response)
        first = response['questions'][0]
        self.assertTrue(any(content._contains(first['evidence'], c['text']) for c in first['choices'] if c['id'] != first['answer']))
        response['plan']['facts'][0]['value_ru'] = response['plan']['facts'][2]['value_ru']
        with self.assertRaises(ValueError):
            content.validate_output(request, response)

    def test_ambiguous_subject_and_wrong_source_are_rejected(self):
        request = self.request()
        for change in ('question', 'source'):
            wire = meaning_provider_response(request)
            subject = request['language_plan']['meaning_plan']['facts'][0]['subject_name']
            if change == 'question':
                wire['questions']['f1']['prompt_ru'] = 'Где сейчас она?'
            else:
                wire['sentences'][2] = wire['sentences'][2].replace(subject, 'Она')
            response = content.resolve_source_references(request, wire)
            with self.assertRaisesRegex(ValueError, 'named participant'):
                content.validate_output(request, response)

    def test_one_question_cannot_reveal_another_questions_venue(self):
        request = self.request('calendar-and-duration-v1')
        wire = meaning_provider_response(request)
        venue = request['language_plan']['meaning_plan']['facts'][1]['value_ru']
        response = content.resolve_source_references(request, wire)
        response['questions'][0]['hint_ru'] = f'Найдите время, которое человек провёл {venue}.'
        with self.assertRaisesRegex(ValueError, 'another planned answer'):
            content.validate_output(request, response)

    def test_checked_feedback_has_mode_role_and_time_without_source_ids(self):
        for unit in ('location-destination-v1', 'calendar-and-duration-v1', 'talking-about-topics-v1'):
            for mode in ('reading', 'listening'):
                with self.subTest(unit=unit, mode=mode):
                    request = self.request(unit, mode)
                    schema = content.provider_schema(request)
                    for question in schema['properties']['questions']['properties'].values():
                        self.assertEqual(set(question['properties']), {'prompt_ru', 'prompt_en', 'sentence_ids'})
                    response = content.resolve_source_references(request, meaning_provider_response(request))
                    content.validate_output(request, response)
                    expected_ru = 'Послушайте' if mode == 'listening' else 'Прочитайте'
                    expected_en = 'Listen' if mode == 'listening' else 'Read'
                    for fact, question in zip(request['language_plan']['meaning_plan']['facts'], response['questions']):
                        self.assertTrue(question['hint_ru'].startswith(expected_ru))
                        self.assertTrue(question['hint'].startswith(expected_en))
                        support = ' '.join(question[field] for field in ('hint', 'hint_ru', 'explanation', 'explanation_ru'))
                        self.assertNotRegex(support, r'\bs\d+\b')
                        self.assertIn(question['evidence'], question['explanation_ru'])
                        if fact['role'] == 'topic_person':
                            self.assertIn('о ком', question['hint_ru'])
                            self.assertNotIn('о чём', question['hint_ru'])
                        if fact['role'] == 'topic_thing':
                            self.assertIn('о чём', question['hint_ru'])
                        if fact['role'] == 'location':
                            if unit == 'calendar-and-duration-v1':
                                self.assertNotIn('сейчас', question['hint_ru'])
                                self.assertIn('stayed', question['hint'])
                            else:
                                self.assertIn('сейчас', question['hint_ru'])
                                self.assertIn('now', question['hint'])

    def test_valid_short_three_fact_message_does_not_need_padding(self):
        request = self.request()
        wire = meaning_provider_response(request)
        facts = request['language_plan']['meaning_plan']['facts']
        wire['sentences'] = ['Привет!',
            f"{facts[0]['subject_name']} {facts[0]['value_ru']}.",
            f"Потом {facts[1]['subject_name']} идёт {facts[1]['value_ru']}.",
            f"{facts[2]['subject_name']} {facts[2]['value_ru']}."]
        for index, question in enumerate(wire['questions'].values(), 2):
            question['sentence_ids'] = ['s' + str(index)]
        self.assertLess(len(content.WORD.findall(' '.join(wire['sentences']))), 20)
        response = content.resolve_source_references(request, wire)
        content.validate_output(request, response)

    def test_two_sentences_can_carry_all_three_meanings(self):
        request = self.request()
        wire = meaning_provider_response(request)
        first, following, second = request['language_plan']['meaning_plan']['facts']
        wire['sentences'] = [
            f"{first['subject_name']} сейчас {first['value_ru']}, потом {following['subject_name']} идёт {following['value_ru']}.",
            f"{second['subject_name']} сейчас {second['value_ru']}."]
        for fact_id, ref in (('f1', 's1'), ('f2', 's1'), ('f3', 's2')):
            wire['questions'][fact_id]['sentence_ids'] = [ref]
        document = content.validate_output(request, content.resolve_source_references(request, wire))
        self.assertEqual(len(document['response']['questions']), 3)
        # An already-frozen four-sentence request retains its older boundary.
        saved = deepcopy(request)
        saved['limits']['minimum_sentences'] = 4
        with self.assertRaisesRegex(ValueError, 'invalid length'):
            content.resolve_source_references(saved, wire)

    def test_source_v3_contract_and_saved_document_remain_unchanged(self):
        request = self.request()
        request['generation_revision'] = 'source-v3'
        request['limits']['minimum_words'] = 20
        request['writer_brief']['limits']['minimum_words'] = 20
        request['generation_input_sha256'] = content._hash(request['writer_brief'])
        request['generation_prompt_sha256'] = hashlib.sha256(content.prompt_for(request).encode()).hexdigest()
        request['generation_schema_sha256'] = content._hash(content.provider_schema(request))
        wire = meaning_provider_response(request)
        self.assertIn('hint_en', wire['questions']['f1'])
        original = content.validate_output(request, content.resolve_source_references(request, wire))
        before = json.dumps(original, sort_keys=True, ensure_ascii=False)
        provider = MagicMock()
        provider.flashcard_model = 'existing-model'
        call = provider.client.with_options.return_value.chat.completions.create
        call.return_value = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(refusal=None, content=json.dumps(wire)))])
        generated = content.generate(request, provider)
        self.assertEqual(json.dumps(generated, sort_keys=True, ensure_ascii=False), before)
        self.assertEqual(call.call_args.kwargs['messages'][0]['content'], content.SYSTEM_PROMPT_V3)
        self.assertNotEqual(content.SYSTEM_PROMPT_V3, content.SYSTEM_PROMPT_V4)

    def test_supporting_location_question_cannot_ask_for_a_person_or_time(self):
        for unit in ('calendar-and-duration-v1', 'talking-about-topics-v1'):
            request = self.request(unit)
            fact = next(f for f in request['language_plan']['meaning_plan']['facts'] if f['role'] == 'location')
            for ru, en in ((f"С кем была {fact['subject_name']}?", f"Who was {fact['subject_en']} with?"),
                           (f"Когда была там {fact['subject_name']}?", f"When was {fact['subject_en']} there?")):
                with self.subTest(unit=unit, question=ru):
                    wire = meaning_provider_response(request)
                    wire['questions'][fact['id']].update(prompt_ru=ru, prompt_en=en)
                    with self.assertRaises(ValueError):
                        content.validate_output(request, content.resolve_source_references(request, wire))
            wire = meaning_provider_response(request)
            wire['questions'][fact['id']].update(
                prompt_ru=f"В каком месте была {fact['subject_name']}?",
                prompt_en=f"In which place was {fact['subject_en']}?")
            content.validate_output(request, content.resolve_source_references(request, wire))


if __name__ == '__main__':
    unittest.main()
