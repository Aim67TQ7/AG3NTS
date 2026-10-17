import asyncio,base64,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding,rsa
from app import credential_import as ci,fresh
from app.core import Invalid
class ImportBoundaryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
  (self.root/'key.pem').write_bytes(self.key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
  self.data={'client':'bunting','requested_by':'synthetic-owner','expires_at':time.time()+600,'batch':'synthetic-import','entries':[{'id':'vps-import-synthetic','label':'Synthetic','system':'key','secret':'synthetic-secret'}]}
  self.marker=fresh.CTX.set({'client':{'id':'bunting'},'role':'owner','user':{'id':'synthetic-owner'}})
  self.store_patch=patch.object(ci.studio,'store',SimpleNamespace(ident=lambda s:s));self.store_patch.start()
  self.root_patch=patch.object(ci,'ROOT',self.root);self.root_patch.start();self.stage()
 def tearDown(self):self.store_patch.stop();self.root_patch.stop();fresh.CTX.reset(self.marker);self.tmp.cleanup()
 def stage(self):
  key=Fernet.generate_key();encrypted=self.key.public_key().encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
  (self.root/'bundle.json').write_text(json.dumps({'key':base64.b64encode(encrypted).decode(),'payload':Fernet(key).encrypt(json.dumps(self.data).encode()).decode()}))
 def test_sealed_bundle_round_trip(self):
  self.assertEqual(ci.bundle()['entries'][0]['secret'],'synthetic-secret')
  self.assertNotIn('synthetic-secret',(self.root/'bundle.json').read_text())
  self.assertNotIn('synthetic-secret',json.dumps(asyncio.run(ci.preview())))
 def test_cross_client_and_nonowner_denied(self):
  for client,role in [('richmond','owner'),('bunting','editor'),('bunting','user')]:
   marker=fresh.CTX.set({'client':{'id':client},'role':role,'user':{'id':'synthetic-owner'}})
   try:
    with self.assertRaises(Invalid):ci.bundle()
   finally:fresh.CTX.reset(marker)
 def test_wrong_owner_expired_and_duplicate_entries_denied(self):
  for change in ({'requested_by':'another-owner'},{'expires_at':time.time()-1},{'entries':self.data['entries']*2}):
   original=dict(self.data);self.data.update(change);self.stage()
   with self.assertRaises(Invalid):ci.bundle()
   self.data=original
 def test_tampered_bundle_denied_without_payload_in_error(self):
  envelope=json.loads((self.root/'bundle.json').read_text());envelope['payload']='tampered';(self.root/'bundle.json').write_text(json.dumps(envelope))
  with self.assertRaisesRegex(Invalid,'No valid encrypted VPS import'):ci.bundle()

class ImportCompanyContextTests(unittest.IsolatedAsyncioTestCase):
 async def test_each_company_uses_own_context_and_restores_owner_on_failure(self):
  original={'client':{'id':'bunting'},'role':'owner','user':{'id':'synthetic-owner'},'company':{'id':'bmc-id','code':'BMC'}}
  marker=fresh.CTX.set(original)
  data={'batch':'synthetic','entries':[{'company':'MAI','id':'a'},{'company':'BME','id':'b'}]}
  seen=[]
  async def save(e,d):
   seen.append((fresh.CTX.get()['user']['id'],fresh.CTX.get()['company']['code']))
   if e['id']=='b':raise Invalid('synthetic failure')
   return {'id':'a'}
  try:
   with patch.object(ci,'bundle',return_value=data),patch.object(fresh,'rest',AsyncMock(return_value=[original['company'],{'id':'mai-id','code':'MAI'}])),patch.object(ci,'import_entry',save):
    with self.assertRaises(Invalid):await ci.consume({'batch':'synthetic'})
   self.assertEqual(seen,[('synthetic-owner','MAI'),('synthetic-owner','BMC')]);self.assertIs(fresh.CTX.get(),original)
  finally:fresh.CTX.reset(marker)
