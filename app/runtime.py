"""Durable TEST execution of pinned, reviewed job specs. No generated-code eval."""
import asyncio,copy,json,os,time,uuid,hashlib,socket,ipaddress
from pathlib import Path
from urllib.parse import urlparse,quote
import httpx
from fastapi import APIRouter
from . import fresh,studio
from .core import digest,compatibility,Invalid
from flux_harness import Harness,Context,run_job
router=APIRouter(prefix='/api/runtime')
WORKER_PATH=Path('/references/.flux-runtime/worker.json')
WORKER=None
ALLOWED={'MAP':'map','RULE':'rule','ROUTE':'route','READ':'adapter'}
def sample(client_id=None):
 a={'type':'object','properties':{'amount':{'type':'number'}},'required':['amount'],'additionalProperties':False}
 b={'type':'object','properties':{'total':{'type':'number'}},'required':['total'],'additionalProperties':False}
 c={'type':'object','properties':{'passed':{'type':'boolean'},'checks':{'type':'array'}},'required':['passed','checks'],'additionalProperties':False}
 configs=[]
 for cap,spec,ins,outs in [('MAP',{'kind':'map','fields':{'total':'amount'}},a,b),('RULE',{'kind':'rule','approved_rule_ref':'builtin:synthetic-total-present-v1','checks':[{'field':'total','op':'present'}]},b,c)]:
  configs.append({'capability':cap,'scope':{'tenant':(client_id or fresh.CTX.get()['client']['id']),'company':'SYNTHETIC','facility':'TEST'},'environment':'TEST','input_schema':ins,'output_schema':outs,'max_attempts':1,'timeout_seconds':30,'cost_ceiling_usd':0,'job_spec':spec,'test_run':True,'resource_refs':[]})
 return {'id':'synthetic-runtime-example','name':'Sample: Transform and check (synthetic)','synthetic':True,'steps':[{'id':'map','name':'Map amount to total','config':configs[0]},{'id':'check','name':'Check total is present','config':configs[1]}]}
def validate_config(config,synthetic=False):
 if config.get('environment')!='TEST':raise Invalid('This runner is TEST-only')
 cap=config.get('capability');spec=config.get('job_spec',{})
 if cap not in ALLOWED or spec.get('kind')!=ALLOWED[cap]:raise Invalid('No certified execution adapter for '+str(cap))
 if cap=='READ' and (spec.get('operation')!='epicor_read' or spec.get('parameters',{}).get('connection_type')!='epicor'):raise Invalid('READ runtime currently supports an explicitly configured Epicor JSON GET connection')
 if spec.get('runtime_review'):raise Invalid('Resolve deferred interview questions before activation')
 if not config.get('input_schema') or not config.get('output_schema'):raise Invalid('Input and output schemas are required')
 if cap=='RULE' and not spec.get('approved_rule_ref'):raise Invalid('Approved rule required')
 return config
