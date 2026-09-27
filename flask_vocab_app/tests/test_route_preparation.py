"""Generated dialogue cannot rewrite route facts or lose paid preparation work."""
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
import wave

from repositories.learning_repository import transaction
from services.learning_assets import LocalAssetStore
from services.route_content import line
from services.route_preparation import (RoutePreparationService, REVIEW_FIELDS, PreparationFailure,
                                        dialogue_context, spoken_lines)


def pack():
    original = line('olya', 'Отнеси эту посылку Анне.', 'Take this parcel to Anna.')
    destination = line('olya', 'Анна сейчас в жёлтом доме.', 'Anna is in the yellow house now.')
    reply = line('olya', 'В доме напротив пекарни.', 'In the house opposite the bakery.')
    return {'speakers': {'olya': {'name': 'Оля', 'role': 'Пекарь', 'role_en': 'Baker'},
                         'anna': {'name': 'Анна', 'role': 'Получатель', 'role_en': 'Recipient'}},
            'recipient_id': 'anna', 'language_level': 'A2',
            'legs': [{'speaker': 'olya', 'arrival_speaker': 'anna', 'lines': [original, destination],
                      'clarify': deepcopy(destination), 'questions': [{'id': 'which-house', 'text': 'Какой дом?', 'reply': reply}],
                      'encounter_contract': {'version': 'test-v1', 'stage': 'address_clarification',
                          'required_lines': [{**original, 'role': 'handover'}, {**destination, 'role': 'incomplete_address'}],
                          'facts': [{'type': 'recipient', 'id': 'anna'}, {'type': 'item', 'id': 'parcel'}],
                          'allowed_entity_ids': ['anna'], 'arrival': {'target_node': 'hidden-door'},
                          'question': {'answer': 'hidden bakery'},
                          'allowed_narrative': [{'ru': 'Спасибо за помощь.', 'en': 'Thanks for your help.'}]}}],
            'future_event': 'secret recipient relocation',
            'ending': line('anna', 'Спасибо за посылку!', 'Thank you for the parcel!')}


class TextProvider:
    flashcard_model = 'configured-test-model'

    def __init__(self):
        self.client = self
        self.chat = types.SimpleNamespace(completions=self)
        self.requests = []
        self.responses = []
        self.check_unlocked = lambda: None

    def with_options(self, **kwargs):
        if kwargs != {'timeout': 60, 'max_retries': 0}:
            raise AssertionError(kwargs)
        return self

    def create(self, **kwargs):
        self.check_unlocked()
        self.requests.append(deepcopy(kwargs))
        response = self.responses.pop(0) if self.responses else (
            {key: True for key in REVIEW_FIELDS} if kwargs['response_format']['json_schema']['name'] == 'delivery_review'
            else {'before': [{'text': 'Спасибо за помощь, Барсик.', 'english': 'Thank you for your help, Barsik.'}], 'after': []})
        if isinstance(response, Exception):
            raise response
        return types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason='stop', message=types.SimpleNamespace(
            content=json.dumps(response, ensure_ascii=False), refusal=None))])


