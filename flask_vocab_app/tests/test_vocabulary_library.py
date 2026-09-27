"""Vocabulary coverage follows actual card identities and Russian word/form links."""
import copy
import sqlite3
import unittest
from unittest.mock import patch

from repositories.learning_repository import transaction, LearningError
from tests.support import isolated_app
from tests.test_personal_flashcards import Provider


class VocabularyLibraryTests(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()
        self.app = isolated_app(self, {'OpenAIService':self.provider})
        self.app.config['OPENAI_API_KEY'] = 'synthetic-test-key'
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        state = self.client.get('/api/v1/household').json
        self.token = state['csrf_token']
        with self.client.session_transaction() as session:
            self.access = session['personal_access_id']

    def post(self, url, data):
        return self.client.post(url, json=data, headers={'X-CSRF-Token':self.token})

    def words(self):
        return {w['id']:w for w in self.client.get('/vocab?fetch_all=true', headers={'Accept':'application/json'}).json['words']}

    def generate(self):
        batch = self.post('/api/v1/card-generation/batches', {'submission_id':'vocab-coverage', 'options':{'kind':'ru-cloze','quantity':1,'word_id':1}}).json
        result = self.post(f'/api/v1/card-generation/batches/{batch["id"]}/next', {}).json
        self.assertEqual(result['saved'],1,result)
        return result

    def test_generated_card_is_counted_for_word_and_exact_form_without_changing_anki(self):
        with transaction(self.db,write=True) as conn:
            conn.execute('UPDATE words SET count=7 WHERE id=1')
        result = self.generate()
        row = self.words()[1]
        self.assertEqual((row['native_count'],row['native_total'],row['anki_exports'],row['count']),(1,1,7,7))
        details = self.client.get('/vocab/words/1').json
        self.assertEqual(sum(f['native_count'] for f in details['forms']),1)
        self.assertEqual(details['cards'][0]['status'],'active')
        self.post(f'/api/v1/card-generation/batches/{result["id"]}/next', {})
        self.assertEqual(self.words()[1]['native_count'],1)
        self.assertEqual(len(self.provider.calls),1)
        self.assertEqual(self.client.get('/api/v1/flashcards?word_id=1').json['counts']['cards'],1)
        self.assertEqual(self.client.get('/api/v1/flashcards?word_id=2').json['counts']['cards'],0)
        self.assertEqual(self.client.get('/api/v1/flashcards?word_id=-1').status_code,400)

    def test_retiring_card_updates_live_count_but_keeps_record(self):
        self.generate()
        card = self.client.get('/api/v1/flashcards').json['cards'][0]
        self.assertEqual(self.post(f'/api/v1/cards/{card["id"]}/delete', {}).status_code,200)
        self.assertEqual((self.words()[1]['native_count'],self.words()[1]['native_total']),(0,1))
        self.assertEqual(self.client.get('/vocab/words/1').json['cards'][0]['status'],'retired')

    def test_card_versions_and_multiple_memberships_are_not_counted_twice(self):
        content = self.app.extensions['learning']['content']
        pack = {'schema_version':2,'id':'coverage','kind':'deck','title':'Coffee','source':'Synthetic test',
                'items':[{'id':'coffee','card_id':'one-coffee','word_id':1,'type':'basic','direction':'ru-en',
                          'sense_key':'drink','sense_label':'Coffee','context':'Это кофе.','prompt':'кофе','answer':'coffee'}]}
        version = content.import_draft(pack)
        self.assertEqual((self.words()[1]['native_count'],self.words()[1]['native_total']),(0,1))
        content.publish(self.access,version,'Me')
        changed = copy.deepcopy(pack);changed['title']='Coffee updated'
        next_version = content.import_draft(changed)
        self.assertEqual(self.words()[1]['native_count'],1)
        content.publish(self.access,next_version,'Me')
        another = copy.deepcopy(pack);another['id']='second-collection'
        content.publish(self.access,content.import_draft(another),'Me')
        self.assertEqual((self.words()[1]['native_count'],self.words()[1]['native_total']),(1,1))
        self.assertEqual(self.client.get('/api/v1/flashcards').json['counts']['cards'],1)

    def test_homographs_keep_separate_word_ids_and_form_records(self):
        with transaction(self.db,write=True) as conn:
            other = conn.execute("INSERT INTO words(lemma,pos,lemma_difficulty,topic) VALUES ('кофе','OTHER',1,'[]')").lastrowid
            conn.execute('INSERT INTO forms(word_id,form,tags) VALUES (?,?,?)',(other,'кофе','{"case":"gent","number":"sing"}'))
        self.generate()
        self.assertEqual(self.words()[other]['native_count'],0)
        detail = self.client.get(f'/vocab/words/{other}').json
        self.assertEqual(detail['forms'][0]['tags']['case'],'gent')
        self.assertEqual(detail['native_count'],0)
        self.assertEqual(self.client.get('/vocab/words/999999').status_code,404)

    def test_page_and_fragment_use_one_mount_and_name_both_sources(self):
        html = self.client.get('/vocab').get_data(as_text=True)
        self.assertEqual(html.count('id="dynamic-vocab-content"'),1)
        self.assertIn('Word library',html);self.assertIn('Google Drive',html)
        self.assertIn('Sync &amp; tools',html)
        self.assertIn('Saved to Google Drive',html)
        response = self.client.get('/vocab',headers={'HX-Request':'true'})
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertNotIn('<html',response.get_data(as_text=True))
        self.assertIn('forms_search',self.words()[1])

    def test_disk_failure_is_an_actionable_json_error(self):
        error = sqlite3.OperationalError('disk I/O error')
        error.sqlite_errorcode = sqlite3.SQLITE_IOERR_FSYNC
        with patch('repositories.learning_repository.connect_db', side_effect=error):
            response = self.client.get('/api/v1/household')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json['error']['code'],'storage_unavailable')
        self.assertIn('disk space',response.json['error']['message'])
