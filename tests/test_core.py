import copy, unittest
from app.core import execute,test_agent,compatibility,validate_workflow,validate_agent,Invalid

def agent():
 s={'type':'object','properties':{'name':{'type':'string'}},'required':['name'],'additionalProperties':False}
 return {'id':'name-mapper','name':'Name mapper','version':'0.1.0','responsibility':'Map supplied name','capability':'MAP','input_schema':s,'output_schema':s,'instructions':'Map only','functions':{k:'Defined' for k in ('trigger','input','execute','output','error','verify')},'execution':{'kind':'map','fields':{'name':'name'}},'tests':[{'input':{'name':'Synthetic'},'expected':{'name':'Synthetic'}},{'input':{},'expect_error':True}],'status':'published'}
class Tests(unittest.TestCase):
 def test_execution(self):self.assertEqual(execute(agent(),{'name':'Synthetic'}),{'name':'Synthetic'})
 def test_tests(self):self.assertTrue(test_agent(agent())['passed'])
 def test_failed_test(self):
  a=agent();a['tests'][0]['expected']={'name':'Wrong'};self.assertFalse(test_agent(a)['passed'])
 def test_no_authority_escalation(self):
  a=agent();a['authority']='P5'
  with self.assertRaises(Invalid):validate_agent(a)
 def test_no_model(self):
  a=agent();a['model_access']=True
  with self.assertRaises(Invalid):validate_agent(a)
 def test_no_arbitrary_code(self):
  a=agent();a['execution']['kind']='python'
  with self.assertRaises(Invalid):validate_agent(a)
 def test_compatibility(self):
  a=agent();self.assertTrue(compatibility(a['output_schema'],a['input_schema']))
 def test_nullable_compatibility(self):
  nullable={'type':['string','null']};self.assertTrue(compatibility({'type':'string'},nullable));self.assertTrue(compatibility(nullable,nullable));self.assertFalse(compatibility(nullable,{'type':'string'}))
 def test_contract_mismatch(self):
  a=agent();s=copy.deepcopy(a['input_schema']);s['properties']['name']['type']='number';self.assertFalse(compatibility(a['output_schema'],s))
 def test_unproven_constraint(self):
  a=agent();s=copy.deepcopy(a['input_schema']);s['properties']['name']['pattern']='^A';self.assertFalse(compatibility(a['output_schema'],s))
 def test_workflow(self):
  a=agent();w={'nodes':[{'id':'one','agent_ref':'a'},{'id':'two','agent_ref':'a'}],'edges':[{'source':'one','target':'two'}]};self.assertEqual(validate_workflow(w,{'a':a}),[])
 def test_cycle(self):
  a=agent();w={'nodes':[{'id':'one','agent_ref':'a'},{'id':'two','agent_ref':'a'}],'edges':[{'source':'one','target':'two'},{'source':'two','target':'one'}]};self.assertIn('Cycle detected',validate_workflow(w,{'a':a}))
 def test_draft_blocked(self):
  a=agent();a['status']='draft';w={'nodes':[{'id':'one','agent_ref':'a'}],'edges':[]};self.assertTrue(validate_workflow(w,{'a':a}))
if __name__=='__main__':unittest.main()
