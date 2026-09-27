"""Library-sized practice, with real frozen contexts and no tutorial fallback."""
import io
import json
import random
import unittest
from PIL import Image

from repositories.learning_repository import encoded, identifier, transaction
from services.journey_games import GAMES
from services.journey_vocabulary import _vocabulary
from services.journey_vocabulary_games import _others
from services.learning_assets import import_asset
from services.route_content import MISSION_IDS
from tests.game_fixtures import grant_earned_game_access
from tests.support import isolated_app
from tests.test_card_media import MediaProvider
from tests.test_personal_flashcards import Provider

EXAMPLES = [
    ('книга','книгу','Анна читает книгу.','Anna is reading a book.','a book','accs'),
    ('парк','парке','Мы гуляем в парке.','We are walking in the park.','the park','loct'),
    ('учитель','учителем','Я говорю с учителем.','I am talking to the teacher.','the teacher','ablt'),
    ('море','море','Мы видим море.','We can see the sea.','the sea','accs'),
    ('собака','собакой','Девочка играет с собакой.','The girl is playing with a dog.','a dog','ablt'),
    ('сад','саду','Отец работает в саду.','Father is working in the garden.','the garden','loct'),
    ('поезд','поезда','Мы ждём поезда.','We are waiting for a train.','a train','gent'),
    ('дом','домом','Машина стоит перед домом.','The car is parked in front of the house.','the house','ablt'),
    ('окно','окна','Кошка сидит около окна.','The cat is sitting near the window.','the window','gent'),
    ('сестра','сестре','Я звоню сестре.','I am calling my sister.','my sister','datv'),
    ('музей','музея','Недалеко от музея есть кафе.','There is a café near the museum.','the museum','gent'),
    ('театр','театре','Сегодня мы встречаемся в театре.','Today we are meeting at the theatre.','the theatre','loct'),
    ('велосипед','велосипеде','Он едет на велосипеде.','He is riding a bicycle.','a bicycle','loct'),
    ('хлеб','хлебом','На столе стоит тарелка с хлебом.','There is a plate of bread on the table.','bread','ablt'),
    ('кофе','кофе','Мама пьёт кофе.','Mum is drinking coffee.','coffee','accs'),
    ('рыба','рыбу','Рыбак поймал рыбу.','The fisherman caught a fish.','a fish','accs'),
    ('дерево','деревом','Скамейка стоит под деревом.','The bench is under a tree.','a tree','ablt'),
    ('магазин','магазине','Я покупаю молоко в магазине.','I am buying milk at the shop.','the shop','loct'),
    ('друг','другу','Я помогаю другу.','I am helping a friend.','a friend','datv'),
    ('река','реке','По реке плывёт лодка.','A boat is sailing along the river.','the river','datv'),
]


class DistinctChoiceTests(unittest.TestCase):
    def test_matching_choices_deduplicate_other_words_from_the_same_sentence(self):
        records = [{'identity': str(i), 'sentence': sentence, 'translation': translation,
                    'assets': [{'kind': 'image', 'id': str(i)}]}
                   for i, (sentence, translation) in enumerate([
                       ('Я сплю дома.', 'I sleep at home.'),
                       ('Я читаю книгу.', 'I am reading a book.'),
                       ('Я читаю книгу.', 'I am reading a book.'),
                       ('Я пью воду.', 'I am drinking water.')])]
        for seed in range(20):
            choices = _others(records, records[0], 4, random.Random(seed))
            self.assertEqual(len(choices), 3)
            self.assertEqual(len({e['sentence'] for e in choices}), 3)
        records[3]['assets'] = records[1]['assets']
        choices = _others(records, records[0], 4, random.Random(0))
        self.assertEqual(len({e['assets'][0]['id'] for e in choices}), len(choices))


