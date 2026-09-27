import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services.yandex_service import YandexService
from services.anki_connect import AnkiConnect
from services.openai_service import OpenAIService
from services.elevenlabs_service import ElevenLabsService


class ProviderUpgradeTests(unittest.TestCase):
    def test_translation_failure_is_not_card_content(self):
        service = YandexService('synthetic')
        with patch('services.yandex_service.requests.post', side_effect=RuntimeError('failure')):
            result = service.translate('кот')
        self.assertIsNone(result['translation'])
        self.assertIn('error', result)

    def test_cloud_translation_contract(self):
        response = Mock()
        response.json.return_value = {'translations': [{'text': 'cat'}]}
        with patch('services.yandex_service.requests.post', return_value=response) as call:
            self.assertEqual(YandexService('synthetic').translate('кот')['translation'], 'cat')
        args = call.call_args.kwargs
        self.assertNotIn('params', args)
        self.assertEqual(args['headers']['Authorization'], 'Api-Key synthetic')
        self.assertEqual(args['json']['texts'], ['кот'])
        self.assertNotIn('folderId', args['json'])

    def test_anki_write_has_timeout_and_no_retry(self):
        response = Mock()
        response.json.return_value = {'result': 10, 'error': None}
        with patch('services.anki_connect.requests.post', return_value=response) as call:
            self.assertEqual(AnkiConnect().add_note({'fields': {}})['result'], 10)
        call.assert_called_once()
        self.assertEqual(call.call_args.kwargs['timeout'], 15)

    def test_image_base64_and_model_override(self):
        service = OpenAIService('synthetic', image_model='test-image')
        service.client = Mock()
        service.client.images.generate.return_value.data = [Mock(url=None, b64_json='YWJj')]
        self.assertEqual(service.generate_image_url('Кот.', 'кот'), 'data:image/png;base64,YWJj')
        self.assertEqual(service.client.images.generate.call_args.kwargs['model'], 'test-image')

    def test_native_memory_picture_does_not_request_written_answers(self):
        service = OpenAIService('synthetic', image_model='test-image')
        service.client = Mock()
        service.client.images.generate.return_value.data = [Mock(url='https://example.test/image', b64_json=None)]
        service.generate_image_url('В музее открыли выставку.', 'выставку', no_text=True)
        prompt = service.client.images.generate.call_args.kwargs['prompt']
        self.assertIn('without ANY readable text', prompt)
        self.assertIn('Never write the target word', prompt)

    def test_audio_failure_preserves_existing_file(self):
        response = Mock(content=b'invalid mp3')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'card.mp3'
            path.write_bytes(b'previous good audio')
            with patch('services.elevenlabs_service.requests.post', return_value=response) as call, \
                 patch('services.elevenlabs_service.AudioSegment.from_file', side_effect=ValueError('decode')):
                service = ElevenLabsService('synthetic', folder, voice_ids=('test-voice',))
                self.assertIsNone(service.generate_audio('Кот.', 'card.mp3'))
            self.assertTrue(call.call_args.args[0].endswith('/test-voice'))
            self.assertEqual(path.read_bytes(), b'previous good audio')
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_anki_uses_structured_content_without_yandex(self):
        from services.flashcard_service import FlashcardService
        provider, yandex, speech, anki = Mock(), Mock(), Mock(), Mock()
        provider.generate_native_card.return_value = {
            'sentence': 'Это кот.', 'english': 'cat', 'sentence_english': 'This is a cat.', 'notes': ''}
        speech.media_dir = '/unused-test-media'
        speech.generate_audio.return_value = None
        provider.generate_image_url.return_value = None
        service = FlashcardService('/unused-test-db', provider, yandex, speech, anki)
        with patch('services.flashcard_service.get_word_by_id', return_value={'lemma_difficulty': 1, 'count': 0}), \
             patch('services.flashcard_service.get_form_by_word_id', return_value={'form': 'кот'}), \
             patch('services.flashcard_service.format_cloze', return_value=('Это {{c1::кот}}.', 'кот', {})):
            success, errors = service.generate_flashcard(1, 'кот', 'NOUN', 'кот', {}, 1, [])
        provider.generate_native_card.assert_called_once()
        yandex.translate_sentence.assert_not_called()
        provider.generate_sentence.assert_not_called()
        provider.get_word_translation.assert_not_called()
        # No media was supplied: export stops before writing an Anki note or counters.
        self.assertFalse(success)
        self.assertTrue(any('No media' in error for error in errors))
        anki.add_note.assert_not_called()

    def test_random_voice_is_selected_for_each_generation(self):
        service = ElevenLabsService('synthetic', '/unused', voice_ids=('first', 'second'))
        with patch('services.elevenlabs_service.random.choice', side_effect=['first', 'second']) as choose, \
             patch('services.elevenlabs_service.requests.post', side_effect=RuntimeError('offline')) as post:
            service.generate_audio('Кот.', 'a.mp3')
            service.generate_audio('Кот.', 'b.mp3')
        self.assertEqual(choose.call_count, 2)
        self.assertTrue(post.call_args_list[0].args[0].endswith('/first'))
        self.assertTrue(post.call_args_list[1].args[0].endswith('/second'))

    def test_story_audio_does_not_publish_a_missing_file(self):
        from services.comprehension_service import ComprehensionService
        service = ComprehensionService.__new__(ComprehensionService)
        service.elevenlabs_service = Mock()
        with tempfile.TemporaryDirectory() as folder:
            service.media_dir = folder
            for result in (None, 'missing.mp3'):
                service.elevenlabs_service.generate_audio.return_value = result
                self.assertEqual(service.generate_audio('Анна пьёт чай.'), '')

            def save_audio(text, path):
                Path(path).write_bytes(b'test audio already validated by the speech service')
                return Path(path).name
            service.elevenlabs_service.generate_audio.side_effect = save_audio
            url = service.generate_audio('Анна пьёт чай.')
            self.assertTrue(url.startswith('/static/media/'))
            self.assertTrue((Path(folder) / url.rsplit('/', 1)[-1]).is_file())

    def test_flashcard_model_is_separate_from_other_workloads(self):
        service = OpenAIService('synthetic', flashcard_model='openai/gpt-5.6-luna', high_model='gpt-5.2')
        service.client = Mock()
        choice = Mock(finish_reason='stop')
        choice.message.refusal = None
        choice.message.content = '{"english":"cat","sentence":"Это кот.","sentence_english":"This is a cat.","notes":""}'
        service.client.with_options.return_value.chat.completions.create.return_value.choices = [choice]
        service.generate_native_card({'form': 'кот'}, 'ru-en')
        request = service.client.with_options.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(request['model'], 'gpt-5.6-luna')
        self.assertEqual(request['reasoning_effort'], 'low')
        self.assertEqual(service.high_model, 'gpt-5.2')