async def compile_workflow(id):
 rows=[w for w in await studio.store.records('workflows') if w['id']==id]
 if not rows:raise Invalid('Save this canvas first')
 w=max(rows,key=lambda r:r.get('created_at',''));nodes=w.get('nodes',[])
 if not nodes or len(nodes)>30:raise Invalid('A workflow needs 1–30 built agents')
 builds=await studio.store.records('builds');sessions=await studio.store.records('teaching');steps=[]
 for node in nodes:
  g=node.get('data',{}).get('guided',{});matches=[b for b in builds if b.get('agent_id')==g.get('id') and b.get('config',{}).get('guided_hash')==digest(g)]
  if not matches:raise Invalid((g.get('name') or node['id'])+': Teach and build this exact card version first')
  build=max(matches,key=lambda b:b.get('source_revision',0));cfg=copy.deepcopy(build['config'])
  if build.get('package_hash')!=digest(build['files']) or build.get('status')!='tested' or not build.get('tests') or not all(t['passed'] for t in build['tests']):raise Invalid('Package hash or fixture tests are invalid')
  current=[s for s in sessions if s['id']==build['session']]
  latest=max(current,key=lambda s:s['revision']) if current else {}
  if not latest.get('readme_confirmed') or latest.get('readme_hash')!=build['package_hash']:raise Invalid(g['name']+': review and confirm this exact package README')
  if digest(latest.get('guided'))!=cfg['guided_hash'] or digest(latest.get('questions'))!=cfg['answer_hash'] or digest(latest.get('fixtures'))!=cfg['fixtures_hash']:raise Invalid('Interview changed; rebuild this agent')
  if cfg['scope']!=fresh.scope():raise Invalid('Build belongs to a different client/company scope')
  validate_config(cfg)
  for ref in g.get('reusable_resources',[]):
   from .library import lookup
   await lookup(ref)
   if ref['kind']=='credential':await fresh.verify_selection(studio.store,ref,g['id'])
  if cfg['capability']=='READ' and len(cfg.get('credential_bindings',[]))!=1:raise Invalid('Manually select exactly one Epicor connection for this READ agent')
  steps.append({'id':node['id'],'name':g['name'],'agent_id':g['id'],'agent_version':g['version'],'build_id':build['id'],'package_hash':build['package_hash'],'review_path':'teaching/'+latest['id']+'--'+str(latest['revision']).zfill(6)+'.json','config':cfg})
 # Derive a single chain from durable read/write bindings; never from visual positions.
 edges=[]
 if any(e.get('data',{}).get('direct') for e in w.get('edges',[])):raise Invalid('Direct communication needs a certified adapter; configure FLUX record bindings for this runner')
 for target in nodes:
  tg=target.get('data',{}).get('guided',{});read=tg.get('bindings',{}).get('reads',{}) or {'record_type':tg.get('fields',{}).get('trigger.source_record',{}).get('value'),'status':'completed'}
  for source in nodes:
   sg=source.get('data',{}).get('guided',{});write=sg.get('bindings',{}).get('writes',{}) or {'record_type':sg.get('fields',{}).get('output.record_type',{}).get('value'),'outcomes':{'COMPLETED':'completed'}}
   if source['id']!=target['id'] and read.get('record_type') and read['record_type']==write.get('record_type') and read.get('status')==write.get('outcomes',{}).get('COMPLETED'):edges.append((source['id'],target['id']))
 by={s['id']:s for s in steps};incoming={s['id']:[a for a,b in edges if b==s['id']] for s in steps};outgoing={s['id']:[b for a,b in edges if a==s['id']] for s in steps}
 roots=[i for i in by if not incoming[i]]
 if len(roots)!=1 or any(len(incoming[i])>1 or len(outgoing[i])>1 for i in by):raise Invalid('Configure one unambiguous FLUX handoff chain; branches/joins require a separate runtime contract')
 ordered=[];id=roots[0]
 while id not in {s['id'] for s in ordered}:
  ordered.append(by[id])
  if not outgoing[id]:break
  id=outgoing[id][0]
 if len(ordered)!=len(steps):raise Invalid('Workflow has an unconnected card or a cycle')
 if any(step['config']['capability']=='ROUTE' for step in ordered[:-1]):raise Invalid('Routing must be terminal; branch dispatch needs a separate execution contract')
 for a,b in zip(ordered,ordered[1:]):
  if not compatibility(a['config']['output_schema'],b['config']['input_schema']):raise Invalid('Adjacent input/output record formats are incompatible')
 return {'id':w['id'],'name':w['name'],'workflow_version':w['version'],'canvas_hash':digest(w),'synthetic':False,'steps':ordered}
@router.get('/status')
async def status():
 c=fresh.CTX.get();workflows=await fresh.rest(studio.store,'GET','flux_runtime_workflows?select=id,name,state,interval_seconds,updated_at&client_id=eq.'+c['client']['id']+'&order=updated_at.desc');jobs=await fresh.rest(studio.store,'GET','flux_runtime_jobs?select=id,workflow_id,status,test_run,created_at,finished_at,result&client_id=eq.'+c['client']['id']+'&order=created_at.desc&limit=30')
 events=await fresh.rest(studio.store,'GET','flux_runtime_events?select=id,action,actor,job_id,created_at&client_id=eq.'+c['client']['id']+'&order=created_at.desc&limit=40')
 health=await fresh.rest(studio.store,'POST','rpc/flux_runtime_health',{})
 result={**(health or {'worker_ready':False}),'events':events,'worker_provisioned':WORKER_PATH.exists(),'workflows':workflows,'runs':jobs,'role':c['role'],'supported':['MAP','RULE','ROUTE','READ: Epicor JSON GET'],'environment':'TEST'}
 from . import mail_runtime
 mail=await mail_runtime.status()
 if mail.get('configured'):result['workflows'].append({'id':mail['workflow_id'],'name':mail['definition']['name'],'state':'active' if mail.get('active') else 'paused','interval_seconds':5,'updated_at':mail.get('last_seen'),'environment':'PRODUCTION_READ_ONLY'})
 return result
