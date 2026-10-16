import unittest,os
from types import SimpleNamespace
from unittest.mock import patch
from app import deployment_settings
from app.core import Invalid
class SettingsTests(unittest.IsolatedAsyncioTestCase):
 async def test_explicit_owner_only_and_other_deployment_denied(self):
  async def get(path):
   self.assertEqual(path,'deployment-settings/pete-https.json')
   return {'deployment':'pete-https','tenant':'bunting-magnetics','members':{'PETE owner':'owner'}}
  with patch.dict(os.environ,{'STUDIO_PUBLIC_HOST':'flux.by-pete.com','STUDIO_DEPLOYMENT_ID':'pete-https'}):
   await deployment_settings.load(SimpleNamespace(get=get,ident=lambda s:s))
   self.assertEqual(os.environ['STUDIO_RECORD_ADMINS'],'PETE owner')
   self.assertNotIn('ssh-owner',os.environ['STUDIO_TENANT_MEMBERS'])
  async def wrong(path):return {'deployment':'other'}
  with patch.dict(os.environ,{'STUDIO_PUBLIC_HOST':'flux.by-pete.com','STUDIO_DEPLOYMENT_ID':'pete-https'}):
   with self.assertRaises(Invalid):await deployment_settings.load(SimpleNamespace(get=wrong,ident=lambda s:s))
