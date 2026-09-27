"""Radio prepares one genuine listening passage, never a gallery of pictures."""
import copy
import io
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

from pydub import AudioSegment

from repositories.learning_repository import LearningError, encoded, transaction
from services.radio_broadcast import (
    RadioBroadcastService, WORD, generate_broadcast, initial_request, validate_broadcast,
)
from tests.support import isolated_app


SCRIPT = (
    'Здравствуйте, друзья! В эфире Почтовое радио. Сегодня расскажем о празднике в нашем парке. '
    'В субботу там откроется небольшая ярмарка. Она начнётся в десять часов утра и закончится вечером. '
    'Местные жители будут продавать книги, игрушки и домашний хлеб. Рядом с входом можно будет выпить горячий чай. '
    'Дети смогут нарисовать открытки для своих друзей. Все материалы для рисования будут бесплатными. '
    'После обеда на маленькой сцене выступит школьный оркестр. Музыканты приготовили весёлые песни, которые многие знают. '
    'Если пойдёт дождь, концерт перенесут в библиотеку через дорогу. Поэтому праздник состоится в любую погоду. '
    'Мы поговорили с организаторами, и они советуют прийти пораньше: утром выбор книг будет больше. '
    'Возьмите с собой удобную сумку для покупок и пригласите соседей. До встречи в парке! '
    'С вами было Почтовое радио. Хорошего дня!'
)


def programme():
    def question(prompt, choices, evidence, help_text, explanation):
        return {'prompt': prompt, 'choices': choices, 'correct_index': 0, 'evidence': evidence,
                'help_english': help_text, 'explanation_english': explanation}
    return {'title': 'Суббота в парке', 'script': SCRIPT,
            'questions': [
                question('Где пройдёт праздник?', ['В парке.', 'На вокзале.', 'В музее.', 'В школе.'],
                         'Сегодня расскажем о празднике в нашем парке.', 'Where is the event?',
                         'The presenter says the event will take place in the park.'),
                question('Когда начнётся ярмарка?', ['В десять часов утра.', 'В полдень.', 'В три часа дня.', 'В семь часов вечера.'],
                         'Она начнётся в десять часов утра и закончится вечером.', 'When does the fair start?',
                         'It starts at ten in the morning.'),
                question('Что смогут сделать дети?', ['Нарисовать открытки.', 'Построить сцену.', 'Испечь хлеб.', 'Продать билеты.'],
                         'Дети смогут нарисовать открытки для своих друзей.', 'What can children do?',
                         'Children can draw postcards for friends.'),
                question('Куда перенесут концерт, если пойдёт дождь?', ['В библиотеку.', 'В кафе.', 'В школу.', 'На вокзал.'],
                         'Если пойдёт дождь, концерт перенесут в библиотеку через дорогу.',
                         'Where will the concert move if it rains?', 'The library is the alternative venue if it rains.'),
            ], 'vocabulary': [
                {'lemma': 'ярмарка', 'form': 'ярмарка', 'pos': 'NOUN', 'sentence': 'В субботу там откроется небольшая ярмарка.',
                 'translation': 'A small fair will open there on Saturday.', 'target_meaning': 'fair', 'grammar_note': ''},
                {'lemma': 'оркестр', 'form': 'оркестр', 'pos': 'NOUN', 'sentence': 'После обеда на маленькой сцене выступит школьный оркестр.',
                 'translation': 'After lunch, the school orchestra will perform on the small stage.', 'target_meaning': 'orchestra', 'grammar_note': ''},
            ]}


class TextProvider:
    flashcard_model = 'configured-existing-model'

    def __init__(self):
        self.calls = []
        self.response = programme()
        self.wait = self.release = None

    def generate_radio_broadcast(self, request):
        self.calls.append(copy.deepcopy(request))
        if self.wait:
            self.wait.set()
            self.release.wait(5)
        return copy.deepcopy(self.response)


class RecordingProvider:
    def __init__(self):
        self.calls, self.specs, self.fail = [], [], False
        output = io.BytesIO()
        AudioSegment.silent(duration=60000, frame_rate=22050).export(output, format='mp3')
        self.audio = output.getvalue()

    def spec(self, kind, item, form):
        self.specs.append(kind)
        return {'text': item['context'], 'model': 'existing-speech-model', 'voice_id': 'frozen-random-voice'}

    def generate(self, kind, spec):
        self.calls.append((kind, copy.deepcopy(spec)))
        if self.fail:
            raise ValueError('temporary connection failure')
        if kind != 'sentence_audio':
            raise AssertionError('Radio must not request an image or individual word audio')
        return self.audio


