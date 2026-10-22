import asyncio,importlib.util,os,tempfile,unittest
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from telethon import errors
from test_gateway import FakeClient

class LoginClient(FakeClient):
    def __init__(self,user=101,two_step=True):super().__init__(user=user,authorized=False);self.two_step=two_step;self.code_accepted=False;self.steps=[];self.password_error=None;self.code_error=None;self.request_error=None;self.codes_requested=0
    async def send_code_request(self,phone):
        self.codes_requested+=1
        if self.request_error:raise self.request_error
        self.code_accepted=False;return SimpleNamespace(phone_code_hash='hash-for-'+phone)
    async def sign_in(self,phone=None,code=None,password=None,phone_code_hash=None):
        self.steps.append('password' if password is not None else 'code')
        if password is not None:
            if not self.code_accepted:raise errors.AuthKeyUnregisteredError(request=None)
            if self.password_error:raise self.password_error
            if password!='correct-password':raise errors.PasswordHashInvalidError(request=None)
            self.authorized=True;return
        if self.code_error:raise self.code_error
        if code!='12345':raise errors.PhoneCodeInvalidError(request=None)
        self.code_accepted=True
        if self.two_step:raise errors.SessionPasswordNeededError(request=None)
        self.authorized=True

class TelegramLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'DATA_DIR':self.tmp.name,'DASHBOARD_KEY':'test-secret','TELEGRAM_API_ID':'','TELEGRAM_API_HASH':''});self.env.start();self.load();self.client=LoginClient();self.app.clients[1]=self.client
    def load(self):
        spec=importlib.util.spec_from_file_location('login_flow_test','backend/app.py');self.app=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.app)
    def tearDown(self):self.app.db.close();self.env.stop();self.tmp.cleanup()
    def run_async(self,coro):return asyncio.run(coro)
    def request(self,slot=1,phone='+919876543210'):return self.run_async(self.app.login(self.app.Login(account_id=slot,phone=phone)))
    def verify(self,**kwargs):return self.run_async(self.app.verify(self.app.Verify(**kwargs)))
    def test_code_then_requested_password_connects(self):
        self.request();self.assertEqual(self.app.login_progress(1)['login_step'],'code');r=self.verify(code='12345');self.assertTrue(r['password_required']);self.assertEqual(self.client.steps,['code']);self.assertEqual(self.app.login_progress(1)['login_step'],'password')
        r=self.verify(password='correct-password');self.assertTrue(r['authorized']);self.assertEqual(self.client.steps,['code','password']);self.assertEqual(self.app.login_progress(1)['login_step'],'phone')
    def test_prefilled_password_never_skips_code(self):
        self.request();self.assertTrue(self.verify(code='12345',password='correct-password')['authorized']);self.assertEqual(self.client.steps,['code','password'])
    def test_password_before_code_is_rejected_without_get_password(self):
        self.request()
        with self.assertRaises(HTTPException) as e:self.verify(password='correct-password')
        self.assertIn('login code first',e.exception.detail);self.assertEqual(self.client.steps,[])
    def test_code_only_account_ignores_unneeded_password(self):
        self.client.two_step=False;self.request();self.verify(code='12345',password='unneeded');self.assertEqual(self.client.steps,['code']);self.assertTrue(self.client.authorized)
    def test_invalid_code_cannot_open_password_step(self):
        self.request()
        with self.assertRaises(HTTPException):self.verify(code='99999',password='correct-password')
        self.assertEqual(self.client.steps,['code']);self.assertEqual(self.app.login_progress(1)['login_step'],'code')
    def test_wrong_password_preserves_validated_code_for_retry(self):
        self.request();self.verify(code='12345')
        with self.assertRaises(HTTPException) as e:self.verify(password='wrong')
        self.assertIn('two-step password is incorrect',e.exception.detail);self.assertEqual(self.app.login_progress(1)['login_step'],'password');self.assertTrue(self.verify(password='correct-password')['authorized'])
    def test_expired_code_and_session_require_fresh_code(self):
        self.request();self.client.code_error=errors.PhoneCodeExpiredError(request=None)
        with self.assertRaises(HTTPException) as e:self.verify(code='12345')
        self.assertEqual(e.exception.status_code,409);self.assertNotIn(1,self.app.login_pending)
        self.client.code_error=None;self.request();self.verify(code='12345');self.client.password_error=errors.AuthKeyUnregisteredError(request=None)
        with self.assertRaises(HTTPException) as e:self.verify(password='correct-password')
        self.assertEqual(e.exception.status_code,409);self.assertIn('new login code',e.exception.detail);self.assertNotIn(1,self.app.login_pending)
    def test_restart_and_timeout_cannot_reuse_password_only(self):
        self.request();self.verify(code='12345');self.app.login_pending.clear()
        with self.assertRaises(HTTPException):self.verify(password='correct-password')
        self.request();self.app.login_pending[1]['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        with self.assertRaises(HTTPException):self.verify(code='12345')
        self.assertNotIn(1,self.app.login_pending)
    def test_pending_logins_are_scoped_to_account_and_phone(self):
        self.app.clients[2]=LoginClient(user=102);self.request()
        with self.assertRaises(HTTPException):self.verify(account_id=2,password='correct-password')
        with self.assertRaises(HTTPException):self.verify(phone='+441234567890',code='12345')
        self.assertEqual(self.client.steps,[]);self.assertEqual(self.app.clients[2].steps,[])
    def test_new_code_starts_code_step_and_phone_format_is_normalized(self):
        self.request();self.verify(code='12345');self.request(phone='+91 98765-43210');self.assertEqual(self.app.login_progress(1)['login_step'],'code');self.assertEqual(self.app.login_pending[1]['phone'],'+919876543210');self.assertEqual(self.app.login_progress(1)['login_phone_hint'],'••••3210')
    def test_valid_connected_account_does_not_request_new_code(self):
        self.client.authorized=True;self.assertTrue(self.request()['authorized']);self.assertEqual(self.client.codes_requested,0)
    def test_rejected_transport_key_is_renewed_only_in_selected_slot(self):
        self.client.request_error=errors.AuthKeyUnregisteredError(request=None);session=SimpleNamespace(auth_key='rejected',save=lambda:None,close=lambda:None);self.client.session=session;replacement=LoginClient();other=LoginClient(user=102);self.app.clients[2]=other
        with patch.object(self.app,'make_client',return_value=replacement):self.request()
        self.assertIsNone(session.auth_key);self.assertIs(self.app.clients[1],replacement);self.assertIs(self.app.clients[2],other);self.assertEqual(replacement.codes_requested,1);self.assertEqual(other.codes_requested,0)
