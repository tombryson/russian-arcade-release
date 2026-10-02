"""The lesson keeps its complete authored work beside optional new examples."""
from html.parser import HTMLParser
import json
import sqlite3
import unittest

from services.curriculum_units import get_unit, _pack
from tests.support import isolated_app


class LessonForms(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms = {}
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.current = {'attrs': attrs, 'fields': {}}
            self.forms[attrs.get('action')] = self.current
        elif tag == 'input' and self.current is not None and attrs.get('name'):
            self.current['fields'][attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.current = None


class CurriculumPracticeChoicesTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.client.get('/api/v1/user-session')

    def test_rendered_actions_start_distinct_authored_and_generated_work(self):
        unit_id = 'social-exchanges-v1'
        path = '/curriculum/units/' + unit_id
        forms = LessonForms(self.client.get(path).get_data(as_text=True)).forms
        activities = ('practice', 'forms', 'fresh-practice', 'fresh-forms')
        requests = [forms[path + '/' + activity]['fields']['request_id'] for activity in activities]
        self.assertEqual(len(set(requests)), 4)
        self.assertEqual(requests[2], requests[0] + '-fresh')
        self.assertEqual(requests[3], requests[1] + '-fresh')
        sessions = []
        for activity in activities:
            with self.subTest(activity=activity):
                form = forms[path + '/' + activity]
                self.assertEqual(form['attrs']['method'], 'post')
                self.assertNotIn('generation', form['fields'])
                result = self.client.post(path + '/' + activity, data=form['fields'])
                self.assertEqual(result.status_code, 303, result.get_data(as_text=True))
                saved = self.client.get('/api/v1/learning-sessions/' + result.location.rsplit('/', 1)[1]).json
                sessions.append(saved['id'])
                with sqlite3.connect(self.db) as conn:
                    pack = json.loads(conn.execute('SELECT payload FROM learning_content_versions WHERE id=?',
                                                   (saved['version_id'],)).fetchone()[0])
                if activity.startswith('fresh-'):
                    self.assertTrue(pack['id'].startswith('curriculum-unit:g1:' + unit_id + ':'))
                    self.assertEqual(saved['total_items'], 6)
                else:
                    self.assertEqual(pack, _pack(get_unit(unit_id), activity))
                self.assertEqual(saved['item']['type'], 'controlled_text' if activity.endswith('forms') else 'choice')
        self.assertEqual(len(set(sessions)), 4)

    def test_secondary_actions_are_localized_within_existing_sections(self):
        for language, label in (('en', 'New examples'), ('ru', 'Новые примеры')):
            with self.subTest(language=language):
                with self.client.session_transaction() as session:
                    session['ui_lang'] = language
                html = self.client.get('/curriculum/units/present-actions-v1').get_data(as_text=True)
                self.assertEqual(html.count('>' + label + ' →</button>'), 2)
                forms = LessonForms(html).forms
                for activity in ('fresh-practice', 'fresh-forms'):
                    self.assertIn('/curriculum/units/present-actions-v1/' + activity, forms)


if __name__ == '__main__':
    unittest.main()
