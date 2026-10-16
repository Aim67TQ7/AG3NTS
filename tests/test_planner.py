import copy, unittest
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app import planner, studio

CAPS=['READ','CLASS','DOC','READ','MAP','RULE','COMMS','WRITE','COMMS']
TITLES=['Mailbox Message Retriever','Message Classifier','Customer PO Reader','Epicor Record Retriever','PO to Sales Order Mapper','Gate Checker','Approval Request','Sales Order Writer','Confirmation Notice']
DESCRIPTION='When a customer emails a PO to the Inside Sales shared mailbox, read it, match the customer and parts in Epicor, build a draft sales order, check it, have the rep approve it, then create the order in Epicor and tell the rep the order number.'
class Tests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.old=studio.store;self.data={};self.calls=[]
  async def put(path,obj):
   if path in self.data:raise RuntimeError('immutable conflict')
   self.data[path]=copy.deepcopy(obj);return obj
  async def records(kind):return [copy.deepcopy(v) for k,v in self.data.items() if k.startswith(kind+'/')]
  async def get(path):return self.data.get(path)
  studio.store=SimpleNamespace(ACTOR=ContextVar('testactor',default='owner'),put=put,records=records,get=get,ident=lambda x:x,now=lambda:'2026-10-14T00:00:00Z')
  self.cards=[{'capability':c,'title':t,'description':t+' processes the committed record; missing values require review.','hints':{'department':'sales','company':'BMC','starts':'mailbox_message'}} for c,t in zip(CAPS,TITLES)]
 async def asyncTearDown(self):studio.store=self.old
 async def draft(self,b,**kw):
  self.calls.append((b,kw));cap=b['capability']
  return {'split':False,'agents':[{'capability':cap,'name_options':['One','Two','Three'],'responsibility_options':['One bounded responsibility.']*3,'fields':{f['id']:{'value':None,'source':'missing'} for s in studio.CATALOG['steps'] for f in s['fields']},'questions_for_user':[]}],'_usage':{'cost_usd':.04,'input_tokens':100,'output_tokens':100}}
 async def test_nine_card_approval_build_and_duplicate_guard(self):
  with patch.object(planner,'propose',AsyncMock(return_value=self.cards)),patch.object(studio,'model_draft',self.draft):
   r=await planner.plan_endpoint({'description':DESCRIPTION});self.assertEqual(r['status'],'awaiting_approval');self.assertEqual(len(self.calls),0)
   r=await planner.approve_endpoint({'run_id':r['id']});self.assertEqual(r['status'],'completed',r.get('error'));self.assertEqual([n['data']['capability'] for n in r['nodes']],CAPS);self.assertEqual(len(self.calls),9)
   self.assertEqual(set(r['blockers']),{'record_formats','approved_rules','procedures','approval_gates'},r['blockers'])
   for n in r['nodes']:
    self.assertEqual(n['data']['guided']['fields']['identity.environment']['value'],'TEST')
    self.assertTrue(all(x['value'] is not None for x in n['data']['guided']['fields'].values()))
   self.assertFalse(r['canvas']['execution_enabled']);self.assertEqual(r['canvas']['facility'],'500')
   self.assertTrue(all(v['company']=='BMC' for k,v in self.data.items() if k.startswith('agents/')))
   with self.assertRaises(Exception):await planner.approve_endpoint({'run_id':r['id']})
 async def test_forbidden_fields_and_options(self):
  c=await studio.catalog();g={'capability':'READ','fields':{}}
  for key,val in [('identity.environment','PROD'),('execute.authority','P5'),('execute.method','invented')]:
   with self.assertRaises(Exception):await planner.set_field(g,key,val,c)
  with self.assertRaises(Exception):await planner.set_field({'capability':'WRITE','fields':{}},'verify.approval_gate','none',c)
 async def test_cross_actor_read_rejected(self):
  with patch.object(planner,'propose',AsyncMock(return_value=self.cards)):r=await planner.plan_endpoint({'description':DESCRIPTION})
  token=studio.store.ACTOR.set('other')
  try:
   with self.assertRaises(Exception):await planner.load(r['id'])
  finally:studio.store.ACTOR.reset(token)
 async def test_failure_retains_budget_and_audit(self):
  with patch.object(planner,'propose',AsyncMock(return_value=self.cards)),patch.object(studio,'model_draft',AsyncMock(side_effect=RuntimeError('provider disconnected'))):
   r=await planner.plan_endpoint({'description':DESCRIPTION});r=await planner.approve_endpoint({'run_id':r['id']})
   self.assertEqual(r['status'],'blocked');self.assertFalse(r['usage_complete']);self.assertGreater(r['reserved_usd'],0);self.assertEqual(r['tools'][-1]['status'],'failed')
 async def test_write_requires_approval_card(self):
  with self.assertRaises(Exception):planner.validate_plan([self.cards[7]])

 async def test_messages_tool_loop_plans_without_building(self):
  import httpx,os,json
  original=httpx.AsyncClient;requests=[]
  def handle(req):
   requests.append(req.url.path)
   if req.url.path.endswith('count_tokens'):return httpx.Response(200,json={'input_tokens':100})
   return httpx.Response(200,json={'content':[{'type':'tool_use','id':'proposal','name':'propose_plan','input':{'cards':self.cards}}],'usage':{'input_tokens':100,'output_tokens':100},'stop_reason':'tool_use'})
  def client(**kw):return original(transport=httpx.MockTransport(handle),**kw)
  with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'synthetic-not-a-key','STUDIO_DRAFT_INPUT_PER_MTOK':'2','STUDIO_DRAFT_OUTPUT_PER_MTOK':'10'}),patch.object(planner.httpx,'AsyncClient',client):
   r=await planner.plan_endpoint({'description':DESCRIPTION})
  self.assertEqual(r['status'],'awaiting_approval',r.get('error'));self.assertEqual(len(r['cards']),9);self.assertEqual(r['nodes'],[]);self.assertEqual(r['tools'][0]['tool'],'propose_plan');self.assertLess(r['reserved_usd'],1)

 async def test_queued_plan_returns_then_persists_result(self):
  import asyncio
  gate=asyncio.Event()
  async def propose(r):await gate.wait();return self.cards
  with patch.object(planner,'propose',propose):
   r=await planner.plan_endpoint({'description':DESCRIPTION,'queued':True});self.assertEqual(r['status'],'planning');task=planner.TASKS[r['id']];gate.set();await task
   saved=await planner.read_run(r['id']);self.assertEqual(saved['status'],'awaiting_approval');self.assertEqual(len(saved['cards']),9)
 async def test_interrupted_plan_is_explicit(self):
  r={'id':'plan-interrupted','created_by':'owner','status':'planning','revision':0};await planner.persist(r)
  saved=await planner.read_run(r['id']);self.assertEqual(saved['status'],'interrupted');self.assertIn('server restart',saved['error'])
