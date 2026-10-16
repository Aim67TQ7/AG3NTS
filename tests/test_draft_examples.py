import base64,copy,json,os,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import httpx
from app.core import Invalid
from app.draft_examples import example_content,MAX_BYTES
from app import studio,runtime,fresh
from tests.test_studio import draft

def body(media='application/pdf',raw=b'%PDF-1.4\nsynthetic example'):
 return {'capability':'DOC','description':'Read a supplied synthetic example into fields.','guide_version':studio.CATALOG['guide_version'],'catalog_version':studio.CATALOG['version'],'example_consent':True,'example':{'media_type':media,'data':base64.b64encode(raw).decode(),'notes':'Read the supplied field labels; ask about missing fields.'}}
class ExampleTests(unittest.TestCase):
 def test_no_example_preserves_text_only(self):self.assertEqual(example_content({}),([],[]))
 def test_consent_required(self):
  b=body();b['example_consent']=False
  with self.assertRaisesRegex(Invalid,'Approve'):example_content(b)
 def test_false_mime_and_bad_encoding_rejected(self):
  b=body(raw=b'not a PDF')
  with self.assertRaisesRegex(Invalid,'does not match'):example_content(b)
  b['example']['data']='!'
  with self.assertRaisesRegex(Invalid,'encoding'):example_content(b)
 def test_size_and_unsupported_format_rejected(self):
  b=body();b['example']['data']='A'*(4*((MAX_BYTES+2)//3)+4)
  with self.assertRaisesRegex(Invalid,'5 MB'):example_content(b)
  b=body(media='image/svg+xml')
  with self.assertRaisesRegex(Invalid,'Choose a PDF'):example_content(b)
 def test_notes_required(self):
  b=body();b['example']['notes']=' '
  with self.assertRaisesRegex(Invalid,'Describe'):example_content(b)
 def test_metadata_has_hash_but_no_contents(self):
  b=body();blocks,evidence=example_content(b)
  self.assertEqual(blocks[0]['type'],'document');self.assertEqual(blocks[0]['source']['data'],b['example']['data'])
  self.assertEqual(evidence[0]['bytes'],len(base64.b64decode(b['example']['data'])));self.assertEqual(len(evidence[0]['sha256']),64)
  self.assertNotIn('data',evidence[0]);self.assertNotIn('notes',evidence[0])
 def test_supported_image_block(self):
  blocks,_=example_content(body('image/png',b'\x89PNG\r\n\x1a\nsynthetic'))
  self.assertEqual(blocks[0]['type'],'image')
class TransportTests(unittest.IsolatedAsyncioTestCase):
 async def test_consented_example_reaches_token_count_and_message_without_raw_audit(self):
  requests=[]
  def respond(request):
   requests.append(json.loads(request.content));return httpx.Response(200,json={'input_tokens':100})
  client=httpx.AsyncClient(transport=httpx.MockTransport(respond));log=AsyncMock();cat=copy.deepcopy(studio.CATALOG);cat['snapshot_hash']='synthetic-hash'
  response=httpx.Response(200,headers={'request-id':'synthetic-request'})
  message={'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps(draft())}],'usage':{'input_tokens':100,'output_tokens':100}}
  streamed=AsyncMock(return_value=(response,message));b=body()
  with patch.object(studio,'store',SimpleNamespace(event=log)),patch.object(studio,'catalog',AsyncMock(return_value=cat)),patch.object(studio.httpx,'AsyncClient',return_value=client),patch.object(studio,'streamed_message',streamed),patch.dict(os.environ,{'STUDIO_DRAFT_ENABLED':'true','ANTHROPIC_API_KEY':'synthetic-test-key','STUDIO_DRAFT_MODEL':'synthetic-model','STUDIO_DRAFT_INPUT_PER_MTOK':'2','STUDIO_DRAFT_OUTPUT_PER_MTOK':'10'}):
   result=await studio.model_draft(b)
  self.assertEqual(len(result['agents']),1)
  for content in [requests[0]['messages'][0]['content'],streamed.call_args.args[2]['messages'][0]['content']]:self.assertEqual(content[0]['source']['data'],b['example']['data'])
  recorded=json.dumps(log.call_args.args[1]);self.assertNotIn(b['example']['data'],recorded);self.assertIn('example_evidence',recorded)
 async def test_runtime_inputs_are_client_scoped_and_paginated(self):
  marker=fresh.CTX.set({'client':{'id':'synthetic-client'}})
  try:
   with patch.object(fresh,'rest',AsyncMock(return_value=[{'id':str(i)} for i in range(25)])) as read:
    result=await runtime.input_records(25)
   self.assertIn('client_id=eq.synthetic-client',read.call_args.args[2]);self.assertIn('offset=25',read.call_args.args[2]);self.assertEqual(result['next_offset'],50)
   with self.assertRaises(Invalid):await runtime.input_records(-1)
  finally:fresh.CTX.reset(marker)
