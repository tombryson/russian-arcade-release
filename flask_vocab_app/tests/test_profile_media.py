"""Direct activity media and private reports across named local profiles."""
import io
import json
from pathlib import Path
import unittest

from PIL import Image

from repositories.learning_repository import timestamp, transaction
from services.learning_assets import import_asset
from tests.support import isolated_app, select_test_profile
from tests.test_native_flashcards import deck


class ProfileMediaTests(unittest.TestCase):
    def setUp(self):
        self.app=isolated_app(self,signed_in=False)
        self.db=self.app.config['DB_PATH']
        with transaction(self.db,write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)",(timestamp(),))
        self.me=self.app.test_client();select_test_profile(self.me)
        self.other=self.app.test_client();select_test_profile(self.other,'other')
        self.media=Path(self.app.config['APP_MEDIA_DIR']);self.media.mkdir(parents=True,exist_ok=True)
        self.uploads=Path(self.app.config['UPLOAD_FOLDER']);self.uploads.mkdir(parents=True,exist_ok=True)

    def file(self,name,bucket='media'):
        path=(self.media if bucket=='media' else self.uploads)/name
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'test media')
        return f'/static/{bucket}/{name}'

    def story(self,audio='',image='',owner='personal-learning'):
        with transaction(self.db,write=True) as conn:
            return conn.execute('INSERT INTO saved_stories(title,text,audio_url,image_url,owner_profile_id) VALUES (?,?,?,?,?)',('Fixture','Текст',audio,image,owner)).lastrowid

    def test_foreign_story_audio_image_and_translation_audio_are_denied_directly(self):
        audio=self.file('story_audio.mp3');image=self.file('story_image_picture.png')
        self.story(audio,image)
        translation=self.file('sentence_audio.mp3')
        with transaction(self.db,write=True) as conn:
            conn.execute("INSERT INTO sentences(sentence,english,topic,difficulty,audio_url,owner_profile_id) VALUES ('Кот','Cat','home',1,?,'personal-learning')",(translation,))
        for url in (audio,image,translation):
            with self.subTest(url=url):
                response=self.me.get(url)
                self.assertEqual(response.status_code,200);self.assertEqual(response.headers['Cache-Control'],'no-store');response.close()
                self.assertEqual(self.other.get(url).status_code,404)
                self.assertEqual(self.app.test_client().get(url).status_code,302)

    def test_uploaded_story_image_and_encoded_legacy_references_keep_ownership(self):
        picture=self.file('Кот и дом.png','uploads')
        from urllib.parse import quote
        self.story(image='http://127.0.0.1:5052'+quote(picture))
        response=self.me.get(picture);self.assertEqual(response.status_code,200);response.close()
        self.assertEqual(self.other.get(picture).status_code,404)
        self.assertEqual(self.other.get('/static/uploads/folder/../Кот и дом.png').status_code,404)

    def test_forging_a_second_record_reference_does_not_grant_private_media_access(self):
        url=self.file('story_secret.mp3');self.story(audio=url)
        self.story(audio=url,owner='other')
        self.assertEqual(self.other.get(url).status_code,404)

    def test_unsaved_preview_requires_server_generated_media_not_editable_story_payload(self):
        url=self.file('story_unsaved.mp3')
        with self.me.session_transaction() as state:state['generated_story_media']=[url]
        with self.other.session_transaction() as state:state['current_story_data']={'audio_url':url}
        response=self.me.get(url);self.assertEqual(response.status_code,200);response.close()
        self.assertEqual(self.other.get(url).status_code,404)

    def test_shared_lesson_and_vocabulary_files_remain_available(self):
        lesson=self.file('lesson-source.pdf','uploads');vocab=self.file('word1_form2.png')
        with transaction(self.db,write=True) as conn:
            conn.execute("INSERT INTO lessons(id,title,pdf_path,created_at) VALUES ('lesson','Shared source',?,'2026-09-15')",(lesson,))
        for url in (lesson,vocab):
            response=self.other.get(url);self.assertEqual(response.status_code,200);response.close()

    def test_shared_native_card_asset_and_household_adult_media_access_remain_available(self):
        content=self.app.extensions['learning']['content']
        image=Image.new('RGB',(2,2),'red');data=io.BytesIO();image.save(data,format='PNG')
        asset_file=self.media/'fixture.png';asset_file.write_bytes(data.getvalue())
        asset=import_asset(self.db,self.app.extensions['learning']['assets'],asset_file.read_bytes(),'Synthetic fixture')
        pack=deck();pack['items'][0]['assets']=[{'id':asset,'kind':'image','role':'answer'}]
        with self.me.session_transaction() as state:credential=state['personal_access_id']
        version=content.import_draft(pack,access_id=credential);content.publish(credential,version,'Fixture')
        response=self.other.get('/api/v1/assets/'+asset);self.assertEqual(response.status_code,200);response.close()
        url=self.file('story_household.mp3');self.story(audio=url)
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True,SECRET_KEY='isolated-private-household-key-at-least32chars')
        self.app.extensions['learning']['household'].configure('Fixture','246810')
        adult=self.app.test_client();token=adult.get('/api/v1/household').json['csrf_token']
        self.assertEqual(adult.post('/api/v1/household/unlock',json={'pin':'246810'},headers={'X-CSRF-Token':token}).status_code,200)
        response=adult.get(url);self.assertEqual(response.status_code,200);response.close()

    def test_card_reports_are_private_but_household_adult_can_review_them_all(self):
        services=self.app.extensions['learning'];content=services['content']
        version=content.import_draft(deck())
        with transaction(self.db,write=True) as conn:
            cv=conn.execute('SELECT id,card_id FROM card_versions WHERE content_version_id=?',(version,)).fetchone()
            for profile,reason in [('personal-learning','My private report'),('other','Other private report')]:
                conn.execute('INSERT INTO card_reports VALUES (?,?,?,?,?,?)',(profile,profile,cv['card_id'],cv['id'],reason,timestamp()))
        for client,expected in [(self.me,'My private report'),(self.other,'Other private report')]:
            with client.session_transaction() as state:credential=state['personal_access_id']
            with self.app.app_context():
                reports=services['card_authoring'].workspace(credential)['reports']
            self.assertEqual([report['reason'] for report in reports],[expected])
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True,SECRET_KEY='isolated-private-household-key-at-least32chars')
        services['household'].configure('Fixture','246810')
        adult=self.app.test_client();token=adult.get('/api/v1/household').json['csrf_token']
        adult.post('/api/v1/household/unlock',json={'pin':'246810'},headers={'X-CSRF-Token':token})
        with adult.session_transaction() as state:credential=state['household_access_id']
        with self.app.app_context():
            reports=services['card_authoring'].workspace(credential)['reports']
        self.assertEqual({report['reason'] for report in reports},{'My private report','Other private report'})
