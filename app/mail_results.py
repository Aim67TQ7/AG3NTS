"""Authenticated client-scoped access to saved production email agent artifacts."""
import json,re
from fastapi import APIRouter
from fastapi.responses import Response
from . import fresh,studio
from .core import Invalid
router=APIRouter(prefix='/api/mail-results')
async def rpc(action,args):
 return await fresh.rest(studio.store,'POST','rpc/flux_mail_results',{'action':action,'args':{**args,'client_id':fresh.CTX.get()['client']['id']}})
@router.get('')
async def results(stage:str='',message_id:str='',attachment_only:bool=False,before:str='',before_time:str='',origin:str='canvas_runtime',agent_id:str=''):
 if stage not in ('','capture','parse','json'):raise Invalid('Unknown email agent stage')
 data=await rpc('list',{'stage':stage,'message_id':message_id[:250],'attachment_only':attachment_only,'before':before,'before_time':before_time,'origin':origin,'agent_id':agent_id})
 rows=data.get('items',[]);data['items']=rows[:50];data['next_cursor']={'before':rows[49]['id'],'before_time':rows[49]['occurred_at']} if len(rows)>50 else None
 return data
@router.get('/{artifact_id}')
async def artifact(artifact_id:str,download:bool=False):
 if not re.fullmatch('[a-f0-9]{64}',artifact_id):raise Invalid('Invalid artifact ID')
 data=await rpc('get',{'id':artifact_id})
 if download:return Response(json.dumps(data,indent=2,ensure_ascii=False),media_type='application/json',headers={'Content-Disposition':'attachment; filename="flux-'+data['stage']+'-'+artifact_id[:16]+'.json"','Cache-Control':'no-store'})
 return data
