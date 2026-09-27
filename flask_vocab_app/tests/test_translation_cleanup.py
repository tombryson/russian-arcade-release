"""Translation direction, persistence, provider failures and reward integrity."""
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
import openai

from repositories.translation_repository import TranslationRepository, TranslationConflict
from services.sentence_service import SentenceService, TranslationUnavailable
from tests.support import isolated_app
from tests.test_activity_cleanup import Document


class TranslationCleanupTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock(spec=SentenceService)
        self.app = isolated_app(self, {'SentenceService': self.service})
        self.repository = TranslationRepository(self.app.config['DB_PATH'])
        self.id, _ = self.repository.save_content('Кот спит дома.', 'The cat is sleeping at home.', 'home', 1)
        self.client = self.app.test_client()
        # These exercise behavior tests submit as the explicitly selected learner.
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']
        self.headers = {'Accept': 'application/json'}
        self.assessment = {'score': 3, 'strength': 'The meaning is clear.', 'next_step': 'Check the verb ending.', 'example': 'Кот спит дома.'}
        self.service.assess_translation.return_value = self.assessment
        self.service.get_sentence.return_value = {'sentence': 'Мы идём в школу.', 'english': 'We are going to school.'}
        self.url = f'/sentences/practice/{self.id}'

    def submit(self, kind='assess', answer='Кот спит дома.', revision=0, headers=None, **extra):
        return self.client.post('/sentence/' + kind, data={'sentence_id': self.id, 'user_response': answer,
            'revision': revision, **extra}, headers=self.headers if headers is None else headers)

    def count(self, table):
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def selected_options(self, html, select_id):
        options = html.split(f'id="{select_id}"', 1)[1].split('</select>', 1)[0]
        return [attrs['value'] for tag, attrs in Document(options).elements
                if tag == 'option' and 'selected' in attrs]

    def test_setup_and_saved_practice_work_without_ai_and_hide_reference(self):
        for headers in ({}, {'HX-Request': 'true', 'HX-Target': 'mainContent'}):
            response = self.client.get(self.url, headers=headers)
            html = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn('The cat is sleeping at home.', html)
            self.assertNotIn('Кот спит дома.', html)
            document = Document(html)
            self.assertEqual(document.answers['translation-answer'], '')
            ids = [attrs['id'] for _, attrs in document.elements if 'id' in attrs]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual('<!DOCTYPE html>' in html, not headers)
        self.service.assess_translation.assert_not_called()
        self.service.get_sentence.assert_not_called()
        self.assertEqual(self.client.get('/sentences/practice/999999').status_code, 404)

    def test_draft_round_trip_preserves_punctuation_and_has_no_reward(self):
        text = 'Он сказал: "Привет!"\n</textarea><script>bad()</script>'
        result = self.submit('save', text)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['revision'], 1)
        self.assertEqual(result.json['state'], 'Draft saved')
        html = self.client.get(self.url).get_data(as_text=True)
        self.assertEqual(Document(html).answers['translation-answer'], text)
        self.assertNotIn('<script>bad()', html)
        self.assertEqual(self.count('translation_attempts'), 0)
        self.assertEqual(self.count('reward_events'), 0)
        self.service.assess_translation.assert_not_called()

    def test_check_uses_server_prompt_and_level_records_answer_and_awards_once(self):
        result = self.submit(answer='Мой вариант.', sentence='forged', english='forged', score=4, difficulty=5)
        self.assertEqual(result.status_code, 200)
        self.service.assess_translation.assert_called_once_with('Кот спит дома.', 'The cat is sleeping at home.', 'Мой вариант.', 'en')
        self.service.generate_audio.assert_not_called()
        first = self.repository.load(self.id)['attempts'][0]
        self.assertEqual(first['response'], 'Мой вариант.')
        self.assertEqual((first['coins_earned'], first['elo_change']), (3, 0))
        self.assertEqual(self.submit(revision=1).status_code, 200)
        current = self.repository.load(self.id)
        self.assertEqual(len(current['attempts']), 2)
        self.assertEqual(current['attempts'][0]['coins_earned'], 0)
        self.assertTrue(current['attempts'][0]['already_rewarded'])
        self.assertEqual(self.count('reward_events'), 0)
        self.assertEqual(self.count('progression_entries'), 1)
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT lingocoins FROM users WHERE user_id=1').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT score FROM sentences WHERE id=?', (self.id,)).fetchone()[0], 0)

    def test_old_reward_ledger_is_preserved_separately_from_new_participation(self):
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            conn.execute('UPDATE users SET lingocoins=70,elo_rating=1100 WHERE user_id=1')
            conn.execute('INSERT INTO reward_events(user_id,reward_key,coins,elo_change,legacy) VALUES (1,?,0,0,1)', (f'sentence:{self.id}',))
        self.assertEqual(self.repository.load(self.id)['attempts'], [])
        self.submit()
        self.assertEqual(self.repository.load(self.id)['attempts'][0]['coins_earned'], 3)
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT lingocoins,elo_rating FROM users WHERE user_id=1').fetchone(), (70,1100))
            self.assertEqual(conn.execute('SELECT coins,elo_change FROM reward_events').fetchall(), [(0,0)])

    def test_check_transaction_rolls_back_draft_attempt_and_reward_together(self):
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            conn.execute("CREATE TRIGGER fail_attempt BEFORE INSERT ON translation_attempts BEGIN SELECT RAISE(ABORT,'test failure'); END")
        result = self.submit()
        self.assertEqual(result.status_code, 503)
        for table in ('translation_attempts', 'translation_drafts', 'reward_events', 'progression_events', 'progression_entries'):
            self.assertEqual(self.count(table), 0)
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT lingocoins,elo_rating FROM users WHERE user_id=1').fetchone(), (0,1000))
        self.assertEqual(self.repository.load(self.id)['revision'], 0)

    def test_provider_failure_has_no_score_and_native_form_retains_answer(self):
        self.service.assess_translation.side_effect = TranslationUnavailable('private details')
        for headers in (self.headers, {}):
            response = self.submit(answer='Сохраните это.', headers=headers)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private details', response.get_data(as_text=True))
            if not headers:
                self.assertEqual(Document(response.get_data(as_text=True)).answers['translation-answer'], 'Сохраните это.')
        self.assertEqual(self.count('translation_attempts'), 0)
        self.assertEqual(self.count('reward_events'), 0)
        self.assertEqual(self.submit('save', 'Сохраните это.', headers={}).status_code, 303)

    def test_stale_and_in_flight_requests_cannot_overwrite(self):
        self.submit('save', 'Первый черновик.')
        self.assertEqual(self.submit(revision=0).status_code, 409)
        self.service.assess_translation.assert_not_called()
        def racing(*args):
            self.repository.save_draft(self.id, 'Новый черновик.', 1)
            return self.assessment
        self.service.assess_translation.side_effect = racing
        self.assertEqual(self.submit(revision=1).status_code, 409)
        self.assertEqual(self.repository.load(self.id)['draft'], 'Новый черновик.')
        self.assertEqual(self.count('reward_events'), 0)

    def test_invalid_or_blank_input_never_reaches_ai(self):
        for answer in (' ', 'я' * 1001):
            self.assertEqual(self.submit(answer=answer).status_code, 400)
        self.assertEqual(self.submit(revision='bad').status_code, 409)
        self.assertEqual(self.submit('save', '').status_code, 200)
        self.service.assess_translation.assert_not_called()

    def test_generation_is_explicit_and_saved_and_has_no_silent_fallback(self):
        self.assertEqual(self.client.get('/sentence/generate?topic=home&difficulty=1').status_code, 303)
        self.service.get_sentence.assert_not_called()
        result = self.client.post('/sentence/generate', data={'topic':'school','difficulty':1}, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json['url'].startswith('/sentences/practice/'))
        self.assertEqual(self.client.get(result.json['url']).status_code, 200)
        before = self.count('sentences')
        self.service.get_sentence.side_effect = TranslationUnavailable('provider unavailable')
        self.assertEqual(self.client.post('/sentence/generate', data={'topic':'home','difficulty':1}, headers=self.headers).status_code, 503)
        self.assertEqual(self.count('sentences'), before)
        self.assertEqual(self.count('reward_events'), 0)

    def test_audio_is_optional_and_failure_leaves_saved_check(self):
        self.assertEqual(self.client.post(f'/sentence/audio/{self.id}').status_code, 400)
        self.submit()
        self.service.generate_audio.return_value = ''
        self.assertEqual(self.client.post(f'/sentence/audio/{self.id}').status_code, 503)
        self.assertEqual(self.count('translation_attempts'), 1)
        self.service.generate_audio.return_value = '/static/media/test.mp3'
        response = self.client.post(f'/sentence/audio/{self.id}')
        self.assertIn('/static/media/test.mp3', response.json['html'])
        self.service.generate_audio.reset_mock()
        self.client.post(f'/sentence/audio/{self.id}')
        self.service.generate_audio.assert_not_called()
        self.assertEqual(self.count('reward_events'), 0)
        self.assertEqual(self.count('progression_entries'), 1)

    def test_library_adds_bilingual_content_without_ai_or_rewards(self):
        data = {'sentence':'Мы дома.','english':'We are at home.','topic':'home','difficulty':1}
        for _ in range(2):
            result = self.client.post('/sentence/add', data=data, headers=self.headers)
            self.assertEqual(result.status_code, 200)
        self.assertEqual(self.count('sentences'), 2)
        self.assertEqual(self.count('reward_events'), 0)
        self.assertEqual(self.count('progression_entries'), 0)
        self.service.translate_for_library.assert_not_called()
        saved = next(item for item in self.repository.list_saved() if item['sentence'] == data['sentence'])
        self.assertEqual(result.json['url'], f'/sentences/saved#sentence-{saved["id"]}')
        self.assertIn('Мы дома.', self.client.get(result.json['url']).get_data(as_text=True))
        native = self.client.post('/sentence/add', data=data)
        self.assertEqual(native.status_code, 303)
        self.assertEqual(native.location, result.json['url'])
        self.assertEqual(self.count('sentences'), 2)
        # Existing detail bookmarks remain usable after add returns to the library.
        self.assertEqual(self.client.get(f'/sentences/saved/{saved["id"]}').status_code, 200)
        self.assertEqual(self.service.mock_calls, [])

    def test_library_add_failure_preserves_text_topic_and_level(self):
        before = self.count('sentences')
        data = {'sentence': '', 'english': 'Please keep <this> text.', 'topic': 'home', 'difficulty': 4}
        response = self.client.post('/sentence/add', data=data)
        self.assertEqual(response.status_code, 400)
        html = response.get_data(as_text=True)
        document = Document(html)
        self.assertEqual(document.answers['add-russian'], data['sentence'])
        self.assertEqual(document.answers['add-english'], data['english'])
        self.assertEqual(self.selected_options(html, 'add-topic'), ['home'])
        self.assertEqual(self.selected_options(html, 'add-level'), ['4'])
        disclosure = next(attrs for tag, attrs in document.elements
                          if tag == 'details' and 'sentence-store-add' in attrs.get('class', '').split())
        self.assertIn('open', disclosure)
        self.assertEqual(self.count('sentences'), before)
        self.assertEqual(self.service.mock_calls, [])

    def test_library_topic_filter_and_russian_interface(self):
        self.repository.save_content('Мы в школе.', 'We are at school.', 'school', 2)
        exported = self.client.get('/sentences/saved?fetch_all=true', headers=self.headers).json
        self.assertIn('school', exported['topics'])
        self.assertTrue(all(isinstance(topic, str) for topic in exported['topics']))
        html = self.client.get('/sentences/saved?topic=school').get_data(as_text=True)
        self.assertIn('We are at school.', html)
        self.assertNotIn('The cat is sleeping at home.', html)
        with self.client.session_transaction() as session:
            session['ui_lang'] = 'ru'
        html = self.client.get(self.url).get_data(as_text=True)
        self.assertIn('Проверить перевод', html)
        self.assertIn('The cat is sleeping at home.', html)
        self.submit()
        self.assertEqual(self.service.assess_translation.call_args.args[-1], 'ru')
        self.assertEqual(self.repository.load(self.id)['attempts'][0]['ui_language'], 'ru')

    def test_library_exposes_both_languages_and_existing_audio_without_a_check(self):
        self.repository.save_audio(self.id, '/static/media/saved-sentence.mp3')
        before = self.repository.load(self.id)
        for headers in ({}, {'HX-Request': 'true', 'HX-Target': 'mainContent'}):
            response = self.client.get('/sentences/saved', headers=headers)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            table = html.split('<table class="translation-library-table">', 1)[1].split('</table>', 1)[0]
            self.assertIn('Кот спит дома.', table)
            self.assertIn('The cat is sleeping at home.', table)
            self.assertIn('/static/media/saved-sentence.mp3', table)
            self.assertNotIn('<details', table)
            audio = [attrs for tag, attrs in Document(html).elements if tag == 'audio']
            self.assertEqual(len(audio), 1)
            self.assertIn('controls', audio[0])
            self.assertEqual(audio[0]['preload'], 'none')
            self.assertEqual(audio[0]['aria-label'], 'Listen to sentence 1')
        self.assertEqual(self.repository.load(self.id), before)
        self.assertEqual(self.count('translation_attempts'), 0)
        self.assertEqual(self.count('progression_entries'), 0)
        self.assertEqual(self.service.mock_calls, [])
        # Browsing a reference must not reveal the answer in a fresh practice session.
        practice = self.client.get(self.url).get_data(as_text=True)
        self.assertNotIn('Кот спит дома.', practice)
        self.assertNotIn('/static/media/saved-sentence.mp3', practice)

    def test_library_lists_every_saved_sentence_and_distinguishes_missing_audio(self):
        ids = [self.id]
        for number in range(35):
            sentence_id, _ = self.repository.save_content(f'Пример {number}.', f'Example {number}.', 'general', 2)
            ids.append(sentence_id)
        html = self.client.get('/sentences/saved').get_data(as_text=True)
        document = Document(html)
        rows = [attrs for tag, attrs in document.elements if tag == 'tr' and 'data-sentence-id' in attrs]
        self.assertCountEqual([attrs['data-sentence-id'] for attrs in rows], [str(sentence_id) for sentence_id in ids])
        self.assertCountEqual([attrs['id'] for attrs in rows], [f'sentence-{sentence_id}' for sentence_id in ids])
        practice_links = [attrs['href'] for tag, attrs in document.elements
                          if tag == 'a' and attrs.get('href', '').startswith('/sentences/practice/')]
        self.assertEqual(practice_links, [])
        self.assertIn('36 sentences', html)
        self.assertIn('No audio', html)
        self.assertNotIn('<audio', html)
        self.assertNotIn('translation-library-meta', html)
        self.assertNotIn('translation-library-profile', html)
        library = html.split('<main ', 1)[1].split('</main>', 1)[0]
        self.assertNotIn('Profile:', library)
        self.assertNotIn('Switch profile', library)

    def test_library_searches_both_languages_combines_topic_and_can_show_all_again(self):
        self.repository.save_content('Мы в школе.', 'We are at school.', 'school', 2)
        self.repository.save_content('Кот в школе.', 'The cat is at school.', 'school', 2)
        for query in ('КОТ', 'CAT'):
            html = self.client.get('/sentences/saved', query_string={'q': query, 'topic': 'school'}).get_data(as_text=True)
            self.assertIn('Кот в школе.', html)
            self.assertNotIn('Кот спит дома.', html)
            self.assertNotIn('Мы в школе.', html)
            self.assertIn('Showing 1 of 3 sentences', html)
            self.assertIn('Show all', html)
            self.assertEqual(Document(html).element('library-search')['value'], query)
        no_matches = self.client.get('/sentences/saved?q=unmatched').get_data(as_text=True)
        self.assertIn('Showing 0 of 3 sentences', no_matches)
        self.assertIn('No sentences found.', no_matches)
        self.assertIn('3 sentences', self.client.get('/sentences/saved').get_data(as_text=True))
        # Preserve the existing explicit all-records JSON endpoint.
        exported = self.client.get('/sentences/saved?fetch_all=true&q=unmatched&topic=school', headers=self.headers)
        self.assertEqual(len(exported.json['sentences']), 3)

    def test_library_level_filter_combines_with_topic_and_search(self):
        self.repository.save_content('Кот в школе.', 'The cat is at school.', 'school', 2)
        target_id, _ = self.repository.save_content('Кот учится в школе.', 'The cat studies at school.', 'school', 3)
        self.repository.save_content('Мы в школе.', 'We are at school.', 'school', 3)
        self.repository.save_content('Кот отдыхает дома.', 'The cat rests at home.', 'home', 3)
        before = self.repository.list_saved()
        for query in ('КОТ', 'CAT'):
            html = self.client.get('/sentences/saved', query_string={
                'level': 3, 'topic': 'school', 'q': query,
            }).get_data(as_text=True)
            rows = [attrs['data-sentence-id'] for tag, attrs in Document(html).elements
                    if tag == 'tr' and 'data-sentence-id' in attrs]
            self.assertEqual(rows, [str(target_id)])
            self.assertIn('Showing 1 of 5 sentences', html)
            self.assertEqual(self.selected_options(html, 'library-level'), ['3'])
            self.assertEqual(self.selected_options(html, 'library-topic'), ['school'])
        # Export stays complete regardless of filters used by the reference view.
        exported = self.client.get('/sentences/saved?fetch_all=true&level=3&topic=school&q=CAT', headers=self.headers)
        self.assertEqual(len(exported.json['sentences']), 5)
        self.assertEqual(self.repository.list_saved(), before)
        self.assertEqual(self.service.mock_calls, [])

    def test_library_invalid_level_is_ignored_without_losing_other_filters(self):
        target_id, _ = self.repository.save_content('Кот в школе.', 'The cat is at school.', 'school', 2)
        self.repository.save_content('Мы в школе.', 'We are at school.', 'school', 3)
        for level in ('', 'bad', '0', '7', '-1', '2.5'):
            with self.subTest(level=level):
                html = self.client.get('/sentences/saved', query_string={
                    'level': level, 'topic': 'school', 'q': 'CAT',
                }).get_data(as_text=True)
                document = Document(html)
                rows = [attrs['data-sentence-id'] for tag, attrs in document.elements
                        if tag == 'tr' and 'data-sentence-id' in attrs]
                self.assertEqual(rows, [str(target_id)])
                self.assertFalse(any(self.selected_options(html, 'library-level')))
                self.assertEqual(self.selected_options(html, 'library-topic'), ['school'])
                self.assertEqual(document.element('library-search')['value'], 'CAT')
        self.assertEqual(self.service.mock_calls, [])

    def test_curriculum_setup_prefills_topic_and_all_six_task_levels(self):
        html = self.client.get('/sentences?topic=law&level=C2').get_data(as_text=True)
        self.assertEqual(self.selected_options(html, 'translation-topic'), ['law'])
        self.assertEqual(self.selected_options(html, 'translation-level'), ['C2'])
        markup = html.split('id="translation-topic"', 1)[1].split('</select>', 1)[0]
        self.assertEqual(sum(tag == 'option' for tag, _ in Document(markup).elements), 52)
        html = self.client.get('/sentences?topic=shopping').get_data(as_text=True)
        self.assertEqual(self.selected_options(html, 'translation-level'), ['A2'])
        html = self.client.get('/sentences?topic=shopping&level=invalid').get_data(as_text=True)
        self.assertEqual(self.selected_options(html, 'translation-level'), ['A2'])
        self.assertNotIn('data-level-explicit="true"', html)
        self.service.get_sentence.assert_not_called()

    def test_c2_generation_and_library_filter_preserve_historical_level_storage(self):
        response = self.client.post('/sentence/generate', data={'topic': 'law', 'difficulty': 'C2'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.service.get_sentence.assert_called_once_with('law', 6)
        sentence_id = int(response.json['url'].rsplit('/', 1)[1])
        saved = self.repository.load(sentence_id)
        self.assertEqual(saved['difficulty'], 6)
        html = self.client.get('/sentences/saved?level=6').get_data(as_text=True)
        self.assertIn(saved['sentence'], html)
        self.assertNotIn('Кот спит дома.', html)
        self.assertEqual(self.selected_options(html, 'library-level'), ['6'])
        self.assertEqual(self.repository.load(self.id)['difficulty'], 1)

    def test_revisiting_same_content_at_another_level_preserves_the_earlier_task(self):
        # A provider can return an existing sentence. Its earlier difficulty
        # must not silently replace the task level the learner just selected.
        self.repository.save_draft(self.id, 'Мой черновик.', 0)
        sentence_id, created = self.repository.save_content(
            'Кот спит дома.', 'The cat is sleeping at home.', 'home', 2)
        self.assertTrue(created)
        self.assertNotEqual(sentence_id, self.id)
        self.assertEqual(self.repository.load(sentence_id)['difficulty'], 2)
        self.assertEqual(self.repository.load(self.id)['difficulty'], 1)
        self.assertEqual(self.repository.load(self.id)['draft'], 'Мой черновик.')

    def test_library_escapes_saved_text_and_localizes_new_controls(self):
        self.repository.save_content('Текст <script>bad()</script>.', 'Text <img src=x onerror=bad()>.', 'home', 1)
        with self.client.session_transaction() as session:
            session['ui_lang'] = 'ru'
        html = self.client.get('/sentences/saved', query_string={'q': '<script>'}).get_data(as_text=True)
        self.assertNotIn('<script>bad()', html)
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;script&gt;bad()', html)
        self.assertIn('Поиск предложений', html)
        self.assertIn('Показано предложений: 1 из 2', html)
        self.assertNotIn('Сменить профиль', html)

    def test_library_and_detail_select_saved_sentences_navigation(self):
        self.client.set_cookie('ui_navigation', 'sidebar')
        with self.client.session_transaction() as session:
            session.pop('ui_navigation', None)
        responses = [self.client.get('/sentences/saved'),
                     self.client.get(f'/sentences/saved/{self.id}'),
                     self.client.post('/sentence/add', data={'sentence': '', 'difficulty': 1})]
        self.assertEqual([response.status_code for response in responses], [200, 200, 400])
        for response in responses:
            links = [attrs for tag, attrs in Document(response.get_data(as_text=True)).elements
                     if tag == 'a' and attrs.get('aria-current') == 'page']
            self.assertTrue(any(link.get('href') == '/sentences/saved' for link in links))
            self.assertFalse(any(link.get('href') in ('/sentences', '/#activities') for link in links))
        practice_links = [attrs for tag, attrs in Document(self.client.get(self.url).get_data(as_text=True)).elements
                          if tag == 'a' and attrs.get('aria-current') == 'page']
        self.assertTrue(any(link.get('href') == '/sentences' for link in practice_links))

    def test_household_library_has_no_unavailable_personal_profile_link(self):
        with self.client.session_transaction() as session:
            access = session['personal_access_id']
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='test-household-secret-at-least-32-characters')
        with self.client.session_transaction() as session:
            session['household_access_id'] = access
        response = self.client.get('/sentences/saved')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('href="/post/profiles"', html)
        self.assertNotIn('Switch profile', html)


class TranslationProviderTests(unittest.TestCase):
    def setUp(self):
        self.service = SentenceService.__new__(SentenceService)
        self.service.client = Mock()
        self.good = {'score':4, 'strength':'Clear meaning.', 'next_step':'Try another sentence.', 'example':'Кот дома.'}
        self.output(self.good)

    def output(self, value, status='completed'):
        self.service.client.responses.create.return_value = SimpleNamespace(status=status, output_text=json.dumps(value))

    def test_direction_and_exact_text_reach_the_provider(self):
        answer = 'Он сказал: "Привет!"\nИ ушёл.'
        self.service.assess_translation('Кот дома.', 'The cat is at home.', answer, 'en')
        kwargs = self.service.client.responses.create.call_args.kwargs
        self.assertIn('English-to-Russian', kwargs['input'][0]['content'])
        self.assertIn('accept', kwargs['input'][0]['content'].lower())
        self.assertEqual(json.loads(kwargs['input'][1]['content'])['russian_answer'], answer)
        self.assertEqual(kwargs['reasoning'], {'effort':'low'})
        self.assertFalse(kwargs['store'])
        self.assertNotIn('temperature', kwargs)

    def test_c2_generation_uses_topic_objectives_and_legacy_levels_still_work(self):
        self.output({'sentence': 'Право нуждается в толковании.', 'english': 'The law needs interpretation.',
                     'topic_id': 'law', 'language_focus': {'requirement_id': 'a1.language.neutral-word-order',
                     'english_excerpt': 'The law needs interpretation.', 'russian_excerpt': 'Право нуждается в толковании.',
                     'expectation': 'Preserve what needs interpretation, accepting natural Russian word order.'}})
        for selected, expected in ((1, 'A1'), ('5', 'C1'), (6, 'C2'), ('C2', 'C2')):
            with self.subTest(selected=selected):
                self.service.get_sentence('law', selected)
                payload = json.loads(self.service.client.responses.create.call_args.kwargs['input'][1]['content'])
                self.assertEqual(payload['level'], expected)
                self.assertEqual(payload['curriculum']['target_level'], expected)
                self.assertEqual(payload['curriculum']['topic_band'], 'C1-C2')
                self.assertTrue(payload['curriculum']['objectives'])
                self.assertTrue(payload['curriculum']['grammar_focus'])
                self.assertTrue(payload['curriculum']['activity_brief'])
        self.service.client.responses.create.reset_mock()
        for invalid in (0, 7, True, None, 'expert', 'B3'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.service.get_sentence('law', invalid)
        self.service.client.responses.create.assert_not_called()

    def test_refusal_incomplete_invalid_scores_and_empty_feedback_fail_closed(self):
        for result in [dict(self.good, score=95), dict(self.good, score=True), dict(self.good, score=-1),
                       dict(self.good, score=3.5), dict(self.good, strength=''), dict(self.good, next_step=None), []]:
            self.output(result)
            with self.assertRaises(TranslationUnavailable):
                self.service.assess_translation('Кот дома.', 'The cat is at home.', 'Кот дома.')
        self.output(self.good, status='incomplete')
        with self.assertRaises(TranslationUnavailable):
            self.service.assess_translation('Кот дома.', 'The cat is at home.', 'Кот дома.')
        self.service.client.responses.create.return_value = SimpleNamespace(status='completed', output_text='')
        with self.assertRaises(TranslationUnavailable):
            self.service.get_sentence('home', 1)

    def test_generation_never_substitutes_a_fallback_or_rewrites_a_pasted_russian_sentence(self):
        self.service.client.responses.create.side_effect = RuntimeError('offline')
        with self.assertRaises(TranslationUnavailable):
            self.service.get_sentence('home', 1)
        self.service.client.responses.create.assert_called_once()
        self.service.client.responses.create.side_effect = None
        self.output({'english':'Hello, world!'})
        self.assertEqual(self.service.translate_for_library('Привет, мир!'), 'Hello, world!')
        self.assertEqual(json.loads(self.service.client.responses.create.call_args.kwargs['input'][1]['content']), {'russian':'Привет, мир!'})

    def test_installed_sdk_serializes_strict_translation_requests(self):
        captured = []
        def handler(request):
            payload = json.loads(request.content); captured.append(payload)
            value = self.good if payload['text']['format']['name'] == 'translation_feedback' else {'sentence':'Кот дома.','english':'The cat is at home.',
                'topic_id': 'home', 'language_focus': {'requirement_id': 'a1.language.neutral-word-order',
                'english_excerpt': 'The cat is at home.', 'russian_excerpt': 'Кот дома.',
                'expectation': 'State where the cat is, accepting natural Russian word order.'}}
            return httpx.Response(200, json={'id':'resp_translation', 'object':'response','created_at':0,'model':'gpt-5-mini','status':'completed',
                'output':[{'id':'msg_translation','type':'message','role':'assistant','status':'completed',
                'content':[{'type':'output_text','text':json.dumps(value),'annotations':[]}]}]})
        self.service.client = openai.OpenAI(api_key='test-only', http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(self.service.client.close)
        pair = self.service.get_sentence('home', 1)
        self.service.assess_translation(pair['sentence'], pair['english'], 'Кот дома.')
        self.assertEqual(len(captured), 2)
        for payload in captured:
            self.assertTrue(payload['text']['format']['strict'])
            self.assertFalse(payload['store'])
