"""Versioned MCP design proposals. No execution, publication, or activation surface."""
import copy,json,math,re,uuid
from contextvars import ContextVar
ACTIVE_SESSION=ContextVar("builder_staged_session",default=None)
from . import fresh,studio
from .core import Invalid,digest,schema,compatibility

class BuilderError(Invalid):
 def __init__(self,code,message,**details):self.error={'code':code,'message':message,**details};super().__init__(message)
def fail(code,message,**details):raise BuilderError(code,message,**details)
def obj(props,required=None):return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}
STR={'type':'string','minLength':1,'maxLength':160}
UUID={'type':'string','format':'uuid'}
HASH={'type':'string','pattern':'^[a-f0-9]{64}$'}
FIELD={'oneOf':[{'type':['string','null']},obj({'value':{'type':['string','null']},'why':{'type':'string','maxLength':1000}},['value'])]}
AGENT=obj({'capability':{'type':'string','enum':sorted(studio.CATALOG['capabilities'][i]['code'] for i in range(len(studio.CATALOG['capabilities'])))},'name_options':{'type':'array','items':{'type':'string','minLength':1,'maxLength':160},'minItems':3,'maxItems':3},'responsibility_options':{'type':'array','items':{'type':'string','minLength':1,'maxLength':4000},'minItems':3,'maxItems':3},'fields':{'type':'object','additionalProperties':FIELD},'questions_for_user':{'type':'array','items':STR,'maxItems':3}},['capability','name_options','responsibility_options','fields'])
EDGE=obj({'source':STR,'target':STR,'on_outcome':STR})
TOOLS=[
 {'name':'get_catalog','description':'Read stable field and option definitions plus the actual publish-rule metadata. Hash is cacheable; identity and registry choices are resolved separately.','inputSchema':obj({})},
 {'name':'list_resources','description':'List canonical non-secret resource pins, approval status and content hashes. Pending dependencies do not authorize publication.','inputSchema':obj({'kind':{'type':'string','enum':['schema','rules','instructions','template','asset']},'status':{'type':'string','enum':['proposed','draft','approved']},'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':100}},[])},
 {'name':'read_resource','description':'Read an exact versioned, non-secret resource reference returned by list_resources or propose_schema/propose_rule.','inputSchema':obj({'id':STR})},
 {'name':'read_agent_draft','description':'Read a saved or proposed agent draft with revision, hash, review status and fresh server validation.','inputSchema':obj({'draft_id':STR})},
 {'name':'update_agent_draft','description':'Propose a targeted field patch. Requires current hash and stable request UUID. Does not overwrite other fields. Any prior review is invalidated.','inputSchema':obj({'request_id':UUID,'draft_id':STR,'expected_hash':HASH,'fields':{'type':'object','minProperties':1,'additionalProperties':FIELD}})},
 {'name':'propose_connected_workflow','description':'Propose a bounded set of agents and semantic FLUX handoff edges atomically. Browser Apply saves the connected canvas, still Off.','inputSchema':obj({'request_id':UUID,'name':STR,'workflow_id':STR,'expected_hash':HASH,'nodes':{'type':'array','minItems':1,'maxItems':30,'items':obj({'key':STR,'agent':AGENT,'draft_id':STR},['key'])},'edges':{'type':'array','maxItems':100,'items':EDGE}},['request_id','name','nodes','edges'])},
 {'name':'propose_connections','description':'Atomically add a set of validated handoff edges to a workflow proposal. Invalid endpoints/outcomes or incompatible known contracts save nothing.','inputSchema':obj({'request_id':UUID,'workflow_id':STR,'expected_hash':HASH,'edges':{'type':'array','minItems':1,'maxItems':100,'items':EDGE}})},
 {'name':'propose_schema','description':'Propose a bounded object JSON Schema for Resources review. Returns its immutable canonical pin; no model approval.','inputSchema':obj({'request_id':UUID,'resource_id':STR,'version':STR,'label':STR,'schema':{'type':'object'}})},
 {'name':'propose_rule','description':'Propose structured equals/present/tolerance checks for Resources review. Tolerance checks remain planning-only until runtime support is certified.','inputSchema':obj({'request_id':UUID,'resource_id':STR,'version':STR,'label':STR,'rule':{'type':'array','minItems':1,'maxItems':50,'items':{'type':'object'}}})},
 {'name':'propose_discovery_waiver','description':'Ask a client owner to explicitly waive discovery. Browser owner approval is mandatory; this tool cannot grant the waiver.','inputSchema':obj({'request_id':UUID,'reason':{'type':'string','minLength':1,'maxLength':4000},**{k:{'type':'array','minItems':1,'maxItems':30,'items':{'type':'string','minLength':1,'maxLength':2000}} for k in ('assumptions','credential_requirements','accountable_roles')}})}]
