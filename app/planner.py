"""Durable, approval-gated workflow design. No publish or runtime adapter."""
import asyncio, copy, json, os, time, uuid
from pathlib import Path
import httpx
from fastapi import APIRouter
from . import studio
from .core import Invalid, digest

router=APIRouter(prefix='/api/studio/planner')
GUIDE=(Path(__file__).resolve().parent.parent/'guides/studio-planner-guide.md').read_text()
SCOPE={'tenant':'Bunting Magnetics','company':'BMC','facility':'500'}
from . import fresh
if fresh.enabled():SCOPE=fresh.Scope()
LOCK=asyncio.Lock()
TASKS={}
CAPS={c['code'] for c in studio.CATALOG['capabilities']}
METHOD=dict(READ='system_read',CLASS='constrained_classification',DOC='document_parse',MAP='deterministic_map',RULE='deterministic_rule',ROUTE='deterministic_rule',REASON='bounded_reasoning',COMMS='message_send',WRITE='transaction_write')

def actor():return studio.store.ACTOR.get()
async def persist(r):
    r['revision']=r.get('revision',0)+1;r['updated_at']=studio.store.now()
    await studio.store.put('planner/'+r['id']+'--'+str(r['revision']).zfill(5)+'.json',copy.deepcopy(r))
async def load(run_id):
    studio.store.ident(run_id)
    rows=[x for x in await studio.store.records('planner') if x['id']==run_id and x['created_by']==actor()]
    if not rows:raise Invalid('Planner run not found for this operator')
    return max(rows,key=lambda x:x['revision'])
async def audited(r,name,args,fn):
    start=time.monotonic();entry={'tool':name,'input':args,'started_at':studio.store.now(),'attempt':1};r['tools'].append(entry)
    await persist(r) # Record intent before any provider call or write.
    try:
        result=await fn();entry['output']=result;entry['status']='completed';return result
    except Exception as e:entry['status']='failed';entry['error']=str(e);raise
    finally:
        entry['duration_ms']=int((time.monotonic()-start)*1000);entry['completed_at']=studio.store.now();await persist(r)

def validate_plan(cards):
    if not isinstance(cards,list) or not 1<=len(cards)<=16:raise Invalid('Plan requires 1–16 cards')
    out=[]
    for c in cards:
        if c.get('capability') not in CAPS:raise Invalid('Unknown capability')
        if not all(isinstance(c.get(k),str) and 1<=len(c[k])<=limit for k,limit in [('title',160),('description',1800)]):raise Invalid('Each card needs a bounded title and description')
        hints=c.get('hints',{})
        if hints.get('company','BMC')!='BMC':raise Invalid('Planner scope is BMC only')
        out.append({'capability':c['capability'],'title':c['title'],'description':c['description'],'hints':hints})
    for i,c in enumerate(out):
        if c['capability']=='WRITE' and (i==0 or out[i-1]['capability']!='COMMS'):raise Invalid('WRITE needs a preceding approval COMMS card')
    return out

def defaults(cap,approval=False):
    return {'identity.environment':'TEST','identity.company':'BMC','input.when_missing':'rejected' if cap=='WRITE' else 'review_required','input.schema':'needs_new_schema','output.schema':'needs_new_schema','error.escalation':'human_review_queue','execute.authority':'P5' if cap=='WRITE' else 'P4' if cap=='COMMS' else 'P2' if cap in ('READ','RULE') else 'P0','execute.model_access':'jev_classifier' if cap=='CLASS' else 'sonnet' if cap in ('DOC','REASON') else 'off','execute.cost_ceiling':'0_01' if cap=='CLASS' else '0_25' if cap in ('DOC','REASON') else 'zero','execute.time_limit':'2m' if cap in ('DOC','REASON','WRITE') else '30s','verify.approval_gate':'single_approver' if cap=='WRITE' or approval else 'none','output.outcomes':'full_set' if cap in ('RULE','WRITE') or approval else 'completed_only' if cap=='COMMS' else 'completed_review','execute.method':METHOD[cap]}

