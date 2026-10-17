import asyncio,io,json,os,time,uuid,zipfile
from datetime import datetime,timezone
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,Response
from fastapi.staticfiles import StaticFiles
from .core import validate_agent,test_agent,execute,validate_workflow,digest,Invalid
from pathlib import Path
from contextvars import ContextVar
ACTOR=ContextVar("studio_actor",default="ssh-owner")
DESIGN_SCOPE=ContextVar("studio_design_scope",default={})
WEB_ROOT=Path(os.environ.get('STUDIO_WEB_ROOT',str(Path(__file__).resolve().parent.parent/'web/dist')))

APP_VERSION='0.4.0'
BUCKET='flux-studio'
BASE=os.environ.get('PZLO_SUPABASE_URL','').rstrip('/')
KEY=os.environ.get('PZLO_SUPABASE_SERVICE_KEY','')
HEAD={'apikey':KEY,'Authorization':'Bearer '+KEY}
from . import fresh
if fresh.enabled():BASE=fresh.URL;KEY=fresh.KEY;HEAD=fresh.HEAD;BUCKET='flux-app'
CLIENT=httpx.AsyncClient(timeout=25)
LOCK=asyncio.Lock()
READ_SLOTS=asyncio.Semaphore(8)

def now():return datetime.now(timezone.utc).isoformat()
def uid():return str(uuid.uuid4())
def ident(s):
    if not isinstance(s,str) or not s or len(s)>140 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._' for c in s):raise Invalid('Invalid record identifier')
    return s
async def put(path,obj):
    if fresh.enabled():
        import sys
        return await fresh.object_put(sys.modules[__name__],path,obj)
    r=await CLIENT.post(BASE+'/storage/v1/object/'+BUCKET+'/'+path,headers={**HEAD,'Content-Type':'application/json','x-upsert':'false'},content=json.dumps(obj))
    if r.status_code not in (200,201):
        try: duplicate=str(r.json().get('statusCode'))=='409'
        except Exception: duplicate=False
        if duplicate or r.status_code==409:raise HTTPException(409,'Immutable record already exists; save a new version')
        raise HTTPException(503,'Durable Operis commit failed: '+str(r.status_code))
    return obj
async def get(path):
    if fresh.enabled():
        import sys
        return await fresh.object_get(sys.modules[__name__],path)
    async with READ_SLOTS:
        for attempt in range(2):
            r=await CLIENT.get(BASE+'/storage/v1/object/authenticated/'+BUCKET+'/'+path,headers=HEAD)
            if r.status_code not in (429,502,503,504) or attempt:break
            await asyncio.sleep(0.25)
    if r.status_code==404 or r.status_code==400:return None
    if r.status_code!=200:raise HTTPException(503,'Operis read unavailable (HTTP '+str(r.status_code)+'). Retry loading the catalog; saved drafts remain intact.')
    return r.json()
async def records(kind):
    if fresh.enabled():
        import sys
        return await fresh.objects(sys.modules[__name__],kind)
    out=[];offset=0
    while True:
        r=await CLIENT.post(BASE+'/storage/v1/object/list/'+BUCKET,headers=HEAD,json={'prefix':fresh.physical(kind) if fresh.enabled() else kind,'limit':100,'offset':offset,'sortBy':{'column':'name','order':'desc'}})
        if r.status_code!=200:raise HTTPException(503,'Operis registry unavailable')
        rows=r.json()
        for x in rows:
            if x.get('id'):out.append(x['name'])
        if len(rows)<100:break
        offset+=100
    return await asyncio.gather(*(get(kind+'/'+x) for x in out))
async def event(action,payload,**extra):
    x={'record_id':uid(),'schema_version':'1.0.0','action':action,'actor':ACTOR.get(),'created_at':now(),'payload':payload,'runtime_version':'flux-studio-'+APP_VERSION,'duration_ms':None,'duration_reason':'Configuration event; elapsed operation duration not measured','attempt':1,'model':None,'input_tokens':0,'output_tokens':0,'model_cost_usd':0,'infrastructure_cost':None,'usage_complete':True,**extra}
    from .governance import envelope
    x.update(envelope(action,payload,ACTOR.get(),extra))
    x.update(DESIGN_SCOPE.get())
    x['content_hash']=digest(x)
    await put('audit/'+x['created_at'].replace(':','-')+'-'+x['record_id']+'.json',x)
    return x
