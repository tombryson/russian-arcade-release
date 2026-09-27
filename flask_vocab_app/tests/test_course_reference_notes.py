"""Reference classifications are display data, not assessment mutations."""
from copy import deepcopy
import json
import sqlite3
import unittest
from unittest.mock import patch

from services import course_progression as course
from services import course_reference_notes as notes
from services.course_releases import load_release
from tests.support import isolated_app


class CourseReferenceNotesTests(unittest.TestCase):
    def data(self):
        return json.loads(notes.DATA_FILE.read_text(encoding='utf-8'))

    def test_authored_notes_cover_preparation_without_changing_published_content(self):
        data = self.data()
        self.assertIs(notes.validate_reference_notes(data), data)
        published = load_release('a1-journey-v2')
        expected = {p['id'] for ch in published['chapters'] for p in ch['preparation']}
        self.assertEqual(set(data['releases']['a1-journey-v2']), expected)
        for chapter in published['chapters']:
            for preparation in chapter['preparation']:
                self.assertNotIn('groups', preparation)
                self.assertTrue(notes.reference_groups('a1-journey-v2', preparation['id']))
        self.assertEqual(published, load_release('a1-journey-v2'))

    def test_validator_rejects_unknown_ids_duplicate_groups_and_incomplete_translations(self):
        mutations = [
            lambda d: d.update(version=True),
            lambda d: d.update(releases={'invented': {}}),
            lambda d: d['releases']['a1-journey-v2'].pop('home-introductions'),
            lambda d: d['releases']['a1-journey-v2'].update(invented={'groups': []}),
            lambda d: d['releases']['a1-journey-v2']['home-introductions'].update(groups=[]),
            lambda d: d['releases']['a1-journey-v2']['home-introductions']['groups'][0].update(title_ru=''),
            lambda d: d['releases']['a1-journey-v2']['home-introductions']['groups'][0]['items'][0].update(label_ru=''),
            lambda d: d['releases']['a1-journey-v2']['home-introductions']['groups'][0]['items'][0].update(en=''),
            lambda d: d['releases']['a1-journey-v2']['home-introductions']['groups'][0]['items'][0].update(ru='x' * 301),
            lambda d: d['releases']['a1-journey-v2']['home-introductions'].update(groups=[
                d['releases']['a1-journey-v2']['home-introductions']['groups'][0]] * 2),
        ]
        for mutate in mutations:
            data = self.data()
            mutate(data)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                notes.validate_reference_notes(data)

    def test_reference_content_stays_short(self):
        for group_count, items_per_group in ((5, 1), (1, 5), (3, 4)):
            data = self.data()
            entry = data['releases']['a1-journey-v2']['home-introductions']
            group = entry['groups'][0]
            entry['groups'] = [dict(deepcopy(group), id=f'group-{i}',
                                   items=[deepcopy(group['items'][0])] * items_per_group)
                               for i in range(group_count)]
            with self.subTest(groups=group_count, items=items_per_group), self.assertRaises(ValueError):
                notes.validate_reference_notes(data)

    def test_returned_groups_cannot_mutate_cached_content(self):
        first = notes.reference_groups('a1-journey-v2', 'home-introductions')
        original = deepcopy(first)
        first[0]['items'][0]['ru'] = 'changed'
        self.assertEqual(notes.reference_groups('a1-journey-v2', 'home-introductions'), original)
        with patch.object(notes, '_catalogue', side_effect=AssertionError('Legacy content must stay independent.')):
            self.assertEqual(notes.reference_groups('a1-v1', None), [])

    def test_projection_updates_receipts_without_mutating_them_or_revealing_locked_notes(self):
        chapter = load_release('a1-journey-v2')['chapters'][0]
        receipt = {'course': {'release_id': 'a1-journey-v2', 'chapters': [
            dict(chapter, status='practice'), dict(chapter, id='later', status='locked')]},
            'result': {'passed': False, 'score': 0.5}}
        stored = deepcopy(receipt)
        projected = course._reveal_receipt(receipt)
        self.assertTrue(projected['course']['chapters'][0]['preparation'][0]['groups'])
        self.assertEqual(projected['course']['chapters'][1]['preparation'], [])
        self.assertEqual(projected['result'], stored['result'])
        self.assertEqual(receipt, stored)

    def test_public_snapshot_has_classified_notes_and_no_database_side_effects(self):
        app = isolated_app(self)
        app.config['COURSE_DEFAULT_RELEASE'] = 'a1-journey-v2'
        response = app.test_client().get('/api/v1/course')
        self.assertEqual(response.status_code, 200)
        state = response.json
        self.assertTrue(state['chapters'][0]['preparation'][0]['groups'])
        self.assertTrue(all(chapter['preparation'] == [] for chapter in state['chapters'][1:]))
        with app.app_context(), sqlite3.connect(app.config['DB_PATH']) as conn:
            before = conn.total_changes
            course.course_snapshot(conn, state['profile_id'])
            self.assertEqual(conn.total_changes, before)
