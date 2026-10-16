import unittest
from app.canvas import validate

def node(id,cap,gate='none'):
 return {'id':id,'data':{'capability':cap,'guided':{'fields':{'verify.approval_gate':{'value':gate},'identity.environment':{'value':'TEST'},'output.record_type':{'value':'review.decision' if cap=='COMMS' and gate!='none' else 'none'}}}}}
def edge(s,t,handle='COMPLETED'):return {'source':s,'target':t,'sourceHandle':handle,'data':{'compatible':True}}
class Tests(unittest.TestCase):
 def test_writer_missing_approval_rejected(self):
  r=validate({'nodes':[node('r','READ'),node('w','WRITE','single_approver')],'edges':[edge('r','w')]});self.assertFalse(r['valid']);self.assertTrue(any('human approval' in e['message'] for e in r['blockers']))
 def test_approval_chain_accepted(self):self.assertTrue(validate({'nodes':[node('a','COMMS','single_approver'),node('w','WRITE','single_approver')],'edges':[edge('a','w')]})['valid'])
 def test_review_cannot_continue_normal_processing(self):
  r=validate({'nodes':[node('d','DOC'),node('r','READ')],'edges':[edge('d','r','REVIEW_REQUIRED')]});self.assertFalse(r['valid']);self.assertTrue(any('must stop' in e['message'] for e in r['blockers']))
 def test_missing_edge_and_cycle(self):
  self.assertFalse(validate({'nodes':[node('a','MAP'),node('b','RULE')],'edges':[]})['valid']);self.assertFalse(validate({'nodes':[node('a','MAP'),node('b','RULE')],'edges':[edge('a','b'),edge('b','a')]})['valid'])
