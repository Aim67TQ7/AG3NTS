import unittest
from unittest.mock import AsyncMock, patch
import httpx
from app import fresh, copackers_operator as operator


class ExternalDirectoryOperator(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.marker = fresh.CTX.set({'client': {'id': 'n0v8v-llc'}, 'company': {'code': 'N0V8V'}, 'role': 'owner'})
 def tearDown(self):
  fresh.CTX.reset(self.marker)
 def test_installed_definition_is_scoped_and_has_no_native_authority(self):
  item = operator.installed_agent()
  self.assertEqual(item['id'], 'copackers-directory-operator')
  self.assertFalse(item['execution']['dispatch_enabled'])
  self.assertIsNone(item['authority'])
  self.assertEqual(item['tests'], [])
  self.assertEqual(item['guided']['runtime_binding']['kind'], 'external_directory')
  for context in [None, {}, {'client': {'id': 'bunting'}, 'company': {'code': 'BMC'}}, {'client': {'id': 'n0v8v-llc'}, 'company': {'code': 'BMC'}}]:
   token = fresh.CTX.set(context)
   try:self.assertIsNone(operator.installed_agent())
   finally:fresh.CTX.reset(token)
 async def test_other_company_cannot_probe_status(self):
  token = fresh.CTX.set({'client': {'id': 'bunting'}, 'company': {'code': 'BMC'}})
  try:
   with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as get:
    response = await operator.status()
    self.assertEqual(response.status_code,404)
    get.assert_not_awaited()
  finally:fresh.CTX.reset(token)
 async def test_fixed_status_target_and_no_execution_grant(self):
  response=httpx.Response(200,json={'status':'partial','leads_received':0})
  with patch.object(httpx.AsyncClient,'get',new_callable=AsyncMock,return_value=response) as get:
   body=await operator.status()
  get.assert_awaited_once_with('http://127.0.0.1:8609/status')
  self.assertTrue(body['available'])
  self.assertFalse(body['native_studio_execution'])
  self.assertEqual(body['status'],'partial')
 async def test_bad_status_is_unavailable(self):
  for response in [httpx.Response(502,text='upstream error'),httpx.Response(200,json=[]),httpx.Response(200,text='not json')]:
   with patch.object(httpx.AsyncClient,'get',new_callable=AsyncMock,return_value=response):
    result=await operator.status()
   self.assertEqual(result.status_code,200)
   self.assertIn(b'"available":false',result.body)
