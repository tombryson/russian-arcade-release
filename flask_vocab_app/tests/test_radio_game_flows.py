"""Radio's public flow is listening -> comprehension -> optional new vocabulary."""
import json
import unittest

from repositories.learning_repository import encoded, identifier, transaction
from tests.game_fixtures import grant_earned_game_access
from tests.support import isolated_app
from tests.test_radio_broadcast import RecordingProvider, SCRIPT, TextProvider


class RadioGameFlowTests(unittest.TestCase):
    def setUp(self):
        self.text, self.media = TextProvider(), RecordingProvider()
        self.app = isolated_app(self, {'OpenAIService': self.text, 'CardMediaProvider': self.media}, demo=False)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.csrf = self.client.get('/api/v1/games').json['csrf_token']
        grant_earned_game_access(self.db)
        with transaction(self.db, write=True) as conn:
            for lemma, form in [('парк', 'парками'), ('книга', 'книгу')]:
                word = conn.execute("INSERT INTO words(lemma,pos,count,lemma_difficulty) VALUES (?,'NOUN',0,2)", (lemma,)).lastrowid
                conn.execute('INSERT INTO forms(word_id,form,count,tags,form_difficulty) VALUES (?,?,0,?,2)',
                             (word, form, encoded({'case': 'ablt' if lemma == 'парк' else 'accs'})))


    def post(self, path, data=None, status=200):
        response = self.client.post(path, json=data or {}, headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(response.status_code, status, response.text)
        return response.json

    def prepare(self):
        state = self.post('/api/v1/games/radio/start', {'request_id': identifier()})
        self.root = '/api/v1/games/sessions/'+state['id']
        self.assertEqual(state['phase'], 'preparing')
        self.assertEqual(state['total_rounds'], 4)
        self.assertEqual(state['preparation']['total'], 2)
        state = self.post(self.root+'/prepare')
        self.assertEqual(state['preparation']['stage'], 'audio', state)
        state = self.post(self.root+'/prepare')
        self.assertEqual(state['phase'], 'listening', state)
        self.key = state['broadcast']['audio_key']
        with transaction(self.db) as conn:
            self.frozen = json.loads(conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?', (state['id'],)).fetchone()[0])
        return state

    def listen(self):
        response = self.client.get('/api/v1/games/media/'+self.key+'/status')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json['status'], 'ready', response.json)
        response = self.client.get(response.json['url'])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.mimetype.startswith('audio/'))
        response.close()
        state = self.post(self.root+'/listen', {'round_id': 'broadcast', 'audio_key': self.key})
        self.assertTrue(state['broadcast']['listened'])
        return self.post(self.root+'/quiz')

    def finish(self, hints=False, transcript=False):
        if transcript:
            self.post(self.root+'/transcript', {'round_id': 'broadcast'})
            self.post(self.root+'/quiz')
        else:
            self.listen()
        for item in self.frozen['rounds']:
            if hints:
                self.post(self.root+'/hint', {'round_id': item['id']})
            self.post(self.root+'/answer', {'round_id': item['id'], 'answer': item['expected_answer']})
            self.post(self.root+'/continue', {'round_id': item['id']})
        return self.post(self.root+'/complete')

    def test_listen_before_questions_no_spoilers_no_repeated_generation_and_one_reward(self):
        state = self.prepare()
        self.assertIsNone(state['round'])
        self.assertNotIn('script', state['broadcast'])
        self.assertNotIn('vocabulary', state['broadcast'])
        self.assertNotIn('words', state)
        self.post(self.root+'/quiz', status=409)
        self.post(self.root+'/complete', status=409)
        first = self.frozen['rounds'][0]
        self.post(self.root+'/answer', {'round_id': first['id'], 'answer': first['expected_answer']}, status=409)
        state = self.listen()
        self.assertEqual(state['phase'], 'play')
        self.assertEqual(len(state['round']['choices']), 4)
        self.assertNotIn('expected_answer', state['round'])
        self.assertNotIn('text', state['round']['clues'][0])
        self.assertNotIn('hint', state['round'])
        for item in self.frozen['rounds']:
            feedback = self.post(self.root+'/answer', {'round_id': item['id'], 'answer': item['expected_answer']})
            self.assertNotIn('script', feedback['broadcast'])
            self.assertNotIn('text', feedback['round']['clues'][0])
            self.assertNotIn('vocabulary', feedback['broadcast'])
            self.post(self.root+'/continue', {'round_id': item['id']})
        finished = self.post(self.root+'/complete')
        self.assertEqual(finished['phase'], 'completed')
        self.assertEqual(finished['broadcast']['script'], SCRIPT)
        self.assertEqual(len(finished['broadcast']['vocabulary']), 2)
        self.assertEqual(finished['reward']['amount'], 3)
        self.assertFalse(finished['study_available'])
        self.post(self.root+'/complete')
        self.post('/api/v1/games/media/'+self.key+'/prepare')
        self.assertEqual(len(self.media.calls), 1)
        self.assertEqual(len(self.text.calls), 1)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='journey_game'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE json_extract(evidence_json,'$._skill.scores.listening') IS NOT NULL").fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], 2)

    def test_optional_hints_do_not_count_as_unassisted_listening_but_still_reward_completion(self):
        self.prepare()
        finished = self.finish(hints=True)
        self.assertEqual(finished['reward']['amount'], 3)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE json_extract(evidence_json,'$._skill.scores.listening') IS NOT NULL").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='journey_game'").fetchone()[0], 1)

    def test_transcript_is_an_explicit_supported_route_and_not_a_listening_claim(self):
        self.prepare()
        supported = self.post(self.root+'/transcript', {'round_id': 'broadcast'})
        self.assertEqual(supported['broadcast']['script'], SCRIPT)
        finished = self.finish(transcript=True)
        self.assertEqual(finished['reward']['amount'], 3)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE json_extract(evidence_json,'$._skill.scores.listening') IS NOT NULL").fetchone()[0], 0)

    def test_discovered_word_add_is_explicit_idempotent_and_owner_scoped(self):
        self.prepare()
        self.post(self.root+'/words', {'word': 'ярмарка', 'lemma': 'ярмарка'}, status=409)
        self.finish()
        details = self.client.get(self.root+'/words?word=ярмарка')
        self.assertEqual(details.status_code, 200, details.text)
        result = self.post(self.root+'/words', {'word': 'ярмарка', 'lemma': 'ярмарка', 'pos': 'NOUN'})
        self.post(self.root+'/words', {'word': 'ярмарка', 'lemma': 'ярмарка', 'pos': 'NOUN'})
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM words WHERE lemma='ярмарка'").fetchone()[0], 1)
            word = conn.execute("SELECT id FROM words WHERE lemma='ярмарка'").fetchone()[0]
            self.assertGreater(conn.execute('SELECT COUNT(*) FROM forms WHERE word_id=?', (word,)).fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0], 0)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        foreign = self.app.test_client()
        with foreign.session_transaction() as session:
            session.clear()
        csrf = foreign.get('/api/v1/games').json['csrf_token']
        self.assertEqual(foreign.get(self.root).status_code, 404)
        self.assertEqual(foreign.get(self.root+'/words?word=ярмарка').status_code, 404)
        self.assertEqual(foreign.get('/api/v1/games/media/'+self.key+'/status').status_code, 404)
        self.assertEqual(foreign.post(self.root+'/words', json={'word': 'оркестр', 'lemma': 'оркестр'}, headers={'X-CSRF-Token': csrf}).status_code, 404)
        self.assertEqual(self.client.post(self.root+'/words', json={'word': 'оркестр', 'lemma': 'оркестр'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
