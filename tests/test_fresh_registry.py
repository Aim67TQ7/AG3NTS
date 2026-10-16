import copy,unittest,os
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
from app import fresh,studio,record_bindings as registry
from app.core import Invalid

class FreshRegistry(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.marker=fresh.CTX.set({'client':{'id':'one'},'company':{'code':'MAI','facility':'500'},'role':'owner'})
  self.env=patch.dict(os.environ,{'FLUX_FRESH':'1'});self.env.start();self.objects={}
  async def records(prefix):return [copy.deepcopy(v) for k,v in self.objects.items() if k.startswith(prefix+'/')]
  async def put(path,value):
   if path in self.objects:raise ValueError('Immutable revision')
   self.objects[path]=copy.deepcopy(value);return value
  self.store=SimpleNamespace(records=records,put=put,event=AsyncMock())
  self.replace=patch.object(studio,'store',self.store);self.replace.start()
  self.old_tables=patch.object(registry,'rest',new_callable=AsyncMock,side_effect=AssertionError('Old table queried'));self.old_tables.start()
 async def asyncTearDown(self):self.old_tables.stop();self.replace.stop();self.env.stop();fresh.CTX.reset(self.marker)
 async def test_empty_registry_and_internal_validation_never_query_legacy_tables(self):
  result=await registry.registry();self.assertEqual(result['items'],[]);self.assertEqual(result['scope']['company'],'MAI')
  with patch.object(registry,'published_schemas',new_callable=AsyncMock,return_value={}):
   self.assertFalse((await registry.validate_canvas({'nodes':[]}))['valid'])
 async def test_immutable_versions_and_stale_hash_rejection(self):
  b={'name':'email.detected','owner':'operator','statuses':['detected'],'terminal_statuses':['detected']}
  first=await registry.save_registry(b);self.assertEqual(first['revision'],1)
  with self.assertRaisesRegex(Invalid,'changed'):await registry.save_registry(b)
  second=await registry.save_registry({**b,'expected_hash':first['content_hash'],'description':'Arrival metadata only'})
  self.assertEqual(second['revision'],2);self.assertEqual(len(self.objects),2)
  self.assertEqual((await registry.registry())['items'],[second])
 async def test_client_company_facility_isolation_and_admin_only_write(self):
  await registry.save_registry({'name':'email.detected','owner':'operator','statuses':['detected']})
  original=fresh.CTX.get()
  for change in ({'client':{'id':'two'}},{'company':{'code':'BMC','facility':'500'}},{'company':{'code':'MAI','facility':'600'}}):
   marker=fresh.CTX.set({**original,**change})
   try:self.assertEqual((await registry.registry())['items'],[])
   finally:fresh.CTX.reset(marker)
  marker=fresh.CTX.set({**original,'role':'editor'})
  try:
   with self.assertRaisesRegex(Invalid,'administrator'):await registry.save_registry({'name':'other.type'})
  finally:fresh.CTX.reset(marker)
 async def test_no_selected_company_can_load_but_cannot_create_records(self):
  marker=fresh.CTX.set({**fresh.CTX.get(),'company':None})
  try:
   self.assertEqual((await registry.registry())['items'],[])
   with self.assertRaises(ValueError):await registry.save_registry({'name':'other.type'})
  finally:fresh.CTX.reset(marker)
 async def test_publication_requires_approved_schema_and_sources_cannot_be_invented(self):
  with patch.object(registry,'published_schemas',new_callable=AsyncMock,return_value={}):
   with self.assertRaisesRegex(Invalid,'approved'):await registry.save_registry({'name':'email.detected','owner':'operator','statuses':['detected'],'published':True})
  with self.assertRaisesRegex(Invalid,'deployment configuration'):await registry.save_registry({'name':'outlook.mail','kind':'source','owner':'operator','statuses':['ready']})
  self.assertFalse(self.objects)
