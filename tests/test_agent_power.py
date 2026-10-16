import unittest,copy
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
from app import runtime,fresh,studio
from app.core import digest,Invalid
from tests.test_runtime import FakeWorker,job

class AgentPower(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.marker=fresh.CTX.set({'client':{'id':'client-one'},'role':'owner'})
  self.g={'id':'mail-agent','name':'Mailbox','fields':{'input.source_system':{'value':'outlook_graph'}}}
  self.canvas={'id':'flow-one','created_at':'2026-10-16','nodes':[{'data':{'guided':self.g}}]}
  self.store=SimpleNamespace(ident=lambda s:s,records=AsyncMock(return_value=[self.canvas]))
  self.replace=patch.object(studio,'store',self.store);self.replace.start();self.writes=[]
  self.mail=patch('app.mail_runtime.status',AsyncMock(return_value={'configured':False}));self.mail.start()
  async def rest(store,method,path,body=None):
   if path=='rpc/flux_runtime_health':return {'worker_ready':True}
   if path=='rpc/flux_agent_controls':
    self.assertEqual(body['client'],'client-one')
    if body.get('operation')=='set':self.writes.append(body);return {'revision':1}
    return []
   raise AssertionError(path)
  self.mock=patch.object(fresh,'rest',side_effect=rest);self.mock.start()
 async def asyncTearDown(self):self.mail.stop();self.mock.stop();self.replace.stop();fresh.CTX.reset(self.marker)
 async def test_graph_stays_off_and_never_calls_activation(self):
  with patch.object(runtime,'action',new_callable=AsyncMock) as action:
   with self.assertRaisesRegex(Invalid,'Graph email listener is not connected'):await runtime.agent_power({'agent_id':self.g['id'],'guided_hash':digest(self.g),'enabled':True})
   action.assert_not_awaited();self.assertFalse(self.writes)
 async def test_off_works_without_compilation_and_is_scoped(self):
  with patch.object(runtime,'compile_workflow',new_callable=AsyncMock) as compile:
   result=await runtime.agent_power({'agent_id':self.g['id'],'enabled':False,'expected_revision':0})
   compile.assert_not_awaited();self.assertFalse(result['enabled']);self.assertEqual(len(self.writes),1)
 async def test_builder_cannot_switch_and_stale_revision_is_rejected(self):
  marker=fresh.CTX.set({**fresh.CTX.get(),'role':'editor'})
  try:
   with self.assertRaisesRegex(Invalid,'Admin'):await runtime.agent_power({'agent_id':self.g['id'],'enabled':False})
  finally:fresh.CTX.reset(marker)
  with self.assertRaisesRegex(Invalid,'changed'):await runtime.agent_power({'agent_id':self.g['id'],'enabled':False,'expected_revision':4})
  self.assertFalse(self.writes)
 async def test_unsaved_version_and_missing_test_never_arm(self):
  with self.assertRaisesRegex(Invalid,'Save this exact'):await runtime.agent_power({'agent_id':self.g['id'],'guided_hash':'wrong','enabled':True})
  self.g['fields']['input.source_system']['value']='flux'
  plan={'id':'flow-one','steps':[]}
  async def missing_test(store,method,path,body=None):
   if path=='rpc/flux_runtime_health':return {'worker_ready':True}
   if path=='rpc/flux_agent_controls':return []
   if path.startswith('flux_runtime_workflows?'):return [{'id':'flow-one','input':{},'interval_seconds':0,'definition':plan}]
   if path.startswith('flux_runtime_jobs?'):return []
   raise AssertionError(path)
  with patch.object(runtime,'compile_workflow',new_callable=AsyncMock,return_value=plan),patch.object(fresh,'rest',side_effect=missing_test):
   with self.assertRaisesRegex(Invalid,'successful workflow test'):await runtime.agent_power({'agent_id':self.g['id'],'guided_hash':digest(self.g),'enabled':True})
  self.assertFalse(self.writes)
 async def test_enable_uses_exact_tested_workflow_and_preserves_schedule_and_input(self):
  self.g['fields']['input.source_system']['value']='flux'
  plan={'id':'flow-one','steps':[{'agent_id':'mail-agent','config':{'guided_hash':digest(self.g)}}]}
  async def rest(store,method,path,body=None):
   if path=='rpc/flux_runtime_health':return {'worker_ready':True}
   if path=='rpc/flux_agent_controls':
    if body.get('operation')=='set':self.writes.append(body);return {'revision':1}
    return []
   if path.startswith('flux_runtime_workflows?'):return [{'id':'flow-one','definition':plan,'input':{'approved':42},'interval_seconds':300}]
   if path.startswith('flux_runtime_jobs?'):return [{'id':'tested'}]
   raise AssertionError(path)
  with patch.object(fresh,'rest',side_effect=rest),patch.object(runtime,'compile_workflow',new_callable=AsyncMock,return_value=plan),patch.object(runtime,'action',new_callable=AsyncMock) as action:
   result=await runtime.agent_power({'agent_id':'mail-agent','enabled':True,'guided_hash':digest(self.g)})
   self.assertTrue(result['enabled']);action.assert_awaited_once_with({'workflow_id':'flow-one','action':'activate','input':{'approved':42},'interval_seconds':300})
  self.assertEqual(len(self.writes),1)
 def test_disabled_or_changed_agent_holds_activation(self):
  plan={'steps':[{'agent_id':'a','config':{'guided_hash':'hash'}}]}
  self.assertTrue(runtime.controls_allow(plan,[]))
  self.assertFalse(runtime.controls_allow(plan,[{'agent_id':'a','enabled':False}]))
  self.assertFalse(runtime.controls_allow(plan,[{'agent_id':'a','enabled':True,'guided_hash':'old'}]))
  self.assertTrue(runtime.controls_allow(plan,[{'agent_id':'a','enabled':True,'guided_hash':'hash'}]))
 async def test_worker_checks_gate_before_action_and_does_not_skip_to_next_agent(self):
  j=job();j['test_run']=False;j['definition']['synthetic']=False
  w=FakeWorker();w.agent_gate=AsyncMock(return_value=False)
  for i,s in enumerate(j['definition']['steps']):
   s['agent_id']='agent-'+str(i);s['build_id']='build-'+str(i);s['config'].update({'guided_hash':'g','answer_hash':'a'})
   files={'agent.py':'approved'};s['package_hash']=digest(files);s['review_path']='review-'+str(i)
   w.rows['builds/'+s['build_id']+'.json']={'files':files,'package_hash':s['package_hash'],'config':copy.deepcopy(s['config']),'status':'tested','tests':[{'passed':True}]}
   w.rows[s['review_path']]={'readme_confirmed':True,'readme_hash':s['package_hash'],'guided':{},'questions':[]}
   s['config']['guided_hash']=digest({});s['config']['answer_hash']=digest([]);w.rows['builds/'+s['build_id']+'.json']['config']=copy.deepcopy(s['config'])
  await w.execute(j);w.agent_gate.assert_awaited_once();self.assertFalse(w.steps);self.assertIsNone(w.finished)
