"""Mounted pages retain forms, media privacy and URLs without altering prose."""
import unittest

from flask import Flask, jsonify, redirect, request, url_for
from werkzeug.test import Client
from werkzeug.wrappers import Response

from hosted_demo_mount import DemoMount, DemoHTML, demo_url, public_asset


class DemoMountTests(unittest.TestCase):
    def test_only_activity_paths_are_mounted(self):
        for original, expected in (
            ('/#home', '/demo/#home'), ('/vocab?q=дом', '/demo/vocab?q=дом'),
            ('/demo/', '/demo/'), ('/demo', '/demo'),
            ('/static/media/voice.mp3', '/demo/static/media/voice.mp3'),
            ('/static/uploads/lesson.pdf', '/demo/static/uploads/lesson.pdf'),
            ('/static/audio/first-steps/hello.mp3', '/static/audio/first-steps/hello.mp3'),
            ('/post/assets/app.js', '/post/assets/app.js'),
            ('/trial/account', '/demo/trial/account'),
            ('/trial/sign-in/google?next=/', '/trial/sign-in/google?next=/'),
            ('https://example.org/x', 'https://example.org/x'), ('//example.org/x', '//example.org/x'),
            ('#activities', '#activities'),
        ):
            self.assertEqual(demo_url(original), expected)
        self.assertFalse(public_asset('/static/media/private.mp3'))
        self.assertFalse(public_asset('/static/uploads/private.pdf'))

    def test_html_preserves_prose_scripts_entities_and_explicit_exit(self):
        html = '''<!doctype html><html><head><script src="/static/js/app_paths.js"></script></head><body>
        <a href="/vocab?a=1&amp;b=2">My words</a><a href="/" data-app-exit>Leave demo</a>
        <form action="/sentences" hx-post="/sentence/add"><input name="answer" value="/leave my text alone" data-saved="/leave my draft alone"></form>
        <audio src="/static/media/a.mp3"></audio><div data-navigation="{&quot;href&quot;:&quot;/writing&quot;}"></div>
        <script>const path = "/keep-script-as-is";</script>Text &amp; punctuation.
        </body></html>'''
        parser = DemoHTML()
        parser.feed(html)
        result = ''.join(parser.parts)
        self.assertIn('name="app-base-path" content="/demo"', result)
        self.assertIn('href="/demo/vocab?a=1&amp;b=2"', result)
        self.assertIn('href="/" data-app-exit', result)
        self.assertIn('hx-post="/demo/sentence/add"', result)
        self.assertIn('value="/leave my text alone"', result)
        self.assertIn('data-saved="/leave my draft alone"', result)
        self.assertIn('src="/demo/static/media/a.mp3"', result)
        self.assertIn('/demo/writing', result)
        self.assertIn('const path = "/keep-script-as-is";', result)
        self.assertIn('Text &amp; punctuation.', result)

    def test_flask_urls_redirects_json_and_streamed_audio(self):
        app = Flask(__name__)
        @app.get('/data')
        def data():
            return jsonify(url=url_for('data'), audio_url='/static/media/a.mp3',
                           answers=['/do not change this'], text='/keep this text',
                           navigation=[{'href': '/writing'}], script_root=request.script_root)
        @app.get('/redirect')
        def jump():
            return redirect('/sentences/saved')
        @app.get('/partial')
        def partial():
            return Response('<form hx-post="/sentence/add"></form>', headers={'HX-Redirect': '/writing'})
        @app.get('/audio')
        def audio():
            return Response(iter([b'one', b'two']), mimetype='audio/mpeg')
        client = Client(DemoMount(app), Response)
        value = client.get('/demo/data').json
        self.assertEqual(value['url'], '/demo/data')
        self.assertEqual(value['audio_url'], '/demo/static/media/a.mp3')
        self.assertEqual(value['answers'], ['/do not change this'])
        self.assertEqual(value['navigation'][0]['href'], '/demo/writing')
        self.assertEqual(value['script_root'], '/demo')
        self.assertEqual(client.get('/demo/redirect').location, '/demo/sentences/saved')
        self.assertEqual(client.get('/demo/partial').headers['HX-Redirect'], '/demo/writing')
        self.assertEqual(client.get('/demo/audio').data, b'onetwo')
        self.assertEqual(client.head('/demo/data').data, b'')


if __name__ == '__main__':
    unittest.main()
