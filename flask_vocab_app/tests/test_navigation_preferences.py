"""Browser navigation preferences span both shells without affecting identity."""
import json
from pathlib import Path
import tempfile
import unittest

from werkzeug.datastructures import MultiDict

from services.personal_learning import PERSONAL_PROFILE
from tests.support import isolated_app
from utils.navigation import activity_navigation, normalize_navigation_layout


class NavigationPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, signed_in=False)
        self.client = self.app.test_client()
        directory = tempfile.TemporaryDirectory(prefix='navigation-build-')
        self.addCleanup(directory.cleanup)
        dist = Path(directory.name)
        (dist / '.vite').mkdir()
        (dist / 'assets').mkdir()
        for filename in ('main.js', 'main.css', 'legacy.js', 'legacy.css'):
            (dist / 'assets' / filename).write_text('/* fixture */')
        (dist / '.vite' / 'manifest.json').write_text(json.dumps({
            'src/main.tsx': {'file': 'assets/main.js', 'css': ['assets/main.css']},
            'src/legacy.ts': {'file': 'assets/legacy.js', 'css': ['assets/legacy.css']},
        }))
        self.app.config.update(WORD_POST_ENABLED=True, WORD_POST_DIST_DIR=str(dist))

    def token(self, client=None):
        return (client or self.client).get('/api/v1/user-session').json['csrf_token']

    def save(self, layout, next_path=None, client=None, **kwargs):
        client = client or self.client
        data = {'layout': layout, 'csrf_token': self.token(client)}
        if next_path is not None:
            data['next'] = next_path
        return client.post('/ui-navigation', data=data, **kwargs)

    def selected_layout(self, client=None):
        with (client or self.client).session_transaction() as saved:
            return saved.get('ui_navigation')

    def assert_layout_selected(self, page, layout):
        for option in ('top', 'sidebar'):
            pressed = 'true' if option == layout else 'false'
            self.assertRegex(page, rf'<button\b(?=[^>]*name="layout")(?=[^>]*value="{option}")(?=[^>]*aria-pressed="{pressed}")[^>]*>')
        self.assertNotIn('type="radio"', page)
        self.assertNotIn('Save appearance', page)
        self.assertNotIn('Сохранить вид', page)

    def select_profile(self, profile=PERSONAL_PROFILE):
        result = self.client.post('/api/v1/user-session/select', json={'profile_id': profile},
                                  headers={'X-CSRF-Token': self.token()})
        self.assertEqual(result.status_code, 200)
        return result.json

    def introduce_progress(self):
        for milestone in ('coins', 'progress'):
            response = self.client.post('/api/v1/onboarding', json={'milestone': milestone},
                                        headers={'X-CSRF-Token': self.token()})
            self.assertEqual(response.status_code, 200)

    def test_default_top_preference_is_normalized_without_database_preferences(self):
        for value in (None, '', 'drawer', {}, ['sidebar'], '<script>', 1):
            self.assertEqual(normalize_navigation_layout(value), 'top')
        self.assertEqual(normalize_navigation_layout('sidebar'), 'sidebar')
        page = self.client.get('/post/profiles').text
        self.assertIn('navigation-layout-top', page)
        self.assert_layout_selected(page, 'top')
        self.assertIsNone(self.selected_layout())

    def test_preference_saves_for_guest_and_is_bootstrapped_into_both_shells(self):
        response = self.save('sidebar', '/#speaking')
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['Location'], '/#speaking')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.selected_layout(), 'sidebar')
        native = self.client.get('/').text
        self.assertIn('data-navigation-layout="sidebar"', native)
        self.assert_layout_selected(self.client.get('/post/profiles').text, 'sidebar')
        self.select_profile()
        legacy = self.client.get('/writing').text
        self.assertIn('navigation-layout-sidebar', legacy)
        self.save('top')
        self.assertIn('data-navigation-layout="top"', self.client.get('/').text)
        self.assertIn('navigation-layout-top', self.client.get('/writing').text)

    def test_preference_is_private_to_each_browser(self):
        other = self.app.test_client()
        self.save('sidebar')
        self.assertEqual(self.selected_layout(), 'sidebar')
        self.assertIsNone(self.selected_layout(other))
        self.assert_layout_selected(other.get('/post/profiles').text, 'top')

    def test_sidebar_contains_the_brand_profile_progress_and_one_click_shortcuts(self):
        self.save('sidebar')
        self.select_profile()
        self.introduce_progress()
        for language, words, sentences, appearance in (
            ('en', 'My words', 'Phrasebook', 'Appearance'),
            ('ru', 'Мои слова', 'Разговорник', 'Внешний вид'),
        ):
            with self.subTest(language=language):
                with self.client.session_transaction() as saved:
                    saved['ui_lang'] = language
                response = self.client.get('/writing')
                self.assertEqual(response.status_code, 200)
                page = response.text
                self.assertNotIn('<header class="arcade-header"', page)
                sidebar = page.split('id="sidebar"', 1)[1].split('</nav>', 1)[0]
                self.assertIn('class="sidebar-brand-row"', sidebar)
                self.assertIn('class="sidebar-brand"', sidebar)
                brand = sidebar.split('class="sidebar-brand-row"', 1)[1].split('</div>', 1)[0]
                self.assertNotIn('class="user-session-link"', brand)
                self.assertIn('class="sidebar-menu-scroll"', sidebar)
                footer, account = sidebar.split('class="sidebar-footer"', 1)[1].split('class="sidebar-account"', 1)
                self.assertIn('data-skill-rail', footer)
                self.assertIn('data-progression-badge', footer)
                self.assertIn('href="/#shop"', footer)
                self.assertIn('Магазин' if language == 'ru' else 'Shop', sidebar)
                self.assertNotIn('class="sidebar-utilities"', footer)
                self.assertIn('class="user-session-link"', account)
                self.assertIn('class="language-picker"', account)
                self.assertLess(account.index('class="user-session-link"'), account.index('class="language-picker"'))
                self.assertIn(f'aria-label="{appearance}"', account)
                self.assertIn('<details', account)
                self.assertIn('action="/ui-navigation"', account)
                self.assert_layout_selected(account, 'sidebar')
                self.assertNotIn('href="/appearance"', page)
                shortcuts = footer.split('class="sidebar-shortcuts"', 1)[1].split('</div>', 1)[0]
                self.assertIn('href="/vocab" hx-boost="false"', shortcuts)
                self.assertIn('href="/sentences/saved" hx-boost="false"', shortcuts)
                self.assertIn(f'aria-label="{words}"', shortcuts)
                self.assertIn(f'aria-label="{sentences}"', shortcuts)
                self.assertEqual(shortcuts.count('<svg '), 2)
                self.assertEqual(sidebar.count('href="/vocab"'), 1)
                self.assertEqual(sidebar.count('href="/sentences/saved"'), 1)
                self.assertNotIn('hx-get="/user/stats"', page)
                for control in ('class="user-session-link"', 'data-progression-badge', 'data-skill-rail', 'class="language-picker"'):
                    self.assertEqual(page.count(control), 1)

    def test_top_layout_keeps_unique_header_controls_and_loads_activity_scripts(self):
        self.select_profile()
        self.introduce_progress()
        page = self.client.get('/writing').text
        header = page.split('<header class="arcade-header"', 1)[1].split('</header>', 1)[0]
        self.assertNotIn('id="sidebar"', page)
        for control in ('class="user-session-link"', 'data-progression-badge', 'data-skill-rail', 'class="language-picker"'):
            self.assertEqual(header.count(control), 1)
            self.assertEqual(page.count(control), 1)
        self.assertEqual(page.count('/static/js/app_shell.js?'), 1)
        self.assertIn('aria-label="Appearance"', header)
        self.assertIn('action="/ui-navigation"', header)
        self.assert_layout_selected(header, 'top')
        self.assertNotIn('href="/appearance"', page)

    def test_top_activity_menu_places_games_immediately_before_all_activities(self):
        self.select_profile()
        for language, label, all_label in (('en', 'Games', 'All activities'), ('ru', 'Игры', 'Все занятия')):
            with self.subTest(language=language):
                with self.client.session_transaction() as saved:
                    saved['ui_lang'] = language
                page = self.client.get('/writing').text
                menu = page.split('class="activities-menu-options"', 1)[1].split('</div>', 1)[0]
                self.assertRegex(menu, rf'<a href="/#games" hx-boost="false">{label}</a>\s*<a class="activities-menu-all" href="/#activities" hx-boost="false">{all_label}')

    def test_sidebar_preserves_progress_introduction_gates(self):
        self.save('sidebar')
        self.select_profile()
        page = self.client.get('/writing').text
        self.assertIn('class="sidebar-footer"', page)
        self.assertNotIn('data-progression-badge', page)
        self.assertNotIn('data-skill-rail', page)

    def test_preference_cookie_outlives_the_learning_session_and_survives_selection(self):
        response = self.save('sidebar')
        cookie = self.client.get_cookie('ui_navigation')
        self.assertEqual(cookie.value, 'sidebar')
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site, 'Lax')
        self.assertEqual(cookie.path, '/')
        self.assertIn('Max-Age=31536000', response.headers.get('Set-Cookie'))
        self.client.delete_cookie(self.app.config['SESSION_COOKIE_NAME'])
        self.assertIsNone(self.selected_layout())
        self.assertIn('data-navigation-layout="sidebar"', self.client.get('/').text)
        self.assert_layout_selected(self.client.get('/post/profiles').text, 'sidebar')
        self.select_profile()
        self.assertEqual(self.selected_layout(), 'sidebar')
        self.assertIn('navigation-layout-sidebar', self.client.get('/writing').text)

    def test_preference_cookie_rejects_unknown_values_and_honours_secure_deployment(self):
        for value in ('left', 'TOP', '<script>', 'sidebar;other=value'):
            with self.subTest(value=value):
                self.client.set_cookie('ui_navigation', value)
                self.assertIn('data-navigation-layout="top"', self.client.get('/').text)
                self.assert_layout_selected(self.client.get('/post/profiles').text, 'top')
        self.app.config['SESSION_COOKIE_SECURE'] = True
        self.save('sidebar')
        self.assertTrue(self.client.get_cookie('ui_navigation').secure)
        self.save('top')
        self.assertEqual(self.client.get_cookie('ui_navigation').value, 'top')

    def test_invalid_or_duplicated_values_do_not_change_the_preference(self):
        self.save('sidebar')
        for value in ('', 'left', 'TOP', 'top sidebar', '<script>alert(1)</script>'):
            with self.subTest(value=value):
                self.assertEqual(self.save(value).status_code, 400)
                self.assertEqual(self.selected_layout(), 'sidebar')
        self.assertEqual(self.client.post('/ui-navigation', data={'csrf_token': self.token()}).status_code, 400)
        duplicate = MultiDict([('layout', 'top'), ('layout', 'sidebar'), ('csrf_token', self.token())])
        self.assertEqual(self.client.post('/ui-navigation', data=duplicate).status_code, 400)
        self.assertEqual(self.selected_layout(), 'sidebar')

    def test_preference_requires_csrf_and_same_origin(self):
        self.token()
        for headers in ({}, {'X-CSRF-Token': 'wrong'}):
            self.assertEqual(self.client.post('/ui-navigation', data={'layout': 'sidebar'}, headers=headers).status_code, 403)
        for headers in ({'Origin': 'https://other.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.save('sidebar', headers=headers).status_code, 403)
        self.assertIsNone(self.selected_layout())

    def test_return_paths_preserve_local_hashes_and_reject_external_redirects(self):
        for path in ('/#flashcards', '/post/profiles#appearance', '/writing?load=1#draft'):
            self.assertEqual(self.save('sidebar', path).headers['Location'], path)
        for path in ('https://other.example/', '//other.example/', '/\\other.example/',
                     '/%2fother.example/', '/%5cother.example/', '/writing%0AInjected', 'javascript:alert(1)', ''):
            with self.subTest(path=path):
                self.assertEqual(self.save('sidebar', path).headers['Location'], '/')
        self.assertEqual(self.save('top').headers['Location'], '/')

    def test_old_appearance_address_redirects_to_home_without_loading_build_assets(self):
        self.app.config['WORD_POST_DIST_DIR'] = '/missing-navigation-test-build'
        response = self.client.get('/appearance')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn("form-action 'self'", response.headers['Content-Security-Policy'])

    def test_create_switch_and_logout_preserve_appearance_but_rotate_identity(self):
        self.save('sidebar')
        original = self.select_profile()
        with self.client.session_transaction() as saved:
            saved['current_story_data'] = {'text': 'previous profile draft'}
        created = self.client.post('/api/v1/user-session/profiles', json={'display_name': 'New reader'},
                                   headers={'X-CSRF-Token': self.token()})
        self.assertEqual(created.status_code, 201)
        self.assertNotEqual(created.json['csrf_token'], original['csrf_token'])
        self.assertEqual(self.selected_layout(), 'sidebar')
        with self.client.session_transaction() as saved:
            self.assertNotIn('current_story_data', saved)
        self.select_profile()
        self.assertEqual(self.selected_layout(), 'sidebar')
        result = self.client.post('/api/v1/user-session/logout', json={}, headers={'X-CSRF-Token': self.token()})
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.json['profile'])
        self.assertEqual(self.selected_layout(), 'sidebar')

    def test_appearance_dropdown_is_accessible_translated_and_has_no_inline_code(self):
        self.save('sidebar')
        with self.client.session_transaction() as saved:
            saved['ui_lang'] = 'ru'
        page = self.client.get('/post/profiles').text
        self.assertIn('id="appearance"', page)
        self.assertIn('aria-label="Внешний вид"', page)
        self.assertIn('<summary', page)
        self.assertIn('Верхнее меню', page)
        self.assertIn('Боковая панель', page)
        self.assertIn('action="/ui-navigation"', page)
        self.assert_layout_selected(page, 'sidebar')
        self.assertNotIn('onclick=', page)
        self.assertNotIn('onchange=', page)
        self.assertNotIn('style=', page)

    def test_navigation_catalogue_covers_shared_main_activities_and_auxiliary_tools(self):
        for language in ('en', 'ru'):
            menu = activity_navigation(language)
            self.assertEqual([item['page'] for item in menu['main']], ['home', 'activities', 'vocab'])
            self.assertEqual(menu['activities'][0]['page'], 'native_flashcards')
            self.assertEqual(menu['main'][0]['href'], '/#home')
            self.assertEqual(menu['tools'][0]['href'], '/tools/anki/')
            self.assertTrue(any(item['href'] == '/#speaking' and not item['boost'] for item in menu['activities']))
            self.assertFalse(any(item['page'] == 'vocab' for item in menu['activities']))
            self.assertEqual([item['page'] for item in menu['tools']], ['flashcards', 'sentences_saved'])
            self.assertTrue(all(item['label'] for item in menu['main'] + menu['activities'] + menu['tools']))

    def test_household_appearance_does_not_require_unlocking(self):
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='test-only-household-secret-' * 2)
        page = self.client.get('/post/household')
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="appearance"', page.text)
        self.assertIn('value="/post/household"', page.text)
        with self.client.session_transaction() as saved:
            token = saved['household_csrf']
        response = self.client.post('/ui-navigation', data={'layout': 'sidebar', 'csrf_token': token, 'next': '/post/household#appearance'})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.selected_layout(), 'sidebar')

    def test_household_unlock_and_both_lock_routes_keep_appearance_and_language(self):
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='test-only-household-secret-' * 2)
        self.app.extensions['learning']['household'].configure('Test household', '246810')
        self.client.set_cookie('ui_navigation', 'sidebar')
        with self.client.session_transaction() as saved:
            saved['ui_lang'] = 'ru'

        def token():
            return self.client.get('/api/v1/household').json['csrf_token']

        def unlock():
            result = self.client.post('/api/v1/household/unlock', json={'pin': '246810'},
                                      headers={'X-CSRF-Token': token()})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(self.selected_layout(), 'sidebar')
            with self.client.session_transaction() as saved:
                self.assertEqual(saved['ui_lang'], 'ru')

        unlock()
        result = self.client.post('/api/v1/household/lock', json={}, headers={'X-CSRF-Token': token()})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.selected_layout(), 'sidebar')
        unlock()
        result = self.client.post('/post/household/actions', data={'action': 'lock', 'csrf_token': token()})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.selected_layout(), 'sidebar')
        with self.client.session_transaction() as saved:
            self.assertNotIn('household_access_id', saved)
            self.assertEqual(saved['ui_lang'], 'ru')

    def test_public_demo_accepts_only_the_harmless_preference_write(self):
        from public_demo import install_demo
        self.app.config['PUBLIC_DEMO'] = True
        install_demo(self.app)
        previous_settings = self.client.get('/appearance')
        self.assertEqual(previous_settings.status_code, 302)
        self.assertEqual(previous_settings.headers['Location'], '/')
        self.assertIn("style-src 'self'", previous_settings.headers['Content-Security-Policy'])
        response = self.save('sidebar', '/#home')
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.selected_layout(), 'sidebar')
        fallback = self.save('sidebar')
        self.assertEqual(fallback.headers['Location'], '/')
        self.assertEqual(self.client.get(fallback.headers['Location']).status_code, 200)
        denied = self.client.post('/api/v1/user-session/profiles', json={'display_name': 'Not allowed'},
                                  headers={'X-CSRF-Token': self.token()})
        self.assertEqual(denied.status_code, 403)
        for service in self.app.extensions['services'].values():
            self.assertIsNone(service.instance)


if __name__ == '__main__':
    unittest.main()
