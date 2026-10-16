import asyncio,unittest
from flux_harness import Context,Harness,Result,run_job
class Store:
 def __init__(self):self.rows={}
 async def get(self,k):return self.rows.get(k)
 async def put(self,k,v):
  if k in self.rows:raise ValueError('Immutable conflict')
  self.rows[k]=v;return v
SCOPE={'tenant':'Bunting Magnetics','company':'BMC','facility':'500'}
CFG={'scope':SCOPE,'capability':'MAP','input_schema':{'type':'object'},'output_schema':{'type':'object'},'max_attempts':1,'timeout_seconds':1,'job_spec':{'kind':'map','fields':{'b':'a'}}}
class Tests(unittest.IsolatedAsyncioTestCase):
 async def test_map_schema_and_idempotency(self):
  store=Store();ctx=Context('MAP',SCOPE)
  async def agent(i,c):return await run_job(i,c,CFG['job_spec'])
  a=await Harness(store).invoke(agent,{'a':3},CFG,ctx,'one');b=await Harness(store).invoke(agent,{'a':3},CFG,Context('MAP',SCOPE),'one')
  self.assertEqual(a['output'],{'b':3});self.assertEqual(a,b);self.assertEqual(a['facility'],'500')
  with self.assertRaises(Exception):await Harness(store).invoke(agent,{'a':4},CFG,Context('MAP',SCOPE),'one')
 async def test_prod_scope_and_tool_denial(self):
  async def agent(i,c):return Result('COMPLETED',{})
  with self.assertRaises(Exception):await Harness(Store()).invoke(agent,{},CFG,Context('MAP',SCOPE,'PROD'),'one')
  with self.assertRaises(Exception):await Context('MAP',SCOPE).operation('epicor_write',{})
 async def test_write_requires_bound_approval(self):
  calls=[]
  async def write(req,scope,env):calls.append(req);return {}
  cfg={**CFG,'capability':'WRITE'}
  async def agent(i,c):return Result('COMPLETED',await c.operation('epicor_write',i))
  r=await Harness(Store()).invoke(agent,{},cfg,Context('WRITE',SCOPE,adapters={'epicor_write':write}),'write')
  self.assertEqual(r['result_status'],'REVIEW_REQUIRED');self.assertEqual(calls,[])
 async def test_uncertain_write_not_retried(self):
  calls=[]
  async def approve(ih,dh,req,scope):
   import time
   from flux_harness.runtime import digest
   return {'decision':'approve','input_hash':ih,'definition_hash':dh,'proposal_hash':digest(req),'scope':scope,'environment':'TEST','reviewer_id':'synthetic-reviewer','expires_at':time.time()+60}
  async def write(req,scope,env):calls.append(1);raise TimeoutError()
  cfg={**CFG,'capability':'WRITE','max_attempts':3}
  async def agent(i,c):return Result('COMPLETED',await c.operation('epicor_write',i))
  store=Store();r=await Harness(store).invoke(agent,{},cfg,Context('WRITE',SCOPE,adapters={'epicor_write':write},approval_check=approve),'write')
  self.assertEqual(r['result_status'],'OUTCOME_UNKNOWN');self.assertEqual(len(calls),1)
 async def test_model_unknown_usage_keeps_reserve(self):
  async def model(req,scope,env):return {'output':{},'usage':{}}
  ctx=Context('REASON',SCOPE,adapters={'model_call':model},cost_ceiling=.25)
  with self.assertRaises(Exception):await ctx.model_call({},.1)
  self.assertEqual(ctx.cost,.1)
 async def test_runtime_review_deferred_question(self):
  r=await run_job({},Context('MAP',SCOPE),{'kind':'map','fields':{'b':'a'},'runtime_review':True})
  self.assertEqual(r.status,'REVIEW_REQUIRED')
