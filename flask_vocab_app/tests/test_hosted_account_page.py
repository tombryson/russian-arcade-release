from html.parser import HTMLParser
from pathlib import Path
import unittest

from hosted_account_page import render_account_page


GOOGLE = {'id': 'google', 'name': 'Google', 'sign_in_url': '/trial/sign-in/google'}
GITHUB = {'id': 'github', 'name': 'GitHub', 'sign_in_url': '/trial/sign-in/github'}


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements, self.content = [], []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.content.append(data)


class HostedAccountPageTests(unittest.TestCase):
    def test_chooser_uses_only_available_providers_and_preserves_return_path(self):
        html = render_account_page('Sign in', providers=[GITHUB, GOOGLE], next_url='/#flashcards')
        page = Page(html)
        links = [attrs['href'] for tag, attrs in page.elements if tag == 'a']
        self.assertIn('/trial/sign-in/google?next=%2F%23flashcards', links)
        self.assertIn('/trial/sign-in/github?next=%2F%23flashcards', links)
        self.assertLess(html.index('Sign in with Google'), html.index('Sign in with GitHub'))
        self.assertIn('Save your words, cards and progress.', html)
        self.assertIn('Already use GitHub here?', html)
        single = render_account_page('Sign in', providers=[GITHUB])
        self.assertNotIn('Sign in with Google', single)
        self.assertNotIn('Already use GitHub here?', single)
        self.assertNotIn('disabled', single)

    def test_no_provider_keeps_guest_access_without_dead_buttons(self):
        html = render_account_page('Sign-in unavailable', 'Please try again later.')
        self.assertIn('Explore the demo', html)
        self.assertNotIn('/trial/sign-in/', html)
        self.assertNotIn('.env', html)

    def test_demo_is_the_primary_entry_and_preserves_safe_return_route(self):
        html = render_account_page('Sign in', providers=[GITHUB],
            demo_enabled=True, next_url='/#speaking')
        self.assertIn('href="/demo?next=%2F%23speaking"', html)
        self.assertLess(html.index('Try demo'), html.index('Sign in with GitHub'))
        self.assertIn('No sign-in needed.', html)
        self.assertIn('shared AI allowance', html)
        self.assertNotIn('Explore the demo', html)

    def test_guest_account_does_not_claim_authentication_or_offer_identity_linking(self):
        html = render_account_page('Demo', providers=[GOOGLE, GITHUB],
            demo_active=True, demo_enabled=True, allowance_message='Shared allowance.')
        self.assertIn('Continue demo', html)
        self.assertIn('Or sign in to your personal account', html)
        self.assertIn('Shared allowance.', html)
        self.assertNotIn('Signed in as', html)
        self.assertNotIn('/trial/connect/', html)
        self.assertNotIn('/trial/sign-out', html)
        self.assertNotIn('Save your words', html)
        personal = render_account_page('Your account', providers=[GITHUB],
            account={'display_name': 'Tom'}, demo_active=True, demo_enabled=True)
        self.assertIn('Continue learning', personal)
        self.assertNotIn('Continue demo', personal)
        self.assertNotIn('Try demo', personal)

    def test_signout_and_account_link_are_distinct_post_forms(self):
        html = render_account_page('Your account', providers=[GOOGLE, GITHUB],
            account={'display_name': 'Sample'}, connected_providers=['github'],
            csrf_token='signout-token', link_csrf_token='link-token',
            allowance_message='Your AI demo allowance is US$1 per day.')
        page = Page(html)
        forms = [attrs for tag, attrs in page.elements if tag == 'form']
        self.assertEqual(forms, [
            {'method': 'post', 'action': '/trial/sign-out'},
            {'method': 'post', 'action': '/trial/connect/google'},
        ])
        self.assertIn('value="signout-token"', html)
        self.assertIn('value="link-token"', html)
        self.assertIn('Connect Google', html)
        self.assertIn('Connected', html)
        self.assertNotIn('Connect GitHub', html)
        details = [attrs for tag, attrs in page.elements if tag == 'details']
        self.assertEqual(len(details), 1)
        self.assertNotIn('open', details[0])
        self.assertLess(html.index('Continue learning'), html.index('AI allowance'))

    def test_connected_but_disabled_method_is_shown_without_connect_button(self):
        html = render_account_page('Your account', account={'display_name': 'Sample'},
            connected_providers=['google'], csrf_token='token')
        self.assertIn('Google', html)
        self.assertIn('Connected', html)
        self.assertNotIn('/trial/connect/', html)

    def test_untrusted_text_and_provider_urls_cannot_add_markup_or_external_links(self):
        html = render_account_page('<script>bad</script>', '<img src=x onerror=bad>',
            providers=[GOOGLE | {'sign_in_url': 'javascript:bad'}, {'id': 'unknown'}],
            next_url='//evil.example')
        page = Page(html)
        self.assertNotIn('script', [tag for tag, attrs in page.elements])
        self.assertNotIn('javascript:', html)
        self.assertNotIn('evil.example', html)
        self.assertIn('&lt;img', html)
        self.assertIn('/trial/sign-in/google', html)
        html = render_account_page('Your account', account={'display_name': '<svg onload=bad>'},
            csrf_token='" onfocus="bad')
        self.assertIn('&lt;svg onload=bad&gt;', html)
        self.assertNotIn('<svg onload', html)
        self.assertIn('&#34; onfocus=&#34;bad', html)

    def test_page_works_under_strict_csp_with_only_local_existing_assets(self):
        html = render_account_page('Sign in', providers=[GOOGLE, GITHUB])
        page = Page(html)
        self.assertNotIn('script', [tag for tag, attrs in page.elements])
        root = Path(__file__).resolve().parents[1]
        for tag, attrs in page.elements:
            self.assertNotIn('style', attrs)
            self.assertFalse(any(key.startswith('on') for key in attrs))
            path = attrs.get('src') or (attrs.get('href') if tag == 'link' else None)
            if path:
                self.assertTrue(path.startswith('/static/'), path)
                self.assertTrue((root / path.lstrip('/').split('?')[0]).is_file(), path)
        self.assertIn('noindex, nofollow', html)


if __name__ == '__main__':
    unittest.main()