for t in TOOLS:t['annotations']={'readOnlyHint':t['name'].startswith(('get_','list_','read_')),'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}
from . import build_changes
AGENT['properties']['connection_requirements']={'type':'array','items':build_changes.CONNECTION,'maxItems':20}
for tool in TOOLS:
 if tool['name'] in ('propose_connected_workflow','propose_connections'):tool['inputSchema']['properties'].update(build_changes.ROUTES)
for tool in TOOLS:
 if tool['name']=='update_agent_draft':
  tool['inputSchema']['properties']['connection_requirements']={'type':'array','items':build_changes.CONNECTION,'maxItems':20}
from . import mcp_v2
TOOLS+=build_changes.TOOLS+mcp_v2.TOOLS
for tool in TOOLS:
 if tool['name'] in ('read_workflow','read_agent_draft','read_resource'):
  tool['inputSchema']['properties']['detail']=mcp_v2.DETAIL
AGENT['properties'].update(bindings={'type':'object','properties':{'reads':{'type':'object'},'writes':{'type':'object'}},'additionalProperties':False},input_config={'type':'object'},trigger_config={'type':'object'},fixtures={'type':'array','maxItems':20,'items':mcp_v2.FIXTURE},mapping={'type':'object','additionalProperties':STR},class_list={'type':'array','maxItems':100,'items':STR},message_template={'type':'string','minLength':1,'maxLength':10000})
NAMES={t['name'] for t in TOOLS}|{'submit_agent_draft','read_workflow','builder_context','submit_workflow_plan'}

def strict_json(value):
 try:encoded=json.dumps(value,allow_nan=False)
 except (ValueError,TypeError):fail('invalid_json','Use finite JSON values only')
 if len(encoded)>200000:fail('request_too_large','Proposal exceeds 200 KB')
 from .mcp_connection import no_secrets
 no_secrets(value)
def validate_rule(checks):
 from .rule_language import validate
 try:return validate(checks)
 except ValueError as e:fail('invalid_rule',str(e),field_path='rule',required_key='op')
async def rpc(store,action,args=None):
 c=fresh.CTX.get();b=dict(args or {})
 if c['token'].startswith('fmca_'):b['access_token']=c['token'];headers={'apikey':fresh.KEY}
 else:b.update(tenant=c['client']['id'],company=c['company']['id']);headers=dict(fresh.HEAD)
 r=await store.CLIENT.post(fresh.URL+'/rest/v1/rpc/flux_builder_session',headers=headers,json={'action':action,'args':b})
 if r.status_code!=200:
  try:e=r.json()
  except Exception:e={}
  reason=e.get('message','');code='conflict' if reason.startswith('BUILDER_CONFLICT') else 'access_denied'
  message='Builder operation denied or unavailable'
  if code=='conflict':
   message='request_id was already used; retry the original content or use a new UUID' if 'request_id' in reason else 'Resource version already has different content; choose a new version' if 'immutable resource' in reason else 'Draft or source changed; read the current revision and reconcile before retrying'
  fail(code,message)
 return r.json()
def ref(kind,tenant,id,version):return kind+':'+tenant+'.'+id+'@'+version
class Session:
 def __init__(self,store,snapshot):
  self.store=store;self.ctx=fresh.CTX.get();self.snapshot=snapshot;self.state=copy.deepcopy(snapshot.get('document') or {});self.changed={};self.resources={}
  for kind in ('agents','workflows','resources','waivers','plans','change_sets'):self.state.setdefault(kind,{})
  for raw in snapshot.get('resources',[]):self.add_resource(raw)
  for r in self.state['resources'].values():self.add_resource({**r['body'],'ref':r['resource_ref'],'approved':False,'status':'proposed'})
 def add_resource(self,r):
  if r.get('kind')=='credential' or 'encrypted_value' in r:return
  content=r.get('content',r.get('schema'));canonical=r.get('ref')
  if not canonical:canonical=r['kind']+':'+(r['id'] if r.get('canonical') else self.ctx['client']['id']+'.'+r['id'])+'@'+r['version']
  item={'id':canonical,'kind':r['kind'],'version':r['version'],'label':r.get('label',r['id']),'content':content,'content_hash':digest(content),'status':'approved' if r.get('approved') else r.get('status','draft')}
  old=self.resources.get(canonical)
  if old and old['content_hash']!=item['content_hash']:fail('resource_version_conflict','One resource version resolved to different content; repair the registry before building',resource_id=canonical)
  if not old or item['status']=='approved':self.resources[canonical]=item
 def catalog(self):
  cat=copy.deepcopy(studio.CATALOG)
  for step in cat['steps']:
   for f in step['fields']:
    if f['id']=='identity.owner':f['options']=[{'id':self.ctx['user']['id'],'label':'Authenticated owner'}]
    if f['id']=='identity.company':f['options']=[{'id':self.ctx['company']['code'],'label':self.ctx['company']['name']}]
    wanted={'published_schemas':'schema','approved_rules':'rules','instructions':'instructions'}.get(f.get('registry'))
    if wanted:f['options']+= [{'id':r['id'],'label':r['label'],'content_hash':r['content_hash']} for r in self.resources.values() if r['kind']==wanted]
    f['options']=list({x['id']:x for x in f['options']}.values())
  return cat
 def fields(self,patch,existing=None,capability=None):
  if not isinstance(patch,dict):fail('invalid_fields','fields must be an object')
  specs={f['id']:f for step in self.catalog()['steps'] for f in step['fields']};out=copy.deepcopy(existing or {});locked=[]
  for key,candidate in patch.items():
   if key not in specs:fail('invalid_field','Unsupported field path',field_path=key)
   if isinstance(candidate,dict):
    if set(candidate)-{'value','why'} or 'value' not in candidate:fail('invalid_field','Use value and optional why; provenance cannot be supplied',field_path=key)
    value=candidate['value'];why=candidate.get('why','MCP proposal')
    if not isinstance(why,str) or len(why)>1000:fail('invalid_field','why must be text under 1000 characters',field_path=key)
   else:value=candidate;why='MCP proposal'
   options=[o['id'] for o in specs[key]['options']]
   if value is not None and (not isinstance(value,str) or value not in options):fail('invalid_option','Choose an exact catalog option identifier or null',field_path=key,submitted_value=value,allowed_values=options)
   old=(existing or {}).get(key,{})
   if key=='identity.owner' and value not in (None,self.ctx['user']['id']):fail('unauthorized_owner','Owner must match the authenticated connection',field_path=key)
   if key=='identity.company' and value not in (None,self.ctx['company']['code']):fail('unauthorized_scope','Company must match this connection',field_path=key)
   protected=studio.decision_locked(key,capability,value,self.catalog())
   if protected and value is not None and key not in ('identity.owner','identity.environment') and value!=old.get('value'):locked.append({'field_path':key,'submitted_value':value})
   if key=='identity.environment' and value not in (None,'TEST'):fail('human_decision_required','MCP drafts are TEST-only',field_path=key)
   out[key]=old if existing and value==old.get('value') else {'value':value,'why':why,'source':'model' if value is not None else 'missing'}
  for rejected in locked:out[rejected['field_path']]['source']='proposed'
  for key in specs:out.setdefault(key,{'value':None,'why':'Human choice required','source':'missing'})
  out['identity.owner']={'value':self.ctx['user']['id'],'source':'verified_identity','why':'Authenticated connection identity'}
  out['identity.company']={'value':self.ctx['company']['code'],'source':'server','why':'Connection company'}
  out['identity.environment']={'value':'TEST','source':'proposed' if 'identity.environment' in patch else 'server','why':'Proposal-only TEST environment; confirm in browser'}
  return out
 def guided(self,a,id):
  from jsonschema import validate,ValidationError
  try:validate(a,AGENT)
  except ValidationError as e:fail('invalid_agent',e.message,field_path='agent.'+'.'.join(map(str,e.absolute_path)))
  return {'id':id,'version':'0.1.0','name':a['name_options'][0],'responsibility':a['responsibility_options'][0],'name_options':a['name_options'],'responsibility_options':a['responsibility_options'],'capability':a['capability'],'fields':self.fields(a['fields'],capability=a['capability']),'connection_requirements':a.get('connection_requirements',[]),'questions_for_user':a.get('questions_for_user',[]),'catalog_version':studio.CATALOG['version'],'guide_version':studio.CATALOG['guide_version'],'input_config':{'kind':'flux'},'trigger_config':{'kind':'webhook','source':'flux','delivery':'webhook','timezone':'America/Chicago'},'user_edits':[],'fixtures':a.get('fixtures',[]),'mapping':a.get('mapping',{}),'class_list':a.get('class_list',[]),'message_template':a.get('message_template'),'builder_version':2,'bindings':a.get('bindings',{}),**{k:copy.deepcopy(a[k]) for k in ('trigger_config','input_config') if k in a}}
 def validation(self,g):
  cat=self.catalog();base=studio.blockers(g['capability'],g.get('fields',{}),cat);findings=[];by={r['id']:r for r in cat['rules']}
  for b in base:
   rule=by.get(b['id']);paths=[b['field']] if b.get('field') else [c['field'] for c in (rule or {}).get('checks',[]) if c.get('field')]
   if not paths and b['id'].startswith('human-'):paths=[b['id'].removeprefix('human-')]
   findings.append({'rule_id':b['id'],'field_paths':paths,'message':b['message'],'blocks_publish':True})
  if not g.get('name') or not g.get('responsibility'):findings.append({'rule_id':'identity-name','field_paths':['name','responsibility'],'message':'Choose one name and one responsibility.','blocks_publish':True})
  for key in ('input.schema','output.schema','execute.rule','execute.instructions'):
   value=g.get('fields',{}).get(key,{}).get('value');r=self.resources.get(value)
   if r and r['status']!='approved':findings.append({'rule_id':'dependency-not-approved','field_paths':[key],'resource_id':value,'message':'Review and approve this exact resource version in Resources.','blocks_publish':True})
   if r and r['kind']=='rules' and isinstance(r['content'],list) and any(isinstance(c,dict) and c.get('op')=='within_tolerance' for c in r['content']):findings.append({'rule_id':'rule-runtime-support','field_paths':[key],'message':'Tolerance rules are planning artifacts. Certify a supported runtime implementation before publication.','blocks_publish':True})
  from .workflow_contract import enrich
  findings=enrich(self,findings+build_changes.connection_findings(self,g)+(mcp_v2.completeness(self,g) if g.get('builder_version')==2 else []),g)
  return {'valid':not findings,'blocks_publish':bool(findings),'findings':findings,'catalog_version':cat['version'],'catalog_rule_count':len(cat['rules']),'definition_hash':digest(g),'validation_scope':'Six-function design contract and dependencies; runtime certification still required','runtime_certified':False}
 def touch(self,kind,id,body,**extra):
  old=self.state[kind].get(id);record={**(old or {}),'created_at':(old or {}).get('created_at',self.store.now()),'id':id,'kind':kind,'body':copy.deepcopy(body),'revision':(old or {}).get('revision',0)+1,'content_hash':digest(body),'review_status':'awaiting_user_review','proposal_id':(old or {}).get('proposal_id',str(uuid.uuid5(uuid.NAMESPACE_URL,':'.join([self.ctx['client']['id'],self.ctx['company']['id'],self.ctx['user']['id'],kind,id])))),**extra}
  
  for key in ('applied_result','applied_hash','approved_by','approved_at','reviewed_by','reviewed_at'):record.pop(key,None)
  self.state[kind][id]=record;self.changed[(kind,id)]=record;return record
 def agent(self,id,write=False):
  if id in self.state['agents']:r=self.state['agents'][id]
  else:
   r=None
   for item in self.snapshot.get('legacy',[]):
    if item.get('proposal',{}).get('kind')=='agent' and id in (item.get('id'),'draft-mcp-'+item.get('id','')):
     g=copy.deepcopy(item['proposal']['guided']);g.update(id=id,version='0.1.0',name=g['name_options'][0],responsibility=g['responsibility_options'][0]);r={'id':id,'kind':'agents','body':g,'revision':0,'content_hash':digest(g),'review_status':'awaiting_user_review'};break
   if not r:
    for native in self.snapshot.get('agents',[]):
     if native['body']['id']==id:
      if write and not native['can_edit']:fail('access_denied','Agent edit permission required')
      g=copy.deepcopy(native['body'].get('guided'))
      if not g:fail('unsupported_agent','Only guided draft definitions can be edited through this tool')
      r={'id':id,'kind':'agents','body':g,'revision':0,'content_hash':digest(g),'native_source':{'path':native['path'],'content_hash':native['body']['content_hash']},'review_status':'requires_renewed_review'};break
   if not r:
    for native in self.snapshot.get('workflows',[]):
     for n in native['body'].get('nodes',[]):
      g=n.get('data',{}).get('guided',{})
      if g.get('id')==id:
       if write and not native['can_edit']:fail('access_denied','Workflow edit permission required')
       r={'id':id,'kind':'agents','body':copy.deepcopy(g),'revision':0,'content_hash':digest(g),'workflow_id':native['body']['id'],'node_id':n['id'],'position':n['position'],'review_status':'requires_renewed_review'}
       if write:self.workflow(native['body']['id'],write=True)
       break
   if not r:fail('not_found','Agent draft not found in this company',draft_id=id)
   self.state['agents'][id]=r
  if write and r.get('native_source'):
   native=next((a for a in self.snapshot.get('agents',[]) if a['body']['id']==id),None)
   if not native or not native['can_edit'] or native['body']['content_hash']!=r['native_source']['content_hash']:fail('conflict','Saved agent changed or edit permission was removed; refresh and reconcile the proposal')
  owner=r['body'].get('fields',{}).get('identity.owner',{}).get('value')
  if write and owner not in (None,self.ctx['user']['id']):fail('unauthorized_owner','Draft owner differs from this authenticated connection')
  return r
 def workflow(self,id,write=False):
  if id in self.state['workflows']:
   r=self.state['workflows'][id]
   if write and r.get('native_source'):
    native=next((w for w in self.snapshot.get('workflows',[]) if w['body']['id']==id),None)
    if not native or not native['can_edit'] or native['body']['content_hash']!=r['native_source']['content_hash']:fail('conflict','Native canvas changed or edit permission was removed; refresh and reconcile the proposal')
   return r
  native=next((w for w in self.snapshot.get('workflows',[]) if w['body']['id']==id),None)
  if not native or write and not native['can_edit']:fail('not_found','Workflow is unavailable for this company or operation',workflow_id=id)
  body=copy.deepcopy(native['body'])
  for n in body.get('nodes',[]):
   if n.get('data',{}).get('guided'):n['data'].update(power='Off',guided_hash=digest(n['data']['guided']))
  r={'id':id,'kind':'workflows','body':body,'revision':0,'content_hash':body['content_hash'],'native_source':{'path':native['path'],'content_hash':body['content_hash']},'review_status':'requires_renewed_review'};self.state['workflows'][id]=r
  for n in body.get('nodes',[]):
   g=n.get('data',{}).get('guided')
   if not g:fail('unsupported_workflow','All nodes must have guided draft contracts')
   self.state['agents'].setdefault(g['id'],{'id':g['id'],'kind':'agents','body':copy.deepcopy(g),'revision':0,'content_hash':digest(g),'review_status':'requires_renewed_review'})
  return r
 def agent_result(self,r):
  result={k:r[k] for k in ('id','revision','content_hash','review_status')};result.update(draft_id=r['id'],draft=copy.deepcopy(r['body']),validation=self.validation(r['body']),activation_enabled=False,review_url='/ai-connections',proposal_id=r.get('proposal_id'))
  if r.get('workflow_id'):result.update({k:r[k] for k in ('workflow_id','node_id','position') if k in r})
  for w in self.state['workflows'].values():
   n=next((n for n in w['body'].get('nodes',[]) if n['data']['guided']['id']==r['id']),None)
   if n:result.update(workflow_id=w['id'],node_id=n['id'],position=n['position'],workflow_content_hash=w['content_hash'],workflow_proposal_id=w.get('proposal_id'));break
  return result
 def pending_proposals(self,w):
  result=[]
  for n in w.get('nodes',[]):
   g=n.get('data',{}).get('guided',{});r=self.state['agents'].get(g.get('id'))
   if r and r.get('review_status')=='awaiting_user_review' and r.get('proposal_id'):
    result.append({'draft_id':r['id'],'node_id':n['id'],'proposal_id':r['proposal_id'],'revision':r['revision'],'content_hash':r['content_hash'],'differs_from_canvas':digest(g)!=digest(r['body'])})
  return result
 def graph(self,w,new_edges=None,caller_keys=None):
  nodes={n['id']:n for n in w['nodes']};edges=copy.deepcopy(w.get('edges',[]));seen={(e['source'],e['target'],e.get('sourceHandle')) for e in edges}
  for e in new_edges or []:
   source,target=e['source'],e['target'];outcome=e['on_outcome']
   if source not in nodes or target not in nodes or source==target:fail('invalid_connection','Endpoints must be distinct members of this workflow',connection=e)
   source_g=nodes[source]['data']['guided'];target_g=nodes[target]['data']['guided'];outcomes=studio.CATALOG['outcomes'].get(source_g['fields'].get('output.outcomes',{}).get('value'),[])
   if outcome not in outcomes:fail('invalid_outcome','Choose an outcome declared by the source agent',connection=e,allowed_values=outcomes)
   if any(x['source']==source and x.get('sourceHandle')==outcome and x['target']!=target for x in edges):fail('ambiguous_handoff','One outcome must have one target; propose explicit outcome routing')
   key=(source,target,outcome)
   if key in seen:continue
   edges.append({'id':str(uuid.uuid5(uuid.NAMESPACE_URL,w['id']+':'+':'.join(key))),'source':source,'target':target,'sourceHandle':outcome,'targetHandle':'input','label':outcome,'data':{'direct':True,'semantics':'Durable FLUX handoff; no direct agent call','dispatch_enabled':False}});seen.add(key)
  for e in edges:
   if e['source'] not in nodes or e['target'] not in nodes:fail('invalid_connection','Stored edge endpoint is not a workflow member')
   choices=studio.CATALOG['outcomes'].get(nodes[e['source']]['data']['guided']['fields'].get('output.outcomes',{}).get('value'),[])
   if e.get('sourceHandle') not in choices:fail('invalid_outcome','Existing handoff is no longer declared by the source; reconcile connections before changing outcomes',edge_id=e['id'],allowed_values=choices)
  adjacent={k:[] for k in nodes}
  for e in edges:adjacent[e['source']].append(e['target'])
  visiting=set();done=set()
  def visit(n):
   if n in visiting:fail('workflow_cycle','Connected drafts must form an acyclic workflow')
   if n in done:return
   visiting.add(n)
   for t in adjacent[n]:visit(t)
   visiting.remove(n);done.add(n)
  for n in nodes:visit(n)
  w['edges']=edges;findings=[]
  for e in edges:
   a=nodes[e['source']]['data']['guided'];b=nodes[e['target']]['data']['guided'];left=self.resources.get(a['fields'].get('output.schema',{}).get('value'));right=self.resources.get(b['fields'].get('input.schema',{}).get('value'))
   if left and right and not compatibility(left['content'],right['content']):fail('incompatible_connection','Source output does not satisfy target input schema',edge_id=e['id'],source=e['source'],target=e['target'],source_key=(caller_keys or {}).get(e['source'],e['source']),target_key=(caller_keys or {}).get(e['target'],e['target']),source_schema={'id':left['id'],'content_hash':left['content_hash']},target_schema={'id':right['id'],'content_hash':right['content_hash']},pending_proposals=self.pending_proposals(w),field_paths=['output.schema','input.schema'])
   proven=bool(left and right);e['data'].update(compatible=proven,gaps=[] if proven else ['Choose versioned input/output schemas to verify this handoff.'])
   if not proven:findings.append({'rule_id':'unverified-connection-contract','field_paths':[e['source']+'.output.schema',e['target']+'.input.schema'],'message':e['data']['gaps'][0],'blocks_publish':True})
  return findings
 def workflow_result(self,r):
  from .workflow_contract import validate
  w=mcp_v2.latest_workflow(self,r)['body'];resolved_hash=digest(w)
  return {**w,'resolved_content_hash':resolved_hash,'snapshot_content_hash':r['content_hash'],'workflow_id':r['id'],'revision':r['revision'],'content_hash':r['content_hash'],'proposal_id':r.get('proposal_id'),'review_status':r['review_status'],'validation':validate(self,w),'pending_proposals':self.pending_proposals(w),'activation_enabled':False}
 def new_workflow(self,id,name):
  return {'id':id,'name':name,'version':'0.0.1','nodes':[],'edges':[],'binding_mode':'records','format':'canvas-v2','status':'draft','execution_enabled':False,'tenant':self.ctx['client']['id'],'company':self.ctx['company']['code'],'facility':self.ctx['company']['facility'],'actor':self.ctx['user']['id']}
 def check_hash(self,r,expected):
  if expected!=r['content_hash']:fail('conflict','Draft changed; read its current hash before retrying',expected_hash=expected,current_hash=r['content_hash'],revision=r['revision'])
 def placement(self,w,g):
  node_id=str(uuid.uuid5(uuid.NAMESPACE_URL,w['id']+':'+g['id']));old=next((n for n in w['nodes'] if n['id']==node_id),None)
  if old:
   old['data'].update(guided=copy.deepcopy(g),guided_hash=digest(g),power='Off');return old
  x=max([n['position']['x'] for n in w['nodes']],default=-260)+360;node={'id':node_id,'type':'capability','position':{'x':x,'y':120},'data':{'guided':copy.deepcopy(g),'guided_hash':digest(g),'capability':g['capability'],'status':'Choices needed','power':'Off'}};w['nodes'].append(node);return node
 async def source(self,source):
  kind=source.get('kind')
  if kind=='workflow':
   r=self.workflow(source['workflow_id']);self.check_hash(r,source['content_hash'])
   if r.get('native_source'):
    current=next((w for w in self.snapshot.get('workflows',[]) if w['body']['id']==r['id']),None)
    if not current or current['body']['content_hash']!=r['native_source']['content_hash']:fail('conflict','The source canvas changed; reconcile the plan with its current hash')
   return source
  if kind=='waiver':
   r=self.state['waivers'].get(source['waiver_id'])
   if not r or r.get('review_status')!='approved' or r['content_hash']!=source['content_hash']:fail('discovery_waiver_required','An owner must approve this exact waiver in FLUX first')
   return source
  if kind=='discovery':
   from .discovery import context
   d=await context(self.store)
   if not d.get('submitted') or d.get('revision')!=source['revision'] or d.get('content_hash')!=source['content_hash']:fail('conflict','Use the current submitted discovery revision and hash')
   return source
  fail('invalid_plan_source','Ground the plan in submitted discovery, an existing workflow hash, or an owner-approved waiver')

 def audit_change(self,r):
  return {'kind':r['kind'],'id':r['id'],'revision':r['revision'],'content_hash':r['content_hash'],'validation':self.validation(r['body']) if r['kind']=='agents' else self.workflow_result(r)['validation'] if r['kind']=='workflows' else build_changes.set_result(self,r)['validation'] if r['kind']=='change_sets' else {'blocks_publish':True,'reason':'Human review required'}}
 async def commit(self,name,args,result):
  required={n['data']['guided']['id'] for (kind,_),w in self.changed.items() if kind=='workflows' for n in w['body']['nodes']}
  original=self.snapshot.get('document') or {}
  for id in required:
   if id not in original.get('agents',{}) and ('agents',id) not in self.changed:self.touch('agents',id,self.state['agents'][id]['body'])
  for kind,records in self.state.items():
   for id in list(records):
    if id not in original.get(kind,{}) and (kind,id) not in self.changed:del records[id]
  for r in self.changed.values():r['request_id']=args['request_id']
  from .mcp_connection import no_secrets
  no_secrets(self.state,limit=2000000)
  changed=[self.audit_change(r) for r in self.changed.values()]
  return await rpc(self.store,'commit',{'request_id':args['request_id'],'request_hash':digest({'tool':name,'arguments':args}),'expected_revision':self.snapshot['revision'],'document':self.state,'changes':changed,'changed_fields':list(args.get('fields',{})),'response':result})

def validate_arguments(name,args):
 from jsonschema import Draft202012Validator,FormatChecker
 from . import mcp_connection
 spec=next(t['inputSchema'] for t in mcp_connection.tools() if t['name']==name)
 error=next(iter(Draft202012Validator(spec,format_checker=FormatChecker()).iter_errors(args)),None)
 strict_json(args)
 if error:fail('invalid_request','Request does not satisfy the tool schema',field_path='.'.join(map(str,error.absolute_path)),constraint=error.validator)

async def dispatch(name,args,store):
 validate_arguments(name,args)
 if name=='get_catalog':
  cat=copy.deepcopy(studio.CATALOG)
  return {'catalog':cat,'content_hash':digest(cat),'catalog_rule_count':len(cat['rules']),'cacheable':True,'identity_options':'builder_context.identity; server resolves owner and company','registry_options':'list_resources'}
 request_id=args.get('request_id');request_hash=digest({'tool':name,'arguments':args})
 active=ACTIVE_SESSION.get()
 snap=active.snapshot if active else await rpc(store,'snapshot',{'request_id':request_id,'request_hash':request_hash} if request_id else {})
 if not active and snap.get('cached'):return snap['response']
 s=active or Session(store,snap)
 if name in mcp_v2.NAMES:return await mcp_v2.handle(name,args,store,s)
 if name in build_changes.NAMES:return await build_changes.handle(name,args,store,s)
 if name=='list_resources':
  rows=[{k:v for k,v in r.items() if k!='content'} for r in sorted(s.resources.values(),key=lambda r:r['id']) if (not args.get('kind') or r['kind']==args['kind']) and (not args.get('status') or r['status']==args['status'])];offset=args.get('offset',0);limit=args.get('limit',25)
  return {'items':rows[offset:offset+limit],'next_offset':offset+limit if offset+limit<len(rows) else None}
 if name=='read_resource':
  r=s.resources.get(args['id'])
  if not r:fail('not_found','Resource is unavailable in this company',resource_id=args['id'])
  return {k:v for k,v in r.items() if k!='content'} if args.get('detail')=='summary' else r
 if name=='builder_context':
  from .mcp_connection import identity,rpc as old_rpc
  return {'identity':identity(),'profile':await old_rpc(store,'mcp_profile',{'access_token':s.ctx['token']}),'catalog':s.catalog(),'catalog_hash':digest(studio.CATALOG),'resources':[{**{k:v for k,v in r.items() if k!='content'},**({'schema':r['content']} if r['kind']=='schema' and args.get('detail')!='summary' else {'title':r['content'].get('title'),'required':r['content'].get('required',[])} if r['kind']=='schema' else {})} for r in sorted(s.resources.values(),key=lambda r:r['id'])],'completeness_matrix':mcp_v2.COMPLETENESS,'secret_kinds':[{'id':k,'required_fields':v[0],'scopes':v[1]} for k,v in mcp_v2.SECRET_KINDS.items()],'connections':s.snapshot.get('connections',[]),'templates':[r for r in s.resources.values() if r['kind']=='template'],'instructions':'One responsibility per agent. Use exact catalog IDs and resource pins. Invalid values are rejected. Publication, credentials and activation require human review in FLUX. Drafts remain TEST and Off.'}
 if name=='read_agent_draft':
  r=s.agent_result(s.agent(args['draft_id']));return mcp_v2.compact_result(r,'agent') if args.get('detail')=='summary' else r
 if name=='read_workflow':
  r=s.workflow_result(s.workflow(args['workflow_id']));return mcp_v2.compact_result(r,'workflow') if args.get('detail')=='summary' else r
 if name=='submit_agent_draft':
  id='draft-mcp-'+request_id;g=s.guided(args['agent'],id);r=s.touch('agents',id,g);w=s.new_workflow('canvas-mcp-'+request_id,g['name']+' workflow');s.placement(w,g);s.touch('workflows',w['id'],w);result=s.agent_result(r)
 elif name=='update_agent_draft':
  old=s.agent(args['draft_id'],write=True);s.check_hash(old,args['expected_hash']);g=copy.deepcopy(old['body']);g['fields']=s.fields(args['fields'],g['fields'],g['capability'])
  if 'connection_requirements' in args:g['connection_requirements']=copy.deepcopy(args['connection_requirements'])
  r=s.touch('agents',old['id'],g)
  for wid,w in list(s.state['workflows'].items()):
   s.workflow(wid,write=True);body=copy.deepcopy(w['body']);changed=False
   for n in body['nodes']:
    if n.get('data',{}).get('guided',{}).get('id')==r['id']:n['data']['guided']=copy.deepcopy(g);n['data']['guided_hash']=digest(g);n['data']['power']='Off';changed=True
   if changed:s.graph(body);s.touch('workflows',wid,body)
  # Standalone native definitions are represented by a reviewable draft canvas.
  if not any(n['data']['guided']['id']==r['id'] for w in s.state['workflows'].values() for n in w['body']['nodes']):
   w=s.new_workflow('canvas-edit-'+str(uuid.uuid5(uuid.NAMESPACE_URL,r['id'])),g['name']+' review');s.placement(w,g);s.touch('workflows',w['id'],w)
  result=s.agent_result(r)
 elif name in ('propose_connected_workflow','propose_connections'):
  if args.get('workflow_id'):
   old=s.workflow(args['workflow_id'],write=True);s.check_hash(old,args.get('expected_hash'));w=mcp_v2.latest_workflow(s,old)['body'];w.pop('resolved_drafts',None)
  else:
   if args.get('expected_hash'):fail('invalid_request','expected_hash requires workflow_id')
   w=s.new_workflow('canvas-mcp-'+request_id,args['name'])
  aliases={n['id']:n['id'] for n in w['nodes']}
  for item in args.get('nodes',[]):
   key=item['key']
   if key in aliases:fail('invalid_node','Node keys must be unique',node_key=key)
   if ('agent' in item)==('draft_id' in item):fail('invalid_node','Supply exactly one agent or draft_id',node_key=key)
   if 'draft_id' in item:r=s.agent(item['draft_id'],write=True)
   else:
    id='draft-'+str(uuid.uuid5(uuid.NAMESPACE_URL,request_id+':'+key));r=s.touch('agents',id,s.guided(item['agent'],id))
   node=s.placement(w,r['body']);aliases[key]=node['id']
  edges=[{**e,'source':aliases.get(e['source'],e['source']),'target':aliases.get(e['target'],e['target'])} for e in args['edges']];s.graph(w,edges,caller_keys={v:k for k,v in aliases.items()})
  if len(w['nodes'])>100 or len(w['edges'])>100:fail('workflow_too_large','Use at most 100 nodes and edges')
  if 'entry_nodes' in args:w['entry_nodes']=[aliases.get(k,k) for k in args['entry_nodes']]
  if 'terminal_outcomes' in args:w['terminal_outcomes']=[{**x,'node':aliases.get(x['node'],x['node'])} for x in args['terminal_outcomes']]
  r=s.touch('workflows',w['id'],w);result=s.workflow_result(r);result['node_keys']=aliases;result['drafts']=[s.agent_result(s.agent(n['data']['guided']['id'])) for n in w['nodes']]
 elif name in ('propose_schema','propose_rule'):
  kind='schema' if name=='propose_schema' else 'rules';id=args['resource_id'];version=args['version']
  if not re.fullmatch(r'[a-z][a-z0-9-]{2,63}',id) or not re.fullmatch(r'\d+\.\d+\.\d+',version):fail('invalid_resource_identity','Use a lowercase slug only, no tenant prefix (3–64 characters), and semantic version',field_path='resource_id/version')
  content=args['schema'] if kind=='schema' else validate_rule(args['rule'])
  if kind=='schema':
   try:schema(content)
   except Exception as e:fail('invalid_schema',str(e),field_path='schema')
  pin=ref(kind,s.ctx['client']['id'],id,version);existing=s.resources.get(pin)
  if existing and existing['content_hash']!=digest(content):fail('resource_version_conflict','Changed content requires a new resource version',resource_id=pin,current_hash=existing['content_hash'])
  if existing:result={**existing,'deduplicated':True,'activation_enabled':False}
  else:
   body={'id':id,'version':version,'kind':kind,'label':args['label'],'content':content,'tenant':s.ctx['client']['id'],'created_by':s.ctx['user']['id'],'created_at':store.now(),'use_roles':['owner','editor'],'status':'draft','schema_version':'1.0.0'};body['content_hash']=digest(body)
   r=s.touch('resources',pin,body,resource_ref=pin);s.add_resource({**body,'ref':pin,'status':'proposed'});result={**s.resources[pin],'proposal_id':r['proposal_id'],'review_status':r['review_status'],'activation_enabled':False}
 elif name=='propose_discovery_waiver':
  id='waiver-'+request_id;r=s.touch('waivers',id,{k:args[k] for k in ('reason','assumptions','credential_requirements','accountable_roles')});result={k:r[k] for k in ('id','revision','content_hash','review_status','proposal_id')};result.update(owner_approval_required=True,activation_enabled=False)
 elif name=='submit_workflow_plan':
  source=await s.source(args['source']);id='plan-'+request_id;r=s.touch('plans',id,{'source':source,'plan':args['plan'],'environment':'TEST','activation_enabled':False});result={k:r[k] for k in ('id','revision','content_hash','review_status','proposal_id')};result.update(draft_id=id,activation_enabled=False,environment='TEST')
 else:fail('unknown_tool','Unknown builder tool')
 return result if active else await s.commit(name,args,result)

async def review(store,proposal,approve,expected_hash,expected_record_revision=None,confirm_proposed=False,approve_resources=False):
 if fresh.CTX.get()['token'].startswith('fmca_'):fail('access_denied','Human browser review required')
 snap=await rpc(store,'snapshot');s=Session(store,snap);kind=proposal['record_kind'];id=proposal['record_id'];r=s.state[kind].get(id)
 if not r:fail('not_found','Proposal is unavailable')
 s.check_hash(r,expected_hash)
 if expected_record_revision is not None and r['revision']!=expected_record_revision:fail('conflict','Proposal revision changed; refresh the complete diff before review')
 if r['review_status'] in ('applied','approved','dismissed'):return r.get('applied_result',{'status':r['review_status']})
 if approve and kind=='waivers' and s.ctx['role']!='owner':fail('access_denied','Only this client owner can authorize a discovery waiver')
 if approve and kind=='plans':await s.source(r['body']['source'])
 if approve and kind=='workflows':s.workflow_result(r) # Refresh authoritative findings; incomplete design may be applied Off.
 payload={'record_kind':kind,'record_id':id,'expected_hash':expected_hash,'expected_revision':snap['revision'],'approve':approve,'confirm_proposed':confirm_proposed,'approve_resources':approve_resources}
 if approve and kind=='workflows':payload['native_body']=prepare_canvas(s,r,confirm_proposed)
 if approve and kind=='change_sets':
  candidate=build_changes.candidate_session(store,snap,r);payload['native_bodies']={x['id']:prepare_canvas(candidate,candidate.state['workflows'][x['id']],confirm_proposed) for x in r['body']['changes'] if x['kind']=='workflows'}
 payload['confirmed_agent_hashes']={g['id']:digest(g) for body in ([payload['native_body']] if 'native_body' in payload else payload.get('native_bodies',{}).values()) for n in body.get('nodes',[]) for g in [n['data']['guided']]}
 payload['resource_hashes']={pin:digest(rec['body']['content']) for pin,rec in (candidate.state['resources'] if approve and kind=='change_sets' else s.state['resources']).items()}
 return await rpc(store,'review',payload)


def prepare_canvas(s,r,confirm_proposed=False):
 canvas=copy.deepcopy(r['body']);canvas.pop('content_hash',None)
 if confirm_proposed:
  for n in canvas.get('nodes',[]):
   for f in n['data']['guided'].get('fields',{}).values():
    if f.get('source')=='proposed':f['source']='user'
   n['data'].pop('guided_hash',None)
 prior=next((w['body'] for w in s.snapshot.get('workflows',[]) if w['path']==r.get('native_source',{}).get('path')),None)
 version=prior['version'].rsplit('.',1)[0]+'.'+str(int(prior['version'].rsplit('.',1)[1])+1) if prior else '0.0.'+str(r['revision'])
 canvas.update(version=version,draft_revision=version,release_version=None,format='canvas-v2',created_at=s.store.now(),actor=s.ctx['user']['id'],status='draft',execution_enabled=False);canvas['content_hash']=digest(canvas)
 return canvas
