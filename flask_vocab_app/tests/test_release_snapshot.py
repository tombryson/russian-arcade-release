"""Publication checks must exclude data even when it was accidentally tracked."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'release_snapshot.py'
SPEC = importlib.util.spec_from_file_location('release_snapshot', SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseSnapshotTests(unittest.TestCase):
    def test_account_fonts_are_explicitly_allowed_with_licences(self):
        root = SCRIPT.parent.parent
        for name in release.ACCOUNT_FONT_FILES:
            path = f'flask_vocab_app/static/fonts/{name}'
            self.assertTrue((root / path).is_file(), path)
            self.assertIsNone(release.exclusion(path), path)
        for path in ('flask_vocab_app/static/images/account/README.md',
                     'flask_vocab_app/static/images/account/LICENSE-GITHUB.txt'):
            self.assertTrue((root / path).is_file(), path)
            self.assertIsNone(release.exclusion(path), path)
        for path in ('flask_vocab_app/static/fonts/unreviewed.woff2',
                     'flask_vocab_app/static/fonts/other/golos-text-latin-400-normal.woff2'):
            self.assertIsNotNone(release.exclusion(path), path)

    def test_private_tracked_files_cannot_pass_source_allowlist(self):
        for path in ('.env', '.env.local', '.git/config', '.codex/generated_images/art.png',
                     'scripts/API_key.py', 'flask_vocab_app/credentials.json',
                     'flask_vocab_app/vocab.db', 'flask_vocab_app/vocab.db-wal',
                     'flask_vocab_app/static/media/sentence_1.mp3',
                     'flask_vocab_app/static/audio/course/learner-recording.mp3',
                     'flask_vocab_app/static/audio/course/curriculum/location-destination-listening-v1/learner-recording.mp3',
                     'flask_vocab_app/static/uploads/lesson.png', 'docs/tutor.pdf',
                     'flask_vocab_app/ui/node_modules/source.js', 'instance/config.py'):
            with self.subTest(path=path):
                self.assertIsNotNone(release.exclusion(path))

    def test_reviewed_source_and_authored_assets_are_included(self):
        for path in ('.env.example', '.github/workflows/security.yml', 'README.md',
                     'scripts/release_snapshot.py', 'flask_vocab_app/migrations/039_game_shop.sql',
                     'flask_vocab_app/ui/src/assets/barsik-shop-v1.png',
                     'flask_vocab_app/content/deliveries/map-blocks.json',
                     'flask_vocab_app/static/audio/course/manifest.json',
                     'flask_vocab_app/static/audio/course/a1-post-office-v1.mp3',
                     'flask_vocab_app/static/audio/course/curriculum/location-destination-listening-v1/manifest.json',
                     'flask_vocab_app/static/audio/course/curriculum/location-destination-listening-v1/shop-now.mp3',
                     'flask_vocab_app/static/audio/deliveries/0123456789abcdef01234567.mp3'):
            with self.subTest(path=path):
                self.assertIsNone(release.exclusion(path))

    def test_every_bundled_curriculum_and_pilot_recording_can_be_exported(self):
        root = SCRIPT.parent.parent
        audio = root / 'flask_vocab_app/static/audio/course/curriculum'
        manifests = sorted(audio.glob('*/manifest.json')) + [audio.parent / 'assessment-pilot/manifest.json']
        self.assertTrue(manifests, 'Bundled curriculum recordings must be present in source')
        expected = set()
        for manifest in manifests:
            content = json.loads(manifest.read_text())
            self.assertTrue(content['clips'])
            paths = [manifest, *(manifest.parent / f'{clip}.mp3' for clip in content['clips'])]
            for path in paths:
                expected.add(path.relative_to(root).as_posix())
                with self.subTest(path=str(path.relative_to(root))):
                    self.assertTrue(path.is_file(), 'Authored recording is missing')
                    self.assertIsNone(release.exclusion(path.relative_to(root).as_posix()))
        self.assertEqual(expected, release.CURRICULUM_AUDIO_PATHS | release.ASSESSMENT_PILOT_AUDIO_PATHS)

    def test_authored_sequence_sources_are_exported_without_broadening_data_policy(self):
        root = SCRIPT.parent.parent
        for directory in ('curriculum_sequences', 'curriculum_sequence_assets', 'curriculum_coverage'):
            paths = sorted((root / 'flask_vocab_app/data' / directory).glob('*.json'))
            self.assertTrue(paths, directory)
            for path in paths:
                with self.subTest(path=path.name):
                    self.assertIsNone(release.exclusion(path.relative_to(root).as_posix()))
        for filename in ('credentials.json', 'token.json', 'responses.db', 'responses.csv'):
            self.assertIsNotNone(release.exclusion(f'flask_vocab_app/data/curriculum_sequence_assets/{filename}'))

    def test_curriculum_audio_allowlist_does_not_admit_unreviewed_recordings(self):
        prefix = 'flask_vocab_app/static/audio/course/curriculum'
        for path in (
            f'{prefix}/objects-recipients-listening-v1/learner-recording.mp3',
            f'{prefix}/possession-absence-listening-v1/learner-recording.mp3',
            f'{prefix}/objects-recipients-listening-v1/borrowed-key.mp3',
            f'{prefix}/learner-listening-v1/manifest.json',
            f'{prefix}/learner-listening-v1/borrowed-key.mp3',
            f'{prefix}/location-destination-sequence-v1/learner-recording.mp3',
            f'{prefix}/location-destination-sequence-v1/' + '0' * 64 + '.mp3',
            f'{prefix}/location-destination-sequence-v2/manifest.json',
            f'{prefix}/action-aspect-listening-v1/learner-recording.mp3',
            f'{prefix}/basic-motion-listening-v1/dinner-progress.mp3',
            'flask_vocab_app/static/audio/course/assessment-pilot/learner-recording.mp3',
            'flask_vocab_app/static/audio/course/assessment-pilot/a1-pilot-c-v1.mp3',
            'flask_vocab_app/static/audio/course/assessment-pilot/a1-pilot-a-v2.mp3',
            'flask_vocab_app/static/audio/course/assessment-pilot/recordings/a1-pilot-a-v1.mp3',
        ):
            with self.subTest(path=path):
                self.assertIsNotNone(release.exclusion(path))

    def test_first_steps_audio_export_is_limited_to_authored_recordings(self):
        from services.first_steps_audio import authored_clips
        paths = {'flask_vocab_app' + url for url in authored_clips()}
        paths.add('flask_vocab_app/static/audio/first-steps-v2/manifest.json')
        self.assertEqual(paths, release.FIRST_STEPS_AUDIO_PATHS)
        for path in paths:
            self.assertTrue((SCRIPT.parent.parent / path).is_file())
            self.assertIsNone(release.exclusion(path))
        self.assertIsNotNone(release.exclusion('flask_vocab_app/static/audio/first-steps-v2/learner-recording.mp3'))

    def test_export_refuses_to_follow_file_or_directory_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'source.txt').write_text('test')
            (root / 'link.txt').symlink_to(root / 'source.txt')
            (root / 'linked-dir').symlink_to(root, target_is_directory=True)
            for path in ('link.txt', 'linked-dir/source.txt'):
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Symlink'):
                    release.read_file(root, path)

    def test_changed_source_cannot_be_exported_under_an_old_scan_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'source'
            root.mkdir()
            (root / 'README.md').write_text('changed after scan')
            report = {'files': [{'path': 'README.md', 'sha256': hashlib.sha256(b'old').hexdigest(), 'executable': False}]}
            with self.assertRaisesRegex(ValueError, 'Source changed during export'):
                release.copy_snapshot(root, Path(temp) / 'export', report)

    def test_existing_checkout_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(FileExistsError):
                release.copy_snapshot(root, root, {'files': []})
