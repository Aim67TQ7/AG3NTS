"""Scoped builder v2 proposals. Never grants credentials or enables business actions."""
import copy,json,re,uuid
from . import mcp_builder as b,studio
from .core import digest,schema,Invalid
from .rule_language import lookup
DETAIL={'type':'string','enum':['summary','full'],'default':'full'}
ID=b.STR
SECRET_KINDS={
 'graph_app':(['tenant_id','client_id','client_secret','mailbox','folder_id'],['mail.read','mail.send'],'outlook_graph'),
 'graph_delegated':(['tenant_id','client_id','refresh_token'],['mail.read','mail.send'],'outlook_graph'),
 'epicor_rest_basic':(['base_url','company_code','username','password','api_key','allowed_paths'],['epicor.read','epicor.write'],'epicor_rest'),
 'epicor_baq_token':(['base_url','company','api_key'],['epicor.read'],'epicor_baq'),
 'sharepoint_app':(['tenant_id','client_id','client_secret'],['files.read','files.write'],'sharepoint'),
 'smtp':(['host','port','username','password'],['mail.send'],'smtp'),
 'api_key':(['base_url','api_key'],['records.read','records.write'],'custom'),
 'teams_app':(['tenant_id','client_id','client_secret','team_id','channel_id'],['teams.send'],'teams'),
 'webhook_hmac':(['endpoint','hmac_secret'],['records.read'],'webhook')}
COMPLETENESS={
 'READ':['input.schema','output.schema','external_connection'],
 'DOC':['input.schema','output.schema','fixtures','model_instructions'],
 'MAP':['input.schema','output.schema','mapping'],
 'RULE':['input.schema','execute.rule','fixtures'],
 'CLASS':['input.schema','output.schema','execute.instructions','fixtures','class_list','model_access','cost_ceiling'],
 'ROUTE':['input.schema','execute.rule','outcome_destinations'],
 'REASON':['input.schema','output.schema','execute.instructions','fixtures','model_access','cost_ceiling'],
 'COMMS':['external_connection','verify.approval_gate','error.escalation','message_template'],
 'WRITE':['external_connection','verify.approval_gate','verify.postcondition','error.ambiguous_external','fixtures']}
