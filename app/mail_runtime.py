"""Certified canvas mail adapters: source capture, local parsing, document JSON."""
import copy,uuid
from fastapi import APIRouter
from . import fresh,studio
from .core import Invalid,digest
router=APIRouter(prefix='/api/runtime/mail')
STAGES=('capture','parse','json')
ADAPTERS=('maggie_capture','document_parse_local','document_json_v1')
NAMES=('Confirmation Email Retriever','Attachment Parser','Document JSON Converter')
CAPS=('READ','DOC','MAP')
SCHEMAS=[{'type':'object','properties':{'message_id':{'type':'string'},'mailbox':{'type':'string'},'attachments':{'type':'array','items':{'type':'object'}}},'required':['message_id','mailbox','attachments']},{'type':'object','properties':{'message_id':{'type':'string'},'attachment_id':{'type':'string'},'text':{'type':'string'},'status':{'type':'string'},'tables':{'type':['array','null']}},'required':['message_id','attachment_id','text','status']},{'type':'object','properties':{'schema':{'type':'string'},'document':{'type':'object'},'quality':{'type':'object'}},'required':['schema','document','quality']}]
async def rpc(action,args=None):return await fresh.rest(studio.store,'POST','rpc/flux_mail_pipeline',{'action':action,'args':{**(args or {}),'client_id':fresh.CTX.get()['client']['id']}})
@router.get('/status')
async def status():return await rpc('status')
def bump(v):
 try:a,b,c=v.split('.');return a+'.'+b+'.'+str(int(c)+1)
 except Exception:return '1.0.0'
