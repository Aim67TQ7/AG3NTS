import copy,json,unittest,uuid
from unittest.mock import patch,AsyncMock
from contextvars import ContextVar
from types import SimpleNamespace
from starlette.requests import Request
from app import mcp_connection as m,fresh,studio
from app.core import Invalid

def request(body,token='fmca_test',origin=None):
 data=json.dumps(body).encode();headers=[(b'authorization',('Bearer '+token).encode())]
 if origin:headers.append((b'origin',origin.encode()))
 async def receive():return {'type':'http.request','body':data,'more_body':False}
 return Request({'type':'http','method':'POST','path':'/mcp','headers':headers},receive)
class McpTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.rows={};self.events=[]
  async def get(p):return self.rows.get(p)
  async def put(p,v):
   if p in self.rows:raise ValueError('Duplicate')
   self.rows[p]=copy.deepcopy(v);return v
  async def records(p):return [copy.deepcopy(v) for k,v in self.rows.items() if k.startswith(p+'/')]
  async def event(*a,**kw):self.events.append((a,kw))
  self.store=SimpleNamespace(ACTOR=ContextVar('test_actor',default='user-a'),get=get,put=put,records=records,event=event,now=lambda:'2026-10-16T12:00:00Z',ident=lambda v:v)
  self.context={'token':'flx_fixture','user':{'id':'user-a','email':'a@example.invalid'},'role':'editor','client':{'id':'tenant-a','name':'Client A'},'company':{'id':'company-a','code':'BMC','facility':'500','name':'BMC'}}
  async def rpc(store,action,args=None,token=None):
   if action=='mcp_get':return {'object':self.rows.get(args['path'])}
   if action=='mcp_put':return await put(args['path'],args['body'])
   if action=='mcp_workflows':return {'workflows':list(self.rows.values())}
   if action=='mcp_event':return {}
   raise AssertionError('Unexpected RPC '+action)
  self.rpcpatch=patch.object(m,'rpc',side_effect=rpc);self.rpcpatch.start()
  self.marker=fresh.CTX.set(self.context);self.patch=patch.object(studio,'store',self.store);self.patch.start()
 async def asyncTearDown(self):self.patch.stop();self.rpcpatch.stop();fresh.CTX.reset(self.marker)
 async def test_no_bearer_is_challenged_and_cross_origin_denied(self):
  self.assertEqual((await m.mcp(request({},token=''),self.store)).status_code,401)
  self.assertEqual((await m.mcp(request({},origin='https://evil.invalid'),self.store)).status_code,403)
 async def test_initialize_stateless_and_context_reset(self):
  resolved={k:v for k,v in self.context.items() if k!='token'}|{'session':'flx_new','connection_id':'connection'}
  with patch.object(m,'rpc',AsyncMock(return_value=resolved)):
   r=await m.mcp(request({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}}),self.store)
  self.assertEqual(json.loads(r.body)['result']['protocolVersion'],'2025-06-18');self.assertEqual(fresh.CTX.get()['token'],'flx_fixture')
 async def test_preference_proposal_is_private_idempotent_and_not_memory(self):
  a={'request_id':str(uuid.uuid4()),'preferences':{'preferred_name':'Robert'}}
  first=await m.dispatch('propose_builder_preferences',a,self.store);second=await m.dispatch('propose_builder_preferences',a,self.store)
  self.assertEqual(first,second)
  with self.assertRaises(Invalid):await m.dispatch('propose_builder_preferences',{**a,'preferences':{'preferred_name':'Other'}},self.store)
  self.assertEqual(len(self.rows),1);self.assertFalse(first['activation_enabled'])
 async def test_secret_and_permission_preferences_rejected(self):
  for prefs in ({'role':'owner'},{'building_goals':'api_key=secretvalue'}):
   with self.assertRaises(Invalid):await m.dispatch('propose_builder_preferences',{'request_id':str(uuid.uuid4()),'preferences':prefs},self.store)
 async def test_company_workflows_are_filtered(self):
  self.rows={'workflows/a':{'id':'a','tenant':'tenant-a','company':'BMC','facility':'500','name':'A','version':'0.0.1'},'workflows/b':{'id':'b','tenant':'other','company':'BMC','facility':'500'}}
  result=await m.dispatch('list_workflows',{},self.store);self.assertEqual([w['id'] for w in result['workflows']],['a'])
  from app import mcp_builder
  with patch.object(mcp_builder,'rpc',AsyncMock(return_value={'revision':0,'document':{},'workflows':[{'path':'workflows/a','body':self.rows['workflows/a'],'can_edit':True}]})):
   with self.assertRaises(Invalid):await m.dispatch('read_workflow',{'workflow_id':'b'},self.store)
 async def test_unknown_methods_never_expose_runtime(self):
  self.assertFalse(any('publish' in t['name'] or 'enable' in t['name'] for t in m.tools()))
  with self.assertRaises(Invalid):await m.dispatch('enable_agent',{},self.store)
 def test_authorization_requires_resource_pkce_and_build_scope(self):
  good={'response_type':'code','code_challenge_method':'S256','code_challenge':'a'*43,'resource':m.RESOURCE,'scope':'flux:build offline_access'}
  self.assertEqual(m.authorization(good),good)
  for bad in ({**good,'resource':'https://other.invalid'},{**good,'code_challenge_method':'plain'},{**good,'scope':'admin'}):
   with self.assertRaises(Invalid):m.authorization(bad)