FIXTURE=b.obj({'adapter_result':{'type':'object'},'name':ID,'input':{'type':'object'},'expected':b.obj({'outcome':ID,'fields':{'type':'object'},'max_cost_usd':{'type':'number','minimum':0,'maximum':1}},['outcome','fields'])},['name','input','expected'])
RESOURCE={'request_id':b.UUID,'resource_id':ID,'version':ID,'label':ID}
TOOLS=[
 {'name':'list_proposals','description':'List this actor/company pending and reviewed proposals; no secrets.','inputSchema':b.obj({'status':ID,'detail':DETAIL},[])},
 {'name':'read_proposal','description':'Read a proposal by its proposal or record ID, including complete change-set review.','inputSchema':b.obj({'id':ID,'detail':DETAIL},['id'])},
 {'name':'list_runs','description':'Read scoped runtime and mail run metadata, no content bytes; cursor pagination.','inputSchema':b.obj({'workflow_id':ID,'since':{'type':'string','format':'date-time'},'outcome':ID,'cursor':ID,'detail':DETAIL},['workflow_id'])},
 {'name':'read_run','description':'Read one scoped stored run, output, metrics, errors and file IDs; no content bytes.','inputSchema':b.obj({'run_id':ID,'detail':DETAIL},['run_id'])},
 {'name':'read_record','description':'Read an exact scoped durable result by declared record type and ID; no bytes.','inputSchema':b.obj({'record_type':ID,'id':ID,'detail':DETAIL},['record_type','id'])},
 {'name':'propose_instructions','description':'Propose versioned procedure text and bounded model contract for human review.','inputSchema':b.obj({**RESOURCE,'text':{'type':'string','minLength':1,'maxLength':20000},'model_contract':b.obj({'output_schema':ID,'max_tokens':{'type':'integer','minimum':1,'maximum':12000},'refusal_behavior':{'enum':['REVIEW_REQUIRED','REJECTED']},'prompt_version':ID})})},
 {'name':'propose_fixtures','description':'Attach named evidence fixtures to a draft; invalidates previous suite evidence.','inputSchema':b.obj({'request_id':b.UUID,'draft_id':ID,'expected_hash':b.HASH,'fixtures':{'type':'array','minItems':1,'maxItems':20,'items':FIXTURE}})},
 {'name':'propose_mapping','description':'Propose a bounded deterministic output-field to input-path mapping.','inputSchema':b.obj({'request_id':b.UUID,'draft_id':ID,'expected_hash':b.HASH,'fields':{'type':'object','minProperties':1,'maxProperties':100,'additionalProperties':ID}})},
 {'name':'run_fixture_suite','description':'Execute fixtures only, no business adapters. Model fixtures require explicit per-call budget and server enablement. Stored suite evidence is version/hash pinned.','inputSchema':b.obj({'request_id':b.UUID,'workflow_id':ID,'expected_hash':b.HASH,'max_cost_usd':{'type':'number','minimum':0,'maximum':1}},['request_id','workflow_id','expected_hash'])},
 {'name':'archive_workflow','description':'Propose recoverable archival for browser review. Refuses active runtime packages; preserves all history.','inputSchema':b.obj({'request_id':b.UUID,'workflow_id':ID,'expected_hash':b.HASH})},
 {'name':'list_secret_kinds','description':'Read credential-type field names and scopes only; never credential values.','inputSchema':b.obj({})},
 {'name':'propose_secret_request','description':'Request secure human credential entry. Contains metadata and field names only; does not approve or create credentials.','inputSchema':b.obj({**RESOURCE,'secret_kind':{'enum':list(SECRET_KINDS)},'purpose':ID,'systems':{'type':'array','items':ID,'minItems':1,'maxItems':5},'scopes':{'type':'array','items':ID,'minItems':1,'maxItems':20},'environment':{'enum':['TEST','PROD']},'test_workflow_id':ID,'test_workflow_hash':b.HASH,'accountable_role':ID,'rotation_days':{'type':'integer','minimum':1,'maximum':365},'used_by_nodes':{'type':'array','items':ID,'minItems':1,'maxItems':30},'fields_required':{'type':'array','items':ID,'minItems':1,'maxItems':12}})},
 {'name':'propose_template','description':'Save a validated workflow design as an Off template with explicit parameter slots; never copies credentials.','inputSchema':b.obj({**RESOURCE,'workflow_id':ID,'expected_hash':b.HASH,'parameters':{'type':'array','maxItems':20,'items':b.obj({'name':ID,'node_id':ID,'field_path':ID})}})}]
for tool in TOOLS:
 if tool['name']=='propose_secret_request':
  spec=tool['inputSchema'];spec['properties']['key']=ID;spec['required']=[k for k in spec['required'] if k not in ('resource_id','version','label','test_workflow_id','test_workflow_hash')];spec['oneOf']=[{'required':['key'],'not':{'required':['resource_id']}},{'required':['resource_id'],'not':{'required':['key']}}]
for t in TOOLS:t['annotations']={'readOnlyHint':t['name'].startswith(('list_','read_')),'idempotentHint':True,'destructiveHint':False,'openWorldHint':False}
NAMES={t['name'] for t in TOOLS}

def field_values(g):return {k:v.get('value') for k,v in g.get('fields',{}).items()}
def summary_agent(g):return {k:g.get(k) for k in ('id','name','capability','version','status')}|{'fields':field_values(g),'definition_hash':digest(g)}
def compact_report(report):
 report=copy.deepcopy(report);registry={}
 for f in report.get('findings',[]):
  refs=[]
  for d in f.pop('dependencies',[]):
   key=digest(d);registry[key]=d;refs.append(key)
  if refs:f['dependency_ids']=refs
  f.pop('location',None)
 report['dependencies']=registry
 return report

def compact_result(value,kind):
 result=copy.deepcopy(value)
 if kind=='agent':result['draft']=summary_agent(result['draft'])
 elif kind=='workflow':
  result['nodes']=[{'id':n['id'],'agent':summary_agent(n['data']['guided']),'draft_revision':n.get('data',{}).get('draft_revision'),'draft_hash':n.get('data',{}).get('guided_hash')} for n in result.get('nodes',[])]
 if 'validation' in result:result['validation']=compact_report(result['validation'])
 return result

