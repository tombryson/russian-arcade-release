"""Scoped sentence observations preserve tutor feedback, originals and ownership."""
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from contracts.curriculum import freeze_task_contract
from repositories.translation_repository import TranslationRepository, TranslationConflict
from services.production_evidence import (translation_contract, jumble_contract, production_report,
    owned_task, saved_response, validate_saved_evidence)
from services.sentence_service import SentenceService, TranslationUnavailable
from services.word_jumble_service import WordJumbleService, AssessmentUnavailable, DraftConflict
from tests.support import isolated_app


def translation_task():
    return {'sentence': 'Я живу в Москве.', 'english': 'I live in Moscow.', 'topic': 'home', 'difficulty': 1}


def translation_focus():
    return {'requirement_id': 'a1.language.neutral-word-order', 'english_excerpt': 'I live in Moscow.',
            'russian_excerpt': 'Я живу в Москве.', 'expectation': 'State who lives where, accepting natural Russian word order.'}


def report_for(contract, answer, *, outcome='satisfied'):
    return {'contract_sha256': contract['contract_sha256'], 'judgements': [{
        'criterion_id': 'language-focus', 'outcome': outcome,
        'score': None if outcome == 'insufficient_evidence' else 2,
        'feedback': 'Your response expresses the requested relationship.',
        'evidence': [] if outcome == 'insufficient_evidence' else [{'quote': answer, 'start': 0, 'end': len(answer)}]}]}


def translation_feedback(contract, answer):
    return {'score': 4, 'strength': 'The meaning is clear.', 'next_step': 'Try another sentence.',
            'example': 'Я живу в Москве.', 'criterion_report': report_for(contract, answer)}


def tutor_feedback(contract, answer):
    return {'score': 4, 'commentary': 'You connected the two events clearly.', 'corrections': [],
            'polished_sentence': '', 'phrasing_note': '', 'extension': '',
            'criterion_report': report_for(contract, answer)}


