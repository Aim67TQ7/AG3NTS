import copy,unittest
from app.record_bindings import validate
from flux_harness import BoundRunner,Context,Result
SCHEMA={'type':'object'}
def reg(name,kind='handoff',statuses=None,terminal=None,approval=None):return {'name':name,'kind':kind,'statuses':statuses or ['ready'],'terminal_statuses':terminal or [],'approval_statuses':approval or [],'content_hash':name+'-hash','published':True,'input_schema_ref':'schema:in@1','output_schema_ref':'schema:out@1'}
def node(id,cap,read,write,out='ready'):
 return {'id':id,'data':{'capability':cap,'guided':{'capability':cap,'fields':{'identity.environment':{'value':'TEST'},'identity.company':{'value':'BMC'},'input.schema':{'value':'schema:in@1'},'output.schema':{'value':'schema:out@1'},'verify.approval_gate':{'value':'single_approver'},'output.outcomes':{'value':'completed_only'}},'bindings':{'reads':{'record_type':read,'status':'ready','registry_hash':read+'-hash'},'writes':{'record_type':write,'outcomes':{'COMPLETED':out},'registry_hash':write+'-hash'}}}}}
class ValidationTests(unittest.TestCase):
 def setUp(self):
  self.rows=[reg('source','source'),reg('input'),reg('output',terminal=['done'],statuses=['done'])];self.w={'nodes':[node('reader','READ','source','input'),node('mapper','MAP','input','output','done')]};self.schemas={'schema:in@1':SCHEMA,'schema:out@1':SCHEMA}
 def test_source_to_handoff_to_terminal(self):self.assertTrue(validate(self.w,self.rows,self.schemas)['valid'])
 def test_source_write_denied(self):self.w['nodes'][1]['data']['guided']['bindings']['writes']['record_type']='source';self.assertFalse(validate(self.w,self.rows,self.schemas)['valid'])
 def test_orphan_status_denied(self):self.w['nodes'].pop(0);self.assertGreater(validate(self.w,self.rows,self.schemas)['missing_handoffs'],0)
 def test_stale_registry_denied(self):self.rows[1]['content_hash']='changed';self.assertFalse(validate(self.w,self.rows,self.schemas)['valid'])
 def test_draft_schema_denied(self):self.rows[1]['published']=False;self.assertFalse(validate(self.w,self.rows,self.schemas)['valid'])
 def test_writer_approval_producer_verified(self):
  self.rows[1].update(approval_statuses=['ready']);self.w['nodes'][1]['data']['guided']['capability']='WRITE';self.w['nodes'][1]['data']['capability']='WRITE'
  self.assertFalse(validate(self.w,self.rows,self.schemas)['valid']);self.w['nodes'][0]['data']['capability']='COMMS';self.w['nodes'][0]['data']['guided']['capability']='COMMS';self.rows[0]['kind']='handoff'
  # Still has no upstream input; approval cannot make that absence disappear.
  self.assertFalse(validate(self.w,self.rows,self.schemas)['valid'])
class RunnerTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.scope={'tenant':'tenant','company':'BMC','facility':'500'};self.types={r['name']:r for r in [reg('input'),reg('output',statuses=['done'],terminal=['done'])]};self.inputs=[{'id':'record-1','record_type':'input','status':'ready','registry_hash':'input-hash','environment':'TEST',**self.scope,'created_at':'2026-10-14T00:00:00Z','payload':{'a':1}}];self.results={};self.handoffs={};self.calls=0
  parent=self
  class Store:
   async def get(self,k):return parent.results.get(k)
   async def put(self,k,v):parent.results[k]=copy.deepcopy(v);return v
  class Records:
   async def record_type(self,n,s):return parent.types.get(n)
   async def poll(self,*args):return parent.inputs
   async def schema(self,r):return SCHEMA
   async def verify_approval(self,*args):return False
   async def verify_approval_result(self,*args):return False
   async def context_for(self,ctx,cfg):return Context(cfg['capability'],cfg['scope'])
   async def append(self,r):parent.handoffs.setdefault(r['idempotency_key'],r);return parent.handoffs[r['idempotency_key']]
  self.runner=BoundRunner(Store(),Records());self.cfg={'agent_ref':'map@1','scope':self.scope,'capability':'MAP','activation_enabled':True,'test_run':False,'environment':'TEST','input_schema':SCHEMA,'output_schema':SCHEMA,'bindings':node('m','MAP','input','output','done')['data']['guided']['bindings']};self.ctx=Context('MAP',self.scope)
  async def job(inp,ctx):parent.calls+=1;return Result('COMPLETED',{'b':inp['a']})
  self.job=job
 async def test_durable_result_scoped_and_idempotent(self):
  await self.runner.poll_once(self.job,self.cfg,self.ctx);await self.runner.poll_once(self.job,self.cfg,self.ctx);self.assertEqual(self.calls,1);self.assertEqual(len(self.handoffs),1);r=next(iter(self.handoffs.values()));self.assertEqual(r['payload'],{'b':1});self.assertEqual(r['tenant'],'tenant');self.assertEqual(r['input_record_id'],'record-1')
 async def test_cross_tenant_denied(self):
  self.inputs[0]['tenant']='other'
  with self.assertRaises(PermissionError):await self.runner.poll_once(self.job,self.cfg,self.ctx)
 async def test_off_by_default(self):
  self.cfg['activation_enabled']=False
  with self.assertRaises(PermissionError):await self.runner.poll_once(self.job,self.cfg,self.ctx)
 async def test_approval_fail_closed(self):
  self.cfg['capability']='WRITE';self.types['input']['approval_statuses']=['ready'];self.ctx=Context('WRITE',self.scope)
  with self.assertRaises(PermissionError):await self.runner.poll_once(self.job,self.cfg,self.ctx)
 async def test_source_write_rejected(self):
  self.types['output']['kind']='source'
  with self.assertRaises(PermissionError):await self.runner.poll_once(self.job,self.cfg,self.ctx)

 async def test_approval_status_cannot_be_fabricated(self):
  self.types['output']['approval_statuses']=['done'];self.cfg['capability']='COMMS';self.ctx=Context('COMMS',self.scope)
  with self.assertRaises(PermissionError):await self.runner.poll_once(self.job,self.cfg,self.ctx)
  self.assertFalse(self.handoffs)
