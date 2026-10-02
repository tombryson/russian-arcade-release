#!/usr/bin/env python3
"""Prepare a source-only public release without copying private Git history.

The default command only reports. --output creates a new, separate directory;
it never updates an existing checkout, commits, pushes or copies .git. --scan
checks an isolated temporary snapshot with Gitleaks and redacts its output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile


ROOT_FILES = {
    '.dockerignore', '.env.example', '.gitignore', '.nvmrc', '.python-version',
    'Dockerfile', 'fly.toml', 'README.md', 'SECURITY.md', 'LICENSE', 'LICENSE.md',
    'flask_vocab_app/.gitignore', 'flask_vocab_app/ui/.gitignore',
}
PRIVATE_PARTS = {
    '.git', '.codex', '.venv', 'venv', 'env', 'node_modules', 'dist',
    '__pycache__', 'instance', 'flask_session', 'uploads', 'recordings',
    'anki_audio', 'anki_audio_english', 'anki_sentence_audio', 'anki_images',
}
SOURCE_EXTENSIONS = {'.py', '.sql', '.html', '.css', '.js', '.mjs', '.ts', '.tsx', '.jsx', '.json'}
IMAGE_EXTENSIONS = {'.svg', '.png', '.jpg', '.webp', '.ico'}
CODE_DIRS = {'blueprints', 'contracts', 'migrations', 'models', 'repositories', 'services', 'templates', 'tests', 'utils'}
ACCOUNT_FONT_FILES = {
    'golos-text-latin-400-normal.woff2', 'golos-text-latin-500-normal.woff2',
    'unbounded-latin-500-normal.woff2', 'google-sans-latin-500-normal.woff2',
    'golos-text-OFL.txt', 'unbounded-OFL.txt', 'google-sans-OFL.txt',
}
# Exact reviewed bundles, never a directory or hash-pattern allowance: adding a
# local recording or editing a media manifest cannot make it public by itself.
CURRICULUM_AUDIO = {
    'action-aspect-listening-v1': ('dinner-progress', 'reading-update', 'future-letter'),
    'basic-motion-listening-v1': ('rainy-journey', 'walk-after-station', 'weekend-trips'),
    'connected-messages-listening-v1': ('meeting-change', 'who-will-call', 'why-wait'),
    'location-destination-listening-v1': ('shop-now', 'after-pharmacy', 'inside-museum'),
    'location-destination-sequence-v1': (
        '1b77b14ae77b021511ef0b5b91b8e583b3d14b5e927cf170238064509afab6ee',
        'c4a03c3fb2e4008825b22f113012c2c3b88e78806f4cdba2a3691f687afc4a89',
        'dcbb702e0f95833cea7d659f919d2a26ea93862e879497fb415c5fd3a7ce51ef',
        '1156015bd4c3feaf0ccaf83858e8e48caf352d8abfb50e972b9f144fe74b31ef',
        'aeb8d578385e611f30bbe22b272f0d6b6fb30cec3ef59271bf324643910d7183',
        '91fa9a41493f42f925f13fffc30c580ede933f42e01a5f4b251f2e104d63103d',
        '82877f2e2c0a32a21ba7ea9b0d7a9212c230524f25628a977789af4237003e56',
        'd95379582948e65f0f034b2291266470145324843cfa54ff4fc485c7ca9ee3f4',
        'c31b0a45c10b1f3944721c48c43bde5953c76f93fbddf6b6d86544246438afce',
        'dc005dbdbea20cb070618e9ffc965b59a758c0a36765c47d5a7962c3be844a98',
        'd9bf2fa46769708533be6f7c262a631504fe80ffe8f8974143399d9d3bf3a05c',
        '382671aa50450d1938c218d56787e149fe658594920ff6cf69add474aa6a42e1',
        'bd73b9ee949f4b450c4beb4768bfc22910df986ddf7164420cd36305ca9e5843',
        '2abd4b87aa59ad8cf79fd769db943e096c2b5bacefde024d0cb81d1fadd14733',
        '9da224d32723d1b0239b5a5b69b56873bbd6b151452d82821449b896eef0169f',
        '2bf4a4fd87f085e9165ff6f05e8cff396bf325b2a6ec4b74cab6409db5bf3f5f',
        'b98c1ee4c397e0d46f4cc74745eab363e245f5d32fda920dc609f3a216e13daf',
        'b32049f0c4a37026057ecd5b9dfda0aab2184c352a57ce965050cc3795283628',
        '58d83fe3242766466730163a783c41b230a01b030a4916f167d666f6b99dc571',
    ),
    'needs-company-listening-v1': ('who-is-cold', 'visit-companion', 'drink-ingredient'),
    'noun-adjective-agreement-listening-v1': ('scarf-left-behind', 'coat-shopping', 'shoes-for-walk'),
    'numbers-quantities-listening-v1': ('changed-order', 'ticket-price', 'lesson-order'),
    'objects-recipients-listening-v1': ('hand-over-envelope', 'ticket-recipient', 'two-purchases'),
    'origins-and-destinations-listening-v1': ('after-doctor', 'leaving-sister', 'after-work'),
    'personal-reference-listening-v1': ('sister-waits', 'book-owner', 'help-neighbour'),
    'possession-absence-listening-v1': ('picnic-call', 'borrowed-key', 'borrowed-umbrella'),
    'social-exchanges-listening-v1': ('repeat-time', 'decline-drink', 'permission-pen'),
    'time-routine-listening-v1': ('changed-visit', 'class-day', 'evening-order'),
}
CURRICULUM_AUDIO_PATHS = {
    f'flask_vocab_app/static/audio/course/curriculum/{unit}/{filename}'
    for unit, clips in CURRICULUM_AUDIO.items()
    for filename in ('manifest.json', *(f'{clip}.mp3' for clip in clips))
}
ASSESSMENT_PILOT_AUDIO_PATHS = {
    f'flask_vocab_app/static/audio/course/assessment-pilot/{filename}'
    for filename in ('manifest.json', 'a1-pilot-a-v1.mp3', 'a1-pilot-b-v1.mp3')
}
FIRST_STEPS_AUDIO = {
    'hello': ('word-hello', 'word-letter-r2', 'word-thanks'),
    'bag': ('letter', 'bag', 'house', 'map', 'listen-object'),
    'introductions': ('name', 'ask', 'exchange', 'listen-name'),
    'gender': ('groups', 'masculine', 'feminine', 'neuter'),
    'ownership': ('masculine', 'feminine', 'neuter', 'worked', 'listen-exchange'),
}
FIRST_STEPS_AUDIO_PATHS = {'flask_vocab_app/static/audio/first-steps-v2/manifest.json'} | {
    f'flask_vocab_app/static/audio/first-steps-v2/{lesson}-{clip}.mp3'
    for lesson, clips in FIRST_STEPS_AUDIO.items() for clip in clips
}


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True)


def candidates(root: Path) -> list[str]:
    return sorted(set(git(root, 'ls-files', '-co', '--exclude-standard', '-z').split('\0')) - {''})


def exclusion(path: str) -> str | None:
    """Classify a path before opening it; tracked private files are still denied."""
    p = PurePosixPath(path)
    parts, name = p.parts, p.name.lower()
    if p.is_absolute() or '..' in parts or not parts:
        return 'invalid path'
    if any(part.lower() in PRIVATE_PARTS for part in parts):
        return 'private or generated directory'
    if (name.startswith('.env') and path != '.env.example') or name in {
        'api_key.py', 'credentials.json', 'token.json', 'vocab-list.txt', 'anki_flashcards.txt',
    }:
        return 'secret or personal data'
    if re.search(r'\.(?:db(?:[-_.].*)?|sqlite3?|bak|pem|key|p12|pfx|pdf|docx?|xlsx?|csv|log|pyc)$', name):
        return 'private data or runtime artifact'
    if path in ROOT_FILES:
        return None
    if path.startswith('.github/workflows/') and p.suffix in {'.yml', '.yaml'}:
        return None
    if parts[0] == 'docs' and p.suffix in {'.md', '.json', *IMAGE_EXTENSIONS}:
        return None
    if parts[0] == 'scripts' and p.suffix == '.py':
        return None
    if parts[0] != 'flask_vocab_app' or len(parts) < 2:
        return 'outside reviewed source locations'
    if len(parts) == 2 and (p.suffix == '.py' or p.name in {'requirements.txt', 'requirements.lock'}):
        return None
    if parts[1] in CODE_DIRS and p.suffix in SOURCE_EXTENSIONS:
        return None
    if parts[1] in {'content', 'data'} and p.suffix == '.json':
        return None
    if parts[1] == 'ui':
        if len(parts) == 3 and p.name in {'package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts', 'README.md'}:
            return None
        if len(parts) > 3 and parts[2] in {'src', 'scripts'} and p.suffix in SOURCE_EXTENSIONS | IMAGE_EXTENSIONS:
            return None
        if len(parts) > 3 and parts[2] == 'public' and p.suffix in IMAGE_EXTENSIONS | {'.txt'}:
            return None
    if path.startswith('flask_vocab_app/static/css/') and p.suffix == '.css':
        return None
    if path.startswith('flask_vocab_app/static/js/') and p.suffix == '.js':
        return None
    if path.startswith('flask_vocab_app/static/images/') and p.suffix in IMAGE_EXTENSIONS:
        return None
    if path in {'flask_vocab_app/static/images/account/README.md',
                'flask_vocab_app/static/images/account/LICENSE-GITHUB.txt'}:
        return None
    if path.startswith('flask_vocab_app/static/fonts/') and p.name in ACCOUNT_FONT_FILES and len(parts) == 4:
        return None
    if path == 'flask_vocab_app/static/audio/deliveries/manifest.json' or re.fullmatch(
        r'flask_vocab_app/static/audio/deliveries/[0-9a-f]{24}\.mp3', path
    ):
        return None
    if path == 'flask_vocab_app/static/audio/course/manifest.json' or re.fullmatch(
        r'flask_vocab_app/static/audio/course/a1-(?:post-office|home|market|delivery)-v[1-9][0-9]*\.mp3', path
    ):
        return None
    if path == 'flask_vocab_app/static/audio/course/milestones-manifest.json' or re.fullmatch(
        r'flask_vocab_app/static/audio/course/(?:a1-journey-v2|a1-targets-v1)/[a-z0-9-]+\.mp3', path
    ):
        return None
    if path in CURRICULUM_AUDIO_PATHS or path in ASSESSMENT_PILOT_AUDIO_PATHS:
        return None
    if path in FIRST_STEPS_AUDIO_PATHS:
        return None
    return 'outside reviewed source locations'


def read_file(root: Path, relative: str) -> tuple[bytes, int]:
    path = root / relative
    # Reject links at every level, including directory links outside the root.
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f'Symlink is not exportable: {relative}')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f'Not a regular file: {relative}')
        return source.read(), metadata.st_mode


def inspect(root: Path) -> dict:
    included, excluded = [], []
    for relative in candidates(root):
        reason = exclusion(relative)
        if reason:
            excluded.append({'path': relative, 'reason': reason})
            continue
        if not (root / relative).exists():
            excluded.append({'path': relative, 'reason': 'removed from working tree'})
            continue
        data, mode = read_file(root, relative)
        included.append({'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                         'executable': bool(mode & stat.S_IXUSR)})
    digest = hashlib.sha256(json.dumps(included, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'format': 1, 'source_commit': git(root, 'rev-parse', 'HEAD').strip(),
            'snapshot_sha256': digest, 'files': included, 'excluded': excluded,
            'total_bytes': sum(row['bytes'] for row in included)}


def copy_snapshot(root: Path, output: Path, report: dict) -> None:
    output.mkdir(parents=True, exist_ok=False)
    for entry in report['files']:
        data, _mode = read_file(root, entry['path'])
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f"Source changed during export; discard and retry: {entry['path']}")
        target = output / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o755 if entry['executable'] else 0o644)


def compare(report: dict, checkout: Path) -> dict:
    previous = set(git(checkout, 'ls-files', '-z').split('\0')) - {''}
    current = {row['path']: row for row in report['files']}
    changed = []
    for relative in sorted(previous & current.keys()):
        data, _mode = read_file(checkout, relative)
        if hashlib.sha256(data).hexdigest() != current[relative]['sha256']:
            changed.append(relative)
    return {'added': sorted(current.keys() - previous), 'changed': changed, 'omitted': sorted(previous - current.keys())}


def scan(root: Path, report: dict, binary: str) -> dict:
    with tempfile.TemporaryDirectory(prefix='russian-arcade-release-scan-') as temp:
        stage = Path(temp) / 'source'
        copy_snapshot(root, stage, report)
        result = subprocess.run([binary, 'dir', str(stage), '--redact=100', '--ignore-gitleaks-allow',
                                 '--no-banner', '--report-format=json', '--report-path', str(Path(temp) / 'findings.json')],
                                text=True, capture_output=True)
        findings_path = Path(temp) / 'findings.json'
        findings = json.loads(findings_path.read_text()) if findings_path.exists() else []
        # Only report locations/rules. Neither scanner logs nor matched values leave this function.
        return {'status': 'passed' if result.returncode == 0 else 'failed', 'exit_code': result.returncode,
                'findings': [{'rule': row.get('RuleID'), 'path': row.get('File'), 'line': row.get('StartLine')}
                             for row in findings]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--compare', type=Path, help='Read-only comparison with the clean public checkout')
    parser.add_argument('--output', type=Path, help='Create a NEW staging directory; existing directories are refused')
    parser.add_argument('--report', type=Path, help='Write the manifest/report outside the source tree')
    parser.add_argument('--scan', action='store_true', help='Require a redacted Gitleaks scan before export')
    parser.add_argument('--gitleaks', default=shutil.which('gitleaks'), help='Path to a verified Gitleaks binary')
    args = parser.parse_args()
    root = args.source.resolve()
    if args.output and args.output.exists():
        parser.error('--output must be a new directory, never an existing checkout')
    if args.output and args.output.resolve().is_relative_to(root):
        parser.error('--output must stay outside the source tree')
    if args.output and not args.scan:
        parser.error('--output requires --scan before files can be exported')
    if args.report and (args.report.resolve().is_relative_to(root) or
                        args.output and args.report.resolve().is_relative_to(args.output.resolve())):
        parser.error('--report must stay outside the source and exported trees')
    if args.scan and not args.gitleaks:
        parser.error('Gitleaks is required for --scan; supply --gitleaks')
    report = inspect(root)
    if args.compare:
        report['comparison'] = compare(report, args.compare.resolve())
    if args.scan:
        report['secret_scan'] = scan(root, report, args.gitleaks)
    else:
        report['secret_scan'] = {'status': 'not run'}
    if args.output and report['secret_scan']['status'] != 'failed':
        copy_snapshot(root, args.output.resolve(), report)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'files': len(report['files']), 'excluded': len(report['excluded']),
                      'bytes': report['total_bytes'], 'snapshot_sha256': report['snapshot_sha256'],
                      'secret_scan': report['secret_scan'],
                      'comparison': {key: len(value) for key, value in report.get('comparison', {}).items()},
                      'exported': bool(args.output and report['secret_scan']['status'] != 'failed')}, indent=2))
    return 1 if report['secret_scan']['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
