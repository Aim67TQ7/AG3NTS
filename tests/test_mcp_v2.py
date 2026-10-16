import copy,json,unittest
from types import SimpleNamespace
from app import fresh,mcp_builder as b,mcp_v2 as v,studio
from app.rule_language import validate,evaluate
from app.sample_sandbox import check
from app.core import digest
class Rules(unittest.TestCase):
 def test_line_match_percentage_and_date(self):
  rules=[{'op':'for_each','path':'ack','baseline_path':'po','match_by':'line','checks':[{'op':'equals_field','field':'quantity','baseline_field':'quantity'},{'op':'percent_tolerance','field':'price','baseline_field':'price','percent':2},{'op':'date_within_days','field':'date','baseline_field':'date','days':1}]}]
  doc={'ack':[{'line':2,'quantity':3,'price':10.1,'date':'2026-10-17'}],'po':[{'line':1,'quantity':8,'price':5,'date':'2026-10-01'},{'line':2,'quantity':3,'price':10,'date':'2026-10-16'}]}
  self.assertTrue(all(x['passed'] for x in evaluate(doc,validate(rules))))
  doc['po'].append(doc['po'][1]);self.assertFalse(all(x['passed'] for x in evaluate(doc,rules)))
 def test_missing_and_malformed_data_fail_closed(self):
  for percent in (-1,float('nan'),True):
   with self.assertRaises(ValueError):validate([{'op':'percent_tolerance','field':'x','baseline_field':'y','percent':percent}])
  self.assertFalse(evaluate({'x':'bad','y':'2026-10-16'},[{'op':'date_within_days','field':'x','baseline_field':'y','days':1}])[0]['passed'])
 def test_required_field_has_property_path(self):
  result=check({'schema':{'type':'object','required':['po_number']},'rules':[],'samples':[{'name':'Missing PO','document':{},'expected':{'schema_valid':False}}]})
  self.assertEqual(result['results'][0]['schema_errors'],[{'field_path':'po_number','constraint':'required'}])
class Proposals(unittest.TestCase):
 def setUp(self):
  self.marker=fresh.CTX.set({'token':'fmca_synthetic','user':{'id':'operator'},'client':{'id':'tenant'},'company':{'id':'company','code':'BMC','name':'BMC'},'role':'owner'})
  self.s=b.Session(SimpleNamespace(now=lambda:'2026-10-16T00:00:00Z'),{'document':{}})
 def tearDown(self):fresh.CTX.reset(self.marker)
 def test_protected_choices_proposed_and_still_block_publish(self):
  fields=self.s.fields({'execute.authority':'P2','execute.model_access':'sonnet','verify.approval_gate':'none'},capability='REASON')
  self.assertEqual(fields['execute.authority']['source'],'proposed');self.assertEqual(fields['execute.model_access']['source'],'proposed');self.assertEqual(fields['verify.approval_gate']['source'],'model')
  self.assertTrue(any(x['id'].startswith('human-') for x in studio.blockers('REASON',fields,self.s.catalog())))
 def test_current_draft_resolution_preserves_saved_snapshot_and_hash(self):
  g={'id':'agent','name':'A','capability':'MAP','fields':{'output.next':{'value':'none'}}};w={'id':'canvas','nodes':[{'id':'node','data':{'guided':g}}],'edges':[]};r=self.s.touch('workflows','canvas',w)
  updated=copy.deepcopy(g);updated['fields']['output.next']['value']='chain_to_next_node';self.s.touch('agents','agent',updated)
  resolved=v.latest_workflow(self.s,r)
  self.assertEqual(resolved['body']['nodes'][0]['data']['guided'],updated);self.assertEqual(r['body'],w);self.assertEqual(r['content_hash'],digest(w))
 def test_summary_drops_editor_history_and_why(self):
  g={'id':'agent','fields':{'x':{'value':'yes','why':'a'*10000}},'user_edits':['secret history']};result=v.summary_agent(g)
  self.assertEqual(result['fields'],{'x':'yes'});self.assertNotIn('user_edits',result);self.assertLess(len(json.dumps(result)),300)
 def test_proposals_readable_by_their_own_ids(self):
  r=self.s.touch('resources','instructions:tenant.example@1.0.0',{'content':'fixture'})
  kind,found=v.find_proposal(self.s,r['proposal_id']);self.assertEqual(kind,'resources');self.assertEqual(found['id'],r['id'])
 def test_credential_types_publish_names_only(self):
  self.assertIn('password',v.SECRET_KINDS['epicor_rest_basic'][0]);self.assertNotIn('secret',json.dumps(v.COMPLETENESS))
