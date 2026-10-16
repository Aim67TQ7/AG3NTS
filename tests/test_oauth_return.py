import json,unittest
from unittest.mock import patch,AsyncMock
from types import SimpleNamespace
from urllib.parse import urlencode,parse_qs,urlsplit
from starlette.requests import Request
from app import fresh,mcp_connection as m,discovery
from app.core import Invalid

def request(path,body=None,query=None):
 async def receive():return {'type':'http.request','body':json.dumps(body or {}).encode(),'more_body':False}
 return Request({'type':'http','method':'POST' if body is not None else 'GET','path':path,'query_string':urlencode(query or {}).encode(),'headers':[]},receive)
class OAuthReturnTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.context={'token':'flx_fixture','user':{'id':'u','email':'u@example.invalid'},'client':{'id':'current','name':'Current'},'company':{'id':'current-company','name':'Current company','code':'C','facility':''},'role':'owner'}
  self.marker=fresh.CTX.set(self.context)
  self.args={'client_id':'client','redirect_uri':'https://example.invalid/complete?keep=yes','response_type':'code','code_challenge_method':'S256','code_challenge':'a'*43,'resource':m.RESOURCE,'scope':'flux:build offline_access','state':'original-state'}
 def tearDown(self):fresh.CTX.reset(self.marker)
 def test_login_continuation_is_local_authorize_only(self):
  good='/oauth/authorize?'+urlencode(self.args);self.assertEqual(fresh.login_destination(good),good)
  for bad in ['https://evil.invalid/','//evil.invalid/oauth/authorize?x=1','/ai-connections','/oauth/authorize','/oauth/authorize?x=1#other','/oauth/authorize?x=1\r\nfoo',None]:self.assertEqual(fresh.login_destination(bad),'/')
 async def test_authorize_page_does_not_load_settings_or_require_current_company(self):
  fresh.CTX.set({**self.context,'company':None})
  with patch.object(m,'rpc',AsyncMock(return_value={'name':'AI client'})) as rpc:
   result=await m.browser(request('/oauth/authorize',query=self.args),None)
  self.assertEqual(result.status_code,200);self.assertIn(b'Approve connection & return',result.body);self.assertEqual([c.args[1] for c in rpc.call_args_list],['client'])
 async def test_old_settings_authorization_url_resumes_focused_consent(self):
  with patch.object(m,'rpc',AsyncMock(return_value={'name':'AI client'})):
   result=await m.browser(request('/ai-connections',query=self.args),None)
  self.assertEqual(result.status_code,303);location=urlsplit(result.headers['location']);self.assertEqual(location.path,'/oauth/authorize');self.assertEqual(parse_qs(location.query)['state'],['original-state'])
 async def test_cancel_returns_to_verified_callback_with_original_state(self):
  with patch.object(m,'rpc',AsyncMock(return_value={'name':'AI client'})) as rpc:
   result=await m.browser(request('/api/ai-connections/cancel',body=self.args),None)
  callback=urlsplit(json.loads(result.body)['redirect']);self.assertEqual(callback.hostname,'example.invalid');self.assertEqual(parse_qs(callback.query),{'keep':['yes'],'error':['access_denied'],'state':['original-state'],'iss':[m.BASE]});self.assertEqual(len(rpc.call_args_list),1)
 async def test_selected_company_validated_before_consent(self):
  targets=[{'client_id':'permitted','company_id':'co'}]
  with patch.object(m,'authorization_targets',AsyncMock(return_value=targets)):
   self.assertEqual(await m.consent_scope(None,{'target_client':'permitted','target_company':'co'}),{'tenant':'permitted','company':'co'})
   with self.assertRaises(Invalid):await m.consent_scope(None,{'target_client':'other','target_company':'co'})
 async def test_approval_uses_selected_target_and_preserves_callback(self):
  async def rpc(store,action,args):return {'code':'issued-code'} if action=='consent' else {'name':'AI client'}
  with patch.object(m,'authorization_targets',AsyncMock(return_value=[{'client_id':'permitted','company_id':'co'}])),patch.object(m,'rpc',side_effect=rpc) as called:
   r=await m.browser(request('/api/ai-connections/authorize',body={**self.args,'target_client':'permitted','target_company':'co'}),None)
  payload=called.call_args_list[-1].args[2];self.assertEqual(payload['tenant'],'permitted');self.assertEqual(payload['company'],'co');self.assertEqual(parse_qs(urlsplit(json.loads(r.body)['redirect']).query)['state'],['original-state'])
 async def test_no_discovery_assignment_does_not_break_connection_settings(self):
  from app import mcp_builder
  with patch.object(discovery,'rpc',AsyncMock(return_value={'assigned':False})) as rpc,patch.object(mcp_builder,'rpc',AsyncMock(return_value={'document':{}})):
   self.assertEqual(await m.reviewed_plans(None,{}),[])
  self.assertEqual(len(rpc.call_args_list),1);self.assertEqual(rpc.call_args.args[1],'get')
 async def test_incomplete_request_shows_recovery_without_redirect(self):
  r=await m.browser(request('/oauth/authorize',query={'redirect_uri':'https://evil.invalid'}),None)
  self.assertEqual(r.status_code,400);self.assertIn(b'Return to Claude',r.body);self.assertNotIn('location',r.headers)
