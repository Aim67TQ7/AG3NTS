import unittest,copy
from types import SimpleNamespace
from contextvars import ContextVar
from app import reviews,studio
class Tests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.old=studio.store;self.audit=[]
  self.r={'record_id':'synthetic-test','agent_ref':'synthetic-rule@1','created_at':'2026-10-14T00:00:00Z','result_status':'REVIEW_REQUIRED','input':{'name':'OTHER SYNTHETIC'},'output':{'matched':False},'content_hash':'result-hash'}
  async def records(k):return copy.deepcopy(self.audit if k=='audit' else [self.r] if k=='runs' else [])
  async def event(a,p,**kw):r={'action':a,'payload':p,'created_at':'2026-10-14T01:00:00Z'};self.audit.append(r);return r
  studio.store=SimpleNamespace(records=records,event=event,BASE='',ACTOR=ContextVar('actor',default='owner'))
 async def asyncTearDown(self):studio.store=self.old
 async def test_test_filter_and_closed_queue(self):
  self.assertEqual((await reviews.queue())['items'],[]);r=(await reviews.queue(True))['items'][0]
  await reviews.decision({'key':r['key'],'evidence_hash':r['evidence_hash'],'decision':'approve','reason':''});self.assertEqual((await reviews.queue(True))['items'],[])
 async def test_reject_reason_and_stale_evidence(self):
  r=(await reviews.queue(True))['items'][0]
  with self.assertRaises(Exception):await reviews.decision({'key':r['key'],'evidence_hash':r['evidence_hash'],'decision':'reject','reason':'  '})
  self.r['output']={'matched':True}
  with self.assertRaises(Exception):await reviews.decision({'key':r['key'],'evidence_hash':r['evidence_hash'],'decision':'approve'})
