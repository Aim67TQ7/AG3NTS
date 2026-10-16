import unittest
from unittest.mock import patch,AsyncMock
from app import governance,fresh,teaching,studio
from app.core import Invalid
class GovernanceTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):self.marker=fresh.CTX.set({'client':{'id':'client-a'},'company':{'id':'company-id','code':'A'},'user':{'id':'operator'},'role':'editor'})
 async def asyncTearDown(self):fresh.CTX.reset(self.marker)
 async def test_rpc_never_trusts_caller_client_id(self):
  with patch.object(fresh,'enabled',return_value=True),patch.object(fresh,'rest',AsyncMock(return_value={'scope':'company'})) as r:
   await governance.set_object({'client':'other-client','key':'agent:test','scope':'company'})
   self.assertEqual(r.call_args.args[3]['args']['client'],'client-a')
 async def test_credential_use_does_not_authorize_management(self):
  with patch.object(fresh,'enabled',return_value=True),patch.object(governance,'rpc',AsyncMock(return_value={'allowed':False})):
   with self.assertRaises(Invalid):await governance.check('resource:secret','manage_secret')
 async def test_builder_cannot_publish_before_external_git_action(self):
  with patch.object(fresh,'enabled',return_value=True),patch.object(teaching,'latest',AsyncMock()) as latest:
   with self.assertRaises(Invalid):await teaching.publish({'id':'session'})
   latest.assert_not_called()
 def test_audit_envelope_uses_authenticated_identity(self):
  e=governance.envelope('agent.tested',{'agent_ref':'agent-a@1.0.0','definition_hash':'hash','workflow_id':'workflow-a','run_id':'run-a'},'forged')
  self.assertEqual(e['client_id'],'client-a');self.assertEqual(e['company_code'],'A');self.assertEqual(e['actor_id'],'operator');self.assertEqual(e['agent_id'],'agent-a');self.assertEqual(e['agent_version'],'1.0.0');self.assertEqual(e['agent_hash'],'hash');self.assertEqual(e['run_id'],'run-a')
 def test_company_header_in_database_requests(self):
  c=fresh.CTX.get();fresh.CTX.set({**c,'token':'flx_fixture'})
  self.assertEqual(dict(fresh.HEAD)['x-flux-company'],'company-id')
