"""The lesson exposes authored example audio without allocating learner work."""
from html.parser import HTMLParser
import unittest
from unittest.mock import patch

from services.curriculum_sequence_content import load_asset, load_manifest
from tests.support import isolated_app


class TeachingPlayers(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.players = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'audio' and 'data-teaching-audio' in attrs:
            self.players.append(attrs)


class CurriculumTeachingAudioTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()

    def test_examples_have_native_players_with_localized_accessible_labels(self):
        teaching = load_asset('location-teaching-v2')['content']
        examples = [example for group in teaching['groups'] for example in group['examples']]
        self.assertTrue(any('Встретимся' in example['ru'] for example in examples))
        for language, label in [('en', 'Listen to example'), ('ru', 'Послушать пример')]:
            with self.subTest(language=language):
                with self.client.session_transaction() as session:
                    session['ui_lang'] = language
                response = self.client.get('/curriculum/units/location-destination-v2')
                self.assertEqual(response.status_code, 200)
                players = TeachingPlayers(response.get_data(as_text=True)).players
                self.assertEqual(len(players), len(examples))
                for player, example in zip(players, examples):
                    self.assertEqual(player['src'], example['audio']['url'])
                    self.assertEqual(player['aria-label'], label + ': ' + example['ru'])
                    self.assertIn('controls', player)
                    self.assertEqual(player['preload'], 'none')
                    self.assertNotIn('autoplay', player)

    def test_example_without_audio_metadata_keeps_text_without_empty_player(self):
        def asset_without_one_recording(identity):
            asset = load_asset(identity)
            if identity == 'location-teaching-v2':
                asset['content']['groups'][0]['examples'][0]['audio'] = None
            return asset

        manifest = load_manifest()
        with patch('services.curriculum_sequence_content.load_asset', side_effect=asset_without_one_recording), \
                patch('services.curriculum_sequence_content.load_manifest', return_value=manifest):
            response = self.client.get('/curriculum/units/location-destination-v2')
        html = response.get_data(as_text=True)
        examples = [example for group in load_asset('location-teaching-v2')['content']['groups'] for example in group['examples']]
        self.assertEqual(response.status_code, 200)
        self.assertIn(examples[0]['ru'], html)
        players = TeachingPlayers(html).players
        self.assertEqual(len(players), len(examples) - 1)
        self.assertNotIn(examples[0]['audio']['url'], [player['src'] for player in players])
