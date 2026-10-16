import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from app import fresh,mail_results
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy/mail_bridge'))
from convert import convert,digest
from bridge import Bridge
class ConversionTests(unittest.TestCase):
 def test_preserves_text_tables_and_identifiers(self):
  p={'status':'extracted','text':'=== page 1 ===\nAlpha\n\n=== page 2 ===\nBeta','tables':[{'rows':[['Item','Qty'],['A','2']]}],'message_id':'m','attachment_id':'a','sha256':'abc','confidence':100}
  out=convert(p);self.assertEqual(out['document']['text'],p['text']);self.assertEqual(out['document']['tables'],p['tables']);self.assertEqual([x['text'] for x in out['document']['pages']],['Alpha','Beta']);self.assertEqual(out['source']['sha256'],'abc');self.assertFalse(out['quality']['human_review_required']);self.assertEqual(out['business_fields'],{})
 def test_all_source_failures_remain_review(self):
  for status in ('empty','unsupported','error'):
   self.assertTrue(convert({'status':status})['quality']['human_review_required'])
  for fields in ({'truncated':True},{'confidence':40},{'error':'reader warning'}):self.assertTrue(convert({'status':'extracted',**fields})['quality']['human_review_required'])
 def test_bridge_is_idempotent_and_reads_only_fixed_tables(self):
  b=object.__new__(Bridge);source={'message_id':'m','mailbox':'ap@buntingmagnetics.com','completed_at':'2026-10-16T01:00:00Z','package':{'subject':'Synthetic','schema_version':'1'}}
  p={'message_id':'m','attachment_id':'a','mailbox':source['mailbox'],'extracted_at':'2026-10-16T01:00:01Z','reader_version':'1','filename':'sample.txt','text':'Example','status':'extracted','tables':None}
  with tempfile.TemporaryDirectory() as tmp,patch('bridge.ROOT',Path(tmp)):
   b.rows=lambda *a:[source];b.rpc=lambda action,payload:payload
   first=b.ingest_document(p);second=b.ingest_document(p);self.assertEqual(first,second)
   a=first['artifacts'];self.assertEqual([x['stage'] for x in a],['capture','parse','json']);self.assertEqual(a[1]['input_artifact_id'],a[0]['id']);self.assertEqual(a[2]['input_artifact_id'],a[1]['id'])
  with self.assertRaises(ValueError):Bridge.rows(b,'other_table',{})
class MailApiTests(unittest.IsolatedAsyncioTestCase):
 async def test_scope_cannot_be_supplied_by_caller(self):
  marker=fresh.CTX.set({'client':{'id':'selected-client'}})
  try:
   with patch.object(fresh,'rest',AsyncMock(return_value={})) as call:
    await mail_results.rpc('list',{'client_id':'bunting'});self.assertEqual(call.call_args.args[3]['args']['client_id'],'selected-client')
  finally:fresh.CTX.reset(marker)
 async def test_download_and_cursor(self):
  rows=[{'id':str(i),'occurred_at':'2026-10-16T01:00:00Z'} for i in range(51)]
  with patch.object(mail_results,'rpc',AsyncMock(return_value={'items':rows})):
   d=await mail_results.results();self.assertEqual(len(d['items']),50);self.assertEqual(d['next_cursor']['before'],'49')
  with patch.object(mail_results,'rpc',AsyncMock(return_value={'id':'a'*64,'stage':'json','output':{'text':'Synthetic'}})):
   response=await mail_results.artifact('a'*64,True);self.assertEqual(json.loads(response.body)['output']['text'],'Synthetic');self.assertIn('.json',response.headers['content-disposition'])