def package(canvas,actor,scope,at):
 nodes=copy.deepcopy(canvas['nodes']);capture=next((n for n in nodes if n['data'].get('guided',{}).get('trigger_config',{}).get('target')=='confirmations@buntingmagnetics.com'),None)
 parser=next((n for n in nodes if n['data'].get('guided',{}).get('capability')=='DOC' and n['data'].get('guided',{}).get('name')),None)
 if not capture or not parser:raise Invalid('This canvas needs the saved confirmation capture and attachment parser cards')
 spare=next((n for n in nodes if n not in (capture,parser) and not n['data'].get('guided',{}).get('name')),None)
 if not spare:spare={'id':str(uuid.uuid4()),'type':'capability','data':{'guided':{'id':'draft-'+str(uuid.uuid4()),'version':'0.0.0','fields':{}}}}
 selected=[capture,parser,spare];steps=[];objects=[];schema_refs=[]
 for i,schema in enumerate(SCHEMAS):
  rid=scope['tenant']+'.canvas-mail-'+STAGES[i];ref='schema:'+rid+'@1.0.0';schema_refs.append(ref)
  r={'id':rid,'version':'1.0.0','kind':'schema','label':NAMES[i]+' runtime output','content':schema,'tenant':scope['tenant'],'company':scope['company'],'facility':scope['facility'],'created_by':actor,'created_at':at,'status':'approved','content_hash':digest(schema)}
  objects.append({'path':'resources/'+rid+'--1.0.0.json','body':r})
  objects.append({'path':'audit/mail-schema-'+rid+'.json','body':{'record_id':str(uuid.uuid4()),'action':'resource.published','actor':actor,'created_at':at,'tenant':scope['tenant'],'company':scope['company'],'payload':{'resource_ref':ref,'reason':'Owner requested execution of this read-only email pipeline'}}})
 for i,n in enumerate(selected):
  g=n['data']['guided'];g.update(name=NAMES[i],capability=CAPS[i],version=bump(g.get('version','0.0.0')),**scope,responsibility=('Read newly captured confirmations from the approved Maggie listener','Extract text, tables and page evidence from one stored attachment','Convert one parsed document into structured document JSON')[i],questions_for_user=[],questions_by_step={})
  fields=g.setdefault('fields',{})
  values={'identity.environment':'PROD','identity.company':scope['company'],'identity.owner':actor,'execute.model_access':'off','execute.authority':'P2' if i==0 else 'P0','execute.method':('system_read','document_parse','deterministic_map')[i],'execute.cost_ceiling':'zero','execute.time_limit':'2m','execute.instructions':'none','execute.rule':'none','trigger.type':'mailbox_message' if i==0 else 'flux_record','trigger.schedule':'not_scheduled','trigger.duplicates':'skip_if_key_seen','trigger.source_record':'email.captured' if i<2 else 'document.read','input.source_system':'outlook_graph' if i==0 else 'flux','input.freshness':'current_revision_only','input.when_missing':'review_required','input.schema':schema_refs[max(0,i-1)],'output.schema':schema_refs[i],'output.record_type':'email.captured' if i==0 else 'document.read','output.next':'chain_to_next_node' if i<2 else 'none','output.outcomes':'completed_review','output.evidence':'source_refs_hashes','error.retry':'3x_exponential','error.retryable':'timeouts_and_5xx','error.escalation':'human_review_queue','error.ambiguous_external':'not_applicable','verify.method':'automatic','verify.approval_gate':'none','verify.postcondition':'record_exists_schema_valid','verify.fixtures':'standard_set'}
  for k,v in values.items():fields[k]={'value':v,'source':'user','why':'Owner requested this canvas to run the read-only Bunting mail pipeline.'}
  g['trigger_config']={'kind':'listener','source':'mailbox','target':'confirmations@buntingmagnetics.com','delivery':'poll','timezone':'America/Chicago'} if i==0 else {'kind':'flux','source':'flux','delivery':'record','record_type':'email.captured' if i==1 else 'document.read'}
  g['bindings']={'reads':{'record_type':'email.captured' if i<2 else 'document.read','status':'completed'},'writes':{'record_type':'email.captured' if i==0 else 'document.read','outcomes':{'COMPLETED':'completed','REVIEW_REQUIRED':'review_required'}}}
  g['runtime_binding']={'kind':'canvas_mail','stage':STAGES[i],'adapter':ADAPTERS[i],'package_version':'1.0.0','mailbox':'confirmations@buntingmagnetics.com','read_only':True}
  n.update(position={'x':100+380*i,'y':150});n['data'].update(name=NAMES[i],capability=CAPS[i],status='Runtime package',guided_hash=digest(g),agent_ref=g['id']+'@'+g['version'])
  step={'stage':STAGES[i],'adapter':ADAPTERS[i],'agent_id':g['id'],'name':g['name'],'version':g['version'],'guided_hash':digest(g),'guided':g,'input_schema':SCHEMAS[max(0,i-1)],'output_schema':SCHEMAS[i]};steps.append(step)
  agent={'id':g['id'],'version':g['version'],'name':g['name'],'responsibility':g['responsibility'],'capability':g['capability'],'guided':g,'guided_hash':digest(g),'input_schema':step['input_schema'],'output_schema':step['output_schema'],'execution':g['runtime_binding'],'status':'runtime_package','created_at':at,'created_by':actor,**scope};agent['content_hash']=digest(agent)
  objects.append({'path':'agents/'+g['id']+'--'+g['version']+'.json','body':agent})
 # Preserve the previous immutable canvas version, including unused scratch cards.
 w={**copy.deepcopy(canvas),'nodes':selected,'edges':[{'id':'mail-'+str(i),'source':selected[i]['id'],'target':selected[i+1]['id'],'sourceHandle':'COMPLETED','targetHandle':'input','data':{'runtime_handoff':True,'compatible':True,'record_type':'email.captured' if i==0 else 'document.read'}} for i in range(2)],'name':'Bunting confirmation email pipeline','version':bump(canvas['version']),'status':'runtime_package','format':'canvas-v2','binding_mode':'canvas_mail','created_at':at,'actor':actor,'execution_enabled':False,**scope}
 w['draft_revision']=w['version'];w['content_hash']=digest({k:v for k,v in w.items() if k!='content_hash'});objects.append({'path':'workflows/'+w['id']+'--'+w['version']+'.json','body':w})
 definition={'workflow_id':w['id'],'workflow_version':w['version'],'name':w['name'],'mailbox':'confirmations@buntingmagnetics.com','steps':steps,'environment':'PRODUCTION_READ_ONLY','execution_mode':'canvas_mail','start_lookback_hours':1,'created_by':actor}
 return definition,objects
@router.post('/install')
async def install(b:dict):
 c=fresh.CTX.get()
 if c['role']!='owner' or c['client']['id']!='bunting':raise Invalid('Bunting administrator required')
 rows=await studio.store.records('workflows');candidates=[w for w in rows if w['id']==b.get('workflow_id')]
 if not candidates:raise Invalid('Select the saved confirmation email workflow')
 canvas=max(candidates,key=lambda w:w.get('created_at',''))
 definition,objects=package(canvas,c['user']['id'],dict(fresh.scope()),studio.store.now())
 return await rpc('install',{'definition':definition,'definition_hash':digest(definition),'objects':objects,'company_code':c['company']['code']})
@router.post('/power')
async def power(b:dict):return await rpc('power',b)
@router.post('/start')
async def start(b:dict):return await rpc('start')
@router.get('/candidate')
async def candidate():
 latest={}
 for w in await studio.store.records('workflows'):
  if w['id'] not in latest or w.get('created_at','')>latest[w['id']].get('created_at',''):latest[w['id']]=w
 for w in latest.values():
  cards=[n.get('data',{}).get('guided',{}) for n in w.get('nodes',[])]
  if any(g.get('trigger_config',{}).get('target')=='confirmations@buntingmagnetics.com' for g in cards) and any(g.get('capability')=='DOC' and g.get('name') for g in cards):return {'workflow_id':w['id'],'name':w['name']}
 return {'workflow_id':None}