class SpeechProvider:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.check_unlocked = lambda: None

    def speak(self, text, voice):
        self.check_unlocked()
        self.calls.append((text, voice))
        if self.fail:
            raise ValueError('private key and provider response must not escape')
        output = io.BytesIO()
        with wave.open(output, 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            # Different text/voice produces different valid audio bytes.
            sample = sha256((text + voice).encode()).digest()[:2]
            audio.writeframes(sample * 3200)
        return output.getvalue()


class RoutePreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'learning.db'
        with sqlite3.connect(self.db) as conn:
            conn.execute('CREATE TABLE learning_assets (id TEXT PRIMARY KEY, storage_key TEXT UNIQUE, sha256 TEXT, byte_size INTEGER, media_type TEXT, source TEXT, created_at INTEGER)')
            conn.execute('CREATE TABLE journey_route_audio_cache (spec_hash TEXT PRIMARY KEY CHECK(length(spec_hash)=64), asset_id TEXT NOT NULL REFERENCES learning_assets(id), created_at INTEGER NOT NULL)')
        self.store = LocalAssetStore(self.root / 'assets')
        self.text, self.speech = TextProvider(), SpeechProvider()
        self.config = {'ELEVENLABS_VOICE_IDS': ['voice-a', 'voice-b'], 'ELEVENLABS_MODEL': 'saved-model',
                       'ELEVENLABS_API_KEY': 'test-key', 'OPENAI_API_KEY': 'test-key'}
        self.service = RoutePreparationService(self.db, self.store, self.text, self.speech, self.config,
                                              static_audio_root=self.root / 'static')
        self.text.check_unlocked = self.speech.check_unlocked = self.assert_unlocked
        self.pack = self.service.plan(pack(), scope='profile-a')

    def assert_unlocked(self):
        with sqlite3.connect(self.db, timeout=0) as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('SELECT 1')
            conn.rollback()

    def advance(self):
        self.pack = self.service.advance(self.pack)
        self.assertNotEqual(self.service.status(self.pack)['status'], 'failed', self.service.status(self.pack))
        return self.pack

    def finish(self):
        for _ in range(20):
            if self.service.status(self.pack)['status'] == 'ready':
                return self.pack
            self.advance()
        self.fail('Preparation did not finish')

    def test_plan_is_pure_frozen_and_contains_no_credentials(self):
        source = pack()
        prepared = self.service.plan(source, scope='profile-a')
        self.assertNotIn('_route_preparation', source)
        state = prepared['_route_preparation']
        self.assertEqual(state['voices'], {'olya': 'voice-a', 'anna': 'voice-b'})
        self.assertEqual(state['model'], self.text.flashcard_model)
        self.assertNotIn('test-key', json.dumps(prepared))
        self.config['ELEVENLABS_VOICE_IDS'] = ['different']
        self.assertEqual(self.service.plan(prepared, scope='profile-a'), prepared)
        with self.assertRaises(PreparationFailure):
            self.service.plan(prepared, scope='profile-b')
        self.assertEqual(self.text.requests, [])
        self.assertEqual(self.speech.calls, [])

    def test_model_does_not_see_hidden_question_answer_or_later_event(self):
        context = dialogue_context(self.pack, 0)
        serialized = json.dumps(context, ensure_ascii=False)
        for secret in ('hidden-door', 'hidden bakery', 'secret recipient relocation', 'напротив', 'arrival', 'question'):
            self.assertNotIn(secret, serialized)
        self.assertIn('Отнеси эту посылку Анне.', serialized)
        self.advance()
        self.assertNotIn('hidden-door', json.dumps(self.text.requests))

    def test_writer_and_reviewer_share_explicit_listener_and_current_circumstance(self):
        self.advance()
        self.advance()
        writer = json.loads(self.text.requests[0]['messages'][1]['content'])
        reviewer = json.loads(self.text.requests[1]['messages'][1]['content'])
        self.assertEqual(writer['listener'], reviewer['listener'])
        self.assertEqual(reviewer['listener']['name'], 'Барсик')
        self.assertIn('barsik', reviewer['allowed_entity_ids'])
        self.assertIn('olya', reviewer['allowed_entity_ids'])
        self.assertIn('speaker and listener', self.text.requests[1]['messages'][0]['content'])
        self.assertIn('not every ordinary noun', self.text.requests[1]['messages'][0]['content'])
        self.assertIn('Do not restate the parcel contents', self.text.requests[0]['messages'][0]['content'])
        record = self.pack['_route_preparation']['dialogue'][0]
        self.assertEqual(record['draft_prompt_version'], 'delivery-dialogue-v2')
        self.assertEqual(record['review_prompt_version'], 'delivery-dialogue-v2')

    def test_independent_check_precedes_audio_and_retains_critical_lines(self):
        original = deepcopy(self.pack)
        self.advance()
        self.assertEqual(self.pack['legs'][0]['lines'], original['legs'][0]['lines'])
        self.assertEqual(self.service.status(self.pack)['stage'], 'review')
        self.assertEqual(self.speech.calls, [])
        self.advance()
        self.assertEqual(self.pack['legs'][0]['lines'][1:], original['legs'][0]['lines'])
        self.assertEqual(self.pack['legs'][0]['questions'], original['legs'][0]['questions'])
        self.assertEqual(len(self.text.requests), 2)
        self.assertEqual(self.service.status(self.pack)['stage'], 'audio')
        self.assertEqual(self.text.requests[0]['model'], 'configured-test-model')
        self.assertEqual(self.text.requests[0]['reasoning_effort'], 'low')
        self.assertEqual(original['legs'][0]['lines'][0]['text'], 'Отнеси эту посылку Анне.')

    def test_wrong_turn_or_invented_landmark_never_enters_the_pack(self):
        for text in ('Поверни направо.', 'Найди музей рядом с парком.'):
            with self.subTest(text=text):
                self.text.responses = [{'before': [{'text': text, 'english': 'Take another route.'}], 'after': []}]
                failed = self.service.advance(self.pack)
                self.assertEqual(self.service.status(failed)['status'], 'pending')
                self.assertEqual(failed['legs'], self.pack['legs'])
                self.assertEqual(self.speech.calls, [])

    def test_semantic_rejection_clears_draft_and_retry_uses_same_map_contract(self):
        for criterion in ('grounded', 'no_spoilers', 'translation_matches', 'natural_russian'):
            with self.subTest(criterion=criterion):
                draft = self.service.advance(self.pack)
                self.text.responses = [{key: key != criterion for key in REVIEW_FIELDS}]
                failed = self.service.advance(draft)
                self.assertEqual(self.service.status(failed)['status'], 'pending')
                self.assertNotIn('draft', failed['_route_preparation']['dialogue'][0])
                diagnostic = failed['_route_preparation']['dialogue'][0]['rejections'][-1]
                self.assertIs(diagnostic['review'][criterion], False)
                self.assertEqual(diagnostic['draft'], draft['_route_preparation']['dialogue'][0]['draft'])
                self.assertNotIn('rejections', self.service.status(failed))
                self.assertIsNone(failed['_route_preparation']['error'])
                self.assertEqual(failed['legs'], self.pack['legs'])
                retried = self.service.advance(failed)
                self.assertEqual(retried['_route_preparation']['dialogue'][0]['attempts'], 2)
                self.assertEqual(retried['legs'], self.pack['legs'])

    def test_preparation_records_every_optional_clip_and_reuses_completed_work(self):
        self.finish()
        distinct = {(speaker, item['text']) for speaker, item in spoken_lines(self.pack)}
        self.assertEqual(len(self.speech.calls), len(distinct))
        self.assertEqual(len(self.text.requests), 2)
        for _, item in spoken_lines(self.pack):
            self.assertTrue(item['asset_id'])
            self.assertEqual(item['audio_url'], '')
        self.assertIn('В доме напротив пекарни.', {text for text, _ in self.speech.calls})
        self.assertIn('Спасибо за посылку!', {text for text, _ in self.speech.calls})
        finished = self.service.advance(self.pack)
        self.assertEqual(finished, self.pack)
        self.assertEqual(len(self.speech.calls), len(distinct))

    def test_interrupted_audio_reuses_exact_text_voice_cache_without_another_call(self):
        self.advance()
        self.advance()
        checkpoint = deepcopy(self.pack)
        self.advance()
        self.assertEqual(len(self.speech.calls), 1)
        replay = self.service.advance(checkpoint)
        self.assertEqual(len(self.speech.calls), 1)
        self.assertEqual(replay['_route_preparation']['audio'], self.pack['_route_preparation']['audio'])
        self.assertEqual(replay['legs'], self.pack['legs'])

    def test_audio_failure_preserves_approved_story_and_prior_recordings(self):
        self.advance()
        self.advance()
        self.advance()
        before = deepcopy(self.pack)
        self.speech.fail = True
        failed = self.service.advance(self.pack)
        self.assertEqual(self.service.status(failed)['status'], 'failed')
        self.assertEqual(failed['legs'], before['legs'])
        self.assertEqual(failed['_route_preparation']['audio'], before['_route_preparation']['audio'])
        self.assertNotIn('private key', json.dumps(failed))
        self.speech.fail = False
        self.pack = self.service.advance(failed)
        self.assertEqual(len(self.text.requests), 2)
        self.assertNotEqual(self.service.status(self.pack)['status'], 'failed')
        self.assertEqual(self.speech.calls[-1], self.speech.calls[-2])

    def test_cache_scope_and_voice_change_do_not_reuse_wrong_audio(self):
        self.finish()
        calls = len(self.speech.calls)
        other = self.service.plan(pack(), scope='profile-b')
        other = self.service.advance(self.service.advance(other))
        other = self.service.advance(other)
        self.assertEqual(len(self.speech.calls), calls + 1)
        different_voice = deepcopy(self.pack)
        different_voice['_route_preparation']['voices']['olya'] = 'new-voice'
        self.service.advance(different_voice)
        self.assertEqual(self.speech.calls[-1][1], 'new-voice')

    def test_identical_bytes_across_owners_keep_both_cache_associations_after_restart(self):
        self.finish()
        first_asset = self.pack['legs'][0]['lines'][0]['asset_id']
        other = self.service.plan(pack(), scope='profile-b')
        other = self.service.advance(self.service.advance(other))
        checkpoint = deepcopy(other)
        calls = len(self.speech.calls)
        other = self.service.advance(other)
        self.assertEqual(len(self.speech.calls), calls + 1)
        self.assertEqual(other['legs'][0]['lines'][0]['asset_id'], first_asset)
        with transaction(self.db) as conn:
            mappings = conn.execute('SELECT spec_hash FROM journey_route_audio_cache WHERE asset_id=?', (first_asset,)).fetchall()
        self.assertEqual(len(mappings), 2)
        restarted = RoutePreparationService(self.db, self.store, self.text, self.speech, self.config,
                                            static_audio_root=self.root / 'static')
        restored = restarted.advance(checkpoint)
        self.assertEqual(restored['_route_preparation']['audio'], other['_route_preparation']['audio'])
        self.assertEqual(restored['legs'], other['legs'])
        self.assertEqual(len(self.speech.calls), calls + 1)

    def test_missing_asset_file_is_prepared_again(self):
        self.finish()
        first = self.pack['legs'][0]['lines'][0]['asset_id']
        with transaction(self.db) as conn:
            key = conn.execute('SELECT storage_key FROM learning_assets WHERE id=?', (first,)).fetchone()[0]
        self.store.path(key).unlink()
        calls = len(self.speech.calls)
        self.assertEqual(self.service.status(self.pack)['stage'], 'audio')
        self.advance()
        self.assertEqual(len(self.speech.calls), calls + 1)
        self.assertEqual(self.service.status(self.pack)['stage'], 'ready')

    def test_provider_errors_are_safe_retryable_errors(self):
        self.text.responses = [ValueError('private upstream response body with keys')]
        failed = self.service.advance(self.pack)
        self.assertNotIn('upstream', failed['_route_preparation']['error'])
        self.assertEqual(failed['legs'], self.pack['legs'])
        self.assertEqual(failed['_route_preparation']['dialogue'][0]['attempts'], 1)

    def test_refused_or_truncated_responses_do_not_reach_dialogue(self):
        for finish, refusal, content in [('stop', 'Refused', None), ('length', None, '{}'), ('stop', None, '{broken')]:
            with self.subTest(finish=finish, refusal=refusal):
                def response(**kwargs):
                    return types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason=finish,
                        message=types.SimpleNamespace(refusal=refusal, content=content))])
                self.text.create = response
                failed = self.service.advance(self.pack)
                self.assertEqual(self.service.status(failed)['status'], 'failed')
                self.assertEqual(failed['legs'], self.pack['legs'])
                self.assertEqual(self.speech.calls, [])

    def test_configured_speech_model_cannot_change_after_planning(self):
        self.advance()
        self.advance()
        self.speech.config = {**self.config, 'ELEVENLABS_MODEL': 'unexpected-model'}
        failed = self.service.advance(self.pack)
        self.assertEqual(self.service.status(failed)['status'], 'failed')
        self.assertEqual(self.speech.calls, [])
        self.assertIn('speech model changed', failed['_route_preparation']['error'])

    def test_duplicate_extras_or_required_text_cannot_create_repeated_line_ids(self):
        repeated = {'text': 'Спасибо за помощь.', 'english': 'Thank you for your help.'}
        required = self.pack['legs'][0]['lines'][0]
        for response in ({'before': [repeated], 'after': [repeated]},
                         {'before': [{key: required[key] for key in ('text', 'english')}], 'after': []}):
            with self.subTest(response=response):
                self.text.responses = [response]
                rejected = self.service.advance(self.pack)
                self.assertEqual(rejected['legs'], self.pack['legs'])
                self.assertEqual(rejected['_route_preparation']['dialogue'][0]['content_rejections'], 1)
                self.assertEqual(self.service.status(rejected)['status'], 'pending')

    def test_two_semantic_rejections_use_checked_context_without_another_model_call(self):
        original = deepcopy(self.pack)
        negative = {key: key != 'no_spoilers' for key in REVIEW_FIELDS}
        self.advance()
        self.text.responses = [negative]
        self.pack = self.service.advance(self.pack)
        self.assertEqual(self.service.status(self.pack)['status'], 'pending')
        self.advance()
        self.text.responses = [negative]
        self.advance()
        record = self.pack['_route_preparation']['dialogue'][0]
        self.assertEqual(record['source'], 'checked_fallback')
        self.assertEqual(record['fallback_reason'], 'content_validation')
        self.assertNotIn('review', record)
        self.assertNotIn('draft', record)
        self.assertEqual(self.pack['legs'][0]['lines'][1:], original['legs'][0]['lines'])
        self.assertEqual(self.pack['legs'][0]['lines'][0]['text'], 'Спасибо за помощь.')
        self.assertEqual(len(self.text.requests), 4)
        self.finish()
        self.assertEqual(len(self.text.requests), 4)

    def test_transport_failures_never_silently_choose_authored_fallback(self):
        self.text.responses = [TimeoutError('provider timed out')] * 3
        current = self.pack
        for _ in range(3):
            current = self.service.advance(current)
            self.assertEqual(self.service.status(current)['status'], 'failed')
        record = current['_route_preparation']['dialogue'][0]
        self.assertNotIn('approved', record)
        self.assertNotIn('source', record)
        self.assertEqual(current['legs'], self.pack['legs'])

    def test_failed_generation_has_a_bounded_retry_limit(self):
        current = self.pack
        self.text.responses = [ValueError('provider failed')] * 4
        for _ in range(5):
            current = self.service.advance(current)
        self.assertEqual(len(self.text.requests), 3)
        self.assertIn('Start a new delivery', current['_route_preparation']['error'])

    def test_mutated_checked_direction_stops_before_provider_calls(self):
        self.pack['legs'][0]['lines'][0]['text'] = 'Поверни направо.'
        with self.assertRaises(PreparationFailure):
            self.service.advance(self.pack)
        self.assertEqual(self.text.requests, [])

    def test_planning_never_initializes_a_lazy_provider_or_requires_a_key(self):
        from utils.lazy import LazyService
        def forbidden():
            self.fail('Planning must not initialize the provider')
        config = {**self.config, 'OPENAI_MODEL_FLASHCARDS': 'openai/configured-test-model', 'OPENAI_API_KEY': ''}
        service = RoutePreparationService(self.db, self.store, LazyService('OpenAIService', forbidden),
                                          self.speech, config, static_audio_root=self.root / 'static')
        prepared = service.plan(pack(), scope='owner')
        self.assertEqual(prepared['_route_preparation']['model'], 'configured-test-model')
        failed = service.advance(prepared)
        self.assertIn('OpenAI API key', failed['_route_preparation']['error'])

    def test_recording_progress_does_not_show_complete_before_audio_is_ready(self):
        self.advance()
        self.advance()
        progress = self.service.status(self.pack)
        self.assertLess(progress['ready'], progress['total'])
        self.advance()
        self.assertGreater(self.service.status(self.pack)['ready'], progress['ready'])
        self.finish()
        progress = self.service.status(self.pack)
        self.assertEqual(progress['ready'], progress['total'])

    def test_real_composed_pack_keeps_checked_phrases_and_validates_after_preparation(self):
        from services.route_world import build_world
        from services.route_mission import build_mission, validate_mission
        original = build_mission(build_world('preparation-test-town'), 'preparation-test-delivery')
        self.pack = self.service.plan(original, scope='profile-a')
        for _ in range(70):
            if self.service.status(self.pack)['status'] == 'ready':
                break
            self.advance()
        self.assertEqual(self.service.status(self.pack)['status'], 'ready')
        validate_mission(self.pack)
        self.assertEqual(len(self.text.requests), 2 * len(original['legs']))
        self.assertEqual(self.pack['map'], original['map'])
        self.assertEqual(self.pack['mission_facts'], original['mission_facts'])
        for before, after in zip(original['legs'], self.pack['legs']):
            self.assertEqual([item['text'] for item in before['lines']],
                             [item['text'] for item in after['lines'][1:]])

    def test_prepared_static_recording_is_reused_only_for_exact_voice_text_and_model(self):
        self.advance()
        self.advance()
        speaker, first = next(spoken_lines(self.pack))
        folder = self.service.static_audio_root
        folder.mkdir()
        (folder / (first['id'] + '.mp3')).write_bytes(b'prepared-media')
        (folder / 'manifest.json').write_text(json.dumps({
            'provider': 'elevenlabs', 'model': 'saved-model', 'speakers': {speaker: 'voice-a'},
            'clips': {first['id']: {'speaker': speaker, 'text': first['text']}}}))
        self.advance()
        self.assertNotEqual(self.speech.calls[0][0], first['text'])
        wrong = json.loads((folder / 'manifest.json').read_text())
        wrong['model'] = 'old-model'
        (folder / 'manifest.json').write_text(json.dumps(wrong))
        self.advance()
        self.assertEqual(self.speech.calls[-1][0], first['text'])


if __name__ == '__main__':
    unittest.main()
