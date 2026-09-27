"""Read-only course inventory and optional migration rehearsal on a DB copy.

Reports counts, never learner names, answers or credentials. The original
database is opened read-only and is never upgraded by this command.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask_vocab_app'))
KNOWN = {'a1-v1': {'a1-post-office', 'a1-home', 'a1-market', 'a1-delivery'},
         'a1-journey-v2': {'home', 'postoffice', 'market', 'leavingtown'}}
PRESERVE = ('course_checkpoint_attempts', 'course_checkpoint_requests', 'course_checkpoint_submissions',
            'course_chapter_passes', 'course_evidence', 'course_continuation_entitlements',
            'course_enrolments', 'course_target_observations', 'course_target_practice_attempts',
            'course_target_practice_requests', 'course_target_practice_receipts',
            'course_release_switches', 'course_checkpoint_followups',
            'activity_task_contracts', 'activity_criterion_reports', 'learning_item_support',
            'comprehension_tasks', 'comprehension_attempts', 'comprehension_support_receipts',
            'translation_attempts', 'word_jumble_attempts', 'translation_reference_views',
            'assessment_pilot_sessions', 'assessment_pilot_components', 'assessment_pilot_support',
            'assessment_pilot_submissions', 'assessment_pilot_reviews', 'assessment_pilot_requests')


def inventory(conn, *, pilot_audio_root=None):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    result = {'schema': conn.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0],
              'counts': {name: conn.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in PRESERVE if name in tables},
              'foreign_key_errors': len(conn.execute('PRAGMA foreign_key_check').fetchall()),
              'integrity_errors': sum(row[0] != 'ok' for row in conn.execute('PRAGMA integrity_check')),
              'unknown_sections': 0, 'unknown_preparations': 0, 'invalid_comprehension_evidence': 0,
              'invalid_production_evidence': 0, 'invalid_assessment_pilot_evidence': 0}
    if any(name.startswith('assessment_pilot_') for name in tables):
        from services.assessment_pilot_integrity import validate_saved_pilot
        try:
            validate_saved_pilot(conn, audio_root=pilot_audio_root)
        except (OSError, ValueError, LookupError, TypeError, KeyError, wave.Error, EOFError):
            result['invalid_assessment_pilot_evidence'] = 1
    if 'comprehension_tasks' in tables:
        from services.activity_evidence import _validate_comprehension_evidence
        try:
            _validate_comprehension_evidence(conn)
        except (ValueError, LookupError, TypeError, KeyError):
            result['invalid_comprehension_evidence'] = 1
    if 'translation_reference_views' in tables:
        from services.production_evidence import validate_saved_evidence, saved_response
        from services.activity_evidence import save_report
        try:
            validate_saved_evidence(conn)
            rows = conn.execute('SELECT r.id,r.profile_id,c.activity,c.task_key,r.source_key '
                                'FROM activity_criterion_reports r JOIN activity_task_contracts c '
                                "ON c.id=r.contract_id AND c.profile_id=r.profile_id WHERE c.activity IN ('translation','word_jumble')").fetchall()
            for identity, profile, activity, task_key, source_key in rows:
                response, report, support = saved_response(conn, profile, activity, task_key, source_key)
                # This record already exists. The idempotency check only
                # compares its original response digest and frozen report.
                if save_report(conn, profile, activity, task_key, source_key, report,
                               response_text=response, support=support) != identity:
                    raise ValueError('Production evidence changed identity.')
        except (ValueError, LookupError, TypeError, KeyError):
            result['invalid_production_evidence'] = 1
    if 'course_checkpoint_attempts' in tables:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(course_checkpoint_attempts)')}
        release = 'release_id' if 'release_id' in columns else "'a1-v1'"
        result['active_attempts'] = conn.execute("SELECT COUNT(*) FROM course_checkpoint_attempts WHERE status='active'").fetchone()[0]
        for edition, section in conn.execute('SELECT ' + release + ',chapter_id FROM course_checkpoint_attempts'):
            if section not in KNOWN.get(edition, set()):
                result['unknown_sections'] += 1
    if 'course_target_practice_attempts' in tables:
        from repositories.learning_repository import LearningError
        from services.course_targets import _practice_context, CATALOGUE_VERSION, PREPARATION_RELEASE
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        for row in cursor.execute('SELECT * FROM course_target_practice_attempts'):
            saved = {'release_id': PREPARATION_RELEASE, 'target_catalogue_version': CATALOGUE_VERSION,
                     'target_snapshot_json': None, **dict(row)}
            try:
                _practice_context(saved)
            except (LearningError, ValueError, TypeError, KeyError):
                result['unknown_preparations'] += 1
    return result


def digest(conn, table, columns):
    rows = conn.execute('SELECT ' + ','.join('"' + c + '"' for c in columns) + ' FROM ' + table).fetchall()
    return hashlib.sha256(json.dumps(sorted([list(r) for r in rows], key=repr), ensure_ascii=False, default=str).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--rehearse', action='store_true')
    parser.add_argument('--pilot-audio-root', type=Path,
                        help='Optionally verify original pilot recordings and frozen review WAVs as well as database bindings.')
    args = parser.parse_args()
    if not args.db.is_file():
        raise SystemExit('Database not found.')
    with sqlite3.connect(args.db.resolve().as_uri() + '?mode=ro', uri=True) as source:
        report = inventory(source, pilot_audio_root=args.pilot_audio_root)
        if any(report[key] for key in ('foreign_key_errors', 'integrity_errors', 'unknown_sections', 'unknown_preparations',
                                      'invalid_comprehension_evidence', 'invalid_production_evidence', 'invalid_assessment_pilot_evidence')):
            print(json.dumps(report, indent=2))
            raise SystemExit('Resolve course integrity findings before release.')
        if args.rehearse:
            snapshots = {}
            for table in report['counts']:
                columns = [row[1] for row in source.execute('PRAGMA table_info(' + table + ')')]
                snapshots[table] = columns, digest(source, table, columns)
            with tempfile.TemporaryDirectory(prefix='arcade-course-rehearsal-') as directory:
                copy = Path(directory) / 'copy.db'
                with sqlite3.connect(copy) as destination:
                    source.backup(destination)
                from migrations import upgrade_database
                version, _ = upgrade_database(str(copy), backup=False)
                with sqlite3.connect(copy) as migrated:
                    retained = all(digest(migrated, table, columns) == expected for table, (columns, expected) in snapshots.items())
                    report['rehearsal'] = {'schema': version, 'existing_course_rows_unchanged': retained,
                                           'foreign_key_errors': len(migrated.execute('PRAGMA foreign_key_check').fetchall())}
                    if not retained or report['rehearsal']['foreign_key_errors']:
                        raise SystemExit('Migration rehearsal failed; original database is unchanged.')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
