"""Curated Operis registry and authoritative binding validation; no raw schema browser."""
import os,re,copy
from fastapi import APIRouter
from jsonschema import Draft202012Validator
from . import studio,fresh
from .core import Invalid,digest,compatibility
from .planner import SCOPE
router=APIRouter(prefix='/api/studio/records')
OUTCOMES={'COMPLETED','NO_ACTION','REVIEW_REQUIRED','REJECTED','FAILED_FINAL','OUTCOME_UNKNOWN'}
def scope():
 from . import fresh
 if fresh.enabled():return fresh.scope()
 # Existing private operator boundary. Public installations require explicit tenant membership.
 if os.environ.get('STUDIO_PUBLIC_HOST'):
  from .library import context
  tenant,_,_=context()
  if tenant!=os.environ.get('STUDIO_RECORD_TENANT_ID',SCOPE['tenant']):raise Invalid('Record scope is not configured for this tenant')
 return dict(SCOPE)
def admin():
 scope()
 if fresh.enabled():
  if fresh.CTX.get()['role']!='owner':raise Invalid('Registry administrator permission required')
  return
 allowed=os.environ.get('STUDIO_RECORD_ADMINS','ssh-owner').split(',')
 if studio.store.ACTOR.get() not in allowed:raise Invalid('Registry administrator permission required')
async def rest(method,table,params=None,body=None):
 if fresh.enabled():raise Invalid('Operational record storage is not connected for this workspace; use Operis Monitor for runtime inputs and results')
 if table not in ('studio_record_types','studio_records'):raise Invalid('Unregistered table')
 s=studio.store
 r=await s.CLIENT.request(method,s.BASE+'/rest/v1/'+table,headers={**s.HEAD,'Prefer':'return=representation'},params=params,json=body)
 if r.status_code not in (200,201,204):raise Invalid('Operis record registry unavailable: '+str(r.status_code))
 return r.json() if r.content else []
def scoped():return {k:'eq.'+v for k,v in scope().items()}
async def registry():
 if fresh.enabled() and not fresh.CTX.get().get('company'):return {'items':[],'scope':{'tenant':fresh.CTX.get()['client']['id']},'admin':fresh.CTX.get()['role']=='owner','runtime_enabled':False,'blocker':'Select a company before managing record types'}
 current=scope()
 if fresh.enabled():
  rows=[r for r in await studio.store.records('record-types') if all(r.get(k)==v for k,v in current.items())]
  latest={}
  for r in rows:
   if r['revision']>latest.get(r['name'],{}).get('revision',0):latest[r['name']]=r
  return {'items':sorted(latest.values(),key=lambda r:(r['kind'],r['name'])),'scope':current,'admin':fresh.CTX.get()['role']=='owner','runtime_enabled':False}
 rows=await rest('GET','studio_record_types',{**scoped(),'order':'kind.asc,name.asc','limit':'200'})
 return {'items':rows,'scope':current,'admin':studio.store.ACTOR.get() in os.environ.get('STUDIO_RECORD_ADMINS','ssh-owner').split(','),'runtime_enabled':False}