class SentenceProductionTests(unittest.TestCase):
    def setUp(self):
        self.jumble = WordJumbleService.__new__(WordJumbleService)
        self.translation = Mock(spec=SentenceService)
        self.app = isolated_app(self, {'WordJumbleService': self.jumble, 'SentenceService': self.translation})
        self.db = self.app.config['DB_PATH']
        self.jumble.db_path = self.db
        self.jumble.client = Mock()
        self.repo = TranslationRepository(self.db)
        self.client = self.app.test_client()
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']
        self.task = translation_task()
        self.contract = translation_contract(self.task, translation_focus(), 'home')
        self.id, _ = self.repo.save_content(**self.task, curriculum_contract=self.contract)

    def count(self, table):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def test_translation_freezes_before_answer_and_keeps_original_alternative(self):
        answer = '  В Москве я живу.\n'
        self.repo.save_check(self.id, answer, 0, translation_feedback(self.contract, answer), 'en')
        item = self.repo.load(self.id)
        self.assertEqual(item['curriculum_contract'], self.contract)
        self.assertEqual(item['attempts'][0]['response'], answer)
        self.assertEqual(item['attempts'][0]['criterion_support'], [])
        self.assertEqual(item['attempts'][0]['criterion_report'], report_for(self.contract, answer))
        self.assertEqual(item['attempts'][0]['score'], 4)
        self.assertEqual(self.count('activity_criterion_reports'), 1)
        with sqlite3.connect(self.db) as conn:
            validate_saved_evidence(conn)
        html = self.client.get(f'/sentences/practice/{self.id}').text
        self.assertIn('What this response shows', html)
        self.assertNotIn('a1.language.neutral-word-order', html)

    def test_translation_retry_records_prior_feedback_and_stale_revision_cannot_duplicate(self):
        answer = 'Я живу в Москве.'
        self.repo.save_check(self.id, answer, 0, translation_feedback(self.contract, answer), 'en')
        self.repo.save_check(self.id, answer, 1, translation_feedback(self.contract, answer), 'en')
        self.assertEqual(self.repo.load(self.id)['attempts'][0]['criterion_support'], ['model_answer'])
        with self.assertRaises(TranslationConflict):
            self.repo.save_check(self.id, answer, 1, translation_feedback(self.contract, answer), 'en')
        self.assertEqual(self.count('translation_attempts'), 2)
        self.assertEqual(self.count('activity_criterion_reports'), 2)

    def test_invalid_report_rolls_back_draft_attempt_reward_and_shared_report(self):
        before = self.count('progression_entries')
        assessment = translation_feedback(self.contract, 'Я живу в Москве.')
        assessment['criterion_report']['judgements'][0]['evidence'][0]['quote'] = 'corrected response'
        with self.assertRaises(ValueError):
            self.repo.save_check(self.id, 'Я живу в Москве.', 0, assessment, 'en')
        self.assertEqual(self.repo.load(self.id)['revision'], 0)
        self.assertEqual(self.count('translation_attempts'), 0)
        self.assertEqual(self.count('activity_criterion_reports'), 0)
        self.assertEqual(self.count('progression_entries'), before)

    def test_dedup_does_not_attach_new_criteria_to_legacy_pair(self):
        other = dict(self.task, english='I live here.')
        identity, _ = self.repo.save_content(**other)
        focus = dict(translation_focus(), english_excerpt=other['english'])
        frozen = translation_contract(other, focus, 'home')
        duplicate, created = self.repo.save_content(**other, curriculum_contract=frozen)
        self.assertEqual(identity, duplicate)
        self.assertFalse(created)
        self.assertIsNone(self.repo.load(identity)['curriculum_contract'])
        with self.assertRaises(ValueError):
            self.repo.save_check(identity, 'Я здесь живу.', 0, translation_feedback(frozen, 'Я здесь живу.'), 'en')

    def test_task_change_profile_crosslink_and_tampered_support_are_rejected(self):
        answer = 'Я живу в Москве.'
        self.repo.save_check(self.id, answer, 0, translation_feedback(self.contract, answer), 'en')
        aid = self.repo.load(self.id)['attempts'][0]['id']
        with sqlite3.connect(self.db) as conn:
            with self.assertRaises(LookupError):
                owned_task(conn, 'another-profile', 'translation', str(self.id))
            with self.assertRaises(ValueError):
                saved_response(conn, 'personal-learning', 'translation', str(self.id), str(aid + 1))
            conn.execute("UPDATE translation_attempts SET criterion_support_json='[\"model_answer\"]' WHERE id=?", (aid,))
            with self.assertRaises(ValueError):
                validate_saved_evidence(conn)
            conn.rollback()
            conn.execute("UPDATE sentences SET english='A different task' WHERE id=?", (self.id,))
            with self.assertRaises(ValueError):
                validate_saved_evidence(conn)

    def test_missing_report_and_orphan_attempt_evidence_fail_import_validation(self):
        answer = 'Я живу в Москве.'
        self.repo.save_check(self.id, answer, 0, translation_feedback(self.contract, answer), 'en')
        with sqlite3.connect(self.db) as conn:
            conn.execute('DELETE FROM activity_criterion_reports')
            with self.assertRaises(ValueError):
                validate_saved_evidence(conn)
            conn.rollback()
            conn.execute('DELETE FROM activity_task_contracts')
            with self.assertRaises(ValueError):
                validate_saved_evidence(conn)

    def test_translation_route_uses_saved_contract_and_rejects_profile_change_before_commit(self):
        answer = 'Я живу в Москве.'
        self.translation.assess_translation.return_value = translation_feedback(self.contract, answer)
        result = self.client.post('/sentence/assess', data={'sentence_id': self.id, 'revision': 0,
            'user_response': answer, 'curriculum_contract': 'forged'}, headers={'Accept': 'application/json'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.translation.assess_translation.call_args.kwargs['curriculum_contract'], self.contract)
        with self.assertRaises(TranslationConflict):
            self.repo.save_check(self.id, answer, 1, translation_feedback(self.contract, answer), 'en', expected_profile='other')
        self.assertEqual(self.count('translation_attempts'), 1)

    def test_phrasebook_reference_receipts_cover_only_visible_rows_and_preserve_earlier_attempts(self):
        self.assertEqual(self.client.get('/sentences/saved?q=not-present').status_code, 200)
        self.assertEqual(self.count('translation_reference_views'), 0)
        self.assertEqual(self.client.get(f'/sentences/practice/{self.id}').status_code, 200)
        self.assertEqual(self.count('translation_reference_views'), 0)
        answer = 'Я живу в Москве.'
        self.repo.save_check(self.id, answer, 0, translation_feedback(self.contract, answer), 'en')
        first = self.repo.load(self.id)['attempts'][0]['id']
        self.assertEqual(self.client.get('/sentences/saved?q=Moscow').status_code, 200)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT after_attempt_id FROM translation_reference_views').fetchone()[0], first)
            validate_saved_evidence(conn)
        self.repo.save_check(self.id, answer, 1, translation_feedback(self.contract, answer), 'en')
        self.assertEqual(self.client.get(f'/sentences/saved/{self.id}').status_code, 200)
        attempts = self.repo.load(self.id)['attempts']
        self.assertEqual(attempts[0]['criterion_support'], ['model_answer'])
        self.assertEqual(attempts[1]['criterion_support'], [])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT after_attempt_id FROM translation_reference_views').fetchone()[0], first)
            validate_saved_evidence(conn)

    def test_reference_seen_before_first_answer_is_assistance(self):
        self.assertEqual(self.client.get(f'/sentences/saved/{self.id}').status_code, 200)
        answer = 'Я живу в Москве.'
        self.repo.save_check(self.id, answer, 0, translation_feedback(self.contract, answer), 'en')
        self.assertEqual(self.repo.load(self.id)['attempts'][0]['criterion_support'], ['model_answer'])
        with sqlite3.connect(self.db) as conn:
            validate_saved_evidence(conn)
        # Returning the complete library as JSON exposes the same references.
        other = dict(self.task, english='I live in the city.')
        frozen = translation_contract(other, dict(translation_focus(), english_excerpt=other['english']), 'home')
        other_id, _ = self.repo.save_content(**other, curriculum_contract=frozen)
        self.assertEqual(self.client.get('/sentences/saved?fetch_all=true', headers={'Accept': 'application/json'}).status_code, 200)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT after_attempt_id FROM translation_reference_views WHERE sentence_id=?', (other_id,)).fetchone(), (None,))

    def test_legacy_and_first_steps_jumble_ids_keep_their_original_open_task(self):
        for game_id in ('old-game', 'a' * 32):
            with sqlite3.connect(self.db) as conn:
                conn.execute("INSERT INTO word_jumble_games(id,topic,difficulty,words,created_at,owner_profile_id) "
                             "VALUES (?, 'home', 'easy', '[\"дом\"]', '2000-01-01', 'personal-learning')", (game_id,))
            game = self.jumble.get_game(game_id)
            self.assertIsNone(game['curriculum_contract'])
            self.assertEqual(game['words'], ['дом'])

    def test_word_jumble_maps_only_visible_scopes_preserving_supplied_vocabulary(self):
        for difficulty in ('easy', 'A1'):
            self.assertIsNone(self.jumble.create_game('any', difficulty)['curriculum_contract'])
        game = self.jumble.create_game('any', 'A2')
        contract = game['curriculum_contract']
        self.assertEqual(contract['content']['words'], game['words'])
        self.assertEqual(contract['content']['task_contract'], game['task_contract'])
        criterion = contract['criteria'][0]
        self.assertEqual(criterion['requirement_id'], 'a1.language.time-and-reason-clauses')
        self.assertEqual(criterion['response_mode'], 'controlled_text')
        self.assertEqual(contract['level'], 'A2')
        self.jumble.client.responses.create.assert_not_called()
        answer = 'Семья дома, потому что идёт дождь.'
        self.jumble.client.responses.create.return_value = SimpleNamespace(status='completed',
            output_text=json.dumps(tutor_feedback(contract, answer)))
        self.jumble.mark_response(game['id'], answer, 0)
        saved = self.jumble.get_game(game['id'])
        self.assertEqual(saved['attempts'][0]['tutor_feedback']['commentary'], 'You connected the two events clearly.')
        self.assertNotIn('criterion_report', saved['attempts'][0]['tutor_feedback'])
        self.assertEqual(saved['attempts'][0]['criterion_support'], [])
        self.jumble.mark_response(game['id'], answer, 1)
        self.assertEqual(self.jumble.get_game(game['id'])['attempts'][0]['criterion_support'], ['model_answer'])
        with sqlite3.connect(self.db) as conn:
            validate_saved_evidence(conn)
        self.assertIn('What this response shows', self.client.get('/word_jumble/load/' + game['id']).text)

    def test_jumble_failed_check_and_newer_draft_cannot_save_report_or_score(self):
        game = self.jumble.create_game('any', 'A2')
        contract, answer = game['curriculum_contract'], 'Семья дома, потому что идёт дождь.'
        invalid = tutor_feedback(contract, answer)
        invalid['criterion_report']['judgements'][0]['evidence'][0]['quote'] = 'fabricated'
        self.jumble.client.responses.create.return_value = SimpleNamespace(status='completed', output_text=json.dumps(invalid))
        with self.assertRaises(AssessmentUnavailable):
            self.jumble.mark_response(game['id'], answer, 0)
        self.assertEqual(self.count('word_jumble_attempts'), 0)
        self.assertEqual(self.jumble.get_game(game['id'])['revision'], 0)
        def edit_during_check(*args):
            self.jumble.save_draft(game['id'], 'A newer draft', 0)
            return tutor_feedback(contract, answer)
        with patch.object(self.jumble, '_assess', side_effect=edit_during_check), self.assertRaises(DraftConflict):
            self.jumble.mark_response(game['id'], answer, 0)
        self.assertEqual(self.count('word_jumble_attempts'), 0)
        self.assertEqual(self.count('activity_criterion_reports'), 0)
        self.assertEqual(self.jumble.get_game(game['id'])['draft'], 'A newer draft')


class ProductionProviderTests(unittest.TestCase):
    def setUp(self):
        self.service = SentenceService.__new__(SentenceService)
        self.service.client = Mock()
        self.task = translation_task()
        self.contract = translation_contract(self.task, translation_focus(), 'home')

    def output(self, value):
        self.service.client.responses.create.return_value = SimpleNamespace(status='completed', output_text=json.dumps(value))

    def test_generation_requires_anchored_focus_and_preserves_c1_legacy_path(self):
        result = {key: self.task[key] for key in ('sentence', 'english')}
        self.output(result)
        with self.assertRaises(TranslationUnavailable):
            self.service.get_sentence('home', 1)
        self.output({**result, 'topic_id': 'home', 'language_focus': translation_focus()})
        self.assertEqual(self.service.get_sentence('home', 1)['curriculum_contract'], self.contract)
        self.output({**result, 'topic_id': 'home', 'language_focus': dict(translation_focus(), english_excerpt='not in task')})
        with self.assertRaises(TranslationUnavailable):
            self.service.get_sentence('home', 1)
        self.output(result)
        self.assertEqual(self.service.get_sentence('home', 'C1'), result)

    def test_valid_alternative_unscored_criterion_keeps_full_tutor_score(self):
        answer = 'Мой дом — Москва.'
        evaluation = translation_feedback(self.contract, answer)
        evaluation['criterion_report'] = report_for(self.contract, answer, outcome='insufficient_evidence')
        self.output(evaluation)
        assessed = self.service.assess_translation(self.task['sentence'], self.task['english'], answer,
                                                   curriculum_contract=self.contract)
        self.assertEqual(assessed['score'], 4)
        self.assertIsNone(assessed['criterion_report']['judgements'][0]['score'])
        request = self.service.client.responses.create.call_args.kwargs
        self.assertIn('not a failed criterion', request['input'][0]['content'])
        self.assertEqual(json.loads(request['input'][1]['content'])['russian_answer'], answer)
        self.assertIn('criterion_report', request['text']['format']['schema']['required'])

    def test_citation_repairs_offsets_only_for_unique_verbatim_original(self):
        answer = '  Я живу в Москве.'
        report = report_for(self.contract, 'Я живу в Москве.')
        grounded = production_report(self.contract, report, answer)
        self.assertEqual(grounded['judgements'][0]['evidence'][0]['start'], 2)
        self.assertEqual(report['judgements'][0]['evidence'][0]['start'], 0)
        with self.assertRaises(ValueError):
            production_report(self.contract, report, '  Я живу в Москве. Я живу в Москве.')
        with self.assertRaises(ValueError):
            production_report(self.contract, report, 'Я живёт в Москве.')

    def test_focus_cannot_be_reassigned_to_unelicited_level_or_unknown_topic(self):
        for focus, topic in ((dict(translation_focus(), requirement_id='b2.language.reported-perspective'), 'home'),
                              (translation_focus(), 'first_steps')):
            with self.assertRaises(ValueError):
                translation_contract(self.task, focus, topic)
