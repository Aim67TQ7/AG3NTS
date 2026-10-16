"""Opt-in durable record polling. Host supplies certified registry/store/adapters.
No background task is started by importing this module or opening Studio.
"""
from .runtime import Harness,digest
from jsonschema import Draft202012Validator
class BoundRunner:
 def __init__(self,store,record_store):self.harness=Harness(store);self.records=record_store
 async def poll_once(self,agent,config,ctx,*,cursor=None,limit=25):
  if not config.get('activation_enabled') or config.get('test_run') or config.get('environment')!='TEST':raise PermissionError('A separately activated TEST package is required')
  if config['scope']!=ctx.scope:raise PermissionError('Tenant/company/facility mismatch')
  if not 1<=limit<=100:raise ValueError('Bounded page required')
  b=config.get('bindings',{});read=b.get('reads',{});write=b.get('writes',{})
  rin=await self.records.record_type(read.get('record_type'),ctx.scope);rout=await self.records.record_type(write.get('record_type'),ctx.scope)
  for binding,r in ((read,rin),(write,rout)):
   if not r or not r.get('published') or r.get('content_hash')!=binding.get('registry_hash'):raise PermissionError('Stale or unpublished registry binding')
  if rout['kind']!='handoff':raise PermissionError('Sources are never write targets')
  if rin['kind']=='source':
   if ctx.capability!='READ':raise PermissionError('Source bindings require READ')
   raise PermissionError('Source event ingestion requires its certified connector; no raw table polling')
  if read.get('status') not in rin['statuses'] or not write.get('outcomes') or any(v not in rout['statuses'] for v in write['outcomes'].values()):raise PermissionError('Invalid bound status')
  if ctx.capability=='WRITE' and read['status'] not in rin.get('approval_statuses',[]):raise PermissionError('WRITE input must be a registered approval status')
  rows=await self.records.poll(read['record_type'],read['status'],ctx.scope,'TEST',cursor,limit);out=[]
  for row in rows:
   if any(row.get(k)!=v for k,v in ctx.scope.items()) or row.get('environment')!='TEST' or row.get('record_type')!=read['record_type'] or row.get('status')!=read['status']:raise PermissionError('Polling returned an out-of-scope record')
   if row.get('registry_hash')!=read['registry_hash']:raise PermissionError('Input record uses a stale registry revision')
   if ctx.capability=='WRITE' and not await self.records.verify_approval(row,config):raise PermissionError('Approval producer/evidence is not certified')
   key='bound-'+digest({'input_record':row['id'],'definition':digest(config),'scope':ctx.scope})
   # A fresh Context is required for every record; the host constructs it with the same certified adapters.
   context=await self.records.context_for(ctx,config)
   context.attach_evidence({'input_record_id':row['id'],'registry_hash':row['registry_hash']})
   result=await self.harness.invoke(agent,row['payload'],config,context,key)
   status=write['outcomes'].get(result['result_status'])
   if not status:raise PermissionError('Result outcome has no bound destination; audited result retained')
   if status in rout.get('approval_statuses',[]) and (ctx.capability!='COMMS' or not await self.records.verify_approval_result(result,config)):raise PermissionError('Approval status requires a verified durable human decision')
   payload=result.get('output')
   if result['result_status']=='COMPLETED':Draft202012Validator(await self.records.schema(rout['output_schema_ref'])).validate(payload)
   published=await self.records.append({'record_type':rout['name'],'status':status,**ctx.scope,'environment':'TEST','payload':payload if payload is not None else {},'evidence':{'result_ref':key,'result_hash':result.get('content_hash'),'reasons':result.get('reasons',[]),'evidence':result.get('evidence',[])},'produced_by_agent':config['agent_ref'],'produced_by_run':key,'input_record_id':row['id'],'registry_hash':rout['content_hash'],'definition_hash':digest(config),'outcome':result['result_status'],'idempotency_key':key})
   out.append(published)
  return {'results':out,'next_cursor':{'created_at':rows[-1]['created_at'],'id':rows[-1]['id']} if len(rows)==limit else None}