async def set_field(g,key,val,cat,approval=False):
    options={f['id']:{x['id'] for x in f['options']} for s in cat['steps'] for f in s['fields']}
    if key not in options or val not in options[key]:raise Invalid('Dropdown value unavailable: '+key)
    if val=='PROD' or ('publish' in str(val).lower()):raise Invalid('Planner cannot publish or use PROD')
    if key=='execute.authority' and val=='P5' and g['capability']!='WRITE':raise Invalid('Transaction authority requires WRITE')
    if key=='verify.approval_gate' and (g['capability']=='WRITE' or approval) and val!='single_approver':raise Invalid('Approval cannot be removed')
    # These are design defaults explicitly accepted in the plan preview, not execution authority.
    g['fields'][key]={'value':val,'why':'Plan defaults approved by the operator; design only.','source':'user' if studio.decision_locked(key,g['capability'],val,cat) else 'planner_default'}

async def get_blockers(r):
    grouped={}
    for n in r['nodes']:
        g=n['data']['guided'];bs=(await studio.validate_definition({'guided':g}))['blockers']
        for key,group in [('input.schema','record_formats'),('output.schema','record_formats'),('execute.rule','approved_rules'),('execute.instructions','procedures')]:
            v=g['fields'].get(key,{}).get('value')
            if v and v.startswith('needs_new_'):bs.append({'field':key,'message':v.replace('_',' '),'group':group})
        for b in bs:
            if b.get('id') in ('input-schema','output-schema'):b['group']='record_formats'
            if b.get('id') in ('approved-rule','rule-required','approved-rule-required'):b['group']='approved_rules'
            if b.get('id')=='external-approval':b['group']='approval_gates'
            grouped.setdefault(b.get('group','approval_gates' if b.get('field') in studio.MODEL_LOCKED else 'choices'),[]).append({'card_id':n['id'],'title':g['name'],**b})
    return grouped

TOOLS=[{'name':'list_capabilities','description':'List the approved capability cards.','input_schema':{'type':'object','properties':{},'additionalProperties':False}}, {'name':'propose_plan','description':'Propose exactly one ordered plan, then stop for human approval.','input_schema':{'type':'object','properties':{'cards':{'type':'array','items':{'type':'object','properties':{'capability':{'type':'string','enum':sorted(CAPS)},'title':{'type':'string'},'description':{'type':'string'},'hints':{'type':'object','properties':{'department':{'type':'string'},'company':{'type':'string'},'starts':{'type':'string'}},'required':['department','company','starts'],'additionalProperties':False}},'required':['capability','title','description','hints'],'additionalProperties':False}}},'required':['cards'],'additionalProperties':False}}]

async def propose(r):
    key=os.environ.get('ANTHROPIC_API_KEY');model=os.environ.get('STUDIO_DRAFT_MODEL',studio.CONFIG['draft_model'])
    pi=float(os.environ.get('STUDIO_DRAFT_INPUT_PER_MTOK','0'));po=float(os.environ.get('STUDIO_DRAFT_OUTPUT_PER_MTOK','0'))
    if not key or min(pi,po)<=0:raise Invalid('Planner model and verified prices must be configured')
    headers={'x-api-key':key,'anthropic-version':'2023-06-01'}
    messages=[{'role':'user','content':json.dumps({'description':r['description'],'hints':r['hints']})}]
    async with httpx.AsyncClient(timeout=60) as client:
        for turn in range(3):
            payload={'model':model,'system':GUIDE+'\nUse tools to list capabilities and propose one plan. Only plan; stop after propose_plan. No live record content. Use the selected company; never infer credentials or company authority.','messages':messages,'tools':TOOLS}
            count=await client.post('https://api.anthropic.com/v1/messages/count_tokens',headers=headers,json=payload);count.raise_for_status()
            bound=count.json()['input_tokens']+2500
            available=min(.15,r['ceiling_usd']-r['reserved_usd']);max_out=min(5000,int((available-bound*pi/1e6)*1e6/po))
            if max_out<200:raise Invalid('Insufficient planning budget')
            reserve=(bound*pi+max_out*po)/1e6;r['reserved_usd']+=reserve;r['usage_complete']=False;await persist(r)
            t=time.monotonic();resp=await client.post('https://api.anthropic.com/v1/messages',headers=headers,json={**payload,'max_tokens':max_out});resp.raise_for_status();msg=resp.json()
            usage=msg.get('usage',{})
            if 'input_tokens' not in usage or 'output_tokens' not in usage:raise Invalid('Provider usage unknown; stop within reserved budget')
            cost=(usage['input_tokens']*pi+usage['output_tokens']*po)/1e6
            if cost>reserve:raise Invalid('Provider exceeded reserved cost; no cards built')
            r['reserved_usd']-=reserve;r['spent_usd']+=cost;r['reserved_usd']+=cost;r['usage_complete']=True
            r['provider_calls'].append({'model':model,'usage':usage,'cost_usd':cost,'duration_ms':int((time.monotonic()-t)*1000),'request_id':resp.headers.get('request-id')});await persist(r)
            messages.append({'role':'assistant','content':msg['content']});results=[]
            for block in msg['content']:
                if block['type']!='tool_use':continue
                if block['name']=='list_capabilities':
                    async def caps():return studio.CATALOG['capabilities']
                    result=await audited(r,'list_capabilities',block['input'],caps)
                elif block['name']=='propose_plan':
                    async def plan():return validate_plan(block['input']['cards'])
                    result=await audited(r,'propose_plan',block['input'],plan);return result
                else:raise Invalid('Unsupported planner tool')
                results.append({'type':'tool_result','tool_use_id':block['id'],'content':json.dumps(result)})
            if not results:raise Invalid('Sonnet did not propose a tool plan')
            messages.append({'role':'user','content':results})
    raise Invalid('Planner did not propose within the tool-turn limit')