async def versions(include_archived=False):
    from .agent_lifecycle import archived_ids
    rows=await records('agents');audit=await records('audit');archived=archived_ids(audit);published={x['payload']['agent_ref'] for x in audit if x['action']=='agent.published'}
    for a in rows:a['status']='published' if a['id']+'@'+a['version'] in published else 'draft'
    return rows if include_archived else [a for a in rows if a['id'] not in archived]
async def agent(ref):
    ident(ref.replace('@','-'))
    for a in await versions():
        if a['id']+'@'+a['version']==ref:return a
    raise Invalid('Unknown agent version')

@asynccontextmanager
async def lifespan(app):
    from .deployment_settings import load
    import sys
    if not fresh.enabled():await load(sys.modules[__name__])
    from . import runtime
    worker_task=await runtime.start()
    yield
    await runtime.stop(worker_task)
    await CLIENT.aclose()
app=FastAPI(title='Operis Studio',version=APP_VERSION,lifespan=lifespan)

@app.middleware('http')
async def boundary(request:Request,call_next):
    if fresh.enabled():
        import sys
        return await fresh.boundary(request,call_next,sys.modules[__name__])
    # Accessible only through host loopback and SSH. Block cross-site browser writes.
    public_host=os.environ.get('STUDIO_PUBLIC_HOST','')
    is_public=bool(public_host) and request.url.hostname==public_host
    if (public_host and not is_public) or (not public_host and request.url.hostname not in ('127.0.0.1','localhost')):
        return Response('Host denied',403)
    if request.method not in ('GET','HEAD'):
        origin=request.headers.get('origin')
        expected_origin='https://'+public_host if is_public else str(request.base_url).rstrip('/')
        if (origin and origin!=expected_origin) or request.headers.get('sec-fetch-site')=='cross-site':return Response('Cross-origin action denied',403)
        if request.headers.get('content-type','').split(';')[0]!='application/json':return Response('JSON required',415)
    raw_body=await request.body() if request.method not in ('GET','HEAD') else b''
    if len(raw_body)>(8*1024*1024 if request.url.path=='/api/studio/draft-agent' else 1048576):return Response('Request exceeds 1 MiB',413)
    try:
        if is_public:
            if request.method not in ('GET','HEAD') and request.headers.get('origin')!='https://'+public_host:return Response('Origin required',403)
            from .browser_auth import authorize
            import sys
            if request.url.path=='/readyz' and request.method=='GET':
                h=await health()
                return Response(json.dumps({'status':h['status']}),200 if h['status']=='ok' else 503,media_type='application/json')
            auth_response=await authorize(request,sys.modules[__name__])
            if auth_response is not None:return auth_response
            ACTOR.set(request.state.actor)
        else:ACTOR.set('ssh-owner')
        response=await call_next(request)
    except (Invalid,ValueError,KeyError,TypeError) as e:
        response=Response(json.dumps({'detail':str(e)}),400,media_type='application/json')
    if request.method not in ('GET','HEAD') and response.status_code>=400 and request.url.path.startswith('/api/'):
        try:
            if hasattr(response,'body_iterator'):
                chunks=[chunk async for chunk in response.body_iterator]
                response_bytes=b''.join(chunks)
            else:response_bytes=response.body
            details=json.loads(response_bytes.decode()).get('detail','Request rejected')
            await event('action.denied_or_failed',{'path':request.url.path,'http_status':response.status_code,'input_hash':None if request.url.path.startswith(('/api/studio/library','/api/studio/teach')) else digest(raw_body.decode(errors='replace')),'error':details,'retryable':False})
            response=Response(response_bytes,status_code=response.status_code,headers=dict(response.headers))
        except Exception:return Response(json.dumps({'detail':'Action failed and its audit could not be persisted'}),503,media_type='application/json')
    return response

