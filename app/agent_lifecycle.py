"""Recoverable agent archives, recorded in the existing client audit history."""
from fastapi import APIRouter
from . import fresh,studio
from .core import Invalid
router=APIRouter(prefix='/api/studio')
def archived_ids(audit):
 states={}
 for row in sorted(audit,key=lambda x:x.get('created_at','')):
  if row.get('action') in ('agent.archived','agent.restored'):
   states[row.get('payload',{}).get('agent_id')]=row['action']=='agent.archived'
 return {id for id,value in states.items() if value}
@router.post('/agent-lifecycle')
async def control(b:dict):
 c=fresh.CTX.get()
 if not c or c['role']!='owner':raise Invalid('Administrator permission required')
 id=b.get('id');studio.store.ident(id)
 action=b.get('action')
 if action not in ('archive','restore'):raise Invalid('Choose archive or restore')
 agents=[a for a in await studio.store.records('agents') if a['id']==id]
 if not agents:raise Invalid('Saved agent not found')
 from .governance import check
 await check('agent:'+id,'edit')
 if action=='archive':
  if any(a.get('guided',{}).get('runtime_binding') for a in agents):raise Invalid('Installed runtime agents must remain available')
  active=await fresh.rest(studio.store,'GET','flux_runtime_workflows?select=definition&client_id=eq.'+c['client']['id']+'&state=eq.active')
  if any(s.get('agent_id')==id for w in active for s in w['definition'].get('steps',[])):raise Invalid('Hold the workflow before archiving an active agent')
 return await studio.store.event('agent.archived' if action=='archive' else 'agent.restored',{'agent_id':id,'action':action,'recoverable':True})
