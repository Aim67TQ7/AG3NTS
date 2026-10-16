import unittest,uuid
from unittest.mock import AsyncMock,patch
from contextvars import ContextVar
from types import SimpleNamespace
from app import studio,mcp_connection as m,mcp_builder as b,fresh
class DraftTest(unittest.IsolatedAsyncioTestCase):
 async def test_submission_rejects_human_fields_instead_of_clearing(self):
  marker=fresh.CTX.set({'token':'fmca_fixture','user':{'id':'operator'},'client':{'id':'test'},'company':{'id':'company','name':'TEST','code':'TEST','facility':'TEST'},'role':'editor'})
  store=SimpleNamespace(ACTOR=ContextVar('actor',default='operator'),now=lambda:'2026-10-16T00:00:00Z')
  try:
   a={'capability':'READ','name_options':['Read mail','Capture mail','Observe mail'],'responsibility_options':['Capture mail.','Read mail.','Observe mail.'],'fields':{'execute.authority':studio.FIELDS['execute.authority']['options'][0]['id']}}
   rpc=AsyncMock(return_value={'revision':0,'document':{}})
   with patch.object(b,'rpc',rpc):
    with self.assertRaises(b.BuilderError) as error:await m.dispatch('submit_agent_draft',{'request_id':str(uuid.uuid4()),'agent':a},store)
   self.assertEqual(error.exception.error['field_path'],'execute.authority');self.assertEqual(rpc.await_count,1) # Snapshot only; no persistence.
  finally:fresh.CTX.reset(marker)