async def control_rows():
 return await fresh.rest(studio.store,'POST','rpc/flux_agent_controls',{'client':fresh.CTX.get()['client']['id']})
def controls_allow(plan,controls):
 by={c['agent_id']:c for c in controls}
 return all(s.get('agent_id') not in by or (by[s['agent_id']]['enabled'] and by[s['agent_id']].get('guided_hash')==s['config'].get('guided_hash')) for s in plan['steps'])
@router.get('/agents/status')
async def agents_status():
 c=fresh.CTX.get();health=await fresh.rest(studio.store,'POST','rpc/flux_runtime_health',{})
 workflows=await fresh.rest(studio.store,'GET','flux_runtime_workflows?select=id,name,state,definition&client_id=eq.'+c['client']['id'])
 result={'role':c['role'],'worker_ready':bool((health or {}).get('worker_ready')),'controls':await control_rows(),'workflows':[{'id':w['id'],'name':w['name'],'state':w['state'],'agents':[{'id':s.get('agent_id'),'guided_hash':s['config'].get('guided_hash')} for s in w['definition']['steps'] if s.get('agent_id')]} for w in workflows]}
 from . import mail_runtime
 mail=await mail_runtime.status()
 if mail.get('configured'):
  result['mail_runtime']=mail;result['workflows'].append({'id':mail['workflow_id'],'name':mail['definition']['name'],'state':'active' if mail.get('active') else 'paused','environment':'PRODUCTION_READ_ONLY','worker_ready':mail.get('worker_ready'),'agents':[{'id':s['agent_id'],'guided_hash':s['guided_hash']} for s in mail['definition']['steps']]})
 return result
