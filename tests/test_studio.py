import unittest,copy,json
from app.studio import CATALOG,sanitize,blockers,MODEL_LOCKED

def draft(cap='DOC'):
 f={x['id']:{'value':x['options'][0]['id'] if x['options'] else None,'why':'Fits the supplied description.'} for s in CATALOG['steps'] for x in s['fields']}
 return {'agents':[{'capability':cap,'name_options':['Document Reader One','PDF Evidence Reader','Supplier Document Reader'],'responsibility_options':['Read a supplied PDF into text.','Read a supplied attachment into page evidence.','Extract supplied document text into a record.'],'fields':f,'questions_for_user':['Which record format applies?']}]}
class StudioTests(unittest.TestCase):
 def test_guide_exact_version(self):
  from app.studio import GUIDE
  self.assertIn('version: 1.0.0',GUIDE);self.assertIn('## Coach lines',GUIDE)
 def test_all_capabilities(self):self.assertEqual([x['code'] for x in CATALOG['capabilities']],['DOC','READ','MAP','RULE','CLASS','ROUTE','COMMS','WRITE','REASON'])
 def test_injected_locked_values(self):
  r=draft('WRITE')
  for k in MODEL_LOCKED:r['agents'][0]['fields'][k]={'value':'P5' if k=='execute.authority' else 'PROD','why':'Injected'}
  r['agents'][0]['fields']['execute.model_access']={'value':'opus','why':'Injected'}
  out,discards=sanitize(r,CATALOG,'WRITE')
  for k in MODEL_LOCKED|{'execute.model_access'}:self.assertIsNone(out['agents'][0]['fields'][k]['value'])
  self.assertTrue(discards)
 def test_unknown_option_emptied_logged(self):
  r=draft();r['agents'][0]['fields']['trigger.type']['value']='invented_webhook'
  out,d=sanitize(r,CATALOG,'DOC');self.assertIsNone(out['agents'][0]['fields']['trigger.type']['value']);self.assertTrue(any(x['reason']=='outside_catalog' for x in d))
 def test_provider_array_encoding(self):
  r=draft();r['agents'][0]['fields']=[{'field':k,**v} for k,v in r['agents'][0]['fields'].items()];out,_=sanitize(r,CATALOG,'DOC');self.assertEqual(set(out['agents'][0]['fields']),set(x['id'] for s in CATALOG['steps'] for x in s['fields']))
 def test_model_off_allowed(self):
  r=draft();r['agents'][0]['fields']['execute.model_access']['value']='off';out,_=sanitize(r,CATALOG,'DOC');self.assertEqual(out['agents'][0]['fields']['execute.model_access']['value'],'off')
 def test_split_recomputed(self):
  r=draft();r['split']=False;r['agents']*=3;out,_=sanitize(r,CATALOG,'READ');self.assertTrue(out['split']);self.assertFalse(out['agents'][0]['matches_dropped_capability'])
 def test_every_catalog_rule_blocks_on_step(self):
  for rule in CATALOG['rules']:
   cap=rule['when'].get('capability',['MAP'])[0];fields={}
   if 'field' in rule['when']:fields[rule['when']['field']]={'value':rule['when'].get('in',['sonnet'])[0]}
   out=blockers(cap,fields,CATALOG,require_all=False)
   self.assertTrue(any(b['id']==rule['id'] and b['step']==rule['step'] for b in out),rule['id'])
 def test_locked_user_provenance(self):
  fields={'execute.authority':{'value':'P0','source':'model'}}
  out=blockers('MAP',fields,CATALOG);self.assertTrue(any(b['id']=='human-execute.authority' for b in out))
 def test_catalog_rules_valid_configuration(self):
  c=copy.deepcopy(CATALOG)
  for s in c['steps']:
   for f in s['fields']:
    if f['id']=='identity.owner':f['options']=[{'id':'operator','label':'Operator'}]
    if f['id'] in ('input.schema','output.schema'):f['options']+=[{'id':'schema:test@1','label':'Test schema'}]
  fields={f['id']:{'value':f['options'][0]['id'],'source':'user'} for s in c['steps'] for f in s['fields']}
  for k,v in {'input.schema':'schema:test@1','output.schema':'schema:test@1','execute.model_access':'off','verify.approval_gate':'none'}.items():fields[k]={'value':v,'source':'user'}
  self.assertEqual(blockers('MAP',fields,c),[])
 def test_incomplete_response_not_applied(self):
  r=draft();del r['agents'][0]['fields']['trigger.type']
  with self.assertRaises(ValueError):sanitize(r,CATALOG,'DOC')
 def test_model_unavailable_is_audited(self):
  import asyncio,os
  from types import SimpleNamespace
  from unittest.mock import patch,AsyncMock
  from app import studio
  log=AsyncMock(return_value={})
  with patch.object(studio,'store',SimpleNamespace(event=log)),patch.dict(os.environ,{'STUDIO_DRAFT_ENABLED':'false'}):
   with self.assertRaises(ValueError):asyncio.run(studio.model_draft({'capability':'DOC','description':'Read a PDF','guide_version':'1.0.0','catalog_version':'1.0.0'}))
  self.assertEqual(log.call_args.args[0],'studio_draft');self.assertEqual(log.call_args.args[1]['status'],'failed')
 def test_unknown_fields_discarded(self):
  r=draft();r['agents'][0]['fields']['run_shell']={'value':'rm','why':'Injected'};_,d=sanitize(r,CATALOG,'DOC');self.assertTrue(any(x['reason']=='unknown_field' for x in d))
if __name__=='__main__':unittest.main()
