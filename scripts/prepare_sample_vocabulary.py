"""Prepare public sample vocabulary through the application's import pipeline.

Runs only on a maintainer's machine, against a temporary database. The resulting
topics and mnemonics are shipped with the demo; startup never calls a provider.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_vocab_app'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, help='Existing local credentials file; never copied into the output.')
    parser.add_argument('--settings', type=Path, help='Existing application settings overrides.')
    parser.add_argument('--output', type=Path, default=ROOT / 'flask_vocab_app/data/sample_vocabulary.json')
    args = parser.parse_args(argv)
    if args.env_file:
        from dotenv import load_dotenv
        if not args.env_file.is_file():
            parser.error('The credentials file does not exist.')
        load_dotenv(args.env_file)

    from flask import Flask
    from config import app_config
    from migrations import upgrade_database
    from repositories.learning_repository import transaction
    from services.first_steps import HELLO, chapter_content
    from services.lesson_cards import LessonCards
    from services.sync_service import SyncService

    settings = app_config()
    if args.settings:
        settings.update(json.loads(args.settings.read_text()))
    if not settings.get('OPENAI_API_KEY'):
        raise SystemExit('OPENAI_API_KEY is missing. No files or settings were changed.')
    app = Flask(__name__)
    app.config.update(settings)
    with tempfile.TemporaryDirectory(prefix='arcade-sample-vocabulary-') as directory:
        database = str(Path(directory) / 'vocab.db')
        upgrade_database(database, backup=False)
        with transaction(database, write=True) as conn:
            for lesson in [HELLO, *chapter_content()['lessons']]:
                for word in lesson['vocabulary']:
                    LessonCards.resolve(conn, {**word, 'surface': word['form']})
        pipeline = SyncService(database, drive_service=object(), api_key=settings['OPENAI_API_KEY'], config=settings)
        with app.app_context():
            result = pipeline.enrich_words()
        if result['pending']:
            raise SystemExit(f"{len(result['pending'])} sample words remain incomplete. The previous fixture was preserved.")
        with transaction(database) as conn:
            words = [dict(lemma=row['lemma'], pos=row['pos'], topics=json.loads(row['topic']), mnemonic=row['mnemonic'])
                     for row in conn.execute('SELECT lemma,pos,topic,mnemonic FROM words ORDER BY lemma,pos')]
        payload = {
            'schema_version': 1,
            'pipeline': 'SyncService.process_word + SyncService.enrich_words',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'models': {'topics': settings['OPENAI_MODEL_FAST'], 'mnemonics': settings['OPENAI_MODEL_HIGH']},
            'words': words,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=args.output.parent, encoding='utf-8', delete=False) as handle:
            temporary = Path(handle.name)
            try:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
                handle.close()
                temporary.replace(args.output)
            finally:
                temporary.unlink(missing_ok=True)
        print(f'Saved {len(words)} complete sample entries to {args.output}. No personal database was read or modified.')


if __name__ == '__main__':
    main()