@router.post('/agents/power')
async def agent_power(b:dict):
 c=fresh.CTX.get()
 if c['role']!='owner':raise Invalid('Admin permission required to switch an agent on or off')
 agent=b.get('agent_id','');studio.store.ident(agent)
 from . import mail_runtime
 mail=await mail_runtime.status()
 if mail.get('configured') and any(s['agent_id']==agent for s in mail['definition']['steps']):
  await mail_runtime.power(b)
  return {'enabled':b['enabled'],'workflow_id':mail['workflow_id'],'note':'Canvas mail agent enabled.' if b['enabled'] else 'Off; the canvas mail pipeline is held.'}
 if not isinstance(b.get('enabled'),bool):raise Invalid('Choose on or off')
 controls=await control_rows();old=next((x for x in controls if x['agent_id']==agent),None)
 if b.get('expected_revision',0)!=(old or {}).get('revision',0):raise Invalid('Agent control changed; refresh before trying again')
 h=b.get('guided_hash');plan=None;workflow=None;ready_to_activate=True
 if b['enabled']:
  health=await fresh.rest(studio.store,'POST','rpc/flux_runtime_health',{})
  if not (health or {}).get('worker_ready'):raise Invalid('Runtime worker is unavailable; the agent remains off')
  rows=await studio.store.records('workflows');latest={}
  for w in rows:
   if w['id'] not in latest or w.get('created_at','')>latest[w['id']].get('created_at',''):latest[w['id']]=w
  candidates=[w for w in latest.values() if any(n.get('data',{}).get('guided',{}).get('id')==agent for n in w.get('nodes',[])) and (not b.get('workflow_id') or w['id']==b['workflow_id'])]
  matches=[n['data']['guided'] for w in candidates for n in w.get('nodes',[]) if n.get('data',{}).get('guided',{}).get('id')==agent and digest(n['data']['guided'])==h]
  if any(g.get('fields',{}).get('input.source_system',{}).get('value')=='outlook_graph' for g in matches):raise Invalid('Microsoft Graph email listener is not connected to this runtime; this agent remains off')
  if len(candidates)!=1:raise Invalid('Open the saved workflow containing this exact agent before switching it on')
  canvas=candidates[0];g=next(n['data']['guided'] for n in canvas['nodes'] if n.get('data',{}).get('guided',{}).get('id')==agent)
  if h!=digest(g):raise Invalid('Save this exact agent and canvas before switching it on')
  if g.get('fields',{}).get('input.source_system',{}).get('value')=='outlook_graph':raise Invalid('Microsoft Graph email listener is not connected to this runtime; this agent remains off')
  plan=await compile_workflow(canvas['id'])
  changed=[x for x in controls if x['agent_id']!=agent]+[{'agent_id':agent,'enabled':True,'guided_hash':h}]
  ready_to_activate=controls_allow(plan,changed)
  # Preserve the operator-selected schedule and input; no schedule or payload is invented.
  current=await fresh.rest(studio.store,'GET','flux_runtime_workflows?select=id,input,interval_seconds,definition&client_id=eq.'+c['client']['id']+'&id=eq.'+canvas['id'])
  if not current or current[0]['definition']!=plan:raise Invalid('Test this exact workflow version successfully in FLUX Monitor before switching it on')
  tests=await fresh.rest(studio.store,'GET','flux_runtime_jobs?select=id&client_id=eq.'+c['client']['id']+'&workflow_id=eq.'+canvas['id']+'&test_run=eq.true&status=eq.completed&limit=1')
  if not tests:raise Invalid('Complete a successful workflow test before switching this agent on')
  workflow=current[0]
 saved=await fresh.rest(studio.store,'POST','rpc/flux_agent_controls',{'client':c['client']['id'],'operation':'set','agent':agent,'enabled':b['enabled'],'guided_hash':h,'expected_revision':b.get('expected_revision',0)})
 if plan and ready_to_activate:
  try:await action({'workflow_id':workflow['id'],'action':'activate','input':workflow['input'],'interval_seconds':workflow['interval_seconds']})
  except Exception:
   await fresh.rest(studio.store,'POST','rpc/flux_agent_controls',{'client':c['client']['id'],'operation':'set','agent':agent,'enabled':False,'guided_hash':h,'expected_revision':saved['revision']})
   raise
 return {'enabled':b['enabled'],'workflow_id':workflow['id'] if workflow else None,'note':('Armed; turn on the remaining agents in this workflow.' if b['enabled'] and not ready_to_activate else 'Enabled in TEST runtime.' if b['enabled'] else 'Off; affected workflows are held. An in-flight request may finish.')}

@router.get('/inputs')
async def input_records(offset:int=0):
 if offset<0 or offset>100000:raise Invalid('Invalid input page')
 c=fresh.CTX.get()
 rows=await fresh.rest(studio.store,'GET','flux_runtime_jobs?select=id,workflow_id,status,test_run,created_at,input&client_id=eq.'+c['client']['id']+'&order=created_at.desc,id.desc&limit=25&offset='+str(offset))
 return {'items':rows,'next_offset':offset+25 if len(rows)==25 else None}
@router.get('/definition/{id}')
async def definition(id:str):
 studio.store.ident(id)
 plan=sample() if id=='synthetic-runtime-example' else await compile_workflow(id)
 return {'name':plan['name'],'input_schema':plan['steps'][0]['config']['input_schema'],'agents':[s['name'] for s in plan['steps']]}
@router.get('/runs/{id}')
async def run_details(id:str):
 studio.store.ident(id);rows=await fresh.rest(studio.store,'GET','flux_runtime_jobs?select=*&id=eq.'+id)
 if not rows:raise Invalid('Run unavailable in this client')
 steps=await fresh.rest(studio.store,'GET','flux_runtime_steps?select=step,result,created_at&job_id=eq.'+id+'&order=step')
 from .governance import rpc
 return {'run':rows[0],'steps':steps,'audit':await rpc('events',{'run_id':id})}
