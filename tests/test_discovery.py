import copy,unittest,uuid
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
from contextvars import ContextVar
from jsonschema import validate,ValidationError
from app import discovery as d,mcp_connection as m,fresh
from app.core import Invalid
class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.ctx={'token':'fmca_fixture','role':'owner','user':{'id':'user-a','email':'test@example.invalid'},'client':{'id':'tenant-a','name':'A'},'company':{'id':'company-a','name':'A','code':'A','facility':''}}
  self.marker=fresh.CTX.set(self.ctx);self.store=SimpleNamespace(ACTOR=ContextVar('discovery-test',default='user-a'),now=lambda:'2026-10-16T12:00:00Z')
  agent={'name':'Read invoice','capability':'READ',**{k:'Synthetic review required' for k in ('responsibility','trigger','input','action','output','error','verify')}}
  flow={'title':'Synthetic invoice study','purpose':'Test only','priority':'needs_clarification','discovery_question_ids':['q1','q8'],**{k:[] for k in ('assumptions','unresolved_questions','systems','credential_needs','accountable_roles','approval_points')},'agents':[agent]}
  self.args={'request_id':str(uuid.uuid4()),'discovery_revision':1,'discovery_hash':'a'*64,'plan':{'summary':'Synthetic plan','workflows':[flow],'open_questions':['Confirm owner']}}
 def tearDown(self):fresh.CTX.reset(self.marker)
 async def test_mcp_uses_verified_connection_scope_only(self):
  client=SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(status_code=200,json=lambda:{'assigned':True})))
  await d.rpc(SimpleNamespace(CLIENT=client),'submit',{'tenant':'other','company':'other','answers':{}})
  payload=client.post.call_args.kwargs
  self.assertEqual(payload['json'],{'action':'mcp_read','args':{'access_token':'fmca_fixture'}});self.assertNotIn('x-flux-session',payload['headers'])
 async def test_browser_scope_overwrites_callers_scope(self):
  fresh.CTX.set({**self.ctx,'token':'flx_fixture'})
  client=SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(status_code=200,json=lambda:{'assigned':True})))
  await d.rpc(SimpleNamespace(CLIENT=client),'save',{'tenant':'other','company':'other'})
  self.assertEqual(client.post.call_args.kwargs['json']['args'],{'tenant':'tenant-a','company':'company-a'})
 async def test_plan_retries_and_stale_discovery(self):
  rows={}
  async def rpc(store,action,args):
   if action=='mcp_get':return {'object':rows.get(args['path'])}
   if action=='mcp_put':rows[args['path']]=copy.deepcopy(args['body']);return {}
   raise AssertionError(action)
  source={'submitted':True,'revision':1,'content_hash':'a'*64,'questionnaire_version':'test-v1'}
  with patch.object(d,'context',AsyncMock(return_value=source)),patch.object(m,'rpc',side_effect=rpc):
   first=await m.dispatch('submit_workflow_plan',self.args,self.store)
   self.assertEqual(first,await m.dispatch('submit_workflow_plan',self.args,self.store));self.assertEqual(len(rows),1)
   self.assertFalse(first['activation_enabled']);self.assertEqual(next(iter(rows.values()))['proposal']['agent_power'],'Off')
   changed=copy.deepcopy(self.args);changed['plan']['summary']='different'
   with self.assertRaises(Invalid):await m.dispatch('submit_workflow_plan',changed,self.store)
   with self.assertRaises(Invalid):await m.dispatch('submit_workflow_plan',{**self.args,'discovery_revision':2},self.store)
 async def test_unsubmitted_discovery_cannot_create_plan(self):
  with patch.object(d,'context',AsyncMock(return_value={'submitted':False})),patch.object(m,'rpc',AsyncMock()) as rpc:
   with self.assertRaises(Invalid):await m.dispatch('submit_workflow_plan',self.args,self.store)
   rpc.assert_not_called()
 def test_plan_rejects_secret_extra_authority_and_bad_question(self):
  bad=copy.deepcopy(self.args);bad['plan']['workflows'][0]['execution_enabled']=True
  with self.assertRaises(ValidationError):validate(bad,m.object_schema(m.PLAN_ARGUMENTS))
  bad=copy.deepcopy(self.args);bad['plan']['workflows'][0]['discovery_question_ids']=['q999']
  with self.assertRaises(ValidationError):validate(bad,m.object_schema(m.PLAN_ARGUMENTS))
  bad=copy.deepcopy(self.args);bad['plan']['summary']='api_key=secret'
  with self.assertRaises(Invalid):m.no_secrets(bad)
 def test_questions_and_unknowns_present(self):
  self.assertEqual(len(d.QUESTIONS),10)
  for option in ('unknown','not_applicable','someone_else'):self.assertIn(option,d.PAGE)
  self.assertIn('get_business_discovery',d.PAGE)

class CompanyDiscoveryTests(unittest.IsolatedAsyncioTestCase):
 async def test_questionnaire_version_selects_company_questions(self):
  marker=fresh.CTX.set({'company':{'name':'n0v8v LLC'}})
  try:
   with patch.object(d,'rpc',AsyncMock(return_value={'assigned':True,'questionnaire_version':'n0v8v-discovery-v1','submitted':False})):
    result=await d.context(None)
   self.assertEqual(len(result['questions']),10);self.assertIn('n0v8v LLC',result['questions'][0]['question']);self.assertNotIn('Richland',str(result));self.assertEqual(result['company_name'],'n0v8v LLC')
   with patch.object(d,'rpc',AsyncMock(return_value={'assigned':True,'questionnaire_version':'richland-discovery-v1','submitted':False})):
    result=await d.context(None)
   self.assertIn('Richland',result['questions'][0]['question']);self.assertNotIn('n0v8v LLC',result['questions'][0]['question'])
  finally:fresh.CTX.reset(marker)
 def test_company_page_is_escaped_and_has_no_other_company_content(self):
  page=d.page_for_company('n0v8v LLC','n0v8v-discovery-v1')
  self.assertIn('n0v8v LLC FLUX',page);self.assertNotIn('Richland',page);self.assertNotIn('joint-interest',page);self.assertNotIn('__COMPANY__',page);self.assertNotIn('__STUDIES__',page)
  self.assertIn('&lt;script&gt;',d.page_for_company('<script>','n0v8v-discovery-v1'))
