import unittest,copy,json,os
from types import SimpleNamespace
from contextvars import ContextVar
from unittest.mock import patch
from cryptography.fernet import Fernet
from app import library,studio
class LibraryTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.old=studio.store;self.rows={};self.events=[]
  async def put(p,r):
   if p in self.rows:raise ValueError('Immutable conflict')
   self.rows[p]=copy.deepcopy(r);return r
  async def get(p):return copy.deepcopy(self.rows.get(p))
  async def event(a,p,**kw):self.events.append((a,p,kw))
  async def records(kind):return [copy.deepcopy(v) for k,v in self.rows.items() if k.startswith(kind+'/')]
  studio.store=SimpleNamespace(records=records,ACTOR=ContextVar('actor',default='alice'),put=put,get=get,event=event,ident=lambda s:s,now=lambda:'2026-10-14T00:00:00Z')
  self.env=patch.dict(os.environ,{'STUDIO_TENANT_ID':'tenant-one','STUDIO_TENANT_MEMBERS':json.dumps({'tenant-one':{'alice':'owner','bob':'user'},'tenant-two':{'bob':'user'}}),'STUDIO_VAULT_MASTER_KEY':Fernet.generate_key().decode(),'STUDIO_VAULT_ALLOWED_ADAPTERS':'["test-adapter"]'})
  self.env.start()
 async def asyncTearDown(self):self.env.stop();studio.store=self.old
 async def test_shared_credential_is_encrypted_and_never_returned(self):
  r=await library.save({'kind':'credential','label':'Reference API','secret':'synthetic-secret'})
  self.assertNotIn('synthetic-secret',json.dumps(self.rows));self.assertNotIn('synthetic-secret',json.dumps(self.events));self.assertNotIn('encrypted_value',r)
  token=studio.store.ACTOR.set('bob')
  try:
   inspected=await library.inspect(r);self.assertNotIn('encrypted_value',inspected)
   self.assertEqual(await library.resolve_credential(r,workflow_id='synthetic-workflow',adapter='test-adapter'),'synthetic-secret')
   with self.assertRaises(Exception):await library.resolve_credential(r,workflow_id='synthetic-workflow',adapter='unapproved')
  finally:studio.store.ACTOR.reset(token)
 async def test_cross_tenant_denied(self):
  r=await library.save({'kind':'template','label':'Notice','content':'Reusable content'})
  with patch.dict(os.environ,{'STUDIO_TENANT_ID':'tenant-two'}):
   token=studio.store.ACTOR.set('bob')
   try:
    with self.assertRaises(Exception):await library.inspect(r)
   finally:studio.store.ACTOR.reset(token)
 async def test_restricted_roles_and_immutable_versions(self):
  r=await library.save({'kind':'template','label':'Restricted','id':'restricted','version':'1.0.0','content':'v1','use_roles':['owner']})
  with self.assertRaises(Exception):await library.save({'kind':'template','label':'Restricted','id':'restricted','version':'1.0.0','content':'v2'})
  token=studio.store.ACTOR.set('bob')
  try:
   with self.assertRaises(Exception):await library.inspect(r)
   with self.assertRaises(Exception):await library.save({'kind':'template','label':'New','content':'x'})
  finally:studio.store.ACTOR.reset(token)
 async def test_vault_missing_is_fail_closed(self):
  with patch.dict(os.environ,{'STUDIO_VAULT_MASTER_KEY':''}):
   with self.assertRaises(Exception):await library.save({'kind':'credential','label':'Test','secret':'synthetic-secret'})
  self.assertEqual(self.rows,{})
 async def test_swapped_ciphertext_binding_rejected(self):
  a=await library.save({'kind':'credential','label':'A','secret':'synthetic-a'})
  b=await library.save({'kind':'credential','label':'B','secret':'synthetic-b'})
  path=library.path('tenant-one',a['id'],a['version']);r=self.rows[path];r['encrypted_value']=self.rows[library.path('tenant-one',b['id'],b['version'])]['encrypted_value'];r.pop('content_hash');r['content_hash']=library.digest(r);a['content_hash']=r['content_hash']
  with self.assertRaises(Exception):await library.resolve_credential(a,workflow_id='synthetic',adapter='test-adapter')
 async def test_approval_bridges_format_into_builder_registry(self):
  r=await library.save({'kind':'schema','label':'Synthetic format','content':{'type':'object','properties':{'id':{'type':'string'}},'required':['id']}})
  approved=await library.approve(r);self.assertTrue(approved['resource_ref'].startswith('schema:tenant-one.'));self.assertTrue(any(k.startswith('resources/') for k in self.rows));self.assertTrue(any(a=='resource.published' for a,p,kw in self.events))
 async def test_member_cannot_approve_and_keys_cannot_publish(self):
  r=await library.save({'kind':'instructions','label':'Instruction','content':'One bounded job'})
  token=studio.store.ACTOR.set('bob')
  try:
   with self.assertRaises(Exception):await library.approve(r)
  finally:studio.store.ACTOR.reset(token)
  key=await library.save({'kind':'credential','label':'Key','secret':'synthetic'})
  with self.assertRaises(Exception):await library.approve(key)

 async def test_lock_archive_restore_are_authorized_and_reversible(self):
  r=await library.save({'kind':'instructions','label':'Controlled','id':'controlled','version':'1.0.0','content':'One job'})
  c=await library.control({**r,'action':'lock','control_revision':0});self.assertTrue(c['locked'])
  with self.assertRaises(Exception):await library.save({'kind':'instructions','id':'controlled','version':'2.0.0','label':'Controlled','content':'Changed'})
  with self.assertRaises(Exception):await library.control({**r,'action':'archive','control_revision':1})
  self.assertEqual((await library.inspect(r))['content'],'One job')
  await library.control({**r,'action':'unlock','control_revision':1});await library.control({**r,'action':'archive','control_revision':2})
  with self.assertRaises(Exception):await library.lookup(r)
  self.assertEqual((await library.inspect(r))['content'],'One job')
  await library.control({**r,'action':'restore','control_revision':3});self.assertEqual((await library.lookup(r))['content'],'One job')
 async def test_control_stale_revision_and_member_denied(self):
  r=await library.save({'kind':'instructions','label':'Control','content':'One job'});await library.control({**r,'action':'lock'})
  with self.assertRaises(Exception):await library.control({**r,'action':'unlock','control_revision':0})
  token=studio.store.ACTOR.set('bob')
  try:
   with self.assertRaises(Exception):await library.control({**r,'action':'unlock','control_revision':1})
  finally:studio.store.ACTOR.reset(token)

 async def test_graph_picker_metadata_exposes_no_secrets(self):
  secret=json.dumps({'connection_type':'entra','tenant_id':'11111111-1111-1111-1111-111111111111','client_id':'22222222-2222-2222-2222-222222222222','client_secret':'synthetic-graph-private-value','mailbox':'observer@example.invalid','folder_id':'Inbox'})
  r=await library.save({'kind':'credential','label':'Graph observer','secret':secret})
  self.assertEqual(r['system'],'outlook_graph');self.assertEqual(r['connection_metadata'],{'mailbox':'observer@example.invalid','folder_id':'Inbox'})
  self.assertNotIn('synthetic-graph-private-value',json.dumps(r));self.assertNotIn('synthetic-graph-private-value',json.dumps(self.events));self.assertNotIn('client_secret',r['connection_metadata'])
  self.assertIn('encrypted_value',self.rows[library.path('tenant-one',r['id'],r['version'])])

 async def test_epicor_walkthrough_saves_encrypted_with_company_hint(self):
  c={'connection_type':'epicor','base_url':'https://epicor.example.invalid/Test','company_code':'TEST','username':'synthetic-user','password':'synthetic-epicor-password','api_key':'synthetic-epicor-key','allowed_paths':'/api/v2/odata/TEST/ApprovedSvc/'}
  r=await library.save({'kind':'credential','label':'Epicor TEST','secret':json.dumps(c)})
  self.assertEqual(r['system'],'epicor_rest');self.assertEqual(r['connection_metadata'],{'company_code':'TEST'})
  for secret in ('synthetic-epicor-password','synthetic-epicor-key'):
   self.assertNotIn(secret,json.dumps(self.rows));self.assertNotIn(secret,json.dumps(self.events));self.assertNotIn(secret,json.dumps(r))