@app.get('/')
async def home():return FileResponse(WEB_ROOT/'index.html')
@app.get('/agent-results')
async def result_snapshot():return FileResponse(WEB_ROOT.parent/'agent-work-results.html')
@app.get('/health')
async def health():
    r=await CLIENT.get(BASE+'/storage/v1/bucket/'+BUCKET,headers=HEAD)
    return {'status':'ok' if r.status_code==200 else 'degraded','project':BASE,'store':'Operis private Storage','mode':'SSH-owner private access','existing_dispatch_modified':False,'version':APP_VERSION,'deployment':os.environ.get('STUDIO_DEPLOYMENT_ID','bunting-private')}
@app.get('/api/state')
async def state():
    agents,resources,workflows,audit,runs=await asyncio.gather(versions(True),records('resources'),records('workflows'),records('audit'),records('runs'))
    teach=await records('teaching');counts={}
    for r in teach:
        if r.get('owner')==ACTOR.get() and (r['agent_id'] not in counts or r['revision']>counts[r['agent_id']]['revision']):counts[r['agent_id']]={'revision':r['revision'],'open':sum(q['resolution']=='open' for q in r['questions'])}
    from .agent_lifecycle import archived_ids
    archived=archived_ids(audit)
    return dict(interviews=counts,archived_agents=[a for a in agents if a['id'] in archived],agents=[a for a in agents if a['id'] not in archived],resources=resources,workflows=workflows,audit=sorted(audit,key=lambda x:x['created_at'],reverse=True),runs=sorted(runs,key=lambda x:x['created_at'],reverse=True))
@app.post('/api/agents')
async def create(a:dict):
    try:validate_agent(a)
    except Exception as e:raise Invalid(str(e)[:800])
    if a['id'] in ('agent01-graph-reader','agent02-document-reader','agent03-jev-classifier','agent04-workflow-router','agent-01-graph-reader','agent-02-document-reader','agent-03-jev-classifier','agent-04-workflow-router'):
        raise Invalid('Existing production identity is reserved')
    for ref in a.get('resource_refs',[]):
        ident(ref['kind']);ident(ref['id']);ident(ref['version'])
        r=await get('resources/'+ref['kind']+'--'+ref['id']+'--'+ref['version']+'.json')
        if not r or r['content_hash']!=ref['content_hash']:raise Invalid('Resource pin unavailable or hash differs')
        actual={'schema':a['input_schema'],'instructions':a['instructions'],'rules':a['execution']}.get(ref['kind'])
        if actual!=r['content']:raise Invalid('Definition differs from pinned resource')
    # Each version is an immutable, self-contained definition with its creation audit.
    a={**a,'authority':'P0','model_access':False,'created_at':now(),'actor':ACTOR.get(),'status':'draft'}
    a['content_hash']=digest(a)
    await put('agents/'+a['id']+'--'+a['version']+'.json',a)
    return a
@app.post('/api/agents/test')
async def test(body:dict):
    a=await agent(body['agent_ref']);result=test_agent(a)
    await event('agent.tested',{'agent_ref':body['agent_ref'],'definition_hash':a['content_hash'],**result})
    return result
@app.post('/api/agents/publish')
async def publish(body:dict):
    async with LOCK:
        a=await agent(body['agent_ref'])
        if a.get('guided'):raise Invalid('Use guided design publication; it does not enable execution')
        result=test_agent(a)
        if not result['passed']:raise Invalid('Acceptance fixtures failed; publication blocked')
        if a['status']=='published':return {'status':'published','duplicate':True}
        return await event('agent.published',{'agent_ref':body['agent_ref'],'definition_hash':a['content_hash'],'tests':result})
