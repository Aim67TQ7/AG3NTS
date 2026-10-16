import unittest,os,json
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import Request
import httpx
from app import fresh,main,library
class FreshTests(unittest.IsolatedAsyncioTestCase):
 def test_storage_and_headers_require_context(self):
  with self.assertRaises(ValueError):fresh.physical('workflows/test.json')
  marker=fresh.CTX.set({'token':'user-token','client':{'id':'richmond'}})
  try:
   self.assertEqual(fresh.physical('agents/x.json'),'richmond/agents/x.json')
   self.assertEqual(dict(fresh.HEAD)['Authorization'],'Bearer user-token')
   self.assertNotEqual(dict(fresh.HEAD)['Authorization'],'Bearer legacy-service-key')
   with self.assertRaises(ValueError):fresh.physical('../bunting/a')
  finally:fresh.CTX.reset(marker)
 async def test_anonymous_api_and_old_owner_cookie_cannot_enter(self):
  async def handler(req):return httpx.Response(401,json={})
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
   request=Request({'type':'http','method':'GET','path':'/api/state','headers':[(b'host',b'flux.by-pete.com'),(b'cookie',b'__Host-flux_session=old-token')],'scheme':'https','query_string':b''})
   with patch.dict(os.environ,{'STUDIO_PUBLIC_HOST':'flux.by-pete.com'}):
    r=await fresh.boundary(request,None,SimpleNamespace(CLIENT=client))
   self.assertEqual(r.status_code,401)
 async def test_other_client_and_non_admin_are_denied(self):
  async def handler(req):
   if req.url.path.endswith('/user'):return httpx.Response(200,json={'id':'alice','email':'alice@example.test','email_confirmed_at':'2026-01-01'})
   if 'flux_memberships' in req.url.path:return httpx.Response(200,json=[{'client_id':'bunting','role':'editor'}])
   if 'flux_clients' in req.url.path:return httpx.Response(200,json=[{'id':'bunting','name':'Bunting'}])
   return httpx.Response(200,json=[])
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
   for path,body in [('/api/account/switch',{'client':'richmond'}),('/api/account/users',{'email':'eve@example.test','role':'owner'})]:
    async def receive():return {'type':'http.request','body':json.dumps(body).encode(),'more_body':False}
    request=Request({'type':'http','method':'POST','path':path,'headers':[(b'host',b'flux.by-pete.com'),(b'origin',b'https://flux.by-pete.com'),(b'content-type',b'application/json'),(b'cookie',b'__Host-flux_access=user-token')],'scheme':'https','query_string':b''},receive)
    with patch.dict(os.environ,{'STUDIO_PUBLIC_HOST':'flux.by-pete.com'}):r=await fresh.boundary(request,None,SimpleNamespace(CLIENT=client,ACTOR=main.ACTOR))
    self.assertEqual(r.status_code,403)
 def test_library_role_comes_from_verified_request_not_legacy_env(self):
  marker=fresh.CTX.set({'token':'user-token','client':{'id':'richmond'},'user':{'id':'alice'},'role':'user'})
  try:
   with patch.dict(os.environ,{'FLUX_FRESH':'1'}):
    self.assertEqual(library.context(),('richmond','alice','user'))
    with self.assertRaises(Exception):library.context(True)
  finally:fresh.CTX.reset(marker)
 async def test_credential_selection_cannot_be_fabricated_or_reused_for_other_agent(self):
  async def get(path):return {'agent_id':'one','client':'bunting','selected_by':'alice','resource_id':'entra','resource_version':'1','resource_hash':'hash'}
  marker=fresh.CTX.set({'client':{'id':'bunting'},'user':{'id':'alice'}})
  try:
   ref={'id':'entra','version':'1','content_hash':'hash','selection_id':'receipt'}
   self.assertEqual((await fresh.verify_selection(SimpleNamespace(get=get),ref,'one'))['selected_by'],'alice')
   with self.assertRaises(ValueError):await fresh.verify_selection(SimpleNamespace(get=get),ref,'two')
   with self.assertRaises(ValueError):await fresh.verify_selection(SimpleNamespace(get=get),{k:v for k,v in ref.items() if k!='selection_id'},'one')
  finally:fresh.CTX.reset(marker)
 async def test_password_only_login_sets_cookie_only_after_verification(self):
  for accepted in (False,True):
   async def handler(req):
    self.assertTrue(req.url.path.endswith('/flux_password_signin'))
    return httpx.Response(200,json={'token':'flx_synthetic','expires_in':28800} if accepted else {'error':'Invalid email or password'})
   async def receive():return {'type':'http.request','body':json.dumps({'email':'alice@example.test','password':'synthetic-password'}).encode(),'more_body':False}
   req=Request({'type':'http','method':'POST','path':'/auth/login','headers':[],'query_string':b''},receive)
   async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
    response=await fresh.auth_request(req,SimpleNamespace(CLIENT=client),'/auth/login')
    self.assertEqual(response.status_code,200 if accepted else 401)
    if accepted:self.assertIn('HttpOnly',response.headers['set-cookie'])
    else:self.assertNotIn('set-cookie',response.headers)
    self.assertNotIn('synthetic-password',response.body.decode())
