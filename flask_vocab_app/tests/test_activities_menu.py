"""The top navigation exposes the shared primary activities as a disclosure."""
from pathlib import Path
import unittest

from jinja2 import Environment, FileSystemLoader

from utils.i18n import translate_ui
from utils.navigation import activity_navigation


class ActivitiesMenuTests(unittest.TestCase):
    def setUp(self):
        templates = Path(__file__).resolve().parents[1] / 'templates'
        self.template = Environment(loader=FileSystemLoader(templates)).get_template('_activities_menu.html')

    def render(self, language='en', active_page='writing'):
        return self.template.render(
            active_page=active_page,
            activity_navigation=activity_navigation(language),
            ui_t=lambda key: translate_ui(key, language),
        )

    def test_primary_activity_links_and_translated_all_activities_last(self):
        for language, all_activities in (('en', 'All activities'), ('ru', 'Все занятия')):
            with self.subTest(language=language):
                menu = self.render(language)
                activities = activity_navigation(language)['activities']
                self.assertEqual(menu.count('<a '), len(activities) + 2)
                self.assertEqual(menu.count('hx-boost="false"'), len(activities) + 2)
                for item in activities:
                    self.assertIn(f'href="{item["href"]}"', menu)
                    self.assertIn(f'>{item["label"]}</a>', menu)
                self.assertIn(f'href="/#activities" hx-boost="false">{all_activities}', menu)
                self.assertIn(f'href="/#games" hx-boost="false">{translate_ui("nav.games", language)}</a>', menu)
                self.assertGreater(menu.index('class="activities-menu-all"'), menu.index('href="/#games"'))
                self.assertNotIn('role="menu"', menu)

    def test_marks_only_the_current_activity_link_and_trigger(self):
        for item in activity_navigation()['activities']:
            with self.subTest(page=item['page']):
                menu = self.render(active_page=item['page'])
                self.assertIn('<summary data-active="true">', menu)
                self.assertIn(f'href="{item["href"]}" hx-boost="false" aria-current="page"', menu)
                self.assertEqual(menu.count('aria-current="page"'), 1)

    def test_profile_vocabulary_and_household_pages_do_not_mark_activities_active(self):
        for page in ('user_sessions', 'vocab', 'sentences_saved', 'household', 'flashcards', None):
            with self.subTest(page=page):
                menu = self.render(active_page=page)
                self.assertNotIn('data-active="true"', menu)
                self.assertNotIn('aria-current="page"', menu)


if __name__ == '__main__':
    unittest.main()
