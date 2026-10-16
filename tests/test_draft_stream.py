import json,unittest,httpx
from app.studio import streamed_message,draft_failure
from app.core import Invalid

def events(complete=True):
    rows=[{'type':'message_start','message':{'usage':{'input_tokens':42},'content':[]}}, {'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}}, {'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':'{"agents":[]}'}}, {'type':'message_delta','delta':{'stop_reason':'end_turn'},'usage':{'output_tokens':9}}]
    if complete:rows.append({'type':'message_stop'})
    return ''.join('data: '+json.dumps(r)+'\n\n' for r in rows).encode()
class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_stream_keeps_final_usage(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=events()))) as c:
            response,message=await streamed_message(c,{},{});self.assertEqual(message['usage'],{'input_tokens':42,'output_tokens':9});self.assertEqual(message['stop_reason'],'end_turn');self.assertEqual(message['content'][0]['text'],'{"agents":[]}')
    async def test_incomplete_stream_never_returns_partial_draft(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=events(False)))) as c:
            with self.assertRaisesRegex(Invalid,'before completing'):await streamed_message(c,{},{})
    async def test_definite_rejection_is_readable(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(429,json={'error':{'message':'limited'}}))) as c:
            response,message=await streamed_message(c,{},{});self.assertIsNone(message);self.assertEqual(response.json()['error']['message'],'limited')
    def test_empty_timeout_has_phase_and_recovery(self):
        self.assertIn('generating',draft_failure(TimeoutError(),'generating choices'));self.assertIn('No fields were applied',draft_failure(httpx.ReadTimeout(''),'generating choices'))
