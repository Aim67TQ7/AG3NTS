"""Atomic related proposals, connection metadata, and side-effect-free sample checks."""
import asyncio,copy,json,sys,uuid
from pathlib import Path
from . import mcp_builder as b
from .core import digest,schema
from .workflow_contract import dependency,enrich,validate
OPERATIONS=['update_agent_draft','propose_schema','propose_rule','propose_connected_workflow','propose_connections']
CONNECTION=b.obj({'connection_id':b.UUID,'capabilities':{'type':'array','items':b.STR,'minItems':1,'maxItems':20,'uniqueItems':True}})
ROUTES={'entry_nodes':{'type':'array','items':b.STR,'minItems':1,'maxItems':30,'uniqueItems':True},'terminal_outcomes':{'type':'array','maxItems':100,'items':b.obj({'node':b.STR,'outcome':b.STR,'destination':{'enum':['terminal','human_review']}})}}
TOOLS=[
 {'name':'validate_workflow','description':'Validate the complete saved/proposed graph, including reachability, required inputs, edge schema compatibility, outcome destinations and dependency/permission blockers. Executes nothing.','inputSchema':b.obj({'workflow_id':b.STR})},
 {'name':'propose_change_set','description':'Stage related draft edits, schemas, rules and edges as one immutable review diff. Saves none of its members until browser Apply; all members apply atomically or none apply.','inputSchema':b.obj({'request_id':b.UUID,'title':b.STR,'operations':{'type':'array','minItems':1,'maxItems':30,'items':b.obj({'tool':{'enum':OPERATIONS},'arguments':{'type':'object'}})}})},
 {'name':'read_change_set','description':'Read the complete before/after diff, dependencies, validation and review hash of a proposed change set.','inputSchema':b.obj({'change_set_id':b.STR})},
 {'name':'sandbox_validate','description':'Check JSON sample documents against the draft input schema and structured rules in an isolated subprocess. Returns expected versus actual checks; no runtime, external calls, business writes or publication approval.','inputSchema':b.obj({'draft_id':b.STR,'expected_hash':b.HASH,'samples':{'type':'array','minItems':1,'maxItems':20,'items':b.obj({'name':b.STR,'document':{'type':'object'},'expected':b.obj({'schema_valid':{'type':'boolean'},'rule_passed':{'type':'boolean'}},[])})}})},
 {'name':'list_connections','description':'Read only approved, permitted connection IDs and approved capabilities. Returns no credential material. Approval is design access, not runtime activation.','inputSchema':b.obj({})}]
for t in TOOLS:t['annotations']={'readOnlyHint':t['name']!='propose_change_set','destructiveHint':False,'idempotentHint':True,'openWorldHint':False}
NAMES={t['name'] for t in TOOLS}

def diff(old,new,path=''):
 if old==new:return []
 if isinstance(old,dict) and isinstance(new,dict):
  return [row for key in sorted(old.keys()|new.keys()) for row in diff(old.get(key),new.get(key),path+'/'+key.replace('~','~0').replace('/','~1'))]
 return [{'op':'add' if old is None else 'remove' if new is None else 'replace','path':path,'before':old,'after':new}]

def connection_findings(s,g):
 visible={c['id']:c for c in s.snapshot.get('connections',[])};findings=[]
 for i,req in enumerate(g.get('connection_requirements',[])):
  c=visible.get(req['connection_id']);missing=sorted(set(req['capabilities'])-set(c['capabilities'] if c else []))
  if not c or missing:findings.append({'rule_id':'connection-permission-required','blocks_publish':True,'field_paths':['connection_requirements.'+str(i)],'connection_id':req['connection_id'],'missing_permissions':missing,'message':'Ask a company owner to approve this connection and the missing capabilities','dependencies':[{'connection_id':req['connection_id'],'status':'missing_or_not_permitted' if not c else 'missing_capabilities','missing_permissions':missing,'read':{'tool':'list_connections','arguments':{}},'review_url':'/ai-connections'}]})
 return findings

def candidate_session(store,snap,r):
 return b.Session(store,{**snap,'document':r['body']['document']})
def set_result(s,r):
 candidate=candidate_session(s.store,s.snapshot,r);findings=[]
 for change in r['body']['changes']:
  if change['kind']=='workflows':findings.extend(validate(candidate,candidate.state['workflows'][change['id']]['body'])['findings'])
  elif change['kind']=='agents':findings.extend(candidate.validation(candidate.state['agents'][change['id']]['body'])['findings'])
 return {k:r[k] for k in ('id','revision','content_hash','review_status','proposal_id')}|{'title':r['body']['title'],'diff':r['body']['diff'],'members':r['body']['changes'],'validation':{'blocks_publish':bool(findings),'findings':findings,'runtime_certified':False},'activation_enabled':False,'review_url':'/ai-connections#proposal-'+r['proposal_id']}