@app.get('/api/export/{ref}')
async def export(ref:str):
    a=await agent(ref);buf=io.BytesIO()
    files={'identity.json':{k:a[k] for k in ('id','name','version','responsibility','capability','authority','model_access')},'contract.json':{'input_schema':a['input_schema'],'output_schema':a['output_schema'],'functions':a['functions']},'instructions.md':a['instructions'],'resources.json':{'refs':a.get('resource_refs',[]),'library_refs':a.get('library_refs',[]),'definition_hash':a['content_hash']},'execution.json':a['execution'],'tests.json':a['tests']}
    if a.get('guided'):
        g=a['guided']
        files['identity.json'].update({k:g.get('fields',{}).get('identity.'+k,{}).get('value') for k in ('department','company','environment','owner')})
        files['contract.json'].update(a.get('contract_metadata',{}))
        files['resources.json'].update({'guide_version':g['guide_version'],'catalog_version':g['catalog_version'],'catalog_snapshot_hash':a['catalog_snapshot_hash'],'guided':g})
    with zipfile.ZipFile(buf,'w') as z:
        for name,value in files.items():z.writestr(a['id']+'/'+name,value if isinstance(value,str) else json.dumps(value,indent=2))
    await event('agent.exported',{'agent_ref':ref})
    return Response(buf.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="'+a['id']+'.zip"'})
@app.post('/api/resources')
async def resource(b:dict):
    if b.get('kind') not in ('schema','instructions','rules'):raise Invalid('Register schemas, instructions or deterministic rules')
    ident(b['id']);ident(b['version'])
    from .library import assert_editable
    await assert_editable('legacy:'+b['kind']+':'+b['id'])
    if b['kind']=='schema':
        from .core import schema
        try:schema(b['content'])
        except Exception as e:raise Invalid(str(e)[:800])
    b={**b,'created_at':now(),'actor':ACTOR.get()};b['content_hash']=digest(b)
    return await put('resources/'+b['kind']+'--'+b['id']+'--'+b['version']+'.json',b)
@app.post('/api/workflows')
async def workflow(w:dict):
    ident(w['id']);ident(w['version'])
    errors=validate_workflow(w,{a['id']+'@'+a['version']:a for a in await versions()})
    w={**w,'validation_errors':errors,'created_at':now(),'actor':ACTOR.get(),'status':'draft'};w['content_hash']=digest(w)
    return await put('workflows/'+w['id']+'--'+w['version']+'.json',w)
@app.post('/api/workflows/validate')
async def validation(w:dict):return {'errors':validate_workflow(w,{a['id']+'@'+a['version']:a for a in await versions()})}
@app.post('/api/workflows/publish')
async def publish_workflow(b:dict):
    ident(b['id']);ident(b['version']);w=await get('workflows/'+b['id']+'--'+b['version']+'.json')
    if not w:raise Invalid('Unknown workflow')
    errors=validate_workflow(w,{a['id']+'@'+a['version']:a for a in await versions()})
    if errors:raise Invalid('; '.join(errors))
    return await event('workflow.published',{'workflow_ref':w['id']+'@'+w['version'],'definition_hash':w['content_hash']})

async def invocation(a,data,key,inputs):
    ident(key)
    previous=await get('runs/'+key+'.json')
    if previous:
        if previous['definition_hash']!=a['content_hash'] or previous['input_hash']!=digest(data):raise Invalid('Idempotency key belongs to different inputs/version')
        return previous
    started=now();start=time.monotonic()
    # Durable intent first; deterministic recovery may safely recompute after process loss.
    intent=await get('intents/'+key+'.json')
    if intent and (intent['input_hash']!=digest(data) or intent['definition_hash']!=a['content_hash']):raise Invalid('Idempotency intent conflicts')
    if not intent:await put('intents/'+key+'.json',{'created_at':started,'execution_id':key,'input':data,'input_hash':digest(data),'definition_hash':a['content_hash'],'agent_ref':a['id']+'@'+a['version'],'actor':ACTOR.get()})
    try:
        out=execute(a,data);status='REVIEW_REQUIRED' if a['execution'].get('on_false')=='review' and out.get('matched') is False else 'VERIFIED';error=None
    except Exception as exc:out=None;status='FAILED';error={'code':'INVALID_INPUT_OR_EXECUTION','type':type(exc).__name__,'message':str(exc)[:800],'retryable':False}
    r={'record_id':key,'created_at':started,'completed_at':now(),'duration_ms':round((time.monotonic()-start)*1000),'agent_ref':a['id']+'@'+a['version'],'definition_hash':a['content_hash'],'input':data,'input_hash':digest(data),'input_refs':inputs,'output':out,'result_status':status,'error':error,'attempt':1,'recovery_recomputed':bool(intent),'runtime':'flux-studio-deterministic-v1','actor':ACTOR.get(),'permission':'P0','model':None,'input_tokens':0,'output_tokens':0,'model_cost_usd':0,'infrastructure_cost':None,'infrastructure_cost_reason':'not measured','validation':'passed' if status in ('VERIFIED','REVIEW_REQUIRED') else 'failed','evidence':{'input_hash':digest(data),'output_hash':digest(out)},'versions':{'agent':a['version'],'interpreter':'1.0.0'}}
    r['content_hash']=digest(r)
    # Audit is embedded in the committed immutable result, avoiding split writes.
    return await put('runs/'+key+'.json',r)
@app.post('/api/execute')
async def run(b:dict):
    async with LOCK:
        a=await agent(b['agent_ref'])
        if a.get('guided'):raise Invalid('New canvas agents are design-only in this iteration')
        if a['status']!='published':raise Invalid('Publish a tested agent before execution')
        return await invocation(a,b['input'],b.get('idempotency_key') or uid(),b.get('input_refs',[]))
@app.post('/api/workflows/run')
async def run_workflow(b:dict):
    async with LOCK:
        ident(b['id']);ident(b['version']);key=ident(b.get('idempotency_key') or uid())
        w=await get('workflows/'+b['id']+'--'+b['version']+'.json')
        if not w:raise Invalid('Unknown workflow')
        if w.get('format')=='canvas-v2':raise Invalid('Canvas drafts cannot dispatch new agents in this iteration')
        audit=await records('audit')
        if not any(x['action']=='workflow.published' and x['payload']['definition_hash']==w['content_hash'] for x in audit):raise Invalid('Workflow publication required')
        agents={a['id']+'@'+a['version']:a for a in await versions()};errors=validate_workflow(w,agents)
        if errors:raise Invalid('; '.join(errors))
        controls=[x for x in audit if x['action'] in ('workflow.paused','workflow.resumed') and x['payload'].get('workflow_ref')==w['id']+'@'+w['version']]
        if controls and sorted(controls,key=lambda x:x['created_at'])[-1]['action']=='workflow.paused':raise Invalid('Workflow paused')
        request_hash=digest({'workflow':w['content_hash'],'input':b['input']})
        old=await get('workflow-inputs/'+key+'.json')
        if old and old['request_hash']!=request_hash:raise Invalid('Workflow key conflicts with prior request')
        if not old:await put('workflow-inputs/'+key+'.json',{'created_at':now(),'request_hash':request_hash,'input':b['input'],'workflow_hash':w['content_hash']})
        incoming={e['target']:e['source'] for e in w['edges']};nodes={n['id']:n for n in w['nodes']};node=next(n for n in nodes if n not in incoming);data=b['input'];refs=['workflow-inputs/'+key];results=[]
        while node:
            r=await invocation(agents[nodes[node]['agent_ref']],data,key+'-'+ident(node),refs)
            results.append(r)
            if r['result_status']=='REVIEW_REQUIRED':
                decisions=[x for x in audit if x['action']=='review.decided' and x['payload'].get('record_id')==r['record_id'] and x['payload'].get('result_hash')==r['content_hash']]
                if not decisions or sorted(decisions,key=lambda x:x['created_at'])[-1]['payload']['decision']!='approve':break
            elif r['result_status']!='VERIFIED':break
            data=r['output'];refs=['runs/'+r['record_id']]
            node=next((e['target'] for e in w['edges'] if e['source']==node),None)
        return {'execution_id':key,'status':results[-1]['result_status'],'results':results}
@app.post('/api/workflows/control')
async def control(b:dict):
    if b['action'] not in ('pause','resume'):raise Invalid('Unknown control')
    return await event('workflow.'+('paused' if b['action']=='pause' else 'resumed'),{'workflow_ref':b['workflow_ref']})

@app.post('/api/review')
async def review(b:dict):
    if b.get('decision') not in ('approve','reject','escalate'):raise Invalid('Unknown review decision')
    ident(b['record_id']);r=await get('runs/'+b['record_id']+'.json')
    if not r or r['result_status']!='REVIEW_REQUIRED':raise Invalid('Result does not require review')
    if not b.get('reason'):raise Invalid('Review reason is required')
    return await event('review.decided',{'record_id':r['record_id'],'result_hash':r['content_hash'],'decision':b['decision'],'reason':b['reason'],'authority_scope':'Internal P0 workflow continuation only; no external action'})

# Existing production agents are observed, never mutated or triggered by Studio.
TABLES={1:('a01_runs','started_at','id,started_at,finished_at,status,completed,errors,error'),2:('a02_runs','started_at','id,started_at,finished_at,status,extracted,errors,llm_calls,llm_usd,error'),3:('a03_runs','started_at','*'),4:('a04_decisions','started_at','decision_id,run_id,routing_version,started_at,completed_at,duration_ms,status,error')}
@app.get('/api/live')
async def live():
    async def one(n):
        port={1:8480,2:8481,3:8482,4:8484}[n]
        try:
            r=await CLIENT.get('http://127.0.0.1:'+str(port)+'/health');health=r.json()
        except Exception:health={'status':'unreachable','reason':'Health endpoint unavailable from container'}
        table,order,fields=TABLES[n]
        r=await CLIENT.get(BASE+'/rest/v1/'+table,headers=HEAD,params={'select':fields,'order':order+'.desc','limit':'20'})
        # Agent 03 schema may differ: expose a concrete error, never fabricated results.
        rows=r.json() if r.status_code==200 else []
        safe=[]
        for row in rows:safe.append({k:v for k,v in row.items() if k not in ('package','input','output','body','text')})
        return {'number':n,'health':health,'runs':safe,'history_error':None if r.status_code==200 else 'Operis query failed '+str(r.status_code),'table':table}
    return {'observed_at':now(),'agents':await asyncio.gather(*(one(n) for n in range(1,5))),'project':BASE,'scope':'Existing pipeline; monitoring only. Agent 04 shadow dispatch unchanged.'}
@app.get('/api/lineage')
async def lineage():
    specs={'capture':('a01_messages','message_id,mailbox,status,completed_at'), 'read':('a02_document_content','message_id,attachment_id,status,char_count,reader_version,extracted_at,truncated'), 'classify':('a03_classifications','message_id,status,primary_classification,classifier_version,classified_at,requires_review'), 'route':('a04_current_routes','message_id,route_name,status,routing_version,requires_review,created_at')}
    result={}
    for key,(table,fields) in specs.items():
        r=await CLIENT.get(BASE+'/rest/v1/'+table,headers=HEAD,params={'select':fields,'limit':'30'})
        result[key]={'rows':r.json() if r.status_code==200 else [],'error':None if r.status_code==200 else 'Query failed '+str(r.status_code),'bounded':True}
    return result

async def library_page(prefix,offset,limit):
    import sys
    if fresh.enabled():return await fresh.library_page(sys.modules[__name__],prefix,offset,limit)
    return await records(prefix)

from . import studio
import sys
studio.store=sys.modules[__name__]
app.include_router(studio.router)
from . import planner
app.include_router(planner.router)
from . import library
app.include_router(library.router)
from . import agent_lifecycle
app.include_router(agent_lifecycle.router)
from . import workflow_json
app.include_router(workflow_json.router)
from . import email_template
app.include_router(email_template.router)
from . import credential_import
app.include_router(credential_import.router)
from . import reviews
app.include_router(reviews.router)
from . import teaching
app.include_router(teaching.router)
from . import record_bindings
app.include_router(record_bindings.router)
from . import runtime
app.include_router(runtime.router)
from . import mail_results
app.include_router(mail_results.router)
from . import mail_runtime
app.include_router(mail_runtime.router)
app.mount('/assets',StaticFiles(directory=WEB_ROOT/'assets'),name='assets')

from . import governance
app.include_router(governance.router)
