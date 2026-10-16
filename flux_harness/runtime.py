import asyncio,json,time,hashlib,uuid
from dataclasses import dataclass,field
from datetime import datetime,timezone
from jsonschema import Draft202012Validator

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
@dataclass
class Result:
 status:str
 output:object=None
 reasons:list=field(default_factory=list)
 evidence:list=field(default_factory=list)

class Context:
 """Tool allowlist is fixed by the host, not generated Python or model text."""
 def __init__(self,capability,scope,environment='TEST',adapters=None,cost_ceiling=0,approval_check=None):
  self.capability=capability;self.scope=dict(scope);self.environment=environment;self.__adapters=adapters or {};self.__approval=approval_check;self.cost_ceiling=cost_ceiling;self.cost=0.;self.tokens_in=0;self.tokens_out=0;self.evidence=[];self.usage=[];self.input_hash=None;self.definition_hash=None;self.external_started=False
 def attach_evidence(self,reference):self.evidence.append(reference)
 async def operation(self,name,request):
  allowed={'MAP':{'map'},'RULE':{'rule'},'CLASS':{'jev_classify'},'DOC':{'parse_document'},'READ':{'flux_read','graph_read','epicor_read'},'ROUTE':{'route'},'REASON':{'model_call'},'COMMS':{'draft_message'},'WRITE':{'epicor_write'}}
  if name not in allowed.get(self.capability,set()):raise PermissionError('Tool is not permitted for this capability')
  if name=='epicor_write':
   if self.environment!='TEST' or not self.__approval:raise PermissionError('Verified, input-bound approval required for TEST write')
   decision=await self.__approval(self.input_hash,self.definition_hash,request,self.scope)
   if not isinstance(decision,dict) or decision.get('decision')!='approve' or decision.get('input_hash')!=self.input_hash or decision.get('definition_hash')!=self.definition_hash or decision.get('proposal_hash')!=digest(request) or decision.get('scope')!=self.scope or decision.get('environment')!='TEST' or not decision.get('reviewer_id') or decision.get('expires_at',0)<=time.time():raise PermissionError('Approval does not bind this input, proposal, revision and scope')
   self.external_started=True
  adapter=self.__adapters.get(name)
  if not adapter:raise LookupError('Approved adapter unavailable: '+name)
  reserve=None
  if name in ('model_call','jev_classify','parse_document'):
   reserve=min(float(request.get('_cost_reserve',self.cost_ceiling-self.cost)),self.cost_ceiling-self.cost)
   if reserve<=0:raise PermissionError('Model operation has no remaining budget')
   self.cost+=reserve;self.usage.append({'usage_complete':False,'reserved_usd':reserve,'operation':name})
   request={**request,'max_cost_usd':reserve}
  response=await adapter(request,dict(self.scope),self.environment)
  if name=='epicor_write':
   receipt=response.get('read_back_receipt') if isinstance(response,dict) else None
   if not receipt or not receipt.get('verified') or receipt.get('scope')!=self.scope or not receipt.get('target_id'):raise RuntimeError('External write has no verified read-back receipt')
   self.attach_evidence(receipt)
   return response['output']
  if reserve is not None:
   usage=response.get('usage',{});cost=usage.get('cost_usd')
   if cost is None or cost>reserve or 'input_tokens' not in usage or 'output_tokens' not in usage:raise RuntimeError('Model usage is unknown or exceeded its reserve')
   self.usage[-1].update(usage_complete=True,cost_usd=cost,input_tokens=usage['input_tokens'],output_tokens=usage['output_tokens'])
   self.cost-=reserve-cost;self.tokens_in+=usage.get('input_tokens',0);self.tokens_out+=usage.get('output_tokens',0)
   return response['output']
  return response
 async def model_call(self,request,max_cost):
  if max_cost<=0 or self.cost+max_cost>self.cost_ceiling:raise PermissionError('Model call exceeds budget')
  return await self.operation('model_call',{**request,'_cost_reserve':max_cost})