@router.post('/plan')
async def plan_endpoint(b:dict):
    if not isinstance(b.get('description'),str) or not 3<=len(b['description'])<=12000:raise Invalid('Describe the workflow in 3–12000 characters')
    r={'id':'plan-'+str(uuid.uuid4()),**SCOPE,'created_by':actor(),'description':b['description'],'hints':b.get('hints',{}),'status':'planning','tools':[],'provider_calls':[],'nodes':[],'edges':[],'ceiling_usd':1.0,'reserved_usd':0.0,'spent_usd':0.0,'guide_hash':digest(GUIDE),'usage_complete':True}
    await persist(r)
    async def finish():
        try:r['cards']=await propose(r);r['status']='awaiting_approval'
        except Exception as e:r['status']='failed';r['error']=str(e)
        await persist(r)
    if b.get('queued'):
        task=asyncio.create_task(finish());TASKS[r['id']]=task
        task.add_done_callback(lambda t:TASKS.pop(r['id'],None))
        return r
    await finish();return r

@router.get('/runs/{run_id}')
async def read_run(run_id:str):
    r=await load(run_id)
    if r['status']=='planning' and run_id not in TASKS:
        r['status']='interrupted';r['error']='Planning was interrupted by a server restart. Saved evidence is retained; review recorded usage before starting a new plan.'
        await persist(r)
    return r