def proposals(s):
 rows=[]
 for kind,records in s.state.items():
  for r in records.values():
   if not r.get('proposal_id'):continue
   rows.append({'proposal_id':r['proposal_id'],'id':r['id'],'kind':kind,'target':r.get('resource_ref',r['id']),'status':r['review_status'],'revision':r['revision'],'content_hash':r['content_hash'],'created_at':r.get('created_at'),'reviewed_at':r.get('reviewed_at'),'reason':r.get('review_reason')})
 return rows

def find_proposal(s,id):
 for kind,records in s.state.items():
  for r in records.values():
   if id in (r['id'],r.get('proposal_id')):return kind,r
 b.fail('not_found','Proposal is unavailable in this actor and company scope')

def latest_workflow(s,r):
 """Resolve same-actor proposed agent heads without mutating a pinned saved canvas."""
 out=copy.deepcopy(r);w=out['body'];revisions={}
 for n in w.get('nodes',[]):
  g=n['data']['guided'];agent=s.state['agents'].get(g['id'])
  native=next((a['body'].get('guided') for a in s.snapshot.get('agents',[]) if a['body'].get('id')==g['id'] and a['body'].get('guided')),None)
  if agent and agent.get('review_status')=='awaiting_user_review':
   n['data'].update(guided=copy.deepcopy(agent['body']),guided_hash=agent['content_hash'],draft_revision=agent['revision']);revisions[g['id']]={'revision':agent['revision'],'content_hash':agent['content_hash'],'proposal_id':agent.get('proposal_id'),'source':'same_actor_pending'}
  elif native:
   n['data'].update(guided=copy.deepcopy(native),guided_hash=digest(native),draft_revision=native.get('version'));revisions[g['id']]={'revision':native.get('version'),'content_hash':digest(native),'source':'current_saved_agent'}
  elif agent and agent.get('review_status')=='applied':
   n['data'].update(guided=copy.deepcopy(agent['body']),guided_hash=agent['content_hash'],draft_revision=agent['revision']);revisions[g['id']]={'revision':agent['revision'],'content_hash':agent['content_hash'],'source':'applied_actor_draft'}
 w['resolved_drafts']=revisions;return out

def resource(s,args,kind,content):
 id=args['resource_id'];version=args['version']
 if not re.fullmatch(r'[a-z][a-z0-9-]{2,63}',id) or not re.fullmatch(r'\d+\.\d+\.\d+',version):b.fail('invalid_resource_identity','Use lowercase slug only, no tenant prefix, and semantic version')
 pin=b.ref(kind,s.ctx['client']['id'],id,version);old=s.resources.get(pin)
 if old and old['content_hash']!=digest(content):b.fail('resource_version_conflict','Changed content requires a new version')
 if old:return {'resource_ref':pin,**old,'deduplicated':True}
 body={'id':id,'kind':kind,'version':version,'label':args['label'],'tenant':s.ctx['client']['id'],'company':s.ctx['company']['code'],'created_by':s.ctx['user']['id'],'created_at':s.store.now(),'status':'draft','content':content};body['content_hash']=digest(body)
 r=s.touch('resources',pin,body,resource_ref=pin);s.add_resource({**body,'ref':pin,'status':'proposed'})
 return {'resource_ref':pin,'proposal_id':r['proposal_id'],'status':'proposed','content_hash':digest(content),'activation_enabled':False}

def completeness(s,g):
 fields=field_values(g);cap=g['capability'];model=fields.get('execute.model_access') not in (None,'off');missing=[]
 external=fields.get('input.source_system') in ('outlook_graph','sharepoint','epicor_baq','epicor_rest','supabase') or cap in ('COMMS','WRITE')
 if external and not g.get('connection_requirements'):missing.append('external_connection')
 if (model or cap in ('DOC','RULE','WRITE')) and not g.get('fixtures'):missing.append('fixtures')
 if model:
  from .fixture_suite import fingerprint
  proof=g.get('fixture_suite',{})
  if not proof.get('passed') or not proof.get('usage_complete') or proof.get('contract_fingerprint')!=fingerprint(g):missing.append('passing_fixture_suite')
 if model and fields.get('execute.instructions') in (None,'none','needs_new_instructions'):missing.append('execute.instructions')
 if cap=='MAP' and not g.get('mapping'):missing.append('mapping')
 if cap=='CLASS' and not g.get('class_list'):missing.append('class_list')
 if cap=='COMMS' and not g.get('message_template'):missing.append('message_template')
 if cap in ('CLASS','REASON') and not model:missing.append('model_access')
 if model and fields.get('execute.cost_ceiling') in (None,'zero'):missing.append('cost_ceiling')
 return [{'rule_id':'complete-'+key,'field_paths':[key],'message':'Supply '+key+' before publish','blocks_publish':True} for key in missing]