async def handle(name,args,store,s):
 if name=='list_connections':return {'items':s.snapshot.get('connections',[]),'runtime_authorized':False}
 if name=='validate_workflow':return validate(s,s.workflow(args['workflow_id'])['body'])
 if name=='read_change_set':
  r=s.state['change_sets'].get(args['change_set_id'])
  if not r:b.fail('not_found','Change set not found in this company')
  return set_result(s,r)
 if name=='sandbox_validate':
  r=s.agent(args['draft_id']);s.check_hash(r,args['expected_hash']);g=r['body'];pin=g['fields']['input.schema']['value'];resource=s.resources.get(pin)
  if not resource:b.fail('missing_dependency','Choose or propose the draft input schema before sample testing',field_path='input.schema',dependency=dependency(s,pin,'input.schema'))
  schema(resource['content'])
  if '$dynamicRef' in json.dumps(resource['content']):b.fail('invalid_schema','Dynamic schema references are forbidden in the offline sample checker',field_path='input.schema')
  rules=[];rule=s.resources.get(g['fields'].get('execute.rule',{}).get('value'))
  if rule:rules=b.validate_rule(rule['content'])
  elif g['fields'].get('execute.rule',{}).get('value') not in (None,'none'):b.fail('missing_dependency','The selected rule is unavailable',field_path='execute.rule')
  worker=Path(__file__).with_name('sample_sandbox.py')
  proc=await asyncio.create_subprocess_exec(sys.executable,'-I','-B',str(worker),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env={'PYTHONDONTWRITEBYTECODE':'1'})
  try:out,_=await asyncio.wait_for(proc.communicate(json.dumps({'schema':resource['content'],'rules':rules,'samples':args['samples']},allow_nan=False).encode()),4)
  except (TimeoutError,asyncio.CancelledError):
   proc.kill();await proc.wait();b.fail('sandbox_limit','Sample checker exceeded its local limit; no live action was performed')
  if proc.returncode or len(out)>200000:b.fail('sandbox_limit','Sample checker rejected or exceeded its local limits; no live action was performed')
  return json.loads(out)|{'draft_id':r['id'],'draft_hash':r['content_hash'],'schema_ref':pin,'schema_status':resource['status'],'rule_ref':rule['id'] if rule else None}
 if name=='propose_change_set':
  staged=b.Session(store,copy.deepcopy(s.snapshot));token=b.ACTIVE_SESSION.set(staged)
  try:
   initial_hashes={}
   for i,op in enumerate(args['operations']):
    payload={**op['arguments'],'request_id':str(uuid.uuid5(uuid.UUID(args['request_id']),str(i)))}
    key=payload.get('workflow_id') or payload.get('draft_id')
    if key and 'expected_hash' in payload:
     record=staged.workflow(key,write=True) if 'workflow_id' in payload else staged.agent(key,write=True)
     original=initial_hashes.setdefault(key,record['content_hash'])
     if payload['expected_hash']!=original:b.fail('conflict','Every related edit must name the original reviewed base hash')
     payload['expected_hash']=record['content_hash']
    await b.dispatch(op['tool'],payload,store)
  finally:b.ACTIVE_SESSION.reset(token)
  original=copy.deepcopy(s.state);original.pop('change_sets',None);document=copy.deepcopy(staged.state);document.pop('change_sets',None)
  # Multiple related operations on the same object produce one proposed revision.
  for (kind,id),record in staged.changed.items():record['revision']=original.get(kind,{}).get(id,{}).get('revision',0)+1;record['request_id']=args['request_id'];document[kind][id]=record
  required={n['data']['guided']['id'] for (k,_),r in staged.changed.items() if k=='workflows' for n in r['body']['nodes']}
  for id in required:
   if id not in original['agents'] and ('agents',id) not in staged.changed:
    r=staged.touch('agents',id,staged.state['agents'][id]['body']);document['agents'][id]=r
  for kind in document:
   for id in list(document[kind]):
    if id not in original.get(kind,{}) and (kind,id) not in staged.changed:del document[kind][id]
  id='changes-'+args['request_id'];parent=str(uuid.uuid5(uuid.NAMESPACE_URL,':'.join([s.ctx['client']['id'],s.ctx['company']['id'],s.ctx['user']['id'],'change_sets',id])))
  for (kind,_),record in staged.changed.items():
   if kind=='resources':record.update(change_set_id=id,review_parent_id=parent);document[kind][record['id']]=record
  changes=[staged.audit_change(r) for r in staged.changed.values()];body={'title':args['title'],'base_document':original,'document':document,'changes':changes,'diff':diff(original,document),'apply_request_id':str(uuid.uuid5(uuid.UUID(args['request_id']),'apply'))}
  r=s.touch('change_sets',id,body);return await s.commit(name,args,set_result(s,r))
 b.fail('unknown_tool','Unknown build change tool')