@router.post('/action')
async def action(b:dict):
 c=fresh.CTX.get()
 if c['role'] not in ('owner','editor'):raise Invalid('Builder permission required')
 if not WORKER_PATH.exists():raise Invalid('Runtime worker is not provisioned')
 op=b.get('action');id=b.get('workflow_id','');studio.store.ident(id)
 plan=None
 if op in ('test','activate'):plan=sample() if id=='synthetic-runtime-example' else await compile_workflow(id)
 if op=='activate' and not plan.get('synthetic') and not controls_allow(plan,await control_rows()):raise Invalid('An agent is switched off or its reviewed version changed; use the agent controls first')
 data=b.get('input',{})
 if not isinstance(data,dict) or len(json.dumps(data).encode())>250000:raise Invalid('Input must be a JSON object under 250 KB')
 response=await studio.store.CLIENT.post(fresh.URL+'/rest/v1/rpc/flux_runtime_action',headers=fresh.HEAD,json={'client':c['client']['id'],'workflow':id,'action':op,'definition':plan,'input':data,'request_id':b.get('request_id') or str(uuid.uuid4()),'interval_seconds':int(b.get('interval_seconds',0))})
 if response.status_code>=400:
  message=response.json().get('message','Runtime action failed')
  safe=['Test this exact workflow version successfully before activation','Activate before submitting work','Admin permission required','A run is in progress','Schedule must be 60 to 86400 seconds']
  raise Invalid(message if message in safe else 'Runtime action was rejected; check workflow state and permissions')
 return response.json()
class WorkerStore:
 def __init__(self,worker,job):self.worker=worker;self.job=job
 async def get(self,path):return await self.worker.rpc('get',self.job['id'],{'path':'runtime/'+self.job['id']+'/'+path})
 async def put(self,path,obj):return await self.worker.rpc('put',self.job['id'],{'path':'runtime/'+self.job['id']+'/'+path,'body':obj})
