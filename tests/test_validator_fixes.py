"""Regressions for MCP reports from the confirmation-email canvas; synthetic data only."""
import copy,unittest
from types import SimpleNamespace
from app import mcp_builder as b,studio,fresh
from app.core import compatibility,digest
from app.workflow_contract import validate

class ValidatorFixes(unittest.TestCase):
 def setUp(self):
  self.marker=fresh.CTX.set({'token':'fmca_synthetic','user':{'id':'operator'},'client':{'id':'bunting'},'company':{'id':'company','code':'BMC','name':'BMC'},'role':'editor'})
  self.session=b.Session(SimpleNamespace(),{'document':{}})
 def tearDown(self):fresh.CTX.reset(self.marker)
 def resource(self,name,content):
  pin='schema:bunting.'+name+'@1.0.0'
  self.session.add_resource({'ref':pin,'id':name,'kind':'schema','version':'1.0.0','content':content,'approved':True})
  return pin
 def graph(self,left,right):
  def node(id,pin):
   return {'id':id,'data':{'guided':{'id':'draft-'+id,'name':id,'responsibility':'Synthetic fixture','capability':'MAP','fields':{k:{'value':v,'source':'model'} for k,v in {'input.schema':pin,'output.schema':pin,'output.record_type':'document.read','output.outcomes':'completed_only'}.items()}}}}
  return {'id':'synthetic-canvas','nodes':[node('parser',left),node('converter',right)],'edges':[{'id':'mail-1','source':'parser','target':'converter','sourceHandle':'COMPLETED','data':{}}]}
 def test_identical_complex_schema_is_compatible_but_different_still_fails_closed(self):
  shape={'type':'object','properties':{'optional':{'anyOf':[{'type':'string'},{'type':'null'}]}},'required':[]}
  self.assertTrue(compatibility(shape,copy.deepcopy(shape)))
  changed=copy.deepcopy(shape);changed['required']=['optional']
  self.assertFalse(compatibility(shape,changed))
 def test_both_graph_paths_accept_same_hash(self):
  pin=self.resource('parse',{'type':'object','properties':{'freeform':{}},'required':[]});w=self.graph(pin,pin)
  self.session.graph(w)
  self.assertFalse(any(f['rule_id']=='incompatible-connection' for f in validate(self.session,w)['findings']))
 def test_record_collision_is_on_output_node_not_edge(self):
  pin=self.resource('parse',{'type':'object'});other=self.resource('json',{'type':'object','required':['value'],'properties':{'value':{'type':'string'}}});w=self.graph(pin,pin)
  w['nodes'][1]['data']['guided']['fields']['output.schema']['value']=other
  report=validate(self.session,w);conflict=next(f for f in report['findings'] if f['rule_id']=='record-type-schema-conflict')
  self.assertEqual(conflict['node_id'],'converter');self.assertEqual(conflict['field_paths'],['output.record_type']);self.assertEqual(conflict['source_schema']['id'],pin);self.assertEqual(conflict['target_schema']['id'],other)
  self.assertFalse(any(f['rule_id']=='incompatible-connection' for f in report['findings']))
  w['nodes'][1]['data']['guided']['fields']['output.record_type']['value']='document.classified'
  self.assertFalse(any(f['rule_id'] in ('incompatible-connection','record-type-schema-conflict') for f in validate(self.session,w)['findings']))
 def test_all_protected_fields_returned_together(self):
  with self.assertRaises(b.BuilderError) as raised:self.session.fields({'execute.authority':'P2','execute.model_access':'sonnet','verify.approval_gate':'single_approver'},capability='WRITE')
  self.assertEqual({f['field_path'] for f in raised.exception.error['locked_fields']},{'execute.authority','execute.model_access','verify.approval_gate'})
 def test_reason_approval_none_matches_catalog_and_validation(self):
  fields=self.session.fields({'verify.approval_gate':'none'},capability='REASON')
  self.assertEqual(fields['verify.approval_gate']['value'],'none')
  self.assertFalse(any(x['id']=='human-verify.approval_gate' for x in studio.blockers('REASON',fields,self.session.catalog())))
  for cap in ('COMMS','WRITE'):
   with self.assertRaises(b.BuilderError):self.session.fields({'verify.approval_gate':'none'},capability=cap)
 def test_matching_identity_accepted_but_spoof_denied(self):
  fields=self.session.fields({'identity.owner':'operator','identity.environment':'TEST'},capability='READ')
  self.assertEqual(fields['identity.owner']['source'],'verified_identity');self.assertEqual(fields['identity.environment']['source'],'server')
  with self.assertRaises(b.BuilderError):self.session.fields({'identity.owner':'someone-else'},capability='READ')
  with self.assertRaises(b.BuilderError):self.session.fields({'identity.environment':'PROD'},capability='READ')
 def test_pending_revision_and_caller_keys_in_schema_error(self):
  left=self.resource('left',{'type':'object'});right=self.resource('right',{'type':'object','required':['x'],'properties':{'x':{'type':'string'}}});w=self.graph(left,right)
  proposed=copy.deepcopy(w['nodes'][1]['data']['guided']);proposed['fields']['input.schema']['value']=left
  self.session.touch('agents',proposed['id'],proposed)
  with self.assertRaises(b.BuilderError) as raised:self.session.graph(w,caller_keys={'parser':'caller-parser','converter':'caller-converter'})
  error=raised.exception.error;self.assertEqual(error['edge_id'],'mail-1');self.assertEqual(error['source_key'],'caller-parser');self.assertEqual(error['target_key'],'caller-converter');self.assertEqual(error['source_schema']['id'],left)
  self.assertEqual(error['pending_proposals'][0]['draft_id'],proposed['id']);self.assertTrue(error['pending_proposals'][0]['differs_from_canvas'])
  report=validate(self.session,w);mismatch=next(f for f in report['findings'] if f['rule_id']=='incompatible-connection')
  self.assertEqual(mismatch['target_schema']['id'],right);self.assertEqual(len(report['pending_proposals']),1)
 def test_existing_human_choice_preserves_provenance(self):
  old={'execute.model_access':{'value':'sonnet','source':'user','why':'Human confirmed'}}
  fields=self.session.fields({'execute.model_access':'sonnet'},old,'REASON');self.assertEqual(fields['execute.model_access'],old['execute.model_access'])