async def handle(name,args,store,s):
 original_args=copy.deepcopy(args)
 if name=='list_secret_kinds':return {'items':[{'id':k,'required_fields':v[0],'scopes':v[1],'system':v[2]} for k,v in SECRET_KINDS.items()],'values_visible':False,'supported_request_environments':['TEST','PROD_after_passing_TEST_fixtures']}
 if name=='list_proposals':return {'items':[r for r in proposals(s) if not args.get('status') or r['status']==args['status']]}
 if name=='read_proposal':
  kind,r=find_proposal(s,args['id'])
  if kind=='change_sets':return b.build_changes.set_result(s,r)
  if kind=='agents':return compact_result(s.agent_result(r),'agent') if args.get('detail','summary')=='summary' else s.agent_result(r)
  if kind=='workflows':return compact_result(s.workflow_result(r),'workflow') if args.get('detail','summary')=='summary' else s.workflow_result(r)
  return copy.deepcopy(r)
 if name in ('list_runs','read_run','read_record'):
  return await observe(store,name,args)
 if name=='propose_instructions':
  schema_pin=args['model_contract']['output_schema']
  if schema_pin not in s.resources:b.fail('missing_dependency','Choose a versioned output schema',resource_id=schema_pin)
  result=resource(s,args,'instructions',{'text':args['text'],'model_contract':args['model_contract']})
 elif name=='propose_secret_request':
  args={**args,'resource_id':args.get('resource_id',args.get('key')),'version':args.get('version','1.0.0'),'label':args.get('label',args['purpose'])};args.pop('key',None)
  spec=SECRET_KINDS[args['secret_kind']]
  if args['environment']=='PROD':
   if not args.get('test_workflow_id') or not args.get('test_workflow_hash'):b.fail('test_fixture_evidence_required','A PROD request requires the current TEST workflow hash and a passing suite')
   tested=s.workflow(args['test_workflow_id']);s.check_hash(tested,args['test_workflow_hash'])
   if not tested['body'].get('nodes'):b.fail('test_fixture_evidence_required','A nonempty TEST workflow is required')
   for node in latest_workflow(s,tested)['body']['nodes']:
    from .fixture_suite import fingerprint
    g=node['data']['guided'];proof=g.get('fixture_suite',{})
    if g['fields'].get('identity.environment',{}).get('value')!='TEST' or not proof.get('passed') or not proof.get('usage_complete') or proof.get('contract_fingerprint')!=fingerprint(g):b.fail('test_fixture_evidence_required','Every current TEST node must pass its fixture suite before requesting PROD credentials')
  if sorted(args['fields_required'])!=sorted(spec[0]) or not set(args['scopes'])<=set(spec[1]) or spec[2] not in args['systems']:b.fail('invalid_secret_request','Use the registered field names, system and capabilities; values are never accepted')
  if any(x.endswith(('.write','.send')) for x in args['scopes']) and any(x.endswith('.read') for x in args['scopes']):b.fail('separate_write_connection','Request read and write capabilities as separate connections')
  content={'format':'flux-secret-request-v1',**{k:v for k,v in args.items() if k not in RESOURCE}}
  duplicate=next((r for r in s.resources.values() if isinstance(r.get('content'),dict) and r['content'].get('format')=='flux-secret-request-v1' and r['content'].get('secret_kind')==content['secret_kind'] and r['content'].get('environment')==content['environment'] and set(r['content'].get('scopes',[]))==set(content['scopes'])),None)
  result={'resource_ref':duplicate['id'],'status':duplicate['status'],'deduplicated':True,**{k:s.state['resources'].get(duplicate['id'],{}).get(k) for k in ('proposal_id','review_status')}} if duplicate else resource(s,args,'asset',content)
 elif name in ('propose_fixtures','propose_mapping'):
  r=s.agent(args['draft_id'],write=True);s.check_hash(r,args['expected_hash']);g=copy.deepcopy(r['body'])
  if name=='propose_mapping':
   if g['capability']!='MAP':b.fail('invalid_mapping','A mapping belongs to a MAP agent')
   from .rule_language import PATH
   if any(not re.fullmatch(PATH,v) for v in args['fields'].values()):b.fail('invalid_mapping','Use bounded input field paths')
   g['mapping']=args['fields']
  else:g['fixtures']=args['fixtures'];g['fixtures_hash']=digest(args['fixtures'])
  g.pop('fixture_suite',None);r=s.touch('agents',r['id'],g);result=s.agent_result(r)
 elif name=='archive_workflow':
  r=s.workflow(args['workflow_id'],write=True);s.check_hash(r,args['expected_hash']);g=copy.deepcopy(r['body'])
  runtime=await observe(store,'runtime_connections',{'workflow_id':r['id']})
  if runtime.get('active'):b.fail('runtime_active','Hold the runtime before proposing archival')
  result=resource(s,{'resource_id':'archive-'+args['request_id'],'version':'1.0.0','label':'Archive '+r['id']},'asset',{'format':'flux-workflow-archive-request-v1','workflow_id':r['id'],'expected_hash':r['content_hash'],'recoverable':True})
 elif name=='propose_template':
  r=s.workflow(args['workflow_id']);s.check_hash(r,args['expected_hash']);report=s.workflow_result(r)['validation']
  if report['blocks_publish']:b.fail('template_incomplete','Resolve validation findings before proposing a reusable template',validation=report)
  w=copy.deepcopy(latest_workflow(s,r)['body'])
  allowed={'input.source_system','identity.department','identity.company'}
  seen=set()
  for param in args['parameters']:
   if param['name'] in seen or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',param['name']) or param['field_path'] not in allowed or not any(n['id']==param['node_id'] for n in w['nodes']):b.fail('invalid_template_parameter','Use unique parameter names and existing node company, department or source-system fields; connection values remain separate')
   seen.add(param['name'])
  for n in w['nodes']:
   g=n['data']['guided'];g.pop('reusable_resources',None);g['connection_requirements']=[]
  result=resource(s,args,'template',{'format':'flux-workflow-template-v1','workflow':w,'parameters':args['parameters'],'execution_enabled':False})
 elif name=='run_fixture_suite':
  from .fixture_suite import run
  return await run(s,args)
 else:b.fail('unknown_tool','Unknown v2 tool')
 return result if b.ACTIVE_SESSION.get() else await s.commit(name,original_args,result)