class Worker:
 def __init__(self,key):self.key=key;self.client=httpx.AsyncClient(timeout=30);self.stopping=False
 async def rpc(self,action,job=None,payload=None):
  r=await self.client.post(fresh.URL+'/rest/v1/rpc/flux_runtime_worker',headers={'apikey':fresh.KEY,'x-flux-worker':self.key},json={'action':action,'job':job,'payload':payload or {}})
  if r.status_code>=400:raise RuntimeError('Runtime database operation failed: '+str(r.status_code))
  return r.json()
 async def read_credential(self,job,step):
  refs=step['config'].get('credential_bindings',[])
  if len(refs)!=1:raise PermissionError('One manually selected credential is required')
  ref=refs[0];consent=await self.rpc('get',job['id'],{'path':'credential-selections/'+ref.get('selection_id','')+'.json'})
  if not consent or any(consent.get(k)!=v for k,v in {'client':job['client_id'],'selected_by':ref.get('selected_by',job['owner_id']),'agent_id':step['agent_id'],'resource_id':ref['id'],'resource_version':ref['version'],'resource_hash':ref['content_hash']}.items()):raise PermissionError('Credential selection is invalid')
  value=await self.rpc('credential',job['id'],{'path':'library-'+job['client_id']+'/'+ref['id']+'--'+ref['version']+'.json','hash':ref['content_hash']})
  return json.loads(value)
 async def epicor(self,job,step,request,scope,environment):
  credential=await self.read_credential(job,step);base=credential.get('base_url','');cfg=step['config']['job_spec'].get('parameters',{});path=cfg.get('path','')
  url=urlparse(base)
  if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or not path.startswith('/') or path.startswith('//') or '..' in path.split('/') or '://' in path:raise PermissionError('Approved HTTPS base URL and relative GET path are required')
  if credential.get('company_code')!=scope['company']:raise PermissionError('Epicor credential company differs from the agent company')
  addresses=await asyncio.to_thread(socket.getaddrinfo,url.hostname,url.port or 443,type=socket.SOCK_STREAM)
  if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise PermissionError('Private/internal hosts need a separately approved network adapter')
  prefixes=[p.strip() for p in credential.get('allowed_paths','').split(',') if p.strip()]
  if not prefixes or not any(path.startswith(p) for p in prefixes):raise PermissionError('GET path is outside the credential allowlist')
  if '/'+scope['company']+'/' not in (url.path.rstrip('/')+path+'/'):raise PermissionError('GET path does not bind the configured Epicor company')
  headers={'X-API-Key':credential['api_key'],'Accept':'application/json'}
  auth=httpx.BasicAuth(credential['username'],credential.get('password','')) if credential.get('username') else None
  async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
   async with client.stream('GET',base.rstrip('/')+path,headers=headers,auth=auth) as response:
    if response.status_code!=200:raise RuntimeError('Epicor GET was not successful')
    content=b''
    async for chunk in response.aiter_bytes():
     content+=chunk
     if len(content)>2000000:raise RuntimeError('Epicor response exceeds 2 MB')
  return json.loads(content)
 async def agent_gate(self,job,step):
  r=await self.client.post(fresh.URL+'/rest/v1/rpc/flux_runtime_agent_gate',headers={'apikey':fresh.KEY,'x-flux-worker':self.key},json={'job':job['id'],'agent':step['agent_id'],'guided_hash':step['config']['guided_hash']})
  if r.status_code>=400:raise PermissionError('Agent enable state could not be verified')
  return r.json() is True
 async def execute(self,job):
  plan=job['definition'];value=job['input'];store=WorkerStore(self,job)
  if plan.get('synthetic') and plan!=sample(job['client_id']):raise PermissionError('Unknown synthetic template')
  if not 1<=len(plan.get('steps',[]))<=30:raise ValueError('Invalid step count')
  for i,step in enumerate(plan['steps']):
   state=await self.rpc('state',job['id'])
   if state['state']!='running':return
   config=copy.deepcopy(validate_config(step['config'],plan.get('synthetic',False)))
   if config['scope']['tenant']!=job['client_id']:raise PermissionError('Cross-client config denied')
   if not plan.get('synthetic'):
    artifact=await self.rpc('get',job['id'],{'path':'builds/'+step['build_id']+'.json'})
    if not artifact or artifact.get('package_hash')!=step['package_hash'] or artifact['package_hash']!=digest(artifact['files']) or artifact['config']!=step['config']:raise PermissionError('Pinned package changed')
    if artifact.get('status')!='tested' or not artifact.get('tests') or not all(t['passed'] for t in artifact['tests']):raise PermissionError('Package fixtures are not approved')
    review=await self.rpc('get',job['id'],{'path':step.get('review_path','')})
    if not review or not review.get('readme_confirmed') or review.get('readme_hash')!=step['package_hash'] or digest(review['guided'])!=artifact['config']['guided_hash'] or digest(review['questions'])!=artifact['config']['answer_hash']:raise PermissionError('Package review no longer matches the build')
   if not job['test_run'] and not plan.get('synthetic') and not await self.agent_gate(job,step):return
   config['test_run']=job['test_run'];spec=config['job_spec']
   async def read_adapter(request,scope,environment):return await self.epicor(job,step,request,scope,environment)
   ctx=Context(config['capability'],config['scope'],adapters={'epicor_read':read_adapter},cost_ceiling=0)
   async def agent(input,ctx):return await run_job(input,ctx,spec)
   result=await Harness(store).invoke(agent,value,config,ctx,'step-'+str(i))
   await self.rpc('step',job['id'],{'step':i,'result':{'agent':step['name'],'agent_id':step.get('agent_id'),'agent_version':step.get('agent_version'),'agent_hash':config.get('guided_hash'),'client_id':job['client_id'],'company_code':config['scope']['company'],'actor_id':'service:flux-runtime:'+job['client_id']+':'+config['scope']['company'],'actor_kind':'service','initiated_by':job['owner_id'],'workflow_id':job.get('workflow_id',plan.get('id')),'workflow_version':plan.get('workflow_version'),'run_id':job['id'],'build_id':step.get('build_id'),'package_hash':step.get('package_hash'),**result}})
   if result['result_status']!='COMPLETED':await self.rpc('finish',job['id'],{'status':'review_required' if result['human_review_required'] else 'failed','result':{'step':i,'status':result['result_status'],'reasons':result['reasons'],'output':result['output'],'synthetic':bool(plan.get('synthetic'))}});return
   value=result['output']
  await self.rpc('finish',job['id'],{'status':'completed','result':{'output':value,'steps_completed':len(plan['steps']),'synthetic':bool(plan.get('synthetic'))}})
 async def heartbeat(self):
  while not self.stopping:
   try:await self.rpc('heartbeat')
   except asyncio.CancelledError:raise
   except Exception:pass
   await asyncio.sleep(5)
 async def serve(self):
  async with asyncio.TaskGroup() as group:
   group.create_task(self.loop());group.create_task(self.heartbeat())
 async def loop(self):
  while not self.stopping:
   job=None
   try:
    job=await self.rpc('claim')
    if job:await self.execute(job)
   except asyncio.CancelledError:raise
   except Exception as e:
    if job:
     try:await self.rpc('finish',job['id'],{'status':'failed','result':{'error_type':type(e).__name__,'reason':'Execution stopped; inspect package, credential selection and connector configuration'}})
     except Exception:pass
   await asyncio.sleep(2)
