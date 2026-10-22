import importlib.util,json,os,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
from urllib.error import URLError

spec=importlib.util.spec_from_file_location('wmm_ping',Path('scripts/ping_gateway.py'));ping=importlib.util.module_from_spec(spec);spec.loader.exec_module(ping)
class KeepAliveTests(unittest.TestCase):
    def test_normalize_only_public_render_health_endpoint(self):
        for value in ['https://example.onrender.com','https://example.onrender.com/','https://example.onrender.com/health',' https://example.onrender.com/health/ ']:self.assertEqual(ping.health_url(value),'https://example.onrender.com/health')
        self.assertEqual(ping.health_url(''),'')
    def test_rejects_secrets_local_urls_and_non_health_paths(self):
        for value in ['http://example.onrender.com','https://localhost','https://127.0.0.1','https://example.com','https://.onrender.com','https://user:secret@example.onrender.com','https://example.onrender.com/status','https://example.onrender.com?key=secret','https://example.onrender.com/#token','https://example.onrender.com:444','https://example.onrender.com:bad']:
            with self.assertRaises(ValueError,msg=value):ping.health_url(value)
    def response(self,data,status=200):
        response=MagicMock();response.status=status;response.read.return_value=json.dumps(data).encode();response.__enter__.return_value=response;return response
    def test_public_request_sends_no_dashboard_credentials(self):
        with patch.object(ping,'urlopen',return_value=self.response({'ok':True,'service':'teamradar','version':'3.6'})) as call:
            result=ping.ping('https://example.onrender.com/health');self.assertTrue(result['ok']);request=call.call_args.args[0];self.assertNotIn('Authorization',request.headers);self.assertEqual(request.get_method(),'GET');self.assertEqual(call.call_args.kwargs['timeout'],75)
    def test_cold_start_retries_then_succeeds(self):
        with patch.object(ping,'urlopen',side_effect=[URLError('waking'),self.response({'ok':True,'service':'teamradar'})]) as call,patch.object(ping.time,'sleep') as sleep:
            ping.ping('https://example.onrender.com/health');self.assertEqual(call.call_count,2);sleep.assert_called_once_with(10)
    def test_unhealthy_or_wrong_service_does_not_pass(self):
        for body in [{'ok':False,'service':'teamradar'},{'ok':True,'service':'other'}]:
            with patch.object(ping,'urlopen',return_value=self.response(body)) as call,patch.object(ping.time,'sleep'):
                with self.assertRaises(RuntimeError):ping.ping('https://example.onrender.com/health')
                self.assertEqual(call.call_count,3)
    def test_missing_target_never_pings_any_service(self):
        with patch.object(ping,'configured_url',return_value=''),patch.object(ping,'ping') as request:
            self.assertEqual(ping.main(),0);request.assert_not_called()
    def test_override_precedes_file_configuration(self):
        with patch.dict(os.environ,{'WMM_GATEWAY_URL':'https://chosen.onrender.com'}):self.assertEqual(ping.configured_url(),'https://chosen.onrender.com/health')
    def test_exact_ten_minute_cadence_and_no_write_permissions(self):
        text=Path('.github/workflows/keep-alive.yml').read_text();self.assertIn("'7,17,27,37,47,57 * * * *'",text);self.assertIn('contents: read',text);self.assertNotIn('contents: write',text);self.assertIn('workflow_dispatch:',text);self.assertIn('timeout-minutes: 5',text)
    def test_gateway_health_response_disables_caching_and_contains_no_credentials(self):
        import test_gateway as gateway_tests
        case=gateway_tests.GatewayTests();case.setUp()
        try:
            response=case.run_async(case.app.health());self.assertIn('no-store',response.headers['cache-control']);data=json.loads(response.body);self.assertEqual(data['service'],'teamradar');self.assertTrue(data['ok']);self.assertNotIn('api_hash',data);self.assertNotIn('contacts',data)
        finally:case.tearDown()
