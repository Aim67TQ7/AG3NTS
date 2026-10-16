"""Immutable human decisions and feedback over client-scoped runtime evidence."""
import asyncio
from . import fresh,studio
from .core import Invalid,digest
LOCK=asyncio.Lock()

def evidence(row):
 return digest({k:row.get(k) for k in ('id','workflow_id','input','definition','result','finished_at')})
def review_path(row):return 'runtime-reviews/'+row['id']+'-'+evidence(row)+'.json'
async def queue(show_tests=False,offset=0):
 if offset<0 or offset>100000:raise Invalid('Invalid review page')
 c=fresh.CTX.get();s=studio.store
 rows=await fresh.rest(s,'GET','flux_runtime_jobs?select=id,workflow_id,status,test_run,created_at,finished_at,input,definition,result&status=eq.review_required&client_id=eq.'+c['client']['id']+'&order=created_at.desc,id.desc&limit=50&offset='+str(offset))
 decisions={(r['run_id'],r['evidence_hash']) for r in await s.records('runtime-reviews')};items=[]
 for row in rows:
  if (row['id'],evidence(row)) in decisions:continue
  if not show_tests and (row.get('test_run') or row.get('definition',{}).get('synthetic')):continue
  result=row.get('result') or {};steps=row.get('definition',{}).get('steps',[]);idx=result.get('step')
  target=steps[idx] if type(idx) is int and 0<=idx<len(steps) else {}
  items.append({'key':'runtime:'+row['id'],'kind':'runtime','runtime':True,'workflow_id':row['workflow_id'],'agent_id':target.get('agent_id'),'agent_name':target.get('name') or result.get('agent') or row['workflow_id'],'summary':'This run needs a human decision.','reasons':result.get('reasons') or [result.get('reason') or 'Review the input and result.'],'input':row.get('input',{}),'output':result.get('output'),'technical':{'run_id':row['id'],'result':result,'package_hash':target.get('package_hash'),'build_id':target.get('build_id')},'created_at':row['created_at'],'evidence_hash':evidence(row)})
 return {'items':items,'next_offset':offset+50 if len(rows)==50 else None,'can_review':c['role'] in ('owner','editor'),'scope':'Human decisions only; agents do not resume automatically.'}

async def decision(body):
 c=fresh.CTX.get();s=studio.store
 if c['role'] not in ('owner','editor'):raise Invalid('Admin or builder permission required to review')
 choice=body.get('decision');reason=body.get('reason','')
 if choice not in ('approve','reject','feedback','escalate'):raise Invalid('Unknown review decision')
 if not isinstance(reason,str) or not 1<=len(reason.strip())<=4000:raise Invalid('Describe the review decision in 1–4000 characters')
 key=body.get('key','')
 if not isinstance(key,str) or not key.startswith('runtime:'):raise Invalid('Choose a runtime review')
 run_id=key.removeprefix('runtime:');s.ident(run_id)
 async with LOCK:
  rows=await fresh.rest(s,'GET','flux_runtime_jobs?select=id,workflow_id,status,test_run,created_at,finished_at,input,definition,result&id=eq.'+run_id+'&client_id=eq.'+c['client']['id'])
  if not rows or rows[0]['status']!='review_required':raise Invalid('Run is unavailable or no longer needs review')
  row=rows[0];sha=evidence(row)
  if body.get('evidence_hash')!=sha:raise Invalid('Evidence changed; reload before reviewing')
  if await s.get(review_path(row)):raise Invalid('This evidence already has a decision; reload the queue')
  steps=row.get('definition',{}).get('steps',[]);idx=(row.get('result') or {}).get('step');target=steps[idx] if type(idx) is int and 0<=idx<len(steps) else {}
  receipt={'id':s.uid(),'record_type':'agent.review_feedback','client_id':c['client']['id'],'run_id':run_id,'workflow_id':row['workflow_id'],'evidence_hash':sha,'decision':choice,'reason':reason.strip(),'reviewer':c['user']['id'],'created_at':s.now(),'target_agent_id':target.get('agent_id'),'target_agent_name':target.get('name'),'build_id':target.get('build_id'),'package_hash':target.get('package_hash'),'delivery_status':'recorded_for_agent_review' if choice in ('feedback','reject') else 'review_recorded','auto_resume':False,'external_actions_authorized':False}
  receipt['content_hash']=digest(receipt)
  await s.event('runtime.review.requested',{'run_id':run_id,'evidence_hash':sha,'decision':choice,'receipt_hash':receipt['content_hash']})
  # The immutable object identity also prevents concurrent duplicate decisions.
  await s.put(review_path(row),receipt)
  await s.event('runtime.review.recorded',{'run_id':run_id,'workflow_id':row['workflow_id'],'decision':choice,'receipt_hash':receipt['content_hash'],'evidence_hash':sha,'auto_resume':False})
  return receipt
