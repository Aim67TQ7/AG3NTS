import unittest,copy
from app import runtime
class FakeWorker(runtime.Worker):
 def __init__(self,stop=False):self.rows={};self.steps=[];self.finished=None;self.hold=stop
 async def rpc(self,action,job=None,payload=None):
  payload=payload or {}
  if action=='state':return {'state':'stopped' if self.hold else 'running'}
  if action=='get':return self.rows.get(payload['path'])
  if action=='put':self.rows[payload['path']]=payload['body'];return payload['body']
  if action=='step':self.steps.append(payload);return True
  if action=='finish':self.finished=payload;return True
  raise AssertionError(action)
def job(data=None):return {'id':'unit-job','client_id':'bunting','owner_id':'owner','definition':runtime.sample('bunting'),'input':data if data is not None else {'amount':42},'test_run':True}
class RuntimeTests(unittest.IsolatedAsyncioTestCase):
 async def test_two_real_harness_steps_and_durable_replay(self):
  w=FakeWorker();await w.execute(job());self.assertEqual(w.finished['status'],'completed');self.assertEqual(len(w.steps),2);self.assertTrue(w.finished['result']['output']['passed'])
  first=copy.deepcopy(w.steps);await w.execute(job());self.assertEqual(w.steps[2]['result'],first[0]['result']);self.assertEqual(w.steps[3]['result'],first[1]['result'])
 async def test_invalid_input_stops_at_review_without_next_agent(self):
  w=FakeWorker();await w.execute(job({'wrong':1}));self.assertEqual(w.finished['status'],'review_required');self.assertEqual(len(w.steps),1)
 async def test_stop_prevents_first_step(self):
  w=FakeWorker(stop=True);await w.execute(job());self.assertFalse(w.steps);self.assertIsNone(w.finished)
 async def test_cannot_modify_builtin_template_to_inject_an_adapter(self):
  j=job();j['definition']['steps'][0]['config']['job_spec']={'kind':'adapter','operation':'epicor_write'}
  with self.assertRaises(PermissionError):await FakeWorker().execute(j)
 def test_external_write_and_unconfigured_read_are_blocked(self):
  cfg=runtime.sample('bunting')['steps'][0]['config'];cfg['capability']='WRITE'
  with self.assertRaises(Exception):runtime.validate_config(cfg)
  cfg['capability']='READ';cfg['job_spec']={'kind':'adapter','operation':'graph_read'}
  with self.assertRaises(Exception):runtime.validate_config(cfg)
