#!/usr/bin/env python3
"""Prepare a checked database artifact. Does not access or deploy to Fly.io."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask_vocab_app'))
from services.account_import import build_account_import


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', required=True, type=Path, help='Offline local SQLite snapshot')
    parser.add_argument('--hosted', required=True, type=Path, help='Offline snapshot of the intended private account')
    parser.add_argument('--output', required=True, type=Path, help='New artifact path; never a live database')
    parser.add_argument('--report', required=True, type=Path, help='New JSON report path')
    parser.add_argument('--local-audio-root', type=Path,
                        help='Original live-conversation-audio directory; required for saved speaking criterion evidence')
    parser.add_argument('--local-pilot-audio-root', type=Path,
                        help='Original assessment-pilot-audio directory; required for pilot Speaking recordings')
    args = parser.parse_args()
    if args.report.exists():
        parser.error('Report path already exists.')
    report = build_account_import(args.local, args.hosted, args.output, local_audio_root=args.local_audio_root,
                                  local_pilot_audio_root=args.local_pilot_audio_root)
    with args.report.open('x') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write('\n')
    args.report.chmod(0o600)
    print('Prepared and checked the database artifact. Media and deployment remain separate.')


if __name__ == '__main__':
    main()
