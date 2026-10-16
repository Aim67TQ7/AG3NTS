import copy,unittest
from app.mail_runtime import package
from app.core import digest
class CanvasMailPackageTests(unittest.TestCase):
 def test_existing_agent_ids_are_preserved_and_contracts_are_connected(self):
  capture={'id':'n1','data':{'guided':{'id':'capture-card','version':'0.1.0','fields':{},'trigger_config':{'target':'confirmations@buntingmagnetics.com'}}}}
  parser={'id':'n2','data':{'guided':{'id':'parser-card','name':'Parse','version':'0.1.0','fields':{},'capability':'DOC'}}}
  converter={'id':'n3','data':{'guided':{'id':'json-card','version':'0.1.0','fields':{},'capability':'DOC'}}}
  original={'id':'flow','version':'0.0.2','nodes':[capture,parser,converter]};before=copy.deepcopy(original)
  plan,objects=package(original,'owner',{'tenant':'bunting','company':'BMC','facility':'500'},'2026-10-16T13:00:00Z')
  self.assertEqual(original,before);self.assertEqual([s['agent_id'] for s in plan['steps']],['capture-card','parser-card','json-card'])
  self.assertEqual([s['adapter'] for s in plan['steps']],['maggie_capture','document_parse_local','document_json_v1'])
  for s in plan['steps']:self.assertEqual(s['guided_hash'],digest(s['guided']));self.assertEqual(s['guided']['fields']['execute.model_access']['value'],'off')
  self.assertEqual(plan['steps'][1]['input_schema'],plan['steps'][0]['output_schema']);self.assertEqual(plan['steps'][2]['input_schema'],plan['steps'][1]['output_schema'])
  workflow=next(x['body'] for x in objects if x['path'].startswith('workflows/'));self.assertEqual(len(workflow['edges']),2);self.assertEqual(workflow['version'],'0.0.3')
