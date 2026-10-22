import asyncio,importlib.util,os,tempfile,unittest
from unittest.mock import patch
from fastapi import HTTPException

class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'DATA_DIR':self.tmp.name,'DASHBOARD_KEY':'test-secret','TELEGRAM_API_ID':'','TELEGRAM_API_HASH':''})
        self.env.start()
        spec=importlib.util.spec_from_file_location('gateway_under_test','backend/app.py')
        self.app=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.app)
    def tearDown(self):
        self.app.db.close();self.env.stop();self.tmp.cleanup()
    def run_async(self,coro):return asyncio.run(coro)
    def test_status_without_api_does_not_expose_credentials(self):
        d=self.run_async(self.app.status())
        self.assertFalse(d['api_configured']);self.assertFalse(d['authorized'])
        self.assertNotIn('api_hash',d)
    def test_api_required_and_auth(self):
        with self.assertRaises(HTTPException) as e:self.app.require_client()
        self.assertEqual(e.exception.status_code,409)
        with self.assertRaises(HTTPException):self.app.auth('Bearer wrong')
        self.app.auth('Bearer test-secret')
    def test_api_hash_validation(self):
        with self.assertRaises(HTTPException) as e:self.run_async(self.app.configure_telegram_api(self.app.TelegramAPI(api_id=12345,api_hash='bad')))
        self.assertEqual(e.exception.status_code,400)
    def test_api_can_be_added_without_environment_credentials(self):
        class FakeClient:
            def __init__(self,*args,**kwargs):pass
            async def connect(self):pass
            async def disconnect(self):pass
            async def is_user_authorized(self):return False
        with patch.object(self.app,'TelegramClient',FakeClient):
            d=self.run_async(self.app.configure_telegram_api(self.app.TelegramAPI(api_id=12345,api_hash='a'*32)))
        self.assertTrue(d['api_configured'])
        self.assertEqual(self.app.db.execute('select api_id from telegram_api').fetchone()[0],12345)
        self.assertNotIn('api_hash',self.run_async(self.app.status()))
    def test_doc_rejected(self):
        with self.assertRaises(HTTPException):self.run_async(self.app.config(self.app.Config(sheet_url='https://docs.google.com/document/d/test')))
    def test_delivery_substitution_and_duplicate_block(self):
        class FakeClient:
            calls=0
            async def get_input_entity(self,uid):return uid
            async def send_message(self,uid,msg):
                if msg!='Hello Test in Group':raise AssertionError(msg)
                self.calls+=1
        fake=FakeClient();self.app.client=fake
        self.run_async(self.app.config(self.app.Config(template='Hello {{name}} in {{group}}')))
        self.app.save({'id':'1:2','user_id':'2','name':'Test','role':'CTO','group':'Group'})
        self.assertEqual(self.run_async(self.app.deliver('1:2'))['status'],'Sent')
        with self.assertRaises(HTTPException) as e:self.run_async(self.app.deliver('1:2'))
        self.assertEqual(e.exception.status_code,409);self.assertEqual(fake.calls,1)

if __name__=='__main__':unittest.main()
