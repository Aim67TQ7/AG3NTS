import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from app import workflow_json as wj,mail_runtime,studio,fresh
from app.core import Invalid
class WorkflowJsonTests(unittest.IsolatedAsyncioTestCase):
 def source(self):
  capture={'id':'n1','data':{'guided':{'id':'capture','version':'0.1.0','fields':{},'trigger_config':{'target':'confirmations@buntingmagnetics.com'}}}}
  parser={'id':'n2','data':{'guided':{'id':'parse','name':'Parse','version':'0.1.0','fields':{},'capability':'DOC'}}}
  converter={'id':'n3','data':{'guided':{'id':'json','version':'0.1.0','fields':{},'capability':'MAP'}}}
  definition,objects=mail_runtime.package({'id':'original','version':'0.0.1','nodes':[capture,parser,converter]},'source-owner',{'tenant':'source','company':'SOURCE','facility':'TEST'},'2026-10-16T00:00:00Z')
  return next(o['body'] for o in objects if o['path'].startswith('workflows/')),[o['body'] for o in objects if o['path'].startswith('resources/')]
 async def package(self):
  canvas,resources=self.source();fake=SimpleNamespace(records=AsyncMock(return_value=resources))
  with patch.object(studio,'store',fake),patch('app.governance.check',AsyncMock()):return await wj.export_canvas(canvas)
 async def test_installed_pipeline_exports_complete_contracts_without_runtime_authority(self):
  p=await self.package();report=wj.validate(p)
  self.assertEqual((report['steps'],report['connections'],report['resource_slots']),(3,2,3))
  self.assertTrue(all(s['contracts']['input'] and s['contracts']['output'] for s in p['workflow']['steps']))
  self.assertNotIn('runtime_binding',json.dumps(p));self.assertNotIn('source-owner',json.dumps(p))
 async def test_import_round_trip_preserves_functions_contracts_and_handoffs_as_new_test_draft(self):
  p=await self.package();marker=fresh.CTX.set({'role':'owner','user':{'id':'destination-owner'},'client':{'id':'destination'},'company':{'code':'DEST'}})
  fake=SimpleNamespace(event=AsyncMock(),records=AsyncMock(return_value=[]))
  async def save(canvas):return {**canvas,'execution_enabled':False,'format':'canvas-v2'}
  try:
   with patch.object(studio,'store',fake),patch.object(studio,'catalog',AsyncMock(return_value=studio.CATALOG)),patch.object(studio,'save_canvas',save):
    result=await wj.import_package({'package':p});w=result['workflow'];self.assertFalse(w['execution_enabled'])
    for n in w['nodes']:
     g=n['data']['guided'];self.assertEqual(g['fields']['identity.environment']['value'],'TEST');self.assertNotIn('runtime_binding',g);self.assertEqual(g['reusable_resources'],[])
    again=await wj.export_canvas(w)
   self.assertEqual([s['functions'] for s in p['workflow']['steps']],[s['functions'] for s in again['workflow']['steps']])
   self.assertEqual(p['workflow']['connections'],again['workflow']['connections'])
   self.assertNotEqual(w['id'],'original')
  finally:fresh.CTX.reset(marker)
 async def test_secrets_cycles_unknown_steps_and_incompatible_contracts_are_rejected(self):
  source=await self.package()
  for change in ('secret','cycle','unknown','contract','credential-content','version','activation'):
   p=copy.deepcopy(source)
   if change=='secret':p['workflow']['steps'][0]['configuration']['api_key']='synthetic-secret'
   elif change=='cycle':p['workflow']['connections'].append({'id':'cycle','from':{'step':'step-3','port':'COMPLETED'},'to':{'step':'step-1','port':'input'},'delivery':'durable_record'})
   elif change=='unknown':p['workflow']['connections'][0]['to']['step']='missing'
   elif change=='contract':p['workflow']['steps'][1]['contracts']['input']={'type':'object','required':['impossible'],'properties':{'impossible':{'type':'string'}},'additionalProperties':False}
   elif change=='credential-content':p['resources'].append({'id':'credential','kind':'credential','label':'Synthetic','content':'synthetic-secret'})
   elif change=='version':p['schema_version']='99.0.0'
   else:p['workflow']['execution_enabled']=True
   with self.subTest(change=change),self.assertRaises(Invalid):wj.validate(p)
 async def test_credential_export_is_a_slot_with_no_value_hash_or_selection(self):
  canvas,resources=self.source();g=canvas['nodes'][0]['data']['guided'];g['reusable_resources']=[{'id':'source-credential','kind':'credential','version':'1.0.0','content_hash':'private-hash','selection_id':'private-selection'}]
  fake=SimpleNamespace(records=AsyncMock(return_value=resources))
  with patch.object(studio,'store',fake),patch('app.governance.check',AsyncMock()),patch('app.library.lookup',AsyncMock(return_value={'id':'source-credential','kind':'credential','label':'Mailbox','encrypted_value':'synthetic-encrypted-secret'})):
   p=await wj.export_canvas(canvas)
  text=json.dumps(p)
  for forbidden in ('synthetic-encrypted-secret','private-hash','private-selection','source-credential'):self.assertNotIn(forbidden,text)
  self.assertTrue(any(r['kind']=='credential' for r in p['resources']))
 async def test_export_removes_credential_bearing_urls(self):
  self.assertEqual(wj.clean({'url':'https://user:synthetic-password@example.invalid/api'})['url'],'[credential-bearing URL omitted]')

 async def test_record_bindings_export_as_handoffs_without_saved_wires(self):
  canvas,resources=self.source();canvas['edges']=[]
  with patch.object(studio,'store',SimpleNamespace(records=AsyncMock(return_value=resources))),patch('app.governance.check',AsyncMock()):
   p=await wj.export_canvas(canvas)
  self.assertEqual([(e['from']['step'],e['to']['step']) for e in p['workflow']['connections']],[('step-1','step-2'),('step-2','step-3')])