@router.get('')
async def listing():return await registry()
@router.post('/registry')
async def save_registry(b:dict):
 admin();name=b.get('name','')
 if not re.fullmatch(r'[a-z][a-z0-9_.]{1,79}',name):raise Invalid('Use a short lowercase record name')
 rows=(await registry())['items'];old=next((r for r in rows if r['name']==name),None)
 if old and b.get('expected_hash')!=old['content_hash']:raise Invalid('Registry changed; reload before saving')
 kind=b.get('kind','handoff');statuses=b.get('statuses',[])
 if old and old['kind']!=kind:raise Invalid('Record kinds cannot be changed')
 if kind not in ('handoff','source') or not isinstance(statuses,list) or not statuses or len(set(statuses))!=len(statuses) or any(not isinstance(x,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,49}',x) for x in statuses):raise Invalid('Choose valid distinct statuses')
 if kind=='source':
  # Sources are deployment-curated, never a caller-selected raw table or arbitrary URL.
  if not old or old['kind']!='source' or b.get('source_ref',old['source_ref'])!=old['source_ref']:raise Invalid('Source adapters are managed by deployment configuration')
  if b.get('approval_statuses'):raise Invalid('Sources cannot issue approvals')
 terminals=b.get('terminal_statuses',[]);approvals=b.get('approval_statuses',[])
 if not all(isinstance(values,list) and all(isinstance(v,str) for v in values) for values in (terminals,approvals)):raise Invalid('Choose valid terminal and approval statuses')
 if not set(terminals+approvals)<=set(statuses):raise Invalid('Terminal and approval statuses must belong to this record type')
 row={**scope(),'name':name,'kind':kind,'statuses':statuses,'terminal_statuses':terminals,'approval_statuses':approvals,'input_schema_ref':b.get('input_schema_ref'),'output_schema_ref':b.get('output_schema_ref'),'description':str(b.get('description',''))[:1000],'owner':str(b.get('owner',''))[:160],'source_ref':old.get('source_ref') if old else None,'revision':old['revision']+1 if old else 1,'published':bool(b.get('published',False))}
 if not row['owner']:raise Invalid('Record owner is required')
 if row['published']:
  schemas=await published_schemas()
  if row['input_schema_ref'] not in schemas or row['output_schema_ref'] not in schemas:raise Invalid('Publication requires approved input and output schemas')
  if not compatibility(schemas[row['output_schema_ref']],schemas[row['input_schema_ref']]):raise Invalid('Published record formats are incompatible')
 row['content_hash']=digest(row)
 await studio.store.event('record_registry.save_requested',{'name':name,'definition_hash':row['content_hash'],**scope()})
 if fresh.enabled():
  # Unique revision paths provide atomic conflict detection without mutable registry rows.
  path='record-types/'+digest(scope())[:20]+'--'+name+'--'+str(row['revision']).zfill(8)+'.json'
  try:saved=[await studio.store.put(path,row)]
  except ValueError:raise Invalid('Registry changed while saving; reload before trying again')
 else:saved=await rest('PATCH' if old else 'POST','studio_record_types',{**scoped(),'name':'eq.'+name,'content_hash':'eq.'+old['content_hash']} if old else None,row)
 if not saved:raise Invalid('Registry changed while saving')
 await studio.store.event('record_registry.saved',{'name':name,'definition_hash':row['content_hash'],**scope()})
 return saved[0]
async def published_schemas():
 from .library import active_resources
 resources=await active_resources(await studio.store.records('resources'));audit=await studio.store.records('audit');approved={a['payload'].get('resource_ref') for a in audit if a['action']=='resource.published'}
 return {'schema:'+r['id']+'@'+r['version']:r['content'] for r in resources if r['kind']=='schema' and 'schema:'+r['id']+'@'+r['version'] in approved}
async def validate_canvas(w):
 rows=(await registry())['items'];return validate(w,rows,await published_schemas())
def validate(w,rows,schemas):
 by={r['name']:r for r in rows};nodes=w.get('nodes',[]);errors=[];writers={};readers={};missing=0
 def err(n,msg):errors.append({'node_id':n.get('id'),'message':msg,'group':'record_bindings'})
 def resolve(n,b,direction):
  r=by.get(b.get('record_type'))
  if not r:err(n,'Choose a registered '+direction+' record');return None
  if b.get('registry_hash')!=r['content_hash']:err(n,'Record registry changed; rebind '+r['name'])
  if not r.get('published'):err(n,r['name']+' is a draft record type')
  return r
 for n in nodes:
  g=n.get('data',{}).get('guided',{});cap=g.get('capability',n.get('data',{}).get('capability'));bindings=g.get('bindings',{})
  if n.get('data',{}).get('deployed'):err(n,'Deployed references belong in monitoring')
  if g.get('fields',{}).get('identity.environment',{}).get('value')!='TEST':err(n,'Build certification is TEST-only')
  if g.get('fields',{}).get('identity.company',{}).get('value')!=(scope()['company'] if fresh.enabled() else 'BMC'):err(n,'Record bindings require the server-authorized company scope')
  read=bindings.get('reads',{});r=resolve(n,read,'input')
  if r:
   if r['kind']=='source' and cap!='READ':err(n,'Only READ cards may bind a read-only Source')
   if read.get('status') not in r['statuses']:err(n,'Unknown input status')
   readers.setdefault((r['name'],read.get('status')),[]).append(n)
   ref=g.get('fields',{}).get('input.schema',{}).get('value');rs=r.get('input_schema_ref')
   if (ref not in schemas or rs not in schemas or not compatibility(schemas[rs],schemas[ref])):err(n,'Input record format is unverified')
  write=bindings.get('writes',{});rout=resolve(n,write,'output')
  if rout:
   if rout['kind']!='handoff':err(n,'Read-only Sources cannot be write targets')
   statuses=write.get('outcomes',{})
   if not statuses or 'COMPLETED' not in statuses:err(n,'Choose an output status for COMPLETED')
   expected=studio.CATALOG['outcomes'].get(g.get('fields',{}).get('output.outcomes',{}).get('value'),['COMPLETED'])
   for o in expected:
    if o not in statuses:err(n,'Choose an output status for '+o)
   for outcome,status in statuses.items():
    if outcome not in OUTCOMES or status not in rout['statuses']:err(n,'Unknown output outcome or status');continue
    writers.setdefault((rout['name'],status),[]).append((n,outcome))
    if status in rout.get('approval_statuses',[]) and (cap!='COMMS' or g.get('fields',{}).get('verify.approval_gate',{}).get('value') not in ('single_approver','two_approvers') or outcome!='COMPLETED'):err(n,'Approval status requires a human approval COMMS step on COMPLETED')
   ref=g.get('fields',{}).get('output.schema',{}).get('value');rs=rout.get('output_schema_ref')
   if ref not in schemas or rs not in schemas or not compatibility(schemas[ref],schemas[rs]):err(n,'Output record format is unverified')
  if cap=='WRITE':
   if not r or r['kind']!='handoff' or read.get('status') not in r.get('approval_statuses',[]):err(n,'WRITE must read an approved handoff status')
   if g.get('fields',{}).get('verify.approval_gate',{}).get('value') not in ('single_approver','two_approvers'):err(n,'Writer approval cannot be disabled')
 for key,ns in readers.items():
  r=by[key[0]];ws=writers.get(key,[])
  for n in ns:
   if r['kind']=='handoff' and not any(p['id']!=n['id'] for p,_ in ws):missing+=1;err(n,'No upstream writer for '+':'.join(key))
   if n['data'].get('capability')=='WRITE' and any(p['data'].get('capability')!='COMMS' or o!='COMPLETED' or p['data']['guided'].get('fields',{}).get('verify.approval_gate',{}).get('value') not in ('single_approver','two_approvers') for p,o in ws):err(n,'Every producer of this approval status must be an approval step')
 for key,ws in writers.items():
  r=by[key[0]]
  for n,o in ws:
   if key[1] not in r.get('terminal_statuses',[]) and not any(p['id']!=n['id'] for p in readers.get(key,[])):missing+=1;err(n,'Output status has no reader or terminal declaration: '+':'.join(key))
 if not nodes:errors.append({'message':'Canvas is empty'})
 return {'valid':not errors,'blockers':errors,'missing_handoffs':missing,'scope':'Registry and binding validation; no activation'}
@router.get('/rows')
async def rows(record_type:str,status:str='',offset:int=0):
 if fresh.enabled():return {'items':[],'scope':scope(),'runtime_enabled':False,'note':'This workspace has no operational handoff adapter. Runtime inputs and results are available in Operis Monitor.'}
 types=(await registry())['items'];r=next((x for x in types if x['name']==record_type and x['kind']=='handoff'),None)
 if not r or offset<0 or (status and status not in r['statuses']):raise Invalid('Unknown handoff query')
 p={**scoped(),'record_type':'eq.'+record_type,'order':'created_at.desc','limit':'25','offset':str(offset)}
 if status:p['status']='eq.'+status
 return {'items':await rest('GET','studio_records',p),'scope':scope()}

class RecordStore:
 """Host-side TEST store; immutable inserts, scoped reads, no arbitrary-source API."""
 def __init__(self,context_factory,approval_verifier=None,approval_result_verifier=None):self.context_factory=context_factory;self.approval_verifier=approval_verifier;self.approval_result_verifier=approval_result_verifier
 async def record_type(self,name,s):
  if s!=scope():raise Invalid('Runtime scope mismatch')
  return next((x for x in (await registry())['items'] if x['name']==name),None)
 async def schema(self,ref):
  s=(await published_schemas()).get(ref)
  if not s:raise Invalid('Published schema is unavailable')
  return s
 async def poll(self,name,status,s,environment,cursor,limit):
  if s!=scope() or environment!='TEST':raise Invalid('Runtime scope mismatch')
  p={**scoped(),'environment':'eq.TEST','record_type':'eq.'+name,'status':'eq.'+status,'order':'created_at.asc,id.asc','limit':str(limit)}
  if cursor:
   # Cursor is host-produced; validate before inserting into PostgREST filter grammar.
   import uuid
   from datetime import datetime
   uuid.UUID(cursor['id']);datetime.fromisoformat(cursor['created_at'].replace('Z','+00:00'))
   if any(c in cursor['created_at'] for c in ',()'):raise Invalid('Invalid cursor')
   p['or']='(created_at.gt.'+cursor['created_at']+',and(created_at.eq.'+cursor['created_at']+',id.gt.'+cursor['id']+'))'
  return await rest('GET','studio_records',p)
 async def verify_approval(self,row,config):return bool(self.approval_verifier and await self.approval_verifier(row,config))
 async def verify_approval_result(self,result,config):return bool(self.approval_result_verifier and await self.approval_result_verifier(result,config))
 async def context_for(self,ctx,config):return await self.context_factory(config)
 async def append(self,row):
  if {k:row.get(k) for k in scope()}!=scope() or row.get('environment')!='TEST':raise Invalid('Runtime output scope mismatch')
  old=await rest('GET','studio_records',{**scoped(),'environment':'eq.TEST','idempotency_key':'eq.'+row['idempotency_key'],'limit':'1'})
  if old:
   if any(old[0].get(k)!=v for k,v in row.items()):raise Invalid('Handoff idempotency conflict')
   return old[0]
  await studio.store.event('record.append_requested',{'key':row['idempotency_key'],'payload_hash':digest(row),**scope()})
  result=await rest('POST','studio_records',body=row)
  await studio.store.event('record.appended',{'id':result[0]['id'],'payload_hash':digest(row),**scope()})
  return result[0]