@router.post('/approve')
async def approve_endpoint(b:dict):
    async with LOCK:
        r=await load(b['run_id'])
        if r['status']!='awaiting_approval':raise Invalid('Run is not awaiting approval; duplicate build denied')
        approved_cards=validate_plan(b.get('cards',r['cards']))
        await studio.store.put('planner-claims/'+r['id']+'.json',{'run_id':r['id'],'actor':actor(),**SCOPE})
        if hasattr(studio.store,'DESIGN_SCOPE'):studio.store.DESIGN_SCOPE.set(SCOPE)
        r['cards']=approved_cards;r['approved_by']=actor();r['approved_at']=studio.store.now();r['approved_hash']=digest(r['cards']);r['status']='building';await persist(r)
        c=await studio.catalog();remaining=len(r['cards'])
        try:
            for index,card in enumerate(r['cards']):
                budget=min(.25,(r['ceiling_usd']-r['reserved_usd'])/remaining)
                if budget<=0:raise Invalid('Planner budget exhausted')
                r['reserved_usd']+=budget;r['usage_complete']=False;await persist(r)
                async def add_card():
                    return await studio.model_draft({'capability':card['capability'],'description':card['description'],'department':card['hints'].get('department'),'company':'BMC','trigger':card['hints'].get('starts') if index==0 else 'flux_record','catalog_version':c['version'],'guide_version':c['guide_version']},budget_ceiling=budget)
                draft=await audited(r,'add_card',{'card':card,'budget_ceiling_usd':budget},add_card)
                usage=draft['_usage'];r['spent_usd']+=usage['cost_usd'];r['reserved_usd']-=budget-usage['cost_usd'];r['usage_complete']=True
                agents=draft['agents']
                if len(r['nodes'])+len(agents)+remaining-1>32:raise Invalid('Split exceeds 32-card run limit')
                if draft.get('split'):
                    async def split():return {'accepted':True,'agents':agents}
                    await audited(r,'accept_split',{'approved_parent':card},split)
                for ai,a in enumerate(agents):
                    if a['capability']=='WRITE' and card['capability']!='WRITE':raise Invalid('Split cannot add unapproved transaction authority')
                    cap=a['capability'];id='draft-'+str(uuid.uuid4());approval=cap=='COMMS' and ((ai+1<len(agents) and agents[ai+1]['capability']=='WRITE') or (ai==len(agents)-1 and index+1<len(r['cards']) and r['cards'][index+1]['capability']=='WRITE'))
                    g={**a,'id':id,'version':'0.1.0','name':card['title'] if len(agents)==1 else a['name_options'][0],'responsibility':a['responsibility_options'][0],'catalog_version':c['version'],'guide_version':c['guide_version'],'planner_approved_run':r['id'],**SCOPE}
                    ds=defaults(cap,approval);ds['identity.department']=card['hints'].get('department') or r['hints'].get('department') or 'sales';ds.update({'trigger.source_record':'none','trigger.schedule':'not_scheduled','trigger.duplicates':'skip_if_key_seen','input.source_system':'flux','input.freshness':'any','execute.instructions':'needs_new_instructions','execute.rule':'needs_new_rule' if cap=='RULE' else 'none','output.record_type':'custom_needs_schema','output.evidence':'fields_with_page_locators' if cap=='DOC' else 'target_readback_receipt' if cap=='WRITE' else 'source_refs_hashes','output.next':'none' if index==len(r['cards'])-1 and ai==len(agents)-1 else 'chain_to_next_node','error.retry':'manual_only','error.retryable':'none','error.ambiguous_external':'suspend_and_reconcile' if cap in ('WRITE','COMMS') else 'not_applicable','verify.postcondition':'target_readback' if cap=='WRITE' else 'record_exists_schema_valid','verify.method':'human_signoff' if cap=='WRITE' else 'automatic','verify.fixtures':'standard_plus_model_safety' if cap in ('DOC','REASON','CLASS') else 'standard_set'});ds['identity.owner']=(await studio.users())['users'][0]['id']
                    ds['trigger.type']=card['hints'].get('starts') or 'mailbox_message' if not r['nodes'] else 'flux_record'
                    if cap in ('READ','WRITE') and 'Epicor' in card['description']:ds['input.freshness']='current_revision_only'
                    elif not r['nodes']:ds['input.freshness']='under_1_hour'
                    for field,val in ds.items():
                        if g['fields'].get(field,{}).get('value') is None or field in ('identity.environment','identity.company','verify.approval_gate','execute.authority'):
                            async def set_one(field=field,val=val):await set_field(g,field,val,c,approval);return g['fields'][field]
                            await audited(r,'set_field',{'card_id':id,'field':field,'value':val},set_one)
                    async def save_one():return await studio.save_definition({'guided':g})
                    saved=await audited(r,'save_draft',{'card_id':id,**SCOPE},save_one)
                    node={'id':id,'type':'capability','position':{'x':80+len(r['nodes'])*420,'y':120},'data':{'capability':cap,'guided':g,'status':'Draft','agent_ref':id+'@0.1.0'}}
                    if r['nodes']:r['edges'].append({'id':str(uuid.uuid4()),'source':r['nodes'][-1]['id'],'target':id,'sourceHandle':'COMPLETED','targetHandle':'input','data':{'compatible':False,'gaps':['Published record formats required']}})
                    r['nodes'].append(node);await persist(r)
                remaining-=1
            async def save_all():return await studio.save_canvas({'id':'canvas-'+r['id'],'version':'0.1.0','name':r['cards'][0]['title']+' workflow','nodes':r['nodes'],'edges':[],'binding_mode':'records',**SCOPE})
            r['canvas']=await audited(r,'save_canvas',{'canvas_id':'canvas-'+r['id'],**SCOPE},save_all)
            async def blocked():return await get_blockers(r)
            r['blockers']=await audited(r,'get_blockers',{},blocked);r['status']='completed'
        except Exception as e:r['status']='blocked';r['error']=str(e)
        await persist(r);return r
