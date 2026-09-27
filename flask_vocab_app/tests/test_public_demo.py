import os
import shutil
import unittest
from unittest.mock import patch

from hosted import create_hosted_app
from public_demo import prepare_demo
from services.demo_limits import DemoLimits


class PublicDemoTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, PUBLIC_DEMO='true', FLASK_SECRET_KEY='synthetic-test-secret-' * 3,
                         HOSTED_HOSTNAME='russian-arcade.fly.dev')
        env.start()
        self.addCleanup(env.stop)
        root = prepare_demo()
        self.addCleanup(shutil.rmtree, root)
        self.app = create_hosted_app()
        self.a, self.b = self.app.test_client(), self.app.test_client()
        self.base = 'https://russian-arcade.fly.dev'
        network = patch('socket.socket.connect', side_effect=AssertionError('Demo must not use providers'))
        network.start()
        self.addCleanup(network.stop)

    def state(self, client):
        return client.get('/api/v1/user-session', base_url=self.base).json

    def test_profiles_are_isolated_and_cannot_be_selected_by_other_visitors(self):
        a, b = self.state(self.a), self.state(self.b)
        self.assertNotEqual(a['profile']['id'], b['profile']['id'])
        for endpoint in ('/api/v1/user-session', '/api/v1/household'):
            state = self.a.get(endpoint, base_url=self.base).json
            self.assertEqual([p['id'] for p in state['profiles']], [a['profile']['id']])
        result = self.a.post('/api/v1/user-session/select', base_url=self.base,
                             json={'profile_id': b['profile']['id']}, headers={'X-CSRF-Token': a['csrf_token']})
        self.assertEqual(result.status_code, 403)

    def test_profile_control_without_trial_shows_public_preview_information(self):
        self.assertNotIn('hosted_trial', self.app.extensions)
        page = self.a.get('/post/profiles', base_url=self.base)
        self.assertEqual(page.status_code, 200)
        self.assertIn('<h1>Demo profile</h1>', page.text)
        self.assertIn('temporary profile', page.text.lower())
        self.assertIn('sign-in', page.text.lower())
        self.assertIn('not enabled', page.text.lower())
        self.assertNotIn('href="/trial/sign-in"', page.text)
        self.assertIn('href="/#home"', page.text)
        account = self.a.get('/trial/account', base_url=self.base)
        self.assertEqual(account.status_code, 200)
        self.assertIn('<h1>Demo profile</h1>', account.text)
        self.assertNotIn('href="/trial/sign-in"', account.text)

    def test_sample_pages_work_and_provider_upload_edit_routes_are_blocked(self):
        for path in ('/', '/vocab', '/curriculum', '/api/v1/flashcards', '/api/v1/first-steps', '/api/v1/games'):
            self.assertEqual(self.a.get(path, base_url=self.base).status_code, 200, path)
        for path in ('/tools/anki/', '/sentence/generate', '/sync_vocab', '/vocab?source=cloud', '/sync/preview'):
            self.assertEqual(self.a.get(path, base_url=self.base).status_code, 403, path)
        state = self.state(self.a)
        for path in ('/api/v1/user-session/profiles', '/api/v1/live-conversations', '/lessons/create',
                     '/api/v1/card-generation/batches', '/api/v1/card-generation/batches/example/next',
                     '/api/v1/live-conversations/example/connect', '/api/v1/flashcards/example/media',
                     '/api/v1/course/checkpoints/example/vocabulary',
                     '/api/v1/course/checkpoints/example/writing',
                     '/api/v1/course/checkpoints/example/flashcards',
                     '/api/v1/games/example/start'):
            self.assertEqual(self.a.post(path, base_url=self.base, json={},
                          headers={'X-CSRF-Token': state['csrf_token']}).status_code, 403, path)

    def test_enabled_guest_demo_offers_direct_access_without_signin_requirement(self):
        self.app.config.update(HOSTED_GUEST_DEMO_ENABLED=True, HOSTED_ACCOUNTS_ENABLED=True)
        page = self.a.get('/', base_url=self.base)
        self.assertIn('href="/demo"', page.text)
        self.assertIn('No sign-in needed', page.text)
        blocked = self.a.post('/api/v1/live-conversations', base_url=self.base, json={})
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json['error']['demo_url'], '/demo')
        self.assertIn('No sign-in is needed', blocked.json['error']['message'])

    def test_shop_is_visible_but_purchases_are_disabled(self):
        from repositories.learning_repository import transaction
        catalogue = self.a.get('/api/v1/games', base_url=self.base).json
        self.assertFalse(catalogue['shop']['enabled'])
        self.assertTrue(all(not game['purchase']['can_purchase'] for game in catalogue['games']))
        response = self.a.post('/api/v1/games/scene-builder/purchase', base_url=self.base,
                               headers={'X-CSRF-Token': catalogue['csrf_token']},
                               json={'request_id': 'demo-purchase', 'expected_price': 25})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json['error']['code'], 'demo_unavailable')
        with transaction(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_purchases').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_access').fetchone()[0], 0)

    def test_unit_typed_forms_use_owned_saved_practice_without_a_provider(self):
        state = self.state(self.a)
        path = '/curriculum/units/location-destination-v1'
        page = self.a.get(path, base_url=self.base)
        self.assertEqual(page.status_code, 200)
        self.assertIn(path + '/forms', page.text)
        response = self.a.post(path + '/forms', base_url=self.base,
                               data={'profile_id': state['profile']['id'], 'request_id': 'demo-forms'},
                               headers={'X-CSRF-Token': state['csrf_token']})
        self.assertEqual(response.status_code, 303, response.text)
        session_id = response.location.rsplit('/', 1)[1]
        url = '/api/v1/learning-sessions/' + session_id
        saved = self.a.get(url, base_url=self.base).json
        self.assertEqual(saved['item']['type'], 'controlled_text')
        checked = self.a.post(url + '/attempts', base_url=self.base,
                              json={'submission_id': 'typed', 'expected_revision': 0,
                                    'item_id': saved['item']['id'], 'answer': {'text': 'ШКОЛУ.'}},
                              headers={'X-CSRF-Token': state['csrf_token']})
        self.assertEqual(checked.status_code, 200, checked.text)
        self.assertEqual(checked.json['attempts'][0]['answer'], {'text': 'ШКОЛУ.'})
        self.assertEqual(checked.json['attempts'][0]['outcome'], 'correct')
        self.state(self.b)
        self.assertEqual(self.b.get(url, base_url=self.base).status_code, 404)

    @patch('utils.lazy.LazyService._get', side_effect=AssertionError('Course demo must not resolve providers'))
    def test_course_checkpoints_are_playable_owned_and_provider_free(self, provider):
        import json
        from repositories.learning_repository import transaction

        response = self.a.get('/api/v1/course', base_url=self.base)
        self.assertEqual(response.status_code, 200, response.text)
        course = response.json
        headers = {'X-CSRF-Token': course['csrf_token']}
        chapter = course['chapters'][0]
        self.assertEqual(chapter['status'], 'practice')
        start_path = '/api/v1/course/chapters/' + chapter['id'] + '/checkpoint'
        self.assertEqual(self.a.post(start_path, base_url=self.base,
            json={'request_id': 'without-csrf', 'challenge': True}).status_code, 403)

        def post(path, data):
            result = self.a.post(path, base_url=self.base, headers=headers, json=data)
            self.assertEqual(result.status_code, 200, result.text)
            return result.json

        attempt = post(start_path, {'request_id': 'demo-course', 'challenge': True})
        path = '/api/v1/course/checkpoints/' + attempt['id']
        self.assertNotIn('result', attempt)
        self.assertNotIn('transcript', attempt['listening'])
        self.assertEqual(self.a.get(path, base_url=self.base).json, attempt)
        with self.a.get(attempt['listening']['audio_url'], base_url=self.base) as audio:
            self.assertEqual(audio.status_code, 200)
            self.assertEqual(audio.mimetype, 'audio/mpeg')
            self.assertGreater(len(audio.data), 0)

        other_headers = {'X-CSRF-Token': self.state(self.b)['csrf_token']}
        self.assertEqual(self.b.get(path, base_url=self.base).status_code, 404)
        for operation, data in [('listened', {}), ('support', {'kind': 'transcript'}),
                                ('answer', {'answers': {}, 'submission_id': 'other-course'})]:
            denied = self.b.post(path + '/' + operation, base_url=self.base, headers=other_headers, json=data)
            self.assertEqual(denied.status_code, 404, denied.text)

        listened = post(path + '/listened', {})
        self.assertTrue(listened['listened'])
        hint = post(path + '/support', {'kind': 'hint', 'question_id': attempt['questions'][0]['id']})
        self.assertTrue(hint['support_used'])
        self.assertIn('hint', hint['questions'][0])
        self.assertNotIn('hint', hint['questions'][1])
        self.assertNotIn('transcript', hint['listening'])
        supported = post(path + '/support', {'kind': 'transcript'})
        self.assertIn('transcript', supported['listening'])
        self.assertNotIn('result', supported)
        self.assertNotIn('selected_answer', json.dumps(supported))

        for number in (1, 2):
            with transaction(self.app.config['DB_PATH']) as conn:
                frozen = json.loads(conn.execute('SELECT frozen_json FROM course_checkpoint_attempts WHERE id=?',
                                                 (attempt['id'],)).fetchone()[0])
            answers = {item['id']: item['answer'] for item in frozen['variant']['questions']}
            result = post(path + '/answer', {'answers': answers, 'submission_id': f'demo-course-{number}'})
            self.assertEqual(result['result']['score'], result['result']['total'])
            self.assertTrue(result['result']['essential_passed'])
            self.assertEqual(result['vocabulary'], [])
            self.assertFalse(result['writing_available'])
            self.assertFalse(result['flashcards_available'])
            self.assertEqual({item['question_id']: item['selected_answer'] for item in result['result']['feedback']}, answers)
            self.assertEqual(self.a.get(path, base_url=self.base).json, result)
            if number == 1:
                self.assertEqual(result['status'], 'retry')
                self.assertFalse(result['result']['passed'])
                retry = post(start_path, {'request_id': 'demo-course-retry', 'challenge': True})
                self.assertNotEqual(retry['letter'], attempt['letter'])
                self.assertFalse(retry['support_used'])
                attempt = retry
                path = '/api/v1/course/checkpoints/' + attempt['id']
                post(path + '/listened', {})
            else:
                self.assertEqual(result['status'], 'passed')
                self.assertTrue(result['result']['passed'])
                self.assertEqual(result['course']['chapters'][0]['status'], 'passed')
                self.assertEqual(result['course']['current_chapter_id'], course['chapters'][1]['id'])
        provider.assert_not_called()

    @patch('utils.lazy.LazyService._get', side_effect=AssertionError('Course preparation must not resolve providers'))
    def test_course_preparation_is_playable_owned_and_provider_free(self, provider):
        import json
        from repositories.learning_repository import transaction

        self.app.config['COURSE_DEFAULT_RELEASE'] = 'a1-journey-v2'
        visitor = self.state(self.a)
        headers = {'X-CSRF-Token': visitor['csrf_token']}
        start_path = '/api/v1/course/chapters/home/practice'
        request_body = {'request_id': 'demo-preparation', 'release_id': 'a1-journey-v2'}
        denied = self.a.post(start_path, base_url=self.base, json=request_body)
        self.assertEqual(denied.status_code, 403)

        def post(path, body):
            response = self.a.post(path, base_url=self.base, headers=headers, json=body)
            self.assertEqual(response.status_code, 200, response.text)
            return response.json

        state = post(start_path, request_body)
        self.assertEqual(state, post(start_path, request_body))
        path = '/api/v1/course/practice/' + state['id']
        self.assertEqual(self.a.get(path, base_url=self.base).json, state)
        self.assertIsNone(state['current_item']['question'])
        self.assertEqual(self.b.get(path, base_url=self.base).status_code, 404)
        first = state['current_item']['id']
        other_headers = {'X-CSRF-Token': self.state(self.b)['csrf_token']}
        for action in ('learn', 'hint', 'transcript', 'listened', 'answer', 'next'):
            body = {'item_id': first, 'request_id': 'other-' + action}
            if action == 'answer':
                body['choice_id'] = 'a'
            denied = self.b.post(path + '/' + action, base_url=self.base, headers=other_headers, json=body)
            self.assertEqual(denied.status_code, 404, denied.text)
        denied = self.a.post(path + '/learn', base_url=self.base,
                             json={'item_id': first, 'request_id': 'missing-csrf'})
        self.assertEqual(denied.status_code, 403)
        with transaction(self.app.config['DB_PATH']) as conn:
            saved = json.loads(conn.execute('SELECT content_json FROM course_target_practice_attempts WHERE id=?',
                                            (state['id'],)).fetchone()[0])

        for item in saved:
            self.assertEqual(state['current_item']['id'], item['id'])
            def action(name, **values):
                return post(path + '/' + name, {'item_id': item['id'], 'request_id': item['id'] + '-' + name} | values)
            state = action('learn')
            self.assertEqual(state['current_item']['stage'], 'question')
            self.assertNotIn('answer', state['current_item']['question'])
            self.assertIsNone(state['current_item']['feedback'])
            if item['question'].get('audio_url'):
                self.assertIsNone(state['current_item']['transcript'])
                with self.a.get(item['question']['audio_url'], base_url=self.base) as audio:
                    self.assertEqual(audio.status_code, 200)
                    self.assertEqual(audio.mimetype, 'audio/mpeg')
                state = action('listened')
                self.assertTrue(state['current_item']['listened'])
                state = action('transcript')
                self.assertEqual(state['current_item']['transcript'], item['question']['transcript'])
            state = action('hint')
            self.assertIsNotNone(state['current_item']['hint'])
            state = action('answer', choice_id=item['question']['answer'])
            self.assertTrue(state['current_item']['feedback']['correct'])
            state = action('next')

        self.assertEqual(state['status'], 'completed')
        self.assertTrue(state['coverage']['ready'])
        self.assertTrue(all(not target['demonstrated'] for target in state['coverage']['targets']))
        self.assertEqual(self.a.get(path, base_url=self.base).json, state)
        with transaction(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes WHERE profile_id=?',
                                          (visitor['profile']['id'],)).fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events WHERE profile_id=?',
                                          (visitor['profile']['id'],)).fetchone()[0], 0)
        provider.assert_not_called()

    @patch('utils.lazy.LazyService._get', side_effect=AssertionError('Saving course drafts must not resolve providers'))
    def test_course_drafts_remain_owned_and_preserve_conflicting_work(self, provider):
        course = self.a.get('/api/v1/course', base_url=self.base).json
        headers = {'X-CSRF-Token': course['csrf_token']}
        started = self.a.post('/api/v1/course/chapters/' + course['chapters'][0]['id'] + '/checkpoint',
            base_url=self.base, headers=headers, json={'request_id': 'draft-start', 'challenge': True})
        self.assertEqual(started.status_code, 200, started.text)
        attempt = started.json
        path = '/api/v1/course/checkpoints/' + attempt['id']
        question = attempt['questions'][0]
        body = {'answers': {question['id']: question['choices'][0]['id']}, 'revision': 0}
        self.assertEqual(self.a.post(path + '/draft', base_url=self.base, json=body).status_code, 403)
        other_headers = {'X-CSRF-Token': self.state(self.b)['csrf_token']}
        denied = self.b.post(path + '/draft', base_url=self.base, headers=other_headers, json=body)
        self.assertEqual(denied.status_code, 404)
        saved = self.a.post(path + '/draft', base_url=self.base, headers=headers, json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json['draft_answers'], body['answers'])
        self.assertEqual(saved.json['draft_revision'], 1)
        self.assertEqual(self.a.post(path + '/draft', base_url=self.base, headers=headers, json=body).json, saved.json)
        conflict = self.a.post(path + '/draft', base_url=self.base, headers=headers,
                               json={'answers': {}, 'revision': 0})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json['error']['code'], 'draft_conflict')
        self.assertEqual(self.a.get(path, base_url=self.base).json['draft_answers'], body['answers'])
        provider.assert_not_called()

    @patch('utils.lazy.LazyService._get', side_effect=AssertionError('Switching a course must not resolve providers'))
    def test_course_switch_is_explicit_owned_and_keeps_previous_access(self, provider):
        from repositories.learning_repository import transaction

        self.app.config['COURSE_DEFAULT_RELEASE'] = 'a1-journey-v2'
        visitor = self.state(self.a)
        profile_id = visitor['profile']['id']
        headers = {'X-CSRF-Token': visitor['csrf_token']}
        with transaction(self.app.config['DB_PATH'], write=True) as conn:
            conn.execute("INSERT INTO course_enrolments VALUES (?,'A1','a1-v1',1,'schema-044')", (profile_id,))
            conn.execute("INSERT INTO course_continuation_entitlements VALUES (?,'A2','a1-v1','legacy-course-completion',1)", (profile_id,))
        course = self.a.get('/api/v1/course', base_url=self.base).json
        self.assertEqual(course['release_id'], 'a1-v1')
        started = self.a.post('/api/v1/course/chapters/' + course['chapters'][0]['id'] + '/checkpoint',
            base_url=self.base, headers=headers, json={'request_id': 'old-course', 'challenge': True})
        self.assertEqual(started.status_code, 200, started.text)
        old_id = started.json['id']
        path = '/api/v1/course/releases/a1-journey-v2/switch'
        body = {'request_id': 'demo-switch', 'from_release_id': 'a1-v1'}
        self.assertEqual(self.a.post(path, base_url=self.base, json=body).status_code, 403)
        other = self.state(self.b)
        response = self.b.post(path, base_url=self.base,
            headers={'X-CSRF-Token': other['csrf_token']}, json=body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.a.get('/api/v1/course', base_url=self.base).json['release_id'], 'a1-v1')
        changed = self.a.post(path, base_url=self.base, headers=headers, json=body)
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json['release_id'], 'a1-journey-v2')
        self.assertEqual(changed.json['unlocked_levels'], ['A1', 'A2'])
        self.assertEqual(changed.json['previous_courses'][0]['attempts'][0]['id'], old_id)
        self.assertEqual(self.a.post(path, base_url=self.base, headers=headers, json=body).json, changed.json)
        self.assertEqual(self.a.get('/api/v1/course/checkpoints/' + old_id, base_url=self.base).json['status'], 'active')
        with transaction(self.app.config['DB_PATH']) as conn:
            rows = conn.execute('SELECT profile_id FROM course_release_switches').fetchall()
            self.assertEqual([row['profile_id'] for row in rows], [profile_id])
        provider.assert_not_called()

    def test_advertised_samples_are_playable_without_providers_and_owned(self):
        import json
        from repositories.learning_repository import transaction
        from services.demo_games import SAMPLE_GAMES
        visitor = self.state(self.a)
        headers = {'X-CSRF-Token':visitor['csrf_token']}
        catalogue = self.a.get('/api/v1/games',base_url=self.base).json
        self.assertEqual({g['id'] for g in catalogue['games'] if g['unlocked']}, SAMPLE_GAMES)
        for game in catalogue['games']:
            if game['id'] not in SAMPLE_GAMES:
                self.assertEqual(game['availability'],'local-only')
                continue
            options = {'grammar_focus':'mixed'} if game['id']=='scene-builder' else {'source':'vocabulary','topic':'custom provider bypass'}
            response = self.a.post('/api/v1/games/'+game['id']+'/start',base_url=self.base,headers=headers,
                                   json={'request_id':'sample-'+game['id'],'options':options})
            self.assertEqual(response.status_code,200,response.text)
            state = response.json
            self.assertTrue(state['sample'])
            self.assertEqual(state['phase'],'play')
            root = '/api/v1/games/sessions/'+state['id']
            self.assertEqual(self.b.get(root,base_url=self.base).status_code,404)
            self.assertEqual(self.a.post(root+'/prepare',base_url=self.base,headers=headers,json={}).status_code,403)
            with transaction(self.app.config['DB_PATH']) as conn:
                content = json.loads(conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?',(state['id'],)).fetchone()[0])
                rounds = content['rounds']
            if state.get('delivery'):
                for index, leg in enumerate(content['legs']):
                    questions = [('ask', {'question_id': leg['required_question']})] if leg.get('required_question') else []
                    for action,payload in [*questions, ('begin',{}),('go',{'path':leg['route']}),('deliver' if index == len(content['legs']) - 1 else 'talk',{})]:
                        result=self.a.post(root+'/route-command',base_url=self.base,headers=headers,json={
                            'request_id':f'demo-route-{state["delivery"]["revision"]}', 'revision':state['delivery']['revision'],
                            'action':action,'payload':payload})
                        self.assertEqual(result.status_code,200,result.text)
                        state=result.json
                self.assertEqual(state['phase'],'completed')
                self.assertFalse(state['study_available'])
                self.assertEqual(state['words'],[])
                continue
            for item in rounds:
                for action, data in [('answer',{'round_id':item['id'],'answer':item['expected_answer']}),('continue',{'round_id':item['id']})]:
                    checked = self.a.post(root+'/'+action,base_url=self.base,headers=headers,json=data)
                    self.assertEqual(checked.status_code,200,checked.text)
                    if action == 'answer':
                        self.assertNotIn('answer_audio',checked.json['result'])
                        if game['id']=='scene-builder':
                            self.assertEqual(checked.json['result']['correct_sentence'],item['correct_sentence'])
                            key=item['answer_audio'][0]['audio_key']
                            self.assertEqual(self.a.post('/api/v1/games/media/'+key+'/prepare',base_url=self.base,
                                                        headers=headers,json={}).status_code,403)
            done = self.a.post(root+'/complete',base_url=self.base,headers=headers,json={})
            self.assertEqual(done.json['phase'],'completed')
            self.assertEqual(done.json['words'],[])
            self.assertFalse(done.json['study_available'])

    def test_riverside_listening_and_section_review_work_without_provider_access(self):
        from services.route_content import build_mission
        visitor = self.state(self.a)
        headers = {'X-CSRF-Token': visitor['csrf_token']}
        result = self.a.post('/api/v1/games/directions/start', base_url=self.base, headers=headers,
                             json={'request_id': 'riverside-listening-demo', 'options': {'delivery_id': 'irina', 'delivery_mode': 'listening'}})
        self.assertEqual(result.status_code, 200)
        state = result.json
        root = '/api/v1/games/sessions/'+state['id']
        def command(action, payload=None):
            nonlocal state
            response = self.a.post(root+'/route-command', base_url=self.base, headers=headers,
                json={'request_id': 'demo-delivery-'+str(state['delivery']['revision']), 'revision': state['delivery']['revision'], 'action': action, 'payload': payload or {}})
            self.assertEqual(response.status_code, 200, response.text)
            state = response.json
        pack = build_mission(mission_id='irina')
        for index, leg in enumerate(pack['legs']):
            self.assertNotIn('text', state['delivery']['lines'][0])
            for line in leg['lines']:
                command('listen', {'leg': index, 'line_id': line['id']})
            command('begin')
            command('go', {'path': leg['route']})
            command('deliver' if index == 2 else 'talk')
        self.assertEqual(state['words'], [])
        self.assertFalse(state['study_available'])
        checks = state['delivery']['first_checks']
        reward = state['reward']['amount']
        command('review_start', {'leg': 1})
        self.assertEqual(state['phase'], 'practice')
        command('review_exit')
        self.assertEqual(state['delivery']['first_checks'], checks)
        self.assertEqual(state['reward']['amount'], reward)
        for suffix in ('words', 'flashcards'):
            response = self.a.post(root+'/'+suffix, base_url=self.base, headers=headers, json={})
            self.assertEqual(response.status_code, 403)

    def test_all_town_missions_are_owned_offline_samples_with_recorded_audio(self):
        import json
        from repositories.learning_repository import transaction
        from services.route_town import TOWN_MISSION_IDS

        other_headers = {'X-CSRF-Token': self.state(self.b)['csrf_token']}
        audio_urls = set()
        self.assertEqual(len(TOWN_MISSION_IDS), 8)
        for mission_id in TOWN_MISSION_IDS:
            with self.subTest(mission=mission_id):
                # Each visitor plays one full mission within the normal write limit.
                client = self.app.test_client()
                headers = {'X-CSRF-Token': self.state(client)['csrf_token']}
                response = client.post('/api/v1/games/directions/start', base_url=self.base, headers=headers,
                    json={'request_id': 'demo-'+mission_id, 'new_game': True,
                          'options': {'delivery_id': mission_id, 'delivery_mode': 'listening'}})
                self.assertEqual(response.status_code, 200, response.text)
                state = response.json
                self.assertTrue(state['sample'])
                self.assertEqual(state['delivery']['map']['scene'], 'town')
                self.assertEqual(state['delivery']['mode'], 'listening')
                root = '/api/v1/games/sessions/'+state['id']
                with transaction(self.app.config['DB_PATH']) as conn:
                    pack = json.loads(conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?',
                                                   (state['id'],)).fetchone()[0])
                self.assertEqual(pack['mission_id'], mission_id)
                self.assertEqual(self.b.get(root, base_url=self.base).status_code, 404)
                denied = self.b.post(root+'/route-command', base_url=self.base, headers=other_headers,
                    json={'request_id': 'other-'+mission_id, 'revision': state['delivery']['revision'],
                          'action': 'begin', 'payload': {}})
                self.assertEqual(denied.status_code, 404, denied.text)

                def command(action, payload=None):
                    nonlocal state
                    result = client.post(root+'/route-command', base_url=self.base, headers=headers,
                        json={'request_id': 'demo-town-'+str(state['delivery']['revision']),
                              'revision': state['delivery']['revision'], 'action': action, 'payload': payload or {}})
                    self.assertEqual(result.status_code, 200, result.text)
                    state = result.json

                for index, leg in enumerate(pack['legs']):
                    audio_urls.update(line['audio_url'] for line in
                                      [*leg['lines'], leg['clarify'], *(q['reply'] for q in leg.get('questions', []))])
                    self.assertFalse(state['delivery']['can_go'])
                    if leg.get('required_question'):
                        self.assertTrue(state['delivery']['question_required'])
                        command('ask', {'question_id': leg['required_question']})
                        self.assertFalse(state['delivery']['question_required'])
                    for line in state['delivery']['lines']:
                        self.assertNotIn('text', line)
                        command('listen', {'leg': index, 'line_id': line['id']})
                    self.assertTrue(state['delivery']['can_go'])
                    command('begin')
                    if leg.get('transport'):
                        command('board', {'transport_id': leg['transport']['id']})
                        self.assertEqual(state['delivery']['transport']['status'], 'aboard')
                        command('ride', {'stop_id': leg['target']})
                        self.assertEqual(state['delivery']['transport']['stop_id'], leg['target'])
                        command('alight')
                    else:
                        command('go', {'path': leg['route']})
                    self.assertEqual(state['delivery']['phase'], 'arrived', state['delivery']['feedback'])
                    command('deliver' if index == len(pack['legs'])-1 else 'talk')
                audio_urls.add(state['delivery']['ending']['audio_url'])
                self.assertEqual(state['phase'], 'completed')
                self.assertFalse(state['study_available'])
                self.assertEqual(state['words'], [])
                for suffix in ('words', 'flashcards'):
                    denied = client.post(root+'/'+suffix, base_url=self.base, headers=headers, json={})
                    self.assertEqual(denied.status_code, 403)

        self.assertTrue(audio_urls)
        for url in sorted(audio_urls):
            with self.subTest(audio=url):
                with self.a.get(url, base_url=self.base) as audio:
                    self.assertEqual(audio.status_code, 200)
                    self.assertEqual(audio.mimetype, 'audio/mpeg')
                    self.assertGreater(len(audio.data), 0)

    def test_new_routes_in_public_modules_are_denied_by_default(self):
        self.app.add_url_rule('/test-provider', endpoint='onboarding.future_provider', view_func=lambda: self.fail('Provider executed'))
        self.assertEqual(self.a.get('/test-provider', base_url=self.base).status_code, 403)

    def test_global_write_limit_survives_fresh_cookies(self):
        a, b = self.state(self.a), self.state(self.b)
        limiter = DemoLimits(self.app.config['DB_PATH'])
        limiter.consume([('writes', 86400, 1)])
        # Fill the daily bucket without thousands of HTTP calls.
        from repositories.learning_repository import transaction
        with transaction(self.app.config['DB_PATH'], write=True) as conn:
            conn.execute("UPDATE demo_limits SET used=10000 WHERE scope='writes' AND duration=86400")
        for client, state in ((self.a, a), (self.b, b)):
            response = client.post('/api/v1/onboarding', json={'milestone': 'coins'}, base_url=self.base,
                                   headers={'X-CSRF-Token': state['csrf_token']})
            self.assertEqual(response.status_code, 429)
            self.assertGreater(int(response.headers['Retry-After']), 0)
        self.assertEqual(self.app.test_client().get('/', base_url=self.base).status_code, 200)

    def test_new_cookie_profile_creation_is_globally_limited(self):
        limiter = DemoLimits(self.app.config['DB_PATH'])
        limiter.consume([('new-visitors', 3600, 1)])
        from repositories.learning_repository import transaction
        with transaction(self.app.config['DB_PATH'], write=True) as conn:
            conn.execute("UPDATE demo_limits SET used=120 WHERE scope='new-visitors' AND duration=3600")
        self.assertEqual(self.a.get('/api/v1/user-session', base_url=self.base).status_code, 429)
        self.assertEqual(self.b.get('/api/v1/user-session', base_url=self.base).status_code, 429)
        self.assertEqual(self.a.get('/static/css/public_demo.css', base_url=self.base).status_code, 200)

    def test_demo_notices_use_external_styles_under_the_existing_csp(self):
        page = self.a.get('/', base_url=self.base)
        self.assertIn("style-src 'self'", page.headers['Content-Security-Policy'])
        self.assertNotIn('style=', page.get_data(as_text=True))
        self.assertIn('<details class="demo-notice">', page.get_data(as_text=True))
        self.assertIn('/static/css/public_demo.css?v=2', page.get_data(as_text=True))
        css = self.a.get('/static/css/public_demo.css?v=2', base_url=self.base)
        self.assertEqual(css.status_code, 200)
        self.assertIn('position: fixed', css.get_data(as_text=True))
        blocked = self.a.get('/comprehension', base_url=self.base)
        self.assertNotIn('style=', blocked.get_data(as_text=True))
        self.assertIn('/static/css/public_demo.css?v=2', blocked.get_data(as_text=True))

    def test_native_review_is_interactive_owned_and_csrf_protected(self):
        state = self.state(self.a)
        data = {'profile_id': state['profile']['id'], 'scope': {}, 'size': 5, 'submission_id': 'demo-start'}
        self.assertEqual(self.a.post('/api/v1/review-sessions', json=data, base_url=self.base).status_code, 403)
        headers = {'X-CSRF-Token': state['csrf_token']}
        response = self.a.post('/api/v1/review-sessions', json=data, base_url=self.base, headers=headers)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        saved = response.json
        self.assertNotIn('answer', saved['item'])
        path = '/api/v1/review-sessions/' + saved['id']
        self.state(self.b)
        self.assertIn(self.b.get(path, base_url=self.base).status_code, (403, 404))
        reveal = self.a.post(path + '/reveal', json={'submission_id': 'reveal',
            'expected_revision': saved['revision'], 'item_id': saved['item']['id']}, base_url=self.base, headers=headers)
        self.assertEqual(reveal.status_code, 200)
        self.assertTrue(reveal.json['item']['answer'])