async def observe(store,action,args):
 from . import fresh
 c=fresh.CTX.get();payload={**args,'access_token':c['token']} if c['token'].startswith('fmca_') else {**args,'tenant':c['client']['id'],'company':c['company']['id']}
 result=await store.CLIENT.post(fresh.URL+'/rest/v1/rpc/flux_builder_observe',headers={'apikey':fresh.KEY} if c['token'].startswith('fmca_') else dict(fresh.HEAD),json={'action':action,'args':payload})
 if result.status_code!=200:b.fail('runtime_read_denied','Runtime result is unavailable in this user, company and facility scope')
 data=result.json()
 if args.get('detail')=='summary' and action in ('read_run','read_record'):
  allowed=('id','run_id','record_id','workflow_id','stage','outcome','status','occurred_at','finished_at','metrics','result_hash','definition_hash')
  return {k:data[k] for k in allowed if k in data}
 return data

def compact_change_set(result):
 result=copy.deepcopy(result);result['diff_summary']=[{'op':x['op'],'path':x['path'],'before_hash':digest(x.get('before')),'after_hash':digest(x.get('after'))} for x in result.pop('diff',[])]
 result['members']=[{k:v for k,v in m.items() if k!='validation'} for m in result.get('members',[])]
 result['validation']=compact_report(result['validation']);return result
