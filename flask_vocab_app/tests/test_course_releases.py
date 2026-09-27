"""Release routing never reinterprets old attempts or continuation rights."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from repositories.learning_repository import LearningError, payload_hash, transaction
from services import course_progression as course
from services import course_releases as releases
from tests import test_course_progression as legacy

fixture_catalogue = legacy.fixture_catalogue


class ReleaseCatalogueTests(unittest.TestCase):
    def test_published_v1_remains_available_and_callers_receive_copies(self):
        first = course.course_catalogue('a1-v1')
        self.assertEqual((first['release_id'], first['band'], first['chapter_count']), ('a1-v1', 'A1', 4))
        self.assertEqual(first['chapters'][0]['id'], 'a1-post-office')
        first['chapters'][0]['title'] = 'Changed locally'
        self.assertNotEqual(course.course_catalogue('a1-v1')['chapters'][0]['title'], 'Changed locally')
        self.assertIn('a1-v1', releases.RELEASES)

    def test_unknown_and_draft_releases_cannot_be_loaded(self):
        draft = deepcopy(releases.RELEASES['a1-v1']) | {'release_id': 'a1-home-pilot', 'status': 'draft'}
        with patch.dict(releases.RELEASES, {'a1-home-pilot': draft}):
            for release_id in ('unknown', 'a1-home-pilot', [], ''):
                with self.subTest(release_id=release_id), self.assertRaises(LearningError):
                    course.course_catalogue(release_id)

    def test_published_bytes_are_immutable(self):
        changed = deepcopy(releases.RELEASES['a1-v1']) | {'catalogue_sha256': '0' * 64}
        with patch.dict(releases.RELEASES, {'a1-v1': changed}), self.assertRaises(ValueError):
            releases.load_release('a1-v1')

    def test_chapter_count_is_a_release_requirement(self):
        catalogue = fixture_catalogue()
        catalogue['chapters'][2]['topic_ids'] += catalogue['chapters'].pop()['topic_ids']
        release = releases.release_metadata() | {'chapter_count': 3}
        self.assertIs(course.validate_course(catalogue, release), catalogue)
        with self.assertRaises(ValueError):
            course.validate_course(catalogue)


class CourseReleaseTests(unittest.TestCase):
    """Reuse the isolated API fixture without rerunning its existing cases."""

    setUp = legacy.CourseProgressionTests.setUp
    post = legacy.CourseProgressionTests.post
    start = legacy.CourseProgressionTests.start
    answers = legacy.CourseProgressionTests.answers
    submit = legacy.CourseProgressionTests.submit
    state = legacy.CourseProgressionTests.state

    def alternate_release(self):
        self.other_release = releases.release_metadata() | {'release_id': 'a1-test-next'}
        self.other_catalogue = deepcopy(self.catalogue)
        for chapter in self.other_catalogue['chapters']:
            chapter['title'] = 'New ' + chapter['title']
        registered = patch.dict(releases.RELEASES, {'a1-test-next': self.other_release})
        registered.start()
        self.addCleanup(registered.stop)
        self.patcher.stop()
        loader = patch.object(course, '_catalogue', side_effect=lambda release_id='a1-v1':
                              self.other_catalogue if release_id == 'a1-test-next' else self.catalogue)
        loader.start()
        self.addCleanup(loader.stop)

    def move_enrolment(self, conn):
        # A test-only future migration. No learner-facing edition switch exists.
        conn.execute("UPDATE course_enrolments SET release_id='a1-test-next',migration_source='a1-v1' WHERE profile_id=?", (self.pid,))

    def test_explicit_release_requests_are_distinct_and_do_not_switch_enrolment(self):
        first = self.post('chapters/chapter-1/checkpoint', {'request_id': 'edition', 'challenge': True, 'release_id': 'a1-v1'})
        self.assertEqual(first.status_code, 200)
        self.assertEqual((first.json['release_id'], first.json['band'], first.json['chapter_count']), ('a1-v1', 'A1', 4))
        self.assertEqual(first.json, self.post('chapters/chapter-1/checkpoint',
            {'request_id': 'edition', 'challenge': True, 'release_id': 'a1-v1'}).json)
        self.assertEqual(self.start(request_id='edition').status_code, 409)
        with transaction(self.db) as conn:
            fingerprint = conn.execute('SELECT payload_hash FROM course_checkpoint_requests WHERE request_id=?', ('edition',)).fetchone()[0]
            self.assertEqual(fingerprint, payload_hash({'chapter_id': 'chapter-1', 'challenge': True, 'release_id': 'a1-v1'}))
        self.alternate_release()
        wrong = self.post('chapters/chapter-1/checkpoint', {'request_id': 'mismatch', 'challenge': True, 'release_id': 'a1-test-next'})
        self.assertEqual(wrong.status_code, 409)
        self.assertEqual(wrong.json['error']['code'], 'course_release_mismatch')
        for invalid in (None, [], 1, '', 'unknown', 'a1-home-pilot'):
            with self.subTest(release_id=invalid):
                response = self.post('chapters/chapter-1/checkpoint', {'request_id': 'invalid', 'challenge': True, 'release_id': invalid})
                self.assertIn(response.status_code, (400, 404))
        self.assertEqual(self.state()['release_id'], 'a1-v1')

    def test_new_profile_reads_do_not_enrol_and_first_command_pins_release(self):
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('new','New','cat','UTC',1)")
            changes = conn.total_changes
            state = course.course_snapshot(conn, 'new')
            self.assertEqual(conn.total_changes, changes)
            self.assertEqual((state['release_id'], state['chapter_count'], state['completed_milestones']), ('a1-v1', 4, 0))
            self.assertIsNone(conn.execute("SELECT * FROM course_enrolments WHERE profile_id='new'").fetchone())
            course.checkpoint_start(conn, 'new', 'chapter-1', 'start', True, now=123, release_id='a1-v1')
            self.assertEqual(tuple(conn.execute("SELECT release_id,started_at,migration_source FROM course_enrolments WHERE profile_id='new'").fetchone()), ('a1-v1', 123, None))

    def test_historical_active_letter_keeps_own_edition_and_passes_cannot_leak(self):
        self.alternate_release()
        old = self.start(request_id='legacy').json
        with transaction(self.db, write=True) as conn:
            self.move_enrolment(conn)
        fresh = self.post('chapters/chapter-1/checkpoint', {'request_id': 'new', 'challenge': True, 'release_id': 'a1-test-next'}).json
        self.assertNotEqual(old['id'], fresh['id'])
        self.assertEqual(fresh['title'], 'New Chapter 1')
        read = self.client.get('/api/v1/course/checkpoints/' + old['id']).json
        self.assertEqual((read['release_id'], read['title'], read['course']['release_id']), ('a1-v1', 'Chapter 1', 'a1-test-next'))
        self.assertEqual(read['letter'], old['letter'])
        self.assertEqual(read['listening'], old['listening'])
        # Legacy receipt replay remains exactly as saved, even after enrolment.
        self.assertEqual(self.start(request_id='legacy').json, old)
        result = self.submit(old['id']).json
        self.assertTrue(result['result']['passed'])
        self.assertEqual(result['course']['completed_milestones'], 0)
        self.assertEqual(result['course']['chapters'][0]['last_attempt_id'], fresh['id'])
        with transaction(self.db) as conn:
            self.assertEqual(tuple(conn.execute('SELECT release_id,requirement_version FROM course_chapter_passes WHERE attempt_id=?', (old['id'],)).fetchone()), ('a1-v1', 'a1-checkpoint-v1'))

    def test_earned_a2_access_survives_a_later_route_with_no_new_passes(self):
        self.alternate_release()
        for number in range(1, 5):
            self.submit(self.start(f'chapter-{number}').json['id'])
        with transaction(self.db, write=True) as conn:
            self.move_enrolment(conn)
        state = self.state()
        self.assertEqual(state['unlocked_levels'], ['A1', 'A2'])
        self.assertEqual(state['completed_milestones'], 0)
        self.assertFalse(state['completed'])
        self.assertTrue(all(chapter['last_attempt_id'] is None for chapter in state['chapters']))

    def test_finishing_old_active_final_letter_awards_old_access_after_route_move(self):
        self.alternate_release()
        for number in range(1, 4):
            self.submit(self.start(f'chapter-{number}').json['id'])
        final = self.start('chapter-4').json
        with transaction(self.db, write=True) as conn:
            self.move_enrolment(conn)
        result = self.submit(final['id']).json
        self.assertTrue(result['result']['passed'])
        self.assertEqual((result['release_id'], result['course']['release_id']), ('a1-v1', 'a1-test-next'))
        self.assertEqual(result['course']['unlocked_levels'], ['A1', 'A2'])
        self.assertEqual(result['course']['completed_milestones'], 0)
        with transaction(self.db) as conn:
            self.assertEqual(tuple(conn.execute('SELECT target_level,source_release_id,source FROM course_continuation_entitlements WHERE profile_id=?', (self.pid,)).fetchone()), ('A2', 'a1-v1', 'course-completion'))


if __name__ == '__main__':
    unittest.main()
