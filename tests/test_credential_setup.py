import unittest,json
from app.credential_setup import normalize
from app.core import Invalid
class SetupTests(unittest.TestCase):
 def epicor(self):return {'connection_type':'epicor','base_url':'https://epicor.example.invalid/Test/','company_code':'TEST','api_key':'synthetic-api-key','username':'synthetic-user','password':'synthetic-password','allowed_paths':'/api/v2/odata/TEST/ApprovedSvc/'}
 def test_epicor_preserves_secret_and_does_not_claim_tested(self):
  c=self.epicor();r=json.loads(normalize(json.dumps(c)));self.assertFalse(r['connection_verified']);self.assertEqual(r['password'],c['password']);self.assertEqual(r['base_url'],'https://epicor.example.invalid/Test')
 def test_epicor_requires_each_part_and_scoped_paths(self):
  for key in ('base_url','company_code','api_key','username','password','allowed_paths'):
   c=self.epicor();c.pop(key)
   with self.subTest(key=key),self.assertRaises(Invalid):normalize(json.dumps(c))
  for path in ('https://other.invalid','/','/api/*','/api/../admin'):
   with self.subTest(path=path),self.assertRaises(Invalid):normalize(json.dumps({**self.epicor(),'allowed_paths':path}))
 def test_url_cannot_contain_password_or_query(self):
  for url in ('http://epicor.example.invalid','https://user:password@epicor.example.invalid','https://epicor.example.invalid?key=secret'):
   with self.subTest(url=url),self.assertRaises(Invalid):normalize(json.dumps({**self.epicor(),'base_url':url}))
 def test_other_auth_methods_and_legacy_key(self):
  for method,fields in [('basic',{'username':'u','password':'p'}),('api_key',{'api_key':'k'}),('bearer',{'access_token':'t'}),('oauth_client_credentials',{'client_id':'id','client_secret':'secret','token_url':'https://auth.example.invalid/token'})]:
   c={'connection_type':'custom','url':'https://api.example.invalid','auth_method':method,**fields};self.assertFalse(json.loads(normalize(json.dumps(c)))['connection_verified'])
  self.assertEqual(normalize('legacy-synthetic-key'),'legacy-synthetic-key')