async def run_job(input,ctx,spec):
 """Approved structured job specs; no generated eval, exec, shell or arbitrary imports."""
 if spec.get('runtime_review'):return Result('REVIEW_REQUIRED',reasons=['Interview question deferred to human review'])
 kind=spec.get('kind')
 if kind=='map':
  output={};missing=[]
  for target,source in spec.get('fields',{}).items():
   value=input
   for part in source.split('.'):
    if not isinstance(value,dict) or part not in value:missing.append(source);value=None;break
    value=value[part]
   output[target]=value
  return Result('REVIEW_REQUIRED' if missing else 'COMPLETED',output,['Missing '+x for x in missing])
 if kind=='rule':
  if not spec.get('approved_rule_ref'):return Result('REVIEW_REQUIRED',reasons=['Approved rule resource is missing'])
  checks=[]
  for rule in spec.get('checks',[]):
   actual=input.get(rule['field']);op=rule['op'];expected=rule.get('value')
   if op=='equals':ok=actual==expected
   elif op=='present':ok=actual is not None
   else:raise ValueError('Unsupported approved rule operator')
   checks.append({'field':rule['field'],'passed':ok})
  if not checks:return Result('REVIEW_REQUIRED',reasons=['No approved checks supplied'])
  return Result('COMPLETED' if all(x['passed'] for x in checks) else 'REVIEW_REQUIRED',{'passed':all(x['passed'] for x in checks),'checks':checks})
 if kind=='route':
  target=spec.get('routes',{}).get(input.get(spec.get('field')))
  return Result('COMPLETED' if target else 'REVIEW_REQUIRED',{'route':target},[] if target else ['No approved route matched'])
 if kind=='adapter':
  try:
   output=await ctx.operation(spec['operation'],{'input':input,'procedure_ref':spec.get('procedure_ref'),'config':spec.get('parameters',{})})
   return Result('REVIEW_REQUIRED' if isinstance(output,dict) and output.get('requires_review') else 'COMPLETED',output,output.get('review_reasons',[]) if isinstance(output,dict) else [])
  except LookupError:return Result('REVIEW_REQUIRED',reasons=['Approved runtime adapter is unavailable'])
 return Result('REVIEW_REQUIRED',reasons=['Job logic is not approved or implemented'])

class Harness:
 VERSION='1.0.0'
 def __init__(self,store):self.store=store
 async def invoke(self,agent,input,config,ctx,key):
  if not key or not all(c.isalnum() or c in '-_' for c in key):raise ValueError('Invalid idempotency key')
  if ctx.environment!='TEST':raise PermissionError('PROD runtime is not enabled')
  if ctx.scope!=config['scope'] or ctx.capability!=config['capability']:raise PermissionError('Context scope/capability mismatch')
  ih=digest(input);dh=digest(config);prior=await self.store.get('harness-results/'+key+'.json')
  if prior:
   if prior['input_hash']!=ih or prior['definition_hash']!=dh:raise ValueError('Idempotency conflict')
   return prior
  intent=await self.store.get('harness-intents/'+key+'.json')
  if intent and (intent['input_hash']!=ih or intent['definition_hash']!=dh):raise ValueError('Intent conflict')
  if intent and ctx.capability=='WRITE':return {'result_status':'OUTCOME_UNKNOWN','reasons':['Existing write intent requires reconciliation'],'input_hash':ih,'definition_hash':dh,**ctx.scope}
  validation_error=None
  try:Draft202012Validator(config['input_schema']).validate(input)
  except Exception:validation_error='Input does not match the approved schema'
  if not intent:await self.store.put('harness-intents/'+key+'.json',{'input_hash':ih,'definition_hash':dh,'environment':'TEST','capability':ctx.capability,**ctx.scope})
  ctx.input_hash=ih;ctx.definition_hash=dh;start=time.monotonic();attempts=[];result=None
  limit=min(3,max(1,int(config.get('max_attempts',1))))
  if validation_error:result=Result('REVIEW_REQUIRED',reasons=[validation_error]);attempts.append({'attempt':1,'status':'REVIEW_REQUIRED','stage':'input_validation'})
  for attempt in range(0 if validation_error else limit):
   try:
    result=await asyncio.wait_for(agent(input,ctx),timeout=min(120,float(config.get('timeout_seconds',30))))
    if result.status not in ('COMPLETED','REVIEW_REQUIRED','REJECTED','FAILED_FINAL','OUTCOME_UNKNOWN'):raise ValueError('Invalid Result status')
    if result.status=='COMPLETED':Draft202012Validator(config['output_schema']).validate(result.output)
    attempts.append({'attempt':attempt+1,'status':result.status});break
   except PermissionError:
    result=Result('REVIEW_REQUIRED',reasons=['Required authority or approval is unavailable']);attempts.append({'attempt':attempt+1,'status':result.status});break
   except Exception as e:
    attempts.append({'attempt':attempt+1,'error_type':type(e).__name__})
    if ctx.external_started:result=Result('OUTCOME_UNKNOWN',reasons=['External result is uncertain; reconcile before retry']);break
    if attempt+1==limit:result=Result('FAILED_FINAL',reasons=['Execution or output validation failed'])
  row={'record_id':key,'result_status':result.status,'input':input,'output':result.output,'reasons':result.reasons,'evidence':result.evidence+ctx.evidence,'input_hash':ih,'definition_hash':dh,'created_at':datetime.now(timezone.utc).isoformat(),'duration_ms':int((time.monotonic()-start)*1000),'attempts':attempts,'input_tokens':ctx.tokens_in,'output_tokens':ctx.tokens_out,'model_cost_usd':ctx.cost if all(x['usage_complete'] for x in ctx.usage) else None,'usage_complete':all(x['usage_complete'] for x in ctx.usage),'budget_reserved_usd':ctx.cost,'provider_usage':ctx.usage,'runtime':'flux_harness-'+self.VERSION,'test_run':bool(config.get('test_run',False)),'environment':'TEST','human_review_required':result.status in ('REVIEW_REQUIRED','OUTCOME_UNKNOWN'),**ctx.scope}
  row['content_hash']=digest(row)
  return await self.store.put('harness-results/'+key+'.json',row)