class RadioBroadcastTests(unittest.TestCase):
    def setUp(self):
        self.provider, self.media = TextProvider(), RecordingProvider()
        self.app = isolated_app(self, {'OpenAIService': self.provider, 'CardMediaProvider': self.media})
        self.db = self.app.config['DB_PATH']
        self.store = self.app.extensions['learning']['assets']
        self.allowed, self.clock = True, 1000
        self.service = RadioBroadcastService(self.db, self.store, self.provider, self.media,
                                              self.authorize, clock=lambda: self.clock)
        content, items = initial_request({'title': 'Post Office Radio'},
                                         [{'lemma': 'парк', 'form': 'парками'}, {'lemma': 'книга', 'form': 'книгу'}],
                                         ['парк', 'книга', 'хлеб', 'чай', 'школа'], 'seed-radio', 'radio-session',
                                         {'source': 'vocabulary', 'rounds': 4},
                                         {'kind': 'vocabulary', 'title': 'My vocabulary', 'href': '#words'})
        self.request = items[0]['request']
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO journey_game_sessions(id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES (?,NULL,?,?,?,?,?,?,?)',
                         ('radio-session', 'guest-radio', 'radio', 'seed-radio', '[]', encoded(content), self.clock, self.clock))
            conn.execute('INSERT INTO journey_game_preparations(session_id,items_json,created_at,updated_at) VALUES (?,?,?,?)',
                         ('radio-session', encoded(items), self.clock, self.clock))

    def authorize(self, conn, session_id):
        row = conn.execute('SELECT * FROM journey_game_sessions WHERE id=?', (session_id,)).fetchone()
        if not self.allowed or not row:
            raise LearningError('not_found', 'This programme belongs to another learner.', 404)
        return row

    def status(self):
        with transaction(self.db) as conn:
            return self.service.status(conn, self.authorize(conn, 'radio-session'))

    def content(self):
        with transaction(self.db) as conn:
            return self.service.content(conn, 'radio-session')

    def test_one_coherent_programme_one_recording_four_questions_no_pictures_or_cards(self):
        self.assertGreaterEqual(len(WORD.findall(SCRIPT)), 100)
        self.assertLessEqual(len(WORD.findall(SCRIPT)), 155)
        self.assertEqual(self.status()['stage'], 'script')
        self.assertIsNone(self.content())
        self.assertEqual(self.service.advance('radio-session')['stage'], 'audio')
        self.assertEqual(self.media.calls, [])
        self.assertEqual(self.service.advance('radio-session')['status'], 'ready')
        frozen = self.content()
        self.assertEqual(frozen['generator'], 'radio-broadcast-v1')
        self.assertEqual(len(frozen['rounds']), 4)
        self.assertEqual(frozen['broadcast']['script'], SCRIPT)
        self.assertTrue(60 < frozen['broadcast']['duration_seconds'] < 63)
        self.assertEqual(len({q['clues'][0]['audio_key'] for q in frozen['rounds']}), 1)
        for item in frozen['rounds']:
            self.assertEqual(len(item['choices']), 4)
            self.assertEqual(len(item['expected_answer']), 1)
            self.assertIn(item['expected_answer'][0], {choice['id'] for choice in item['choices']})
            self.assertNotIn('objects', item)
        self.assertEqual({item['lemma'] for item in frozen['vocabulary_refs']}, {'ярмарка', 'оркестр'})
        self.assertEqual(frozen['vocabulary_refs'][0]['tags']['case'], 'nomn')
        self.assertNotIn('case', frozen['vocabulary_refs'][1]['tags'])
        self.assertEqual(self.media.specs, ['sentence_audio'])
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(len(self.media.calls), 1)
        self.service.advance('radio-session')
        self.assertEqual(self.content(), frozen)
        self.assertEqual(len(self.media.calls), 1)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_assets').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0], 0)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_failed_audio_does_not_regenerate_script_or_choose_a_new_voice(self):
        self.service.advance('radio-session')
        self.media.fail = True
        self.assertEqual(self.service.advance('radio-session')['status'], 'failed')
        first = self.media.calls[0]
        self.service.advance('radio-session')
        self.assertEqual(len(self.media.calls), 1)
        self.media.fail = False
        self.assertEqual(self.service.advance('radio-session', retry=True)['status'], 'ready')
        self.assertEqual(self.media.calls, [first, first])
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.media.specs, ['sentence_audio'])

    def test_concurrent_prepare_claims_generation_once_and_releases_sqlite_before_network(self):
        self.provider.wait, self.provider.release = threading.Event(), threading.Event()
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(self.service.advance, 'radio-session')
            self.assertTrue(self.provider.wait.wait(3))
            # Another write can proceed during the provider call.
            with transaction(self.db, write=True) as conn:
                conn.execute('UPDATE journey_game_sessions SET updated_at=? WHERE id=?', (1001, 'radio-session'))
            self.assertEqual(self.service.advance('radio-session')['stage'], 'script')
            self.provider.release.set()
            self.assertEqual(first.result(timeout=5)['stage'], 'audio')
        self.assertEqual(len(self.provider.calls), 1)

    def test_failure_keeps_explicit_retry_and_ownership_checks(self):
        self.provider.response['questions'][0]['evidence'] = 'Этого никто не говорил.'
        self.assertEqual(self.service.advance('radio-session')['status'], 'failed')
        self.service.advance('radio-session')
        self.assertEqual(len(self.provider.calls), 1)
        self.provider.response = programme()
        self.assertEqual(self.service.advance('radio-session', retry=True)['stage'], 'audio')
        self.allowed = False
        with self.assertRaises(LearningError):
            self.service.advance('radio-session')
        with self.assertRaises(LearningError):
            self.content()
        self.assertEqual(self.media.calls, [])

    def test_rejected_paid_draft_is_saved_for_inspection_and_explicit_repair(self):
        self.provider.response['questions'][0]['evidence'] = 'Этого никто не говорил.'
        self.assertEqual(self.service.advance('radio-session')['status'], 'failed')
        with transaction(self.db) as conn:
            record = json.loads(conn.execute('SELECT items_json FROM journey_game_preparations WHERE session_id=?',
                                             ('radio-session',)).fetchone()[0])[0]
        self.assertEqual(record['draft'], self.provider.response)
        self.assertEqual(record['validation_error'], 'Question evidence is absent from the programme')
        self.provider.response = programme()
        self.assertEqual(self.service.advance('radio-session', retry=True)['stage'], 'audio')
        retry_request = self.provider.calls[-1]
        self.assertEqual(retry_request['previous_validation_error'], record['validation_error'])
        self.assertEqual(retry_request['previous_draft'], record['draft'])
        self.assertNotIn('previous_validation_error', self.request)
        self.assertEqual(self.service.advance('radio-session')['status'], 'ready')
        self.assertEqual(self.media.specs, ['sentence_audio'])

    def test_dictionary_guesses_are_not_published_as_new_russian_lexemes(self):
        value = programme()
        value['script'] = value['script'].replace('ярмарка', 'маркурышмапс')
        value['vocabulary'][0].update(lemma='маркурышмапс', form='маркурышмапс',
                                      sentence=value['vocabulary'][0]['sentence'].replace('ярмарка', 'маркурышмапс'))
        with self.assertRaisesRegex(ValueError, 'does not belong'):
            validate_broadcast(value, self.request)

    def test_validation_rejects_wrong_language_duplicate_answers_known_words_and_false_forms(self):
        corruptions = [
            lambda item: item.update(script='Я люблю парк и книгу.'),
            lambda item: item['questions'][0]['choices'].__setitem__(1, 'In the museum'),
            lambda item: item['questions'][0]['choices'].__setitem__(1, 'В парке'),
            lambda item: item['questions'][0].update(correct_index=True),
            lambda item: item['vocabulary'][0].update(lemma='парк'),
            lambda item: item['vocabulary'][0].update(form='ярмаркой'),
            lambda item: item['vocabulary'][0].update(lemma='театр'),
        ]
        for corrupt in corruptions:
            with self.subTest(corruption=corrupt):
                value = programme(); corrupt(value)
                with self.assertRaises(ValueError):
                    validate_broadcast(value, self.request)
        # Library forms are anchors, not mandatory frozen forms inside speech.
        self.assertNotIn('парками', SCRIPT)
        self.assertEqual(validate_broadcast(programme(), self.request)['title'], 'Суббота в парке')

    def test_generated_contract_uses_configured_model_and_low_effort(self):
        provider = SimpleNamespace(client=MagicMock(), flashcard_model='existing-configured-model')
        provider.client.with_options.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[
            SimpleNamespace(finish_reason='stop', message=SimpleNamespace(refusal=None, content=json.dumps(programme())))])
        result = generate_broadcast(provider, self.request)
        self.assertEqual(result['script'], SCRIPT)
        arguments = provider.client.with_options.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(arguments['model'], 'existing-configured-model')
        self.assertEqual(arguments['reasoning_effort'], 'low')
        self.assertEqual(arguments['response_format']['json_schema']['schema']['properties']['questions']['maxItems'], 4)
        self.assertNotIn('images', arguments)

    def test_short_or_missing_recording_is_not_published_as_a_programme(self):
        self.service.advance('radio-session')
        output = io.BytesIO()
        AudioSegment.silent(duration=500).export(output, format='mp3')
        self.media.audio = output.getvalue()
        self.assertEqual(self.service.advance('radio-session')['status'], 'failed')
        self.assertIsNone(self.content())
        self.assertEqual(len(self.provider.calls), 1)


if __name__ == '__main__':
    unittest.main()
