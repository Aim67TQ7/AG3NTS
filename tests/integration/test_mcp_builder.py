"""Real local PostgreSQL via PGlite; existing OAuth/ACL contracts are synthetic stubs."""
import asyncio,copy,json,os,shutil,subprocess,unittest,uuid
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
from app import mcp_builder as b,mcp_connection as m,fresh,studio
from app.core import digest,Invalid
ROOT=Path(__file__).resolve().parents[2]
NODE=os.environ.get('FLUX_TEST_NODE') or shutil.which('node') or 'node'
BRIDGE=os.environ.get('FLUX_TEST_PG_BRIDGE',str(ROOT/'tests/postgres/bridge.mjs'))
U='00000000-0000-4000-8000-000000000001';C='00000000-0000-4000-8000-000000000002';OTHER='00000000-0000-4000-8000-000000000003'
class Database:
 def __init__(self):self.p=subprocess.Popen([NODE,BRIDGE],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 def call(self,**q):
  self.p.stdin.write(json.dumps(q)+'\n');self.p.stdin.flush();x=json.loads(self.p.stdout.readline())
  if not x['ok']:raise RuntimeError(x['error'])
  return x['result']
 def sql(self,q,params=None):return self.call(sql=q,params=params or [])['rows']
 def close(self):self.p.stdin.close();self.p.wait(timeout=10);self.p.stdout.close();self.p.stderr.close()
class BuilderIntegration(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):
  cls.db=Database();cls.db.call(exec=(ROOT/'tests/integration/builder_bootstrap.sql').read_text());cls.db.call(exec=(ROOT/'migrations/20261016_mcp_build_sessions.sql').read_text());cls.db.call(exec=__import__('runpy').run_path(str(ROOT/'scripts/generate_builder_lock_sql.py'))['migration_sql']());cls.db.call(exec=(ROOT/'sql/flux_mcp_v2.sql').read_text());cls.db.call(exec=(ROOT/'sql/flux_mcp_v2_environments.sql').read_text());cls.db.sql('insert into flux_memberships values ($1,$2,$3)',[U,'tenant-a','owner']);cls.db.sql('insert into flux_companies values ($1,$2,$3,$4)',[C,'tenant-a','BMC','500'])
 @classmethod
 def tearDownClass(cls):cls.db.close()
 async def asyncSetUp(self):
  self.db.sql('select set_config($1,$2,false)',['test.actor',U]);self.db.sql('select set_config($1,$2,false)',['test.tenant','tenant-a']);self.db.sql('select set_config($1,$2,false)',['test.company',C]);self.db.sql('select set_config($1,$2,false)',['test.company_denied','no'])
  self.ctx={'token':'fmca_synthetic','user':{'id':U,'email':'synthetic@example.invalid'},'role':'owner','client':{'id':'tenant-a','name':'A'},'company':{'id':C,'code':'BMC','facility':'500','name':'BMC'}};self.marker=fresh.CTX.set(self.ctx)
  async def post(url,headers,json):
   args=json['args'];self.last_args=args
   try:
    rpc_name='flux_builder_observe' if url.endswith('/flux_builder_observe') else 'flux_builder_session'
    r=self.db.sql('select public.'+rpc_name+'($1,$2::jsonb) result',[json['action'],__import__('json').dumps(args)]);return SimpleNamespace(status_code=200,json=lambda:r[0]['result'])
   except RuntimeError as e:
    return SimpleNamespace(status_code=400,json=lambda:{'message':str(e),'code':'P0001'})
  self.store=SimpleNamespace(CLIENT=SimpleNamespace(post=post),ACTOR=ContextVar('builder_test_actor',default=U),now=lambda:'2026-10-16T12:00:00Z')
 async def asyncTearDown(self):fresh.CTX.reset(self.marker)
 def agent(self,**fields):return {'capability':'READ','name_options':['Retriever','Reader','Source reader'],'responsibility_options':['Read one source','Retrieve one source','Obtain one source'],'fields':{'output.outcomes':'completed_only',**fields}}
 async def call(self,tool,**args):return await m.dispatch(tool,args,self.store)
 async def submit(self,**fields):return await self.call('submit_agent_draft',request_id=str(uuid.uuid4()),agent=self.agent(**fields))
 async def test_targeted_edit_stale_invalid_and_owner(self):
  a=await self.submit();old=copy.deepcopy(a['draft']);id=a['draft_id'];args={'request_id':str(uuid.uuid4()),'draft_id':id,'expected_hash':a['content_hash'],'fields':{'output.record_type':'document.extracted'}}
  # Pick an actual catalog option rather than invent a business record.
  f=studio.FIELDS['output.record_type'];args['fields']['output.record_type']=f['options'][0]['id']
  saved=await self.call('update_agent_draft',**args);self.assertEqual(saved['revision'],2);self.assertEqual(saved['draft']['fields']['trigger.type'],old['fields']['trigger.type']);self.assertTrue(saved['validation']['blocks_publish']);self.assertEqual(saved,await self.call('update_agent_draft',**args))
  with self.assertRaises(b.BuilderError):await self.call('update_agent_draft',**{**args,'request_id':str(uuid.uuid4())})
  before=self.db.sql('select count(*) n from flux_private.builder_history')[0]['n']
  for fields in ({'output.record_type':'bogus'},{'not.a.field':'x'},{'identity.owner':OTHER},{'output.record_type':44}):
   with self.assertRaises(b.BuilderError):await self.call('update_agent_draft',**{**args,'request_id':str(uuid.uuid4()),'expected_hash':saved['content_hash'],'fields':fields})
  self.assertEqual(before,self.db.sql('select count(*) n from flux_private.builder_history')[0]['n']);self.assertEqual((await self.call('read_agent_draft',draft_id=id))['content_hash'],saved['content_hash'])
 async def test_seven_step_atomic_connected_and_browser_apply(self):
  args={'request_id':str(uuid.uuid4()),'name':'Seven steps','nodes':[{'key':str(i),'agent':self.agent()} for i in range(7)],'edges':[{'source':str(i),'target':str(i+1),'on_outcome':'COMPLETED'} for i in range(6)]}
  x=await self.call('propose_connected_workflow',**args);self.assertEqual(len(x['edges']),6);self.assertEqual([n['position']['x'] for n in x['nodes']],[100+360*i for i in range(7)]);self.assertEqual(x,await self.call('propose_connected_workflow',**args));self.assertEqual(x['drafts'][0]['draft']['fields']['identity.owner']['value'],U)
  with self.assertRaises(b.BuilderError):await self.call('propose_connected_workflow',**{**args,'name':'Changed'})
  with self.assertRaises(b.BuilderError):await self.call('propose_connections',request_id=str(uuid.uuid4()),workflow_id=x['workflow_id'],expected_hash=x['content_hash'],edges=[{'source':x['nodes'][0]['id'],'target':'foreign','on_outcome':'COMPLETED'}])
  self.assertEqual(len((await self.call('read_workflow',workflow_id=x['workflow_id']))['edges']),6)
  proposal={'record_kind':'workflows','record_id':x['workflow_id']}
  with self.assertRaises(b.BuilderError):await b.review(self.store,proposal,True,x['content_hash'])
  self.ctx['token']='flx_browser';result=await b.review(self.store,proposal,True,x['content_hash']);self.assertEqual(len(result['canvas']['edges']),6);self.assertFalse(result['canvas']['execution_enabled']);self.assertEqual(result,await b.review(self.store,proposal,True,x['content_hash']))
  native=self.db.sql("select body from flux_app_objects where path=$1",['workflows/'+x['workflow_id']+'--0.0.1.json'])[0]['body'];self.assertEqual(len(native['nodes']),7);self.assertEqual(native['content_hash'],digest({k:v for k,v in native.items() if k!='content_hash'}));self.assertTrue(all(n['data']['guided_hash']==digest(n['data']['guided']) for n in native['nodes']))
 async def test_resources_immutable_canonical_pending_and_approval(self):
  rid='shape-'+uuid.uuid4().hex[:10];args={'request_id':str(uuid.uuid4()),'resource_id':rid,'version':'1.0.0','label':'Synthetic contract','schema':{'type':'object','properties':{'amount':{'type':'number'}}}}
  r=await self.call('propose_schema',**args);self.assertEqual(r['status'],'proposed');self.assertEqual(r['content_hash'],digest(args['schema']));self.assertEqual(r,await self.call('propose_schema',**args))
  duplicate=await self.call('propose_schema',**{**args,'request_id':str(uuid.uuid4())});self.assertTrue(duplicate['deduplicated'])
  with self.assertRaises(b.BuilderError):await self.call('propose_schema',**{**args,'request_id':str(uuid.uuid4()),'schema':{'type':'object'}})
  rule=await self.call('propose_rule',request_id=str(uuid.uuid4()),resource_id='tolerance-'+uuid.uuid4().hex[:8],version='1.0.0',label='Explicit tolerance',rule=[{'op':'within_tolerance','field':'amount','baseline_field':'expected','absolute_tolerance':0.01}])
  a=await self.submit(**{'input.schema':r['id'],'execute.rule':rule['id']});findings=a['validation']['findings'];self.assertTrue(any(f['rule_id']=='dependency-not-approved' for f in findings));self.assertTrue(any(f['rule_id']=='rule-runtime-support' for f in findings))
  self.ctx['token']='flx_browser';await b.review(self.store,{'record_kind':'resources','record_id':r['id']},True,digest((await b.rpc(self.store,'snapshot'))['document']['resources'][r['id']]['body']))
  # Synthetic approval uses the existing canonical resource + resource.published shape.
  canonical_id='tenant-a.'+rid;body={'id':canonical_id,'version':'1.0.0','kind':'schema','content':args['schema'],'content_hash':r['content_hash'],'tenant':'tenant-a'}
  self.db.sql('insert into flux_app_objects(client_id,path,body) values ($1,$2,$3::jsonb)',['tenant-a','resources/'+canonical_id+'--1.0.0.json',json.dumps(body)])
  self.db.sql('insert into flux_app_objects(client_id,path,body) values ($1,$2,$3::jsonb)',['tenant-a','audit/'+uuid.uuid4().hex+'.json',json.dumps({'action':'resource.published','payload':{'resource_ref':r['id']}})])
  full=await self.call('read_resource',id=r['id']);self.assertEqual(full['status'],'approved');self.assertEqual(full['content_hash'],r['content_hash']);items=(await self.call('list_resources',kind='schema',limit=100))['items'];self.assertEqual(sum(i['id']==r['id'] for i in items),1)
 async def test_sql_cas_scope_and_audit_immutable(self):
  await self.submit();snap=await b.rpc(self.store,'snapshot')
  with self.assertRaises(b.BuilderError):await b.rpc(self.store,'commit',{'request_id':str(uuid.uuid4()),'request_hash':'a'*64,'expected_revision':snap['revision']-1,'document':snap['document'],'changes':[],'response':{}})
  forged=copy.deepcopy(snap['document']);forged['waivers']={'fake':{'review_status':'approved'}}
  with self.assertRaises(b.BuilderError):await b.rpc(self.store,'commit',{'request_id':str(uuid.uuid4()),'request_hash':'a'*64,'expected_revision':snap['revision'],'document':forged,'changes':[],'response':{}})
  with self.assertRaises(RuntimeError):self.db.sql('delete from flux_private.builder_history')
  self.db.sql('select set_config($1,$2,false)',['test.company_denied','yes'])
  with self.assertRaises(b.BuilderError):await self.call('list_resources')
 async def test_waiver_owner_review_and_plan_without_discovery(self):
  w=await self.call('propose_discovery_waiver',request_id=str(uuid.uuid4()),reason='Owner understands this synthetic business',assumptions=['Confirm details'],credential_requirements=['None during design'],accountable_roles=['Owner'])
  plan={'summary':'Synthetic plan','workflows':[{'title':'Review','purpose':'Review documents','priority':'low','discovery_question_ids':[],**{k:[] for k in ('assumptions','unresolved_questions','systems','credential_needs','accountable_roles','approval_points')},'agents':[{'name':'Read','capability':'READ','responsibility':'Read one document',**{k:'Requires confirmation' for k in ('trigger','input','action','output','error','verify')}}]}],'open_questions':[]}
  args={'request_id':str(uuid.uuid4()),'source':{'kind':'waiver','waiver_id':w['id'],'content_hash':w['content_hash']},'plan':plan}
  with self.assertRaises(b.BuilderError):await self.call('submit_workflow_plan',**args)
  self.ctx['token']='flx_browser';self.ctx['role']='editor'
  with self.assertRaises(b.BuilderError):await b.review(self.store,{'record_kind':'waivers','record_id':w['id']},True,w['content_hash'])
  self.ctx['role']='owner';await b.review(self.store,{'record_kind':'waivers','record_id':w['id']},True,w['content_hash']);x=await self.call('submit_workflow_plan',**args);self.assertFalse(x['activation_enabled'])
  await b.review(self.store,{'record_kind':'plans','record_id':x['id']},True,x['content_hash'])
  from app import discovery
  with patch.object(discovery,'rpc',AsyncMock(return_value={'assigned':False})):
   plans=await m.reviewed_plans(self.store,{})
  self.assertTrue(any(p['proposal'].get('source',{}).get('waiver_id')==w['id'] for p in plans))
 async def test_known_incompatible_schema_rejects_entire_graph(self):
  r=await self.call('propose_schema',request_id=str(uuid.uuid4()),resource_id='strict-'+uuid.uuid4().hex[:8],version='1.0.0',label='Required',schema={'type':'object','properties':{'required_field':{'type':'string'}},'required':['required_field']})
  o=await self.call('propose_schema',request_id=str(uuid.uuid4()),resource_id='empty-'+uuid.uuid4().hex[:8],version='1.0.0',label='Empty',schema={'type':'object','properties':{},'additionalProperties':False})
  before=self.db.sql('select count(*) n from flux_private.builder_requests')[0]['n']
  with self.assertRaises(b.BuilderError):await self.call('propose_connected_workflow',request_id=str(uuid.uuid4()),name='Invalid chain',nodes=[{'key':'a','agent':self.agent(**{'output.schema':o['id']})},{'key':'b','agent':self.agent(**{'input.schema':r['id']})}],edges=[{'source':'a','target':'b','on_outcome':'COMPLETED'}])
  self.assertEqual(before,self.db.sql('select count(*) n from flux_private.builder_requests')[0]['n'])
 async def test_catalog_transport_contract_and_secret_rejection(self):
  result=await self.call('get_catalog');self.assertEqual(result['catalog_rule_count'],23);self.assertEqual(result,await self.call('get_catalog'))
  with self.assertRaises(b.BuilderError):await self.call('submit_agent_draft',request_id='invalid',agent=self.agent())
  self.assertTrue({'read_agent_draft','update_agent_draft','propose_connections','propose_schema','propose_rule'}<={t['name'] for t in m.tools()})
 async def test_reviewed_draft_patch_requires_renewed_review_and_new_canvas_version(self):
  a=await self.submit();proposal={'record_kind':'workflows','record_id':a['workflow_id']};self.ctx['token']='flx_browser';await b.review(self.store,proposal,True,a['workflow_content_hash'])
  read=await self.call('read_agent_draft',draft_id=a['draft_id']);self.assertEqual(read['review_status'],'applied')
  rule=await self.call('propose_rule',request_id=str(uuid.uuid4()),resource_id='exact-'+uuid.uuid4().hex[:8],version='1.0.0',label='Exact check',rule=[{'op':'present','field':'invoice_number'}])
  x=await self.call('update_agent_draft',request_id=str(uuid.uuid4()),draft_id=a['draft_id'],expected_hash=read['content_hash'],fields={'execute.rule':rule['id']});self.assertEqual(x['review_status'],'awaiting_user_review');self.assertEqual(x['draft']['fields']['execute.rule']['value'],rule['id']);self.assertEqual(x['draft']['fields']['trigger.type'],read['draft']['fields']['trigger.type'])
  canvas=await b.review(self.store,proposal,True,x['workflow_content_hash']);self.assertEqual(canvas['canvas']['version'],'0.0.2');self.assertFalse(canvas['canvas']['execution_enabled'])
 async def test_existing_native_agent_and_workflow_grounded_plan(self):
  sid='native-'+uuid.uuid4().hex[:8];s=b.Session(self.store,{'revision':0,'document':{}});g=s.guided(self.agent(),sid);g['fields']['execute.authority']={'value':studio.FIELDS['execute.authority']['options'][0]['id'],'source':'user','why':'Synthetic human choice'}
  body={'id':sid,'version':'1.0.0','guided':g,'company':'BMC','facility':'500','content_hash':digest(g)}
  self.db.sql('insert into flux_app_objects(client_id,path,body) values ($1,$2,$3::jsonb)',['tenant-a','agents/'+sid+'--1.0.0.json',json.dumps(body)])
  a=await self.call('read_agent_draft',draft_id=sid);self.assertEqual(a['draft']['fields']['execute.authority']['source'],'user')
  x=await self.call('update_agent_draft',request_id=str(uuid.uuid4()),draft_id=sid,expected_hash=a['content_hash'],fields={'output.record_type':studio.FIELDS['output.record_type']['options'][0]['id']});self.assertEqual(x['draft']['fields']['execute.authority'],g['fields']['execute.authority'])
  from app.mcp_connection import PLAN_ARGUMENTS
  plan={'summary':'Existing workflow plan','workflows':[{'title':'Read','purpose':'Read source','priority':'low','discovery_question_ids':[],**{k:[] for k in ('assumptions','unresolved_questions','systems','credential_needs','accountable_roles','approval_points')},'agents':[{'name':'Reader','capability':'READ','responsibility':'Read source',**{k:'Confirm with owner' for k in ('trigger','input','action','output','error','verify')}}]}],'open_questions':[]}
  result=await self.call('submit_workflow_plan',request_id=str(uuid.uuid4()),source={'kind':'workflow','workflow_id':x['workflow_id'],'content_hash':x['workflow_content_hash']},plan=plan);self.assertEqual(result['review_status'],'awaiting_user_review')
 async def test_outcomes_cycles_and_all_or_nothing_connections(self):
  x=await self.call('propose_connected_workflow',request_id=str(uuid.uuid4()),name='Branch checks',nodes=[{'key':str(i),'agent':self.agent()} for i in range(3)],edges=[])
  ids=[n['id'] for n in x['nodes']];base={'workflow_id':x['workflow_id'],'expected_hash':x['content_hash']}
  cases=[[{'source':ids[0],'target':ids[1],'on_outcome':'COMPLETED'},{'source':ids[1],'target':ids[2],'on_outcome':'BOGUS'}],[{'source':ids[0],'target':ids[1],'on_outcome':'COMPLETED'},{'source':ids[1],'target':ids[0],'on_outcome':'COMPLETED'}],[{'source':ids[0],'target':ids[1],'on_outcome':'COMPLETED'},{'source':ids[0],'target':ids[2],'on_outcome':'COMPLETED'}]]
  for edges in cases:
   with self.assertRaises(b.BuilderError):await self.call('propose_connections',request_id=str(uuid.uuid4()),edges=edges,**base)
  self.assertEqual((await self.call('read_workflow',workflow_id=x['workflow_id']))['edges'],[])
 async def test_cross_client_company_and_membership_removal(self):
  a=await self.submit();self.db.sql('select set_config($1,$2,false)',['test.actor',OTHER])
  with self.assertRaises(b.BuilderError):await self.call('read_agent_draft',draft_id=a['draft_id'])
  self.db.sql('select set_config($1,$2,false)',['test.actor',U]);self.ctx['token']='flx_browser';self.ctx['client']['id']='other-client'
  with self.assertRaises(b.BuilderError):await self.call('list_resources')
 async def test_legacy_draft_can_be_read_and_corrected(self):
  id=str(uuid.uuid4());s=b.Session(self.store,{'revision':0,'document':{}});g=s.guided(self.agent(),'draft-mcp-'+id)
  row={'id':id,'created_by':U,'tenant':'tenant-a','company':C,'request_hash':'a'*64,'proposal':{'kind':'agent','guided':g}}
  self.db.sql('insert into flux_private.mcp_proposals(path,user_id,tenant,company,body) values ($1,$2,$3,$4,$5::jsonb)',['mcp-inbox/'+U+'-'+id+'.json',U,'tenant-a',C,json.dumps(row)])
  read=await self.call('read_agent_draft',draft_id='draft-mcp-'+id);saved=await self.call('update_agent_draft',request_id=str(uuid.uuid4()),draft_id=read['draft_id'],expected_hash=read['content_hash'],fields={'execute.rule':'none'});self.assertEqual(saved['draft']['fields']['execute.rule']['value'],'none')
  with self.assertRaises(b.BuilderError):await self.call('submit_agent_draft',request_id=id,agent=self.agent())
 async def test_transport_structured_errors_and_old_client_tools(self):
  from starlette.requests import Request
  async def old_rpc(store,action,args=None,token=None):
   if action=='resolve':return {k:v for k,v in self.ctx.items() if k!='token'}
   if action=='mcp_event':return {}
   raise AssertionError(action)
  payload=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'submit_agent_draft','arguments':{'request_id':str(uuid.uuid4()),'agent':self.agent(**{'output.record_type':'bogus'})}}}).encode()
  async def receive():return {'type':'http.request','body':payload,'more_body':False}
  request=Request({'type':'http','method':'POST','path':'/mcp','headers':[(b'authorization',b'Bearer fmca_synthetic')]},receive)
  with patch.object(m,'rpc',side_effect=old_rpc):result=json.loads((await m.mcp(request,self.store)).body)['result']
  self.assertTrue(result['isError']);error=json.loads(result['content'][0]['text'])['error'];self.assertEqual(error['field_path'],'output.record_type');self.assertIn('allowed_values',error)
  names={t['name'] for t in m.tools()};self.assertTrue({'get_business_discovery','submit_workflow_plan','builder_context','list_workflows','read_workflow','submit_agent_draft','get_builder_profile','propose_builder_preferences'}<=names)
 async def test_end_to_end_documented_example(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('builder_example',ROOT/'examples/mcp_build_session.py');example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)
  result=await example.run(self.call,str(uuid.uuid4()));self.assertEqual(result['nodes'],7);self.assertEqual(result['edges'],6);self.assertTrue(result['validation']['blocks_publish'])
  if os.environ.get('FLUX_CAPTURE_E2E'):Path(os.environ['FLUX_CAPTURE_E2E']).write_text(json.dumps(result,indent=2)+'\n')
 async def test_anon_has_only_scoped_rpc_access_and_no_direct_private_reads(self):
  await self.submit();self.db.sql('set role anon')
  try:
   with self.assertRaises(RuntimeError):self.db.sql('select * from flux_private.builder_sessions')
   with self.assertRaises(RuntimeError):self.db.sql('select * from flux_private.builder_history')
   rows=self.db.sql('select public.flux_builder_session($1,$2::jsonb) result',['snapshot',json.dumps({'access_token':'fmca_synthetic'})]);self.assertIn('document',rows[0]['result'])
   with self.assertRaises(RuntimeError):self.db.sql('select public.flux_builder_session($1,$2::jsonb) result',['review',json.dumps({'access_token':'fmca_synthetic','expected_revision':rows[0]['result']['revision']})])
  finally:self.db.sql('reset role')
 async def test_whole_workflow_unreachable_missing_inputs_and_outcomes(self):
  w=await self.call('propose_connected_workflow',request_id=str(uuid.uuid4()),name='Disconnected design',nodes=[{'key':str(i),'agent':self.agent()} for i in range(3)],edges=[{'source':'0','target':'1','on_outcome':'COMPLETED'}],entry_nodes=['0'])
  report=await self.call('validate_workflow',workflow_id=w['workflow_id']);ids={f['rule_id'] for f in report['findings']};self.assertTrue({'unreachable-node','missing-required-input','outcome-without-destination'}<=ids)
  blocked=next(f for f in report['findings'] if f['rule_id']=='unreachable-node');self.assertEqual(blocked['node_id'],w['nodes'][2]['id']);self.assertEqual(blocked['location']['workflow_id'],w['workflow_id'])
 async def test_navigable_pending_schema_dependency(self):
  r=await self.call('propose_schema',request_id=str(uuid.uuid4()),resource_id='navigate-'+uuid.uuid4().hex[:8],version='1.0.0',label='Pending shape',schema={'type':'object'})
  a=await self.submit(**{'input.schema':r['id']});f=next(f for f in a['validation']['findings'] if f['rule_id']=='dependency-not-approved');d=next(d for d in f['dependencies'] if d['resource_id']==r['id']);self.assertEqual(d['proposal_id'],r['proposal_id']);self.assertIn('#proposal-',d['review_url']);self.assertEqual(d['read']['tool'],'read_resource')
 async def test_atomic_change_set_review_and_save(self):
  a=await self.submit();suffix=uuid.uuid4().hex[:8];pin='schema:tenant-a.batch-'+suffix+'@1.0.0'
  operations=[{'tool':'propose_schema','arguments':{'resource_id':'batch-'+suffix,'version':'1.0.0','label':'Related contract','schema':{'type':'object'}}},{'tool':'update_agent_draft','arguments':{'draft_id':a['draft_id'],'expected_hash':a['content_hash'],'fields':{'input.schema':pin,'output.schema':pin}}}]
  args={'request_id':str(uuid.uuid4()),'title':'Contract and draft together','operations':operations};r=await self.call('propose_change_set',**args);self.assertTrue(r['diff']);self.assertEqual(r,await self.call('propose_change_set',**args))
  self.assertEqual((await self.call('read_agent_draft',draft_id=a['draft_id']))['content_hash'],a['content_hash'])
  with self.assertRaises(b.BuilderError):await self.call('read_resource',id=pin)
  self.ctx['token']='flx_browser';result=await b.review(self.store,{'record_kind':'change_sets','record_id':r['id']},True,r['content_hash']);self.assertEqual(result['status'],'applied');self.assertEqual((await self.call('read_resource',id=pin))['status'],'draft');self.assertEqual((await self.call('read_agent_draft',draft_id=a['draft_id']))['draft']['fields']['input.schema']['value'],pin)
  self.assertEqual(result,await b.review(self.store,{'record_kind':'change_sets','record_id':r['id']},True,r['content_hash']))
 async def test_change_set_late_failure_rolls_back_every_member(self):
  suffix=uuid.uuid4().hex[:8];rid='rollback-'+suffix
  ops=[{'tool':'propose_schema','arguments':{'resource_id':rid,'version':'1.0.0','label':'Rollback contract','schema':{'type':'object'}}},{'tool':'propose_connected_workflow','arguments':{'name':'Rejected canvas','nodes':[{'key':'a','agent':self.agent()}],'edges':[]}}]
  r=await self.call('propose_change_set',request_id=str(uuid.uuid4()),title='All or none',operations=ops);before=self.db.sql('select count(*) n from flux_app_objects')[0]['n'];self.ctx['token']='flx_browser'
  self.db.call(exec="create function public.reject_test_canvas() returns trigger language plpgsql as $$begin if new.body->>'name'='Rejected canvas' then raise exception 'synthetic late write rejection';end if;return new;end$$;create trigger reject_test_canvas before insert on flux_app_objects for each row execute function public.reject_test_canvas();")
  try:
   with self.assertRaises(b.BuilderError):await b.review(self.store,{'record_kind':'change_sets','record_id':r['id']},True,r['content_hash'])
   self.assertEqual(before,self.db.sql('select count(*) n from flux_app_objects')[0]['n']);self.assertEqual((await self.call('read_change_set',change_set_id=r['id']))['review_status'],'awaiting_user_review')
  finally:self.db.call(exec='drop trigger reject_test_canvas on flux_app_objects;drop function public.reject_test_canvas();')
 async def test_change_set_invalid_member_and_stale_base_leave_members_unchanged(self):
  a=await self.submit();ops=[{'tool':'update_agent_draft','arguments':{'draft_id':a['draft_id'],'expected_hash':a['content_hash'],'fields':{'execute.rule':'none'}}},{'tool':'update_agent_draft','arguments':{'draft_id':a['draft_id'],'expected_hash':a['content_hash'],'fields':{'output.record_type':'bogus'}}}]
  with self.assertRaises(b.BuilderError):await self.call('propose_change_set',request_id=str(uuid.uuid4()),title='Invalid related edit',operations=ops)
  self.assertEqual((await self.call('read_agent_draft',draft_id=a['draft_id']))['content_hash'],a['content_hash'])
  r=await self.call('propose_change_set',request_id=str(uuid.uuid4()),title='Stale related edit',operations=ops[:1]);await self.call('update_agent_draft',request_id=str(uuid.uuid4()),draft_id=a['draft_id'],expected_hash=a['content_hash'],fields={'output.record_type':studio.FIELDS['output.record_type']['options'][0]['id']});self.ctx['token']='flx_browser'
  with self.assertRaises(b.BuilderError):await b.review(self.store,{'record_kind':'change_sets','record_id':r['id']},True,r['content_hash'])
 async def test_sample_sandbox_checks_expected_actual_without_writes(self):
  suffix=uuid.uuid4().hex[:8];schema=await self.call('propose_schema',request_id=str(uuid.uuid4()),resource_id='sample-'+suffix,version='1.0.0',label='Sample numbers',schema={'type':'object','properties':{'amount':{'type':'number'},'expected':{'type':'number'}},'required':['amount','expected']});rule=await self.call('propose_rule',request_id=str(uuid.uuid4()),resource_id='sample-rule-'+suffix,version='1.0.0',label='Sample tolerance',rule=[{'op':'within_tolerance','field':'amount','baseline_field':'expected','absolute_tolerance':0.01}]);a=await self.submit(**{'input.schema':schema['id'],'execute.rule':rule['id']})
  before=self.db.sql('select count(*) n from flux_private.builder_history')[0]['n'];result=await self.call('sandbox_validate',draft_id=a['draft_id'],expected_hash=a['content_hash'],samples=[{'name':'match','document':{'amount':10,'expected':10},'expected':{'schema_valid':True,'rule_passed':True}},{'name':'mismatch','document':{'amount':11,'expected':10},'expected':{'schema_valid':True,'rule_passed':False}},{'name':'missing input','document':{'amount':10},'expected':{'schema_valid':False,'rule_passed':False}}]);self.assertTrue(result['all_expectations_met']);self.assertFalse(result['live_actions']);self.assertFalse(result['publication_authorized']);self.assertEqual(before,self.db.sql('select count(*) n from flux_private.builder_history')[0]['n'])
 async def test_connection_permissions_projection_and_secrets_exclusion(self):
  id=str(uuid.uuid4());credential='credential-'+uuid.uuid4().hex[:8];self.db.sql('insert into flux_app_objects(client_id,path,body) values($1,$2,$3::jsonb)',['tenant-a','library-tenant-a/'+credential+'--1.0.0.json',json.dumps({'id':credential,'version':'1.0.0','kind':'credential','encrypted_value':'SYNTHETIC-CIPHERTEXT','company':'BMC'})]);self.ctx['token']='flx_browser'
  await b.rpc(self.store,'approve_connection',{'id':id,'request_id':str(uuid.uuid4()),'credential_id':credential,'credential_version':'1.0.0','system':'epicor_rest','capabilities':['epicor.read']});connections=await self.call('list_connections');self.assertNotIn('SYNTHETIC-CIPHERTEXT',json.dumps(connections));self.assertNotIn('credential_path',json.dumps(connections))
  agent=self.agent();agent['connection_requirements']=[{'connection_id':id,'capabilities':['epicor.write']}];a=await self.call('submit_agent_draft',request_id=str(uuid.uuid4()),agent=agent);f=next(f for f in a['validation']['findings'] if f['rule_id']=='connection-permission-required');self.assertEqual(f['missing_permissions'],['epicor.write','read_only_capabilities'])
  with self.assertRaises(Exception):await self.call('submit_agent_draft',request_id=str(uuid.uuid4()),agent={**self.agent(),'questions_for_user':['password=do-not-save']})
  await b.rpc(self.store,'revoke_connection',{'id':id,'request_id':str(uuid.uuid4())});self.assertFalse(any(c['id']==id for c in (await self.call('list_connections'))['items']))
 async def test_catalog_lock_policy_matches_database_for_every_option(self):
  for cap in [c['code'] for c in studio.CATALOG['capabilities']]:
   rows=[{'field':field['id'],'value':option['id'],'expected':studio.decision_locked(field['id'],cap,option['id'])} for step in studio.CATALOG['steps'] for field in step['fields'] for option in field['options']]
   mismatches=self.db.sql("select x from jsonb_array_elements($1::jsonb) x where flux_private.builder_decision_locked(x->>'field',$2,x->>'value') is distinct from (x->>'expected')::boolean",[json.dumps(rows),cap])
   self.assertEqual(mismatches,[],cap)
 async def test_reason_none_persists_but_database_denies_protected_model_choice(self):
  a=self.agent(**{'verify.approval_gate':'none'});a['capability']='REASON'
  result=await self.call('submit_agent_draft',request_id=str(uuid.uuid4()),agent=a)
  self.assertEqual(result['draft']['fields']['verify.approval_gate']['value'],'none')
  # Simulate bypassing only the Python proposal guard; the database remains authoritative.
  original=b.Session.fields
  def bypass(session,patch,existing=None,capability=None):
   safe={k:v for k,v in patch.items() if k!='execute.model_access'};fields=original(session,safe,existing,capability)
   fields['execute.model_access']={'value':'sonnet','source':'model','why':'Synthetic attempted bypass'};return fields
  with patch.object(b.Session,'fields',bypass):
   with self.assertRaises(b.BuilderError):await self.call('submit_agent_draft',request_id=str(uuid.uuid4()),agent=a)
 async def test_v2_proposed_fields_require_explicit_browser_confirmation(self):
  agent=self.agent(**{'execute.authority':'P2','execute.model_access':'sonnet','verify.approval_gate':'none'});agent['capability']='REASON'
  draft=await self.call('submit_agent_draft',request_id=str(uuid.uuid4()),agent=agent)
  self.assertEqual(draft['draft']['fields']['execute.model_access']['source'],'proposed')
  workflow=await self.call('read_workflow',workflow_id=draft['workflow_id']);self.ctx['token']='flx_browser'
  result=await b.review(self.store,{'record_kind':'workflows','record_id':workflow['id']},True,workflow['content_hash'],confirm_proposed=True)
  fields=result['canvas']['nodes'][0]['data']['guided']['fields']
  self.assertEqual(fields['execute.model_access']['source'],'user');self.assertFalse(result['canvas']['execution_enabled'])
  reread=await self.call('read_agent_draft',draft_id=draft['draft_id']);self.assertEqual(reread['draft']['fields']['execute.authority']['source'],'user')
 async def test_v2_runtime_reads_enforce_current_permission_company_and_facility(self):
  wid='runtime-'+uuid.uuid4().hex;job=str(uuid.uuid4());other=str(uuid.uuid4())
  body={'id':wid,'version':'0.0.1','tenant':'tenant-a','company':'BMC','facility':'500'};body['content_hash']=digest(body)
  self.db.sql('insert into flux_app_objects values($1,$2,$3,clock_timestamp())',['tenant-a','workflows/'+wid+'--0.0.1.json',json.dumps(body)])
  definition={'steps':[{'config':{'scope':{'company':'BMC','facility':'500'}}}]}
  for jid,co in ((job,'BMC'),(other,'OTHER')):
   d=copy.deepcopy(definition);d['steps'][0]['config']['scope']['company']=co
   self.db.sql("insert into flux_runtime_jobs(id,client_id,workflow_id,definition,definition_hash,result,status,test_run,created_at) values($1,'tenant-a',$2,$3,'hash',$4,'review_required',true,now())",[jid,wid,json.dumps(d),json.dumps({'output':{'invoice':'synthetic','contentBytes':'DO_NOT_RETURN_BYTES'},'error':'sample'})])
  result=await self.call('list_runs',workflow_id=wid,outcome='REVIEW_REQUIRED');self.assertEqual([x['id'] for x in result['items']],['job:'+job])
  read=await self.call('read_run',run_id='job:'+job);self.assertNotIn('DO_NOT_RETURN_BYTES',json.dumps(read));self.assertEqual(read['result']['output']['invoice'],'synthetic')
  with self.assertRaises(b.BuilderError):await self.call('read_run',run_id='job:'+other)
  denied=copy.deepcopy(body);denied['deny']='view'
  self.db.sql('insert into flux_app_objects values($1,$2,$3,clock_timestamp())',['tenant-a','workflows/'+wid+'--0.0.2.json',json.dumps(denied)])
  with self.assertRaises(b.BuilderError):await self.call('read_run',run_id='job:'+job)
 async def test_v2_one_atomic_set_references_schemas_instructions_and_protected_fields(self):
  rid=str(uuid.uuid4());shape={'type':'object','properties':{'value':{'type':'string'}}}
  a=self.agent(**{'input.schema':'$schema:shape','output.schema':'$schema:shape','execute.instructions':'$instructions:procedure','execute.authority':'P0','execute.model_access':'sonnet','verify.approval_gate':'none'});a['capability']='REASON'
  operations=[{'key':'shape','tool':'propose_schema','arguments':{'resource_id':'shape-'+uuid.uuid4().hex[:8],'version':'1.0.0','label':'Synthetic schema','schema':shape}},{'key':'procedure','tool':'propose_instructions','arguments':{'resource_id':'instructions-'+uuid.uuid4().hex[:8],'version':'1.0.0','label':'Synthetic instructions','text':'Copy supplied evidence; send uncertainty to review.','model_contract':{'output_schema':'$schema:shape','max_tokens':100,'refusal_behavior':'REVIEW_REQUIRED','prompt_version':'1.0.0'}}},{'key':'workflow','tool':'propose_connected_workflow','arguments':{'name':'Atomic v2','nodes':[{'key':'reason','agent':a}],'edges':[],'entry_nodes':['reason'],'terminal_outcomes':[{'node':'reason','outcome':'COMPLETED','destination':'terminal'}]}}]
  result=await self.call('propose_change_set',request_id=rid,title='Atomic full design',operations=operations)
  read=await self.call('read_change_set',proposal_id=result['proposal_id']);self.assertEqual(read['content_hash'],result['content_hash'])
  self.ctx['token']='flx_browser';applied=await b.review(self.store,{'record_kind':'change_sets','record_id':result['id']},True,result['content_hash'],confirm_proposed=True,approve_resources=True)
  self.assertFalse(applied['activation_enabled']);resources=self.db.sql("select body from flux_app_objects where client_id='tenant-a' and path like 'resources/%' and body->>'label' in ('Synthetic schema','Synthetic instructions')")
  self.assertEqual(len(resources),2)
 async def test_v2_proposal_summary_reads_and_offline_fixture_suite(self):
  shape=await self.call('propose_schema',request_id=str(uuid.uuid4()),resource_id='fixture-'+uuid.uuid4().hex[:8],version='1.0.0',label='Synthetic fixture shape',schema={'type':'object','properties':{'value':{'type':'string'}}})
  agent=self.agent(**{'input.schema':shape['id'],'output.schema':shape['id']});agent['capability']='MAP';agent['mapping']={'value':'value'};agent['fixtures']=[{'name':'copy','input':{'value':'sample'},'expected':{'outcome':'COMPLETED','fields':{'value':'sample'}}}]
  draft=await self.call('submit_agent_draft',request_id=str(uuid.uuid4()),agent=agent)
  proposals=await self.call('list_proposals');self.assertTrue(any(x['proposal_id']==shape['proposal_id'] for x in proposals['items']))
  compact=await self.call('read_agent_draft',draft_id=draft['draft_id'],detail='summary');self.assertNotIn('why',json.dumps(compact['draft']))
  workflow=await self.call('read_workflow',workflow_id=draft['workflow_id']);suite=await self.call('run_fixture_suite',request_id=str(uuid.uuid4()),workflow_id=workflow['id'],expected_hash=workflow['content_hash'])
  self.assertTrue(suite['passed']);self.assertEqual(suite['cost_usd'],0);self.assertFalse(suite['live_actions'])
  current=await self.call('read_workflow',workflow_id=workflow['id'])
  spec=b.mcp_v2.SECRET_KINDS['graph_app']
  prod=await self.call('propose_secret_request',request_id=str(uuid.uuid4()),key='prod-'+uuid.uuid4().hex[:8],secret_kind='graph_app',purpose='Synthetic PROD request only',systems=['outlook_graph'],scopes=['mail.read'],environment='PROD',accountable_role='Synthetic owner',rotation_days=90,used_by_nodes=['reader'],fields_required=spec[0],test_workflow_id=current['id'],test_workflow_hash=current['content_hash'])
  self.assertEqual((await self.call('read_proposal',id=prod['proposal_id']))['body']['content']['environment'],'PROD')
 async def test_v2_secret_requests_dedupe_and_never_accept_values(self):
  args={'resource_id':'request-'+uuid.uuid4().hex[:8],'version':'1.0.0','label':'Synthetic Epicor TEST request','secret_kind':'epicor_rest_basic','purpose':'Read synthetic PO','systems':['epicor_rest'],'scopes':['epicor.read'],'environment':'TEST','accountable_role':'ERP administrator','rotation_days':90,'used_by_nodes':['reader'],'fields_required':['base_url','company_code','username','password','api_key','allowed_paths']}
  one=await self.call('propose_secret_request',request_id=str(uuid.uuid4()),**args)
  two=await self.call('propose_secret_request',request_id=str(uuid.uuid4()),**{**args,'resource_id':'duplicate-'+uuid.uuid4().hex[:8]});self.assertEqual(one['resource_ref'],two['resource_ref']);self.assertTrue(two['deduplicated']);self.assertEqual(one['proposal_id'],two['proposal_id'])
  with self.assertRaises(b.BuilderError):await self.call('propose_secret_request',request_id=str(uuid.uuid4()),**{**args,'environment':'PROD'})
  with self.assertRaises(Invalid):await self.call('propose_secret_request',request_id=str(uuid.uuid4()),**{**args,'password':'do-not-store-a-value'})
 async def test_v2_archive_legacy_snapshot_without_reassigning_agent(self):
  wid='legacy-'+uuid.uuid4().hex;g={'id':'legacy-reader','capability':'READ','fields':{'identity.owner':{'value':'ssh-owner'},'identity.environment':{'value':'PROD'}}}
  w={'id':wid,'version':'0.0.1','tenant':'tenant-a','company':'BMC','facility':'500','nodes':[{'id':'node','position':{'x':1,'y':1},'data':{'guided':g}}],'edges':[]};w['content_hash']=digest(w)
  self.db.sql('insert into flux_app_objects values($1,$2,$3,clock_timestamp())',['tenant-a','workflows/'+wid+'--0.0.1.json',json.dumps(w)])
  request=await self.call('archive_workflow',request_id=str(uuid.uuid4()),workflow_id=wid,expected_hash=w['content_hash']);self.ctx['token']='flx_browser'
  await b.review(self.store,{'record_kind':'resources','record_id':request['resource_ref']},True,(await self.call('read_proposal',id=request['proposal_id']))['content_hash'])
  archived=self.db.sql("select body from flux_app_objects where client_id='tenant-a' and path like 'audit/archive-%' and body->'payload'->>'canvas_id'=$1",[wid]);self.assertEqual(len(archived),1)
  saved=self.db.sql("select body from flux_app_objects where client_id='tenant-a' and path=$1",['workflows/'+wid+'--0.0.1.json'])[0]['body'];self.assertEqual(saved,w)
 async def test_v2_pending_read_and_summary_hash_do_not_rewrite_saved_canvas(self):
  draft=await self.submit();old=await self.call('read_workflow',workflow_id=draft['workflow_id'])
  updated=await self.call('propose_mapping',request_id=str(uuid.uuid4()),draft_id=draft['draft_id'],expected_hash=draft['content_hash'],fields={'value':'value'}) if draft['draft']['capability']=='MAP' else await self.call('update_agent_draft',request_id=str(uuid.uuid4()),draft_id=draft['draft_id'],expected_hash=draft['content_hash'],fields={'output.next':'none'})
  current=await self.call('read_workflow',workflow_id=draft['workflow_id'],detail='summary')
  self.assertEqual(current['nodes'][0]['draft_hash'],updated['content_hash']);self.assertIn('snapshot_content_hash',current);self.assertIn('resolved_content_hash',current)
 async def test_v2_model_fixture_requires_confirmation_and_replay_never_calls_twice(self):
  from app import fixture_suite
  resource=await self.call('propose_schema',request_id=str(uuid.uuid4()),resource_id='model-shape-'+uuid.uuid4().hex[:8],version='1.0.0',label='Model fixture shape',schema={'type':'object','properties':{'value':{'type':'string'}}})
  instruction=await self.call('propose_instructions',request_id=str(uuid.uuid4()),resource_id='model-procedure-'+uuid.uuid4().hex[:8],version='1.0.0',label='Model fixture procedure',text='Copy the synthetic value.',model_contract={'output_schema':resource['id'],'max_tokens':100,'refusal_behavior':'REVIEW_REQUIRED','prompt_version':'1'})
  a=self.agent(**{'input.schema':resource['id'],'output.schema':resource['id'],'execute.model_access':'sonnet','execute.cost_ceiling':'0_05','execute.instructions':instruction['resource_ref']});a['capability']='REASON';a['fixtures']=[{'name':'copy','input':{'value':'synthetic'},'expected':{'outcome':'COMPLETED','fields':{'value':'synthetic'},'max_cost_usd':0.05}}]
  draft=await self.call('submit_agent_draft',request_id=str(uuid.uuid4()),agent=a);workflow=await self.call('read_workflow',workflow_id=draft['workflow_id'])
  with self.assertRaises(b.BuilderError):await self.call('run_fixture_suite',request_id=str(uuid.uuid4()),workflow_id=workflow['id'],expected_hash=workflow['content_hash'],max_cost_usd=0.05)
  self.ctx['token']='flx_browser';await b.review(self.store,{'record_kind':'workflows','record_id':workflow['id']},True,workflow['content_hash'],confirm_proposed=True);self.ctx['token']='fmca_synthetic';workflow=await self.call('read_workflow',workflow_id=workflow['id'])
  args={'request_id':str(uuid.uuid4()),'workflow_id':workflow['id'],'expected_hash':workflow['content_hash'],'max_cost_usd':0.05}
  fixture=AsyncMock(return_value=({'value':'synthetic'},0.01,{'model':'synthetic-model','usage':{'input_tokens':1,'output_tokens':1}}))
  with patch.object(fixture_suite,'model_fixture',fixture):
   result=await self.call('run_fixture_suite',**args);replay=await self.call('run_fixture_suite',**args)
  self.assertEqual(result,replay);self.assertTrue(result['passed']);self.assertEqual(fixture.await_count,1);self.assertEqual(result['cost_usd'],0.01)
  agent=await self.call('read_agent_draft',draft_id=draft['draft_id']);self.assertTrue(agent['draft']['fixture_suite']['passed'])
 async def test_v2_seven_capability_design_single_apply_and_fixture_regression(self):
  # Structural acceptance only: external results and the model are synthetic stubs.
  # Start a separate synthetic build session instead of copying the other tests history.
  self.db.sql("update flux_private.builder_sessions set document='{}' where tenant='tenant-a' and user_id=$1",[U])
  operations=[]
  for key in ('attachment','document','ack'):
   operations.append({'key':key,'tool':'propose_schema','arguments':{'resource_id':key+'-'+uuid.uuid4().hex[:8],'version':'1.0.0','label':'Synthetic '+key,'schema':{'type':'object','properties':{'value':{'type':'string'}}}}})
  for key,output in (('parse','document'),('extract','ack')):
   operations.append({'key':key,'tool':'propose_instructions','arguments':{'resource_id':key+'-'+uuid.uuid4().hex[:8],'version':'1.0.0','label':'Synthetic '+key,'text':'Copy the synthetic value.','model_contract':{'output_schema':'$schema:'+output,'max_tokens':100,'refusal_behavior':'REVIEW_REQUIRED','prompt_version':'1.0.0'}}})
  operations.append({'key':'checks','tool':'propose_rule','arguments':{'resource_id':'checks-'+uuid.uuid4().hex[:8],'version':'1.0.0','label':'Synthetic check','rule':[{'op':'present','field':'value'}]}})
  for key,kind,scopes in (('mail','graph_app',['mail.read']),('erp','epicor_rest_basic',['epicor.read']),('teams','teams_app',['teams.send'])):
   spec=b.mcp_v2.SECRET_KINDS[kind]
   operations.append({'key':key,'tool':'propose_secret_request','arguments':{'key':key+'-'+uuid.uuid4().hex[:8],'secret_kind':kind,'purpose':'Synthetic structural test only','systems':[spec[2]],'scopes':scopes,'environment':'TEST','accountable_role':'Synthetic owner','rotation_days':90,'used_by_nodes':[key],'fields_required':spec[0]}})
  nodes=[]
  for key,cap,inp,out in [('retriever','READ','attachment','attachment'),('parser','DOC','attachment','document'),('converter','MAP','document','document'),('extractor','REASON','document','ack'),('matcher','READ','ack','ack'),('checker','RULE','ack','ack'),('notifier','COMMS','ack','ack')]:
   fields={'input.schema':'$schema:'+inp,'output.schema':'$schema:'+out,'output.record_type':'none'}
   a=self.agent(**fields);a['capability']=cap;a['fixtures']=[{'name':'synthetic','input':{'value':'synthetic'},'expected':{'outcome':'COMPLETED','fields':{}}}]
   if cap in ('DOC','REASON'):
    a['fields'].update({'execute.model_access':'sonnet','execute.instructions':'$instructions:'+('parse' if cap=='DOC' else 'extract'),'execute.cost_ceiling':'0_05'})
   elif cap=='MAP':a['mapping']={'value':'value'}
   elif cap=='RULE':a['fields']['execute.rule']='$rule:checks'
   else:a['fixtures'][0]['adapter_result']={'value':'synthetic'}
   if key in ('retriever','matcher','notifier'):
    req={'retriever':('mail','mail.read'),'matcher':('erp','epicor.read'),'notifier':('teams','teams.send')}[key];a['connection_requirements']=[{'secret_request':'$secret_request:'+req[0],'capabilities':[req[1]]}]
   nodes.append({'key':key,'agent':a})
  operations.append({'key':'workflow','tool':'propose_connected_workflow','arguments':{'name':'Synthetic seven responsibility regression','nodes':nodes,'edges':[{'source':nodes[i]['key'],'target':nodes[i+1]['key'],'on_outcome':'COMPLETED'} for i in range(6)],'entry_nodes':['retriever'],'terminal_outcomes':[{'node':'notifier','outcome':'COMPLETED','destination':'terminal'}]}})
  result=await self.call('propose_change_set',request_id=str(uuid.uuid4()),title='Synthetic seven-agent v2 acceptance',operations=operations)
  self.assertEqual(len([m for m in result['members'] if m['kind']=='agents']),7)
  self.assertTrue(result['validation']['blocks_publish']) # missing human/integration/business inputs remain honest blockers.
  self.ctx['token']='flx_browser';await b.review(self.store,{'record_kind':'change_sets','record_id':result['id']},True,result['content_hash'],confirm_proposed=True,approve_resources=True);self.ctx['token']='fmca_synthetic'
  wid=next(m['id'] for m in result['members'] if m['kind']=='workflows');w=await self.call('read_workflow',workflow_id=wid)
  with patch('app.fixture_suite.model_fixture',AsyncMock(return_value=({'value':'synthetic'},.001,{'mode':'mocked_model'}))) as model:
   suite=await self.call('run_fixture_suite',request_id=str(uuid.uuid4()),workflow_id=wid,expected_hash=w['content_hash'],max_cost_usd=.01)
  self.assertTrue(suite['passed'],suite);self.assertEqual(model.await_count,2);self.assertEqual(len(suite['nodes']),7);self.assertFalse(suite['live_actions'])
 async def test_v2_record_reads_require_exact_company_runtime_package_and_declared_type(self):
  wid='record-'+uuid.uuid4().hex;sid='source-'+uuid.uuid4().hex;aid=uuid.uuid4().hex
  w={'id':wid,'version':'0.0.1','tenant':'tenant-a','company':'BMC','facility':'500'}
  self.db.sql('insert into flux_app_objects values($1,$2,$3,now())',['tenant-a','workflows/'+wid+'--0.0.1.json',json.dumps(w)])
  definition={'steps':[{'agent_id':'parser','guided':{'fields':{'output.record_type':{'value':'document.read'}}}}]}
  self.db.sql("insert into flux_private.mail_sources values($1,'tenant-a',now())",[sid]);self.db.sql("insert into flux_private.mail_pipelines values($1,'tenant-a','BMC',$2,$3,'definition-pin')",[sid,wid,json.dumps(definition)])
  body={'origin':'canvas_runtime','workflow_id':wid,'agent_id':'parser','definition_hash':'definition-pin','output':{'value':'synthetic','file_id':'file-synthetic','contentBytes':'DO_NOT_RETURN','signed_url':'https://example.invalid/file?token=do-not-return'}}
  self.db.sql("insert into flux_private.mail_artifacts values($1,$2,'parsed',now(),'completed',$3,'result-hash')",[sid,aid,json.dumps(body)])
  result=await self.call('read_record',record_type='document.read',id=aid)
  self.assertEqual(result['output'],{'value':'synthetic','file_id':'file-synthetic'});self.assertEqual(result['result_hash'],'result-hash')
  with self.assertRaises(b.BuilderError):await self.call('read_record',record_type='other.record',id=aid)
  self.db.sql("update flux_private.mail_pipelines set definition_hash='new-package' where source_id=$1",[sid])
  with self.assertRaises(b.BuilderError):await self.call('read_record',record_type='document.read',id=aid)