class VocabularyGameTests(unittest.TestCase):
    def setUp(self):
        self.provider = MediaProvider()
        self.discoveries = []
        def discover(provider, **request):
            self.discoveries.append(request)
            return {'identity': 'new-'+request['seed'], 'word_id': None, 'form_id': None, 'lemma': 'подарок',
                    'form': 'подарки', 'pos': 'NOUN', 'tags': {'case': 'accs', 'number': 'plur'},
                    'sentence': 'Анна покупает подарки.', 'translation': 'Anna is buying presents.',
                    'target_meaning': 'presents', 'notes': '', 'mnemonic': '', 'new_word': True,
                    'assets': [], 'metadata': {'lemma_difficulty': 5}, 'source': {'kind': 'discovery'}}
        self.app = isolated_app(self, {'OpenAIService': Provider(), 'CardMediaProvider': self.provider,
                                      'GameDiscovery': discover}, demo=False)
        self.client = self.app.test_client(); self.db = self.app.config['DB_PATH']
        self.csrf = self.client.get('/api/v1/games').json['csrf_token']
        grant_earned_game_access(self.db)
        self.examples = {}
        with transaction(self.db, write=True) as conn:
            for lemma, form, sentence, translation, meaning, case in EXAMPLES:
                word_id = conn.execute("INSERT INTO words(lemma,pos,count,lemma_difficulty,topic) VALUES (?,'NOUN',0,4,'[\"Everyday\"]')", (lemma,)).lastrowid
                conn.execute('INSERT INTO forms(word_id,form,count,tags,form_difficulty) VALUES (?,?,0,?,5)', (word_id, form, encoded({'case':case,'number':'sing'})))
                self.examples[lemma] = (sentence,translation,meaning)

            candidates = _vocabulary(conn)
        store = self.app.extensions['learning']['assets']
        for index, record in enumerate(candidates):
            picture = io.BytesIO(); Image.new('RGB',(4,4),(index*11 % 255,90,70)).save(picture,format='PNG')
            image_id = import_asset(self.db,store,picture.getvalue(),'test illustration')
            audio_id = import_asset(self.db,store,self.provider.mp3,'test recording')
            sentence,translation,meaning = self.examples[record['lemma']]
            record.update(sentence=sentence,translation=translation,target_meaning=meaning,assets=[{'id':image_id,'kind':'image'},{'id':audio_id,'kind':'sentence_audio'}])
            with transaction(self.db, write=True) as conn:
                conn.execute("INSERT INTO journey_game_examples(id,profile_id,identity,word_id,form_id,content_json,created_at) VALUES (?,'personal-learning',?,?,?,?,1)", (identifier(),record['identity'],record['word_id'],record['form_id'],encoded(record)))

    def post(self, path, value=None, status=200):
        r = self.client.post(path,json=value or {},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(r.status_code,status,r.text)
        return r.json

    def start(self, game, **extra):
        return self.post('/api/v1/games/'+game+'/start', {'request_id':identifier(),**extra})

    def ready(self, state):
        for _ in range(50):
            if state['phase'] != 'preparing': break
            state = self.post('/api/v1/games/sessions/'+state['id']+'/prepare')
            self.assertNotEqual(state.get('preparation',{}).get('status'),'failed',state)
        self.assertEqual(state['phase'],'play',state)
        return state

    def stored(self, state):
        with transaction(self.db) as conn:
            return json.loads(conn.execute('SELECT content_json FROM journey_game_sessions WHERE id=?',(state['id'],)).fetchone()[0])

    def finish(self, state):
        root='/api/v1/games/sessions/'+state['id']
        for item in self.stored(state)['rounds']:
            if item.get('audio_required'):
                self.post(root+'/transcript',{'round_id':item['id']})
            self.post(root+'/answer',{'round_id':item['id'],'answer':item['expected_answer']})
            self.post(root+'/continue',{'round_id':item['id']})
        return self.post(root+'/complete')

    def test_example_games_mix_familiar_and_new_words_without_unneeded_media_or_publication(self):
        # Scene Builder has a separate authored grammar curriculum and suite.
        for game in (g for g in GAMES if g['id'] not in ('radio', 'directions', 'scene-builder')):
            before = len(self.provider.calls)
            state=self.ready(self.start(game['id']))
            content=self.stored(state)
            self.assertEqual(state['total_rounds'],5)
            self.assertEqual(state['source']['kind'],'vocabulary')
            self.assertEqual(content['version'],'journey-vocabulary-v1')
            picture_game = game['id'] in ('pairs', 'pack-bag', 'detective')
            self.assertEqual(len(content['vocabulary_refs']), 4 if picture_game else 5)
            self.assertEqual(sum(w['lemma'] not in self.examples for w in content['vocabulary_refs']), 1)
            for word in content['vocabulary_refs']:
                if word['lemma'] not in self.examples:
                    continue
                self.assertEqual(word['sentence'],self.examples[word['lemma']][0])
                self.assertNotEqual(word['form'],word['lemma']) if word['lemma'] not in ('море','кофе') else None
            self.assertEqual(self.finish(state)['phase'],'completed')
            new_calls = self.provider.calls[before:]
            self.assertEqual([kind for kind, _ in new_calls], ['image'] if picture_game else ['sentence_audio'] if game['id']=='letter-back' else [])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0],0)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], 20)
        self.assertEqual(len(self.discoveries), 6)

    def test_authored_routes_open_immediately_without_any_generation(self):
        state = self.start('directions', options={'delivery_id': MISSION_IDS[0]})
        self.assertEqual(state['phase'], 'play')
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.discoveries, [])
        self.assertEqual(self.stored(state)['version'], 'journey-delivery-v2')
        self.assertTrue(self.stored(state)['vocabulary_refs'])
        for leg in self.stored(state)['legs']:
            for action,payload in [('begin',{}),('go',{'path':leg['route']}),
                                   ('deliver' if leg['id']=='recipient' else 'talk',{})]:
                state=self.post('/api/v1/games/sessions/'+state['id']+'/route-command',
                                {'request_id':identifier(),'revision':state['delivery']['revision'],'action':action,'payload':payload})
        self.assertEqual(state['phase'], 'completed')

    def test_replay_selects_fresh_words_and_identical_request_never_restarts_preparation(self):
        request={'request_id':identifier()}
        first=self.post('/api/v1/games/pairs/start',request)
        self.assertEqual(self.post('/api/v1/games/pairs/start',request)['id'],first['id'])
        self.post('/api/v1/games/sessions/'+first['id']+'/complete',status=409)
        a=self.stored(self.ready(first)); self.finish(first)
        second=self.ready(self.start('pairs')); b=self.stored(second)
        self.assertFalse({e['word_id'] for e in a['vocabulary_refs'] if e['word_id']} & {e['word_id'] for e in b['vocabulary_refs'] if e['word_id']})
        self.assertNotEqual(a['lesson_version'],b['lesson_version'])
        self.post('/api/v1/games/pairs/start',dict(request,options={'source':'vocabulary','rounds':10}),status=409)

    def test_new_selection_preserves_an_unfinished_attempt_and_its_frozen_pool(self):
        first=self.ready(self.start('pairs')); before=self.stored(first)
        second=self.start('pairs',new_game=True)
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(self.stored(first),before)
        with transaction(self.db) as conn:
            row=conn.execute('SELECT completed_at,superseded_at,answers_json FROM journey_game_sessions WHERE id=?',(first['id'],)).fetchone()
            self.assertIsNone(row['completed_at']);self.assertIsNotNone(row['superseded_at']);self.assertEqual(row['answers_json'],'{}')

    def test_owned_images_and_cloze_and_dictation_answers_do_not_leak(self):
        state=self.ready(self.start('missing-stamp')); item=state['round']
        self.assertIn('[[blank]]',item['sentence']);self.assertTrue(item['translation'])
        self.assertNotIn('answer_audio',item);self.assertNotIn('expected_answer',item)
        image = self.ready(self.start('pairs'))['round']['right'][0]['image_url']
        with self.client.get(image) as response:
            self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/api/v1/games/sessions/not-mine/assets/'+image.rsplit('/',1)[1]).status_code,404)
        letter=self.ready(self.start('letter-back'))
        self.assertNotIn('text',letter['round']['clues'][0]);self.assertTrue(letter['round']['translation'])
        self.post('/api/v1/games/sessions/'+letter['id']+'/answer', {'round_id':letter['round']['id'],'answer':self.stored(letter)['rounds'][0]['expected_answer']},status=409)

    def test_new_word_sets_supply_new_evidence_without_claiming_a_torfl_level(self):
        first=self.ready(self.start('pairs'));self.finish(first)
        second=self.ready(self.start('pairs'));self.finish(second)
        with transaction(self.db) as conn:
            evidence=conn.execute("SELECT target_level,evidence_json FROM progression_events WHERE activity='journey_game' ORDER BY rowid").fetchall()
            self.assertEqual(len(evidence),2)
            for row in evidence:
                self.assertIsNone(row['target_level'])
                receipt = json.loads(row['evidence_json'])
                if receipt['unassisted_count']:
                    self.assertIn('reading',receipt['_skill']['scores'])
                    self.assertEqual(receipt['_skill']['task_rating'],1000)
                else:
                    self.assertNotIn('_skill',receipt)  # Shuffled familiar pairs are supported practice.
            self.assertIn('_skill',json.loads(evidence[0]['evidence_json']))


if __name__=='__main__': unittest.main()
