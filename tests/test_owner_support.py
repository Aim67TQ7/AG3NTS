import copy,unittest
from app.owner_support import corrected
from app.core import Invalid,digest
class OwnerSupportTests(unittest.TestCase):
 def setUp(self):
  self.body={'id':'a','name':'Original','responsibility':'Read one thing','version':'0.1.9','status':'draft','actor':'client-user','created_at':'old','tenant':'tenant-a','company':'A','execution_enabled':False,'guided':{'id':'a','name':'Original','responsibility':'Read one thing','version':'0.1.9','fields':{'identity.owner':{'value':'client-user'},'identity.company':{'value':'A'}}}}
 def test_new_version_preserves_owner_configuration_and_input(self):
  old=copy.deepcopy(self.body);new=corrected(self.body,{'name':'Clear name','responsibility':'Read one specific source'},'platform-owner','now')
  self.assertEqual(old,self.body);self.assertEqual(new['version'],'0.1.10');self.assertEqual(new['guided']['version'],'0.1.10');self.assertEqual(new['guided']['fields'],old['guided']['fields']);self.assertEqual(new['actor'],'platform-owner');self.assertFalse(new['execution_enabled']);self.assertEqual(new['guided_hash'],digest(new['guided']))
 def test_unknown_fields_cannot_change_authority_or_config(self):
  for key in ['fields','actor','tenant','execution_enabled','sharing','version','password']:
   with self.assertRaises(Invalid):corrected(self.body,{key:'anything'},'owner','now')
 def test_published_or_invalid_versions_rejected(self):
  for extra in [{'status':'published'},{'version':'bad'}]:
   with self.assertRaises(Invalid):corrected({**self.body,**extra},{'name':'New'},'owner','now')
 def test_empty_or_oversize_fields_rejected(self):
  for changes in [{'name':''},{'name':' '*10},{'name':'a'*161},{'responsibility':'a'*4001},{'name':False}]:
   with self.assertRaises(Invalid):corrected(self.body,changes,'owner','now')
 def test_workflow_nodes_unchanged(self):
  body={'id':'w','name':'Original','version':'0.0.1','status':'draft','nodes':[{'id':'a','data':{'guided':self.body}}],'edges':[],'execution_enabled':False}
  new=corrected(body,{'name':'Better title'},'owner','now');self.assertEqual(new['nodes'],body['nodes']);self.assertEqual(new['edges'],[]);self.assertIsNone(new['release_version'])
