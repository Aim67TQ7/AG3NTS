import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from app import email_template as et,workflow_json as wj,studio,fresh
from app.core import Invalid
class EmailTemplateTests(unittest.IsolatedAsyncioTestCase):
 def test_only_mailbox_changes_between_template_instances(self):
  a=et.workflow_definition('one@example.invalid');b=et.workflow_definition('two@example.invalid')
  self.assertEqual((len(a['workflow']['steps']),len(a['workflow']['connections'])),(3,2))
  self.assertTrue(wj.validate(a)['valid'])
  self.assertNotIn('runtime_binding',json.dumps(a));self.assertNotIn('api_key',json.dumps(a))
  a['workflow']['name']=b['workflow']['name']
  for key in ('input_config','trigger_config'):
   a['workflow']['steps'][0]['configuration'][key]=b['workflow']['steps'][0]['configuration'][key]
  self.assertEqual(a,b)
 def test_invalid_mailboxes_rejected(self):
  for mailbox in ('','missing-at','one@example.invalid/extra','a b@example.invalid',None,'a'*255+'@example.invalid'):
   with self.subTest(mailbox=mailbox),self.assertRaises(Invalid):et.workflow_definition(mailbox)
 async def test_new_workflows_get_fresh_ids_test_scope_and_no_credential_selections(self):
  marker=fresh.CTX.set({'role':'owner','client':{'id':'synthetic'},'user':{'id':'owner'},'company':{'code':'SYNTHETIC'}})
  async def save(canvas):return {**copy.deepcopy(canvas),'execution_enabled':False}
  try:
   with patch.object(studio,'store',SimpleNamespace(event=AsyncMock())),patch.object(studio,'catalog',AsyncMock(return_value=studio.CATALOG)),patch.object(studio,'save_canvas',save):
    a=await et.use_template({'mailbox':'one@example.invalid'});b=await et.use_template({'mailbox':'two@example.invalid'})
   self.assertNotEqual(a['workflow']['id'],b['workflow']['id'])
   self.assertFalse(a['workflow']['execution_enabled']);self.assertEqual(a['workflow']['name'],'Email to JSON · one@example.invalid')
   for n in a['workflow']['nodes']:
    g=n['data']['guided'];self.assertEqual(g['fields']['identity.environment']['value'],'TEST');self.assertEqual(g['reusable_resources'],[]);self.assertNotIn('runtime_binding',g)
  finally:fresh.CTX.reset(marker)
 async def test_regular_user_cannot_create_a_template_workflow(self):
  marker=fresh.CTX.set({'role':'user'})
  try:
   with self.assertRaises(Invalid):await et.use_template({'mailbox':'one@example.invalid'})
  finally:fresh.CTX.reset(marker)

class EmailRetrieverTests(unittest.IsolatedAsyncioTestCase):
 def test_exactly_one_capture_agent(self):
  p=et.definition('one@example.invalid')
  self.assertEqual(len(p['workflow']['steps']),1)
  self.assertEqual(p['workflow']['connections'],[])
  step=p['workflow']['steps'][0]
  self.assertEqual(step['capability'],'READ')
  self.assertEqual(step['functions']['execute']['method'],'system_read')
  self.assertEqual(step['functions']['output']['next'],'none')
  self.assertEqual(step['configuration']['input_config']['mailbox'],'one@example.invalid')
  self.assertTrue(wj.validate(p)['valid'])
 async def test_saves_one_agent_without_workflow_or_permissions(self):
  marker=fresh.CTX.set({'role':'owner','client':{'id':'synthetic'},'user':{'id':'owner'},'company':{'code':'SYNTHETIC'}})
  try:
   store=SimpleNamespace(event=AsyncMock(),records=AsyncMock(return_value=[]),now=lambda:'test',ACTOR=SimpleNamespace(get=lambda:'owner'),ident=lambda x:x,put=AsyncMock(side_effect=lambda path,a:a))
   with patch.object(studio,'store',store),patch.object(studio,'catalog',AsyncMock(return_value={**studio.CATALOG,'snapshot_hash':'synthetic'})),patch.object(fresh,'enabled',return_value=False),patch.object(studio,'save_canvas',AsyncMock()) as canvas:
    a=await et.use_agent_template({'mailbox':'one@example.invalid'})
    b=await et.use_agent_template({'mailbox':'two@example.invalid'})
   self.assertNotEqual(a['agent']['id'],b['agent']['id'])
   self.assertEqual(store.put.await_count,2)
   self.assertTrue(all(c.args[0].startswith('agents/') for c in store.put.await_args_list))
   canvas.assert_not_awaited()
   g=a['agent']['guided']
   self.assertEqual(g['reusable_resources'],[])
   self.assertEqual(g['fields']['identity.environment']['value'],'TEST')
   self.assertNotIn('runtime_binding',g)
   self.assertFalse(a['agent']['execution']['dispatch_enabled'])
  finally:fresh.CTX.reset(marker)
 async def test_user_cannot_create(self):
  marker=fresh.CTX.set({'role':'user'})
  try:
   with self.assertRaises(Invalid):await et.use_agent_template({'mailbox':'one@example.invalid'})
  finally:fresh.CTX.reset(marker)
