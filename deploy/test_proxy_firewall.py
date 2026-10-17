import importlib.util,pathlib,unittest,copy
p=pathlib.Path(__file__).with_name('operis-proxy-firewall-sync.py')
spec=importlib.util.spec_from_file_location('proxy_firewall',p);fw=importlib.util.module_from_spec(spec);spec.loader.exec_module(fw)
class ProxyFirewallTests(unittest.TestCase):
 def test_accepts_only_expected_proxy_identity_and_private_network(self):
  proxy={'Name':'/hub-caddy','State':{'Running':True},'Config':{'Image':'lucaslorentz/caddy-docker-proxy:ci-alpine'},'NetworkSettings':{'Networks':{'hub-net':{'IPAddress':'172.18.0.11','Gateway':'172.18.0.1'}}}}
  self.assertEqual(fw.proxy_address(proxy),'172.18.0.11')
  for update in ('name','image','network','stopped'):
   bad=copy.deepcopy(proxy)
   if update=='name':bad['Name']='/other'
   if update=='image':bad['Config']['Image']='other'
   if update=='network':bad['NetworkSettings']['Networks']['hub-net']['IPAddress']='8.8.8.8'
   if update=='stopped':bad['State']['Running']=False
   with self.subTest(update=update),self.assertRaises(ValueError):fw.proxy_address(bad)
 def test_only_exact_managed_rules_can_be_removed(self):
  text='Status: active\n172.18.0.1 8498/tcp ALLOW IN 172.18.0.3 # FLUX Studio Caddy only\n172.18.0.1 8498/tcp ALLOW IN 172.18.0.11 # Operis Studio Caddy only\n172.18.0.1 8498/tcp ALLOW IN 172.18.0.4 # Another policy\n8421 ALLOW IN 172.18.0.0/16 # News\n'
  self.assertEqual(fw.managed_sources(text),{'172.18.0.3','172.18.0.11'})
  self.assertEqual(fw.managed_sources(text.replace('ALLOW IN', 'ALLOW')),{'172.18.0.3','172.18.0.11'})
  with self.assertRaises(ValueError):fw.managed_sources('Status: inactive')
