"""Authoritative access settings; secret values never cross this API."""
from fastapi import APIRouter
from . import fresh,studio
from .core import Invalid
router=APIRouter(prefix='/api/governance')
async def rpc(action,args=None):
 c=fresh.CTX.get()
 if not fresh.enabled() or not c:raise Invalid('Client sign-in required')
 return await fresh.rest(studio.store,'POST','rpc/flux_governance',{'action':action,'args':{**(args or {}),'client':c['client']['id']}})
@router.get('/object')
async def get_object(key:str):return await rpc('get',{'key':key})
@router.post('/object')
async def set_object(b:dict):return await rpc('set',b)
@router.get('/audit')
async def audit(run_id:str):return await rpc('events',{'run_id':run_id})
@router.get('/members')
async def members():return await rpc('members')
@router.get('/companies')
async def companies():return await rpc('companies')
@router.post('/companies')
async def company_set(b:dict):return await rpc('company_set',b)
async def check(key,op):
 if fresh.enabled():
  result=await rpc('check',{'key':key,'op':op})
  if not result.get('allowed'):raise Invalid('You do not have permission to '+op+' this saved item')

def envelope(action,payload,actor,extra=None):
 c=fresh.CTX.get() or {};company=c.get('company') or {};g=payload.get('guided') or {};fields=g.get('fields') or {};agent_ref=payload.get('agent_ref','')
 return {'audit_schema_version':'2.0','client_id':(c.get('client') or {}).get('id'),'company_id':company.get('id'),'company_code':company.get('code'),'environment':fields.get('identity.environment',{}).get('value','TEST'),'actor_id':(c.get('user') or {}).get('id',actor),'actor_kind':'user' if c.get('user') else 'service','initiated_by':(c.get('user') or {}).get('id'),'accountable_owner':fields.get('identity.owner',{}).get('value'),'agent_id':payload.get('agent_id') or g.get('id') or(agent_ref.split('@')[0] if agent_ref else None),'agent_version':g.get('version') or(agent_ref.split('@')[1] if '@' in agent_ref else None),'agent_hash':payload.get('guided_hash') or payload.get('definition_hash') if payload.get('agent_id') or agent_ref or g else None,'workflow_id':payload.get('workflow_id') or payload.get('canvas_id'),'workflow_version':payload.get('workflow_version'),'run_id':payload.get('run_id') or payload.get('job_id'),'approved_by':payload.get('reviewer') if 'review' in action or 'approved' in action else None,'credential_refs':payload.get('credential_refs',[])}