async def start():
 global WORKER
 if not fresh.enabled() or not WORKER_PATH.exists():return None
 WORKER=Worker(json.loads(WORKER_PATH.read_text())['worker_key']);return asyncio.create_task(WORKER.serve())
async def stop(task):
 if task:task.cancel();await asyncio.gather(task,return_exceptions=True)
 if WORKER:await WORKER.client.aclose()

@router.get('/executions')
async def executions(workflow_id:str='',agent_id:str='',before:str=''):
 """Keyset-paged execution steps, with the exact job and result evidence together."""
 c=fresh.CTX.get();query='flux_runtime_jobs?select=id,workflow_id,status,test_run,created_at,finished_at,definition,flux_runtime_steps(step,result,created_at)&client_id=eq.'+c['client']['id']
 if workflow_id:studio.store.ident(workflow_id);query+='&workflow_id=eq.'+workflow_id
 if agent_id:
  studio.store.ident(agent_id);query+='&definition->steps=cs.'+quote(json.dumps([{'agent_id':agent_id}],separators=(',',':')),safe='')
 if before:
  try:
   from datetime import datetime
   stamp,_,job_cursor=before.partition('~');datetime.fromisoformat(stamp.replace('Z','+00:00'))
   if job_cursor:uuid.UUID(job_cursor)
  except ValueError:raise Invalid('Invalid execution cursor')
  if job_cursor:query+='&or=(created_at.lt.'+quote(stamp,safe='')+',and(created_at.eq.'+quote(stamp,safe='')+',id.lt.'+job_cursor+'))'
  else:query+='&created_at=lt.'+quote(stamp,safe='')
 jobs=await fresh.rest(studio.store,'GET',query+'&order=created_at.desc,id.desc&limit=26')
 rows=[]
 for job in jobs[:25]:
  steps=job.get('flux_runtime_steps') or [];definitions=job.get('definition',{}).get('steps',[])
  if not steps:
   if not agent_id:rows.append({'id':job['id'],'job_id':job['id'],'workflow_id':job['workflow_id'],'agent_id':None,'agent_name':'Awaiting agent execution','created_at':job['created_at'],'status':job['status'],'test_run':job['test_run'],'result':None})
   continue
  for step in steps:
   definition=definitions[step['step']] if step['step']<len(definitions) else {};aid=definition.get('agent_id') or definition.get('id');result=step['result']
   if agent_id and aid!=agent_id:continue
   rows.append({'id':job['id']+':'+str(step['step']),'job_id':job['id'],'workflow_id':job['workflow_id'],'agent_id':aid,'agent_name':result.get('agent') or definition.get('name') or aid,'created_at':step['created_at'],'status':result.get('result_status',job['status']),'test_run':job['test_run'],'result':result,'package_hash':definition.get('package_hash')})
 rows.sort(key=lambda r:(r['created_at'],r['id']),reverse=True)
 return {'items':rows,'next_cursor':jobs[24]['created_at']+'~'+jobs[24]['id'] if len(jobs)>25 else None,'page_size_jobs':25,'environment':'TEST'}
