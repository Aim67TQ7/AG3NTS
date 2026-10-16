import unittest
from unittest.mock import AsyncMock,patch
from app import runtime,fresh
from app.core import Invalid
class ExecutionTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):self.marker=fresh.CTX.set({'client':{'id':'tenant-a'}})
 async def asyncTearDown(self):fresh.CTX.reset(self.marker)
 async def test_steps_cost_and_pinned_agent_are_projected(self):
  rows=[{'id':'job','workflow_id':'flow','status':'completed','test_run':True,'created_at':'2026-10-16T12:00:00Z','definition':{'steps':[{'agent_id':'agent-a','name':'A','package_hash':'hash'}]},'flux_runtime_steps':[{'step':0,'created_at':'2026-10-16T12:00:01Z','result':{'result_status':'COMPLETED','duration_ms':42,'model_cost_usd':0,'input_tokens':0,'output_tokens':0}}]}]
  with patch.object(fresh,'rest',AsyncMock(return_value=rows)) as read:
   r=await runtime.executions(workflow_id='flow',agent_id='agent-a');self.assertEqual(r['items'][0]['result']['duration_ms'],42);self.assertEqual(r['items'][0]['package_hash'],'hash');self.assertIn('client_id=eq.tenant-a',read.call_args.args[2]);self.assertIn('workflow_id=eq.flow',read.call_args.args[2])
   self.assertEqual((await runtime.executions(agent_id='other'))['items'],[])
 async def test_cursor_and_pending_execution(self):
  rows=[{'id':'job','workflow_id':'flow','status':'pending','test_run':False,'created_at':'2026-10-16T12:00:00Z','definition':{},'flux_runtime_steps':[]}]
  with patch.object(fresh,'rest',AsyncMock(return_value=rows)) as read:
   r=await runtime.executions(before='2026-10-16T12:00:01Z');self.assertIsNone(r['items'][0]['result']);self.assertIn('created_at=lt.',read.call_args.args[2])
   with self.assertRaises(Invalid):await runtime.executions(before='bad-cursor')
