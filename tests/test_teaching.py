import copy,unittest
from contextvars import ContextVar
from types import SimpleNamespace
from app import studio,teaching
class Tests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.old=studio.store;self.rows={}
  async def records(kind):return [copy.deepcopy(r) for k,r in self.rows.items() if k.startswith(kind+'/')]
  async def put(k,v):
   if k in self.rows:raise ValueError('immutable')
   self.rows[k]=copy.deepcopy(v);return v
  async def get(k):return copy.deepcopy(self.rows.get(k))
  async def event(a,b,**kw):return {}
  studio.store=SimpleNamespace(records=records,put=put,get=get,event=event,ACTOR=ContextVar('actor',default='owner'),ident=lambda x:x,now=lambda:'2026-10-14T00:00:00Z')
  self.guided={'id':'map-test','name':'Synthetic field mapper','capability':'MAP','responsibility':'Map an approved field','fields':{'identity.environment':{'value':'TEST'},'identity.company':{'value':'BMC'},'input.schema':{'value':'schema:in@1'},'output.schema':{'value':'schema:out@1'}}}
  for id in ('in','out'):
   self.rows['resources/'+id]={'id':id,'version':'1','kind':'schema','content':{'type':'object'}};self.rows['audit/'+id]={'action':'resource.published','payload':{'resource_ref':'schema:'+id+'@1'}}
 async def asyncTearDown(self):studio.store=self.old
 async def ready(self):
  r=await teaching.start({'guided':self.guided})
  for q in r['questions']:q.update(answer='Synthetic approved test answer',resolution='answered')
  return await teaching.save({**r,'fixtures':[{'input':{'a':i},'expected':{'b':i}} for i in range(5)],'job_spec':{'kind':'map','fields':{'b':'a'}},'logic_approved':True})
 async def test_build_generates_files_and_tests(self):
  r=await self.ready();r=await teaching.build({'id':r['id']});a=r['last_build'];self.assertEqual(a['status'],'tested');self.assertTrue(all(x['passed'] for x in a['tests']));self.assertIn('agent.py',a['files']);self.assertIn('config.yaml',a['files']);self.assertIn('tests/test_agent.py',a['files']);self.assertIn('flux_harness',a['files']['agent.py']);self.assertFalse(a['config']['activation_enabled'])
 async def test_unanswered_blocks(self):
  r=await teaching.start({'guided':self.guided})
  with self.assertRaises(Exception):await teaching.build({'id':r['id']})
 async def test_failure_creates_question(self):
  r=await self.ready();r['fixtures'][0]['expected']={'b':100};r=await teaching.save(r);r=await teaching.build({'id':r['id']});self.assertEqual(r['last_build']['status'],'failed');self.assertTrue(any(q['resolution']=='open' for q in r['questions']))
 async def test_changed_interview_blocks_release(self):
  r=await self.ready();r=await teaching.build({'id':r['id']});r['questions'][0]['answer']='changed';r=await teaching.save(r)
  with self.assertRaises(Exception):await teaching.publish({'id':r['id'],'build_id':r['last_build']['id'],'canvas':{}})
 async def test_publish_commits_exact_tested_package(self):
  import os,tempfile,subprocess
  from unittest.mock import patch
  from test_record_bindings import node,reg
  self.guided['bindings']=node('mapper','MAP','input','output','done')['data']['guided']['bindings']
  r=await self.ready();r=await teaching.build({'id':r['id']});r['readme_confirmed']=True;r['readme_hash']=r['last_build']['package_hash'];r=await teaching.save(r)
  canvas={'binding_mode':'records','nodes':[node('reader','READ','source','input'),{'id':'node','data':{'capability':'MAP','guided':self.guided}}],'edges':[]}
  async def registry():return {'items':[reg('source','source'),reg('input'),reg('output',statuses=['done'],terminal=['done'])]}
  with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'STUDIO_PACKAGE_ROOT':root}),patch('app.record_bindings.registry',registry):
   r=await teaching.publish({'id':r['id'],'build_id':r['last_build']['id'],'canvas':canvas})
   sha=subprocess.check_output(['git','-C',root,'rev-parse','HEAD'],text=True).strip();self.assertEqual(sha,r['release']['git_commit']);self.assertFalse(r['release']['activation_enabled']);self.assertEqual(r['release']['version'],'1.0.0')
 async def test_secrets_rejected(self):
  r=await self.ready();r['job_spec']={'kind':'adapter','parameters':{'api_key':'synthetic-do-not-store'}}
  with self.assertRaises(Exception):await teaching.save(r)
 async def test_exported_python_matches_harness_test(self):
  import types
  from flux_harness import Context,Harness
  r=await self.ready();r=await teaching.build({'id':r['id']});a=r['last_build'];module=types.ModuleType('generated_test_agent');exec(a['files']['agent.py'],module.__dict__)
  actual=await Harness(studio.store).invoke(module.run,{'a':2},a['config'],Context('MAP',a['config']['scope']),'exported-one');self.assertEqual(actual['output'],{'b':2})
