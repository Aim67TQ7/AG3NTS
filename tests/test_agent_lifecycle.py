import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from app import agent_lifecycle as life,fresh
from app.core import Invalid
class LifecycleTests(unittest.IsolatedAsyncioTestCase):
 def test_archive_applies_to_every_version_and_restore_wins(self):
  rows=[{'action':'agent.restored','created_at':'2','payload':{'agent_id':'a'}},{'action':'agent.archived','created_at':'1','payload':{'agent_id':'a'}},{'action':'agent.archived','created_at':'3','payload':{'agent_id':'b'}}]
  self.assertEqual(life.archived_ids(rows),{'b'})
 async def test_nonowner_cannot_archive(self):
  marker=fresh.CTX.set({'role':'editor'})
  try:
   with self.assertRaises(Invalid):await life.control({'id':'a','action':'archive'})
  finally:fresh.CTX.reset(marker)
 async def test_installed_and_active_agents_are_protected(self):
  marker=fresh.CTX.set({'role':'owner','client':{'id':'synthetic'}})
  try:
   for binding,active in [({'kind':'canvas_mail'},[]),(None,[{'definition':{'steps':[{'agent_id':'a'}]}}])]:
    store=SimpleNamespace(ident=lambda x:x,records=AsyncMock(return_value=[{'id':'a','guided':{'runtime_binding':binding}}]),event=AsyncMock())
    with patch.object(life.studio,'store',store),patch('app.governance.check',AsyncMock()),patch.object(fresh,'rest',AsyncMock(return_value=active)):
     with self.assertRaises(Invalid):await life.control({'id':'a','action':'archive'})
     store.event.assert_not_called()
  finally:fresh.CTX.reset(marker)
 async def test_draft_archive_is_audited_and_recoverable(self):
  marker=fresh.CTX.set({'role':'owner','client':{'id':'synthetic'}})
  store=SimpleNamespace(ident=lambda x:x,records=AsyncMock(return_value=[{'id':'a','guided':{}}]),event=AsyncMock())
  try:
   with patch.object(life.studio,'store',store),patch('app.governance.check',AsyncMock()),patch.object(fresh,'rest',AsyncMock(return_value=[])):
    await life.control({'id':'a','action':'archive'});await life.control({'id':'a','action':'restore'})
    self.assertEqual([c.args[0] for c in store.event.await_args_list],['agent.archived','agent.restored'])
    self.assertTrue(all(c.args[1]['recoverable'] for c in store.event.await_args_list))
  finally:fresh.CTX.reset(marker)
