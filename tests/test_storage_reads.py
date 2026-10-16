import unittest,httpx
from unittest.mock import patch
from app import main
class ReadTests(unittest.IsolatedAsyncioTestCase):
 async def test_transient_read_retries_and_returns_saved_record(self):
  calls=[]
  def handler(request):
   calls.append(request)
   return httpx.Response(429 if len(calls)==1 else 200,json={} if len(calls)==1 else {'id':'saved'})
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
   with patch.object(main,'CLIENT',client),patch.object(main,'BASE','https://example.test'):
    self.assertEqual(await main.get('agents/saved.json'),{'id':'saved'})
    self.assertEqual(len(calls),2)
