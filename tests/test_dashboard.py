import copy,json,os,unittest,uuid
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
from starlette.requests import Request
import httpx
from app import fresh,studio,runtime_reviews,graph_credentials
from app.core import Invalid

class Reviews(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.marker=fresh.CTX.set({'client':{'id':'client-one'},'user':{'id':'reviewer'},'role':'owner'})
  self.old=studio.store;self.objects={};self.events=[]
  self.row={'id':'synthetic-review-id','workflow_id':'synthetic-flow','status':'review_required','test_run':True,'created_at':'2026-10-15T01:00:00Z','finished_at':'2026-10-15T01:01:00Z','input':{'amount':42},'definition':{'synthetic':True,'steps':[{'agent_id':'synthetic-agent','name':'Check amount','package_hash':'pinned-package','build_id':'pinned-build'}]},'result':{'step':0,'reasons':['Required evidence missing'],'output':None}}
  async def objects(k):return [copy.deepcopy(v) for p,v in self.objects.items() if p.startswith(k+'/')]
  async def get(p):return copy.deepcopy(self.objects.get(p))
  async def put(p,v):
   if p in self.objects:raise ValueError('Immutable record')
   self.objects[p]=copy.deepcopy(v);return v
  async def event(a,p,**kw):self.events.append((a,p));return p
  studio.store=SimpleNamespace(records=objects,get=get,put=put,event=event,ident=lambda x:x,uid=lambda:str(uuid.uuid4()),now=lambda:'2026-10-15T02:00:00Z')
  async def rest(s,method,path,body=None):
   self.assertEqual(method,'GET');self.assertIn('client_id=eq.client-one',path)
   return [copy.deepcopy(self.row)]
  self.mock=patch.object(fresh,'rest',side_effect=rest);self.mock.start()
 async def asyncTearDown(self):self.mock.stop();studio.store=self.old;fresh.CTX.reset(self.marker)
 async def test_queue_filters_tests_and_targets_exact_agent(self):
  self.assertEqual((await runtime_reviews.queue())['items'],[])
  row=(await runtime_reviews.queue(True))['items'][0]
  self.assertEqual(row['agent_id'],'synthetic-agent');self.assertTrue(row['evidence_hash'])
 async def test_feedback_is_immutable_scoped_and_does_not_resume(self):
  q=(await runtime_reviews.queue(True))['items'][0];before=copy.deepcopy(self.row)
  b={'key':q['key'],'evidence_hash':q['evidence_hash'],'decision':'feedback','reason':'Supply the missing evidence and test again.'}
  receipt=await runtime_reviews.decision(b)
  self.assertEqual(receipt['target_agent_id'],'synthetic-agent');self.assertEqual(receipt['package_hash'],'pinned-package');self.assertFalse(receipt['auto_resume']);self.assertFalse(receipt['external_actions_authorized']);self.assertEqual(self.row,before)
  self.assertEqual((await runtime_reviews.queue(True))['items'],[])
  with self.assertRaisesRegex(Invalid,'already has'):await runtime_reviews.decision(b)
  self.assertEqual(len(self.objects),1);self.assertEqual(len(self.events),2)
 async def test_stale_evidence_and_viewer_decisions_rejected(self):
  q=(await runtime_reviews.queue(True))['items'][0];self.row['input']['amount']=43
  b={'key':q['key'],'evidence_hash':q['evidence_hash'],'decision':'approve','reason':'Reviewed'}
  with self.assertRaisesRegex(Invalid,'Evidence changed'):await runtime_reviews.decision(b)
  marker=fresh.CTX.set({**fresh.CTX.get(),'role':'user'})
  try:
   with self.assertRaisesRegex(Invalid,'permission'):await runtime_reviews.decision(b)
  finally:fresh.CTX.reset(marker)
  self.assertFalse(self.objects)
 async def test_unknown_choice_and_empty_feedback_rejected(self):
  with self.assertRaises(Invalid):await runtime_reviews.decision({'decision':'resume'})
  with self.assertRaises(Invalid):await runtime_reviews.decision({'decision':'reject','reason':' '})

class PublicBoundary(unittest.IsolatedAsyncioTestCase):
 async def test_public_overview_and_root_have_signin_but_no_workspace_data(self):
  for path in ('/','/overview'):
   req=Request({'type':'http','method':'GET','path':path,'scheme':'https','headers':[(b'host',b'flux.by-pete.com')],'query_string':b''})
   result=await fresh.boundary(req,None,SimpleNamespace())
   self.assertEqual(result.status_code,200);text=result.body.decode();self.assertIn('href="/auth/login"',text);self.assertNotIn('Bunting',text);self.assertNotIn('/api/state',text)
 async def test_existing_anonymous_api_boundary_unchanged(self):
  req=Request({'type':'http','method':'GET','path':'/api/state','scheme':'https','headers':[(b'host',b'flux.by-pete.com')],'query_string':b''})
  self.assertEqual((await fresh.boundary(req,None,SimpleNamespace())).status_code,401)
 async def test_file_size_allowance_is_only_for_drafting(self):
  for path,expected in [('/api/studio/draft-agent',401),('/api/studio/review/decision',413)]:
   async def receive():return {'type':'http.request','body':b'x'*1100000,'more_body':False}
   req=Request({'type':'http','method':'POST','path':path,'scheme':'https','headers':[(b'host',b'flux.by-pete.com'),(b'origin',b'https://flux.by-pete.com'),(b'content-type',b'application/json')],'query_string':b''},receive)
   self.assertEqual((await fresh.boundary(req,None,SimpleNamespace())).status_code,expected)

class GraphCredentials(unittest.TestCase):
 def config(self):return {'connection_type':'entra','tenant_id':str(uuid.uuid4()),'client_id':str(uuid.uuid4()),'client_secret':'synthetic-secret','mailbox':'mailbox@example.test','folder_id':'inbox','secret_expires_on':'2027-01-01'}
 def test_fixed_endpoints_mailbox_scope_and_unverified_permission(self):
  c=self.config();c['resource_url']='https://untrusted.example';c['authority_url']='https://untrusted.example'
  result=json.loads(graph_credentials.normalize(json.dumps(c)))
  self.assertEqual(result['resource_url'],'https://graph.microsoft.com');self.assertEqual(result['scope'],'https://graph.microsoft.com/.default');self.assertFalse(result['permission_verified']);self.assertEqual(result['allowed_mailboxes'],['mailbox@example.test'])
 def test_missing_mailbox_secret_and_invalid_tenant_are_rejected(self):
  for key in ('mailbox','client_secret','tenant_id','folder_id'):
   c=self.config();c.pop(key)
   with self.assertRaises(Invalid):graph_credentials.normalize(json.dumps(c))
 def test_other_credentials_are_unchanged(self):self.assertEqual(graph_credentials.normalize('synthetic-key'),'synthetic-key')
