"""Portable workflow definitions. Packages are data, never executable authority."""
import copy,json,re,uuid
from urllib.parse import urlsplit,parse_qsl
from fastapi import APIRouter
from jsonschema import Draft202012Validator
from . import studio,fresh,library
from .core import CAPS,Invalid,digest,compatibility,schema
router=APIRouter(prefix='/api/studio/workflow-json')
FORMAT='operis.workflow';VERSION='1.0.0';FUNCTIONS=('trigger','input','execute','output','error','verify')
SENSITIVE=re.compile(r'(?i)(^token$|^key$|^credential$|password|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|encrypted_value|selection_id|selected_by|authorization|credential_selections)')
TOKEN=re.compile(r'(?:\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}|\bsb_secret_[A-Za-z0-9_-]+|\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)')
PACKAGE_SCHEMA={'type':'object','additionalProperties':False,'required':['format','schema_version','workflow','resources'],'properties':{'format':{'const':FORMAT},'schema_version':{'const':VERSION},'workflow':{'type':'object','additionalProperties':False,'required':['name','steps','connections'],'properties':{'name':{'type':'string','minLength':1,'maxLength':160},'steps':{'type':'array','minItems':1,'maxItems':100,'items':{'type':'object','additionalProperties':False,'required':['id','name','capability','functions','contracts','resources'],'properties':{'id':{'type':'string','pattern':'^[a-zA-Z0-9_-]{1,100}$'},'name':{'type':'string','maxLength':160},'responsibility':{'type':'string','maxLength':5000},'capability':{'enum':sorted(CAPS)},'functions':{'type':'object','additionalProperties':False,'properties':{k:{'type':'object'} for k in FUNCTIONS}},'configuration':{'type':'object'},'bindings':{'type':'object'},'contracts':{'type':'object','additionalProperties':False,'properties':{'input':{'type':['object','null']},'output':{'type':['object','null']}}},'resources':{'type':'array','items':{'type':'string'}},'position':{'type':'object','properties':{'x':{'type':'number'},'y':{'type':'number'}},'additionalProperties':False},'adapter_hint':{'type':'string','maxLength':100}}}},'connections':{'type':'array','maxItems':500,'items':{'type':'object','additionalProperties':False,'required':['id','from','to','delivery'],'properties':{'id':{'type':'string'},'from':{'type':'object','required':['step','port'],'additionalProperties':False,'properties':{'step':{'type':'string'},'port':{'type':'string'}}},'to':{'type':'object','required':['step','port'],'additionalProperties':False,'properties':{'step':{'type':'string'},'port':{'type':'string'}}},'delivery':{'const':'durable_record'},'record_type':{'type':['string','null']},'status':{'type':['string','null']}}}}}},'resources':{'type':'array','maxItems':300,'items':{'type':'object','additionalProperties':False,'required':['id','kind','label'],'properties':{'id':{'type':'string'},'kind':{'enum':sorted(library.KINDS)},'label':{'type':'string','maxLength':160},'content':{},'system':{'type':'string'}}}}}}
PACKAGE_SCHEMA['properties']['workflow']['properties']['steps']['items']['properties']['functions']['required']=list(FUNCTIONS)

def clean(value):
 if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if not SENSITIVE.search(k)}
 if isinstance(value,list):return [clean(v) for v in value]
 if isinstance(value,str):
  if value.startswith(('https://','http://')):
   u=urlsplit(value)
   if u.username or u.password or any(SENSITIVE.search(k) for k,v in parse_qsl(u.query)):return '[credential-bearing URL omitted]'
  return TOKEN.sub('[credential omitted]',value)
 return value
def check_secret_data(value,path='package'):
 if isinstance(value,dict):
  for k,v in value.items():
   if SENSITIVE.search(k):raise Invalid('Credential values or selections are not allowed in workflow JSON')
   check_secret_data(v,path+'.'+k)
 elif isinstance(value,list):
  for v in value:check_secret_data(v,path)
 elif isinstance(value,str):
  if TOKEN.search(value):raise Invalid('Remove credential values before importing workflow JSON')
  if value.startswith(('https://','http://')):
   u=urlsplit(value)
   if u.username or u.password or any(SENSITIVE.search(k) for k,v in parse_qsl(u.query)):raise Invalid('Credential-bearing URLs are not allowed in workflow JSON')
def validate(package):
 if not isinstance(package,dict) or len(json.dumps(package).encode())>1500000:raise Invalid('Use a workflow package under 1.5 MB')
 check_secret_data(package)
 errors=list(Draft202012Validator(PACKAGE_SCHEMA).iter_errors(package))
 if errors:raise Invalid('Invalid workflow JSON at '+'.'.join(map(str,errors[0].absolute_path))+': '+errors[0].message[:240])
 steps=package['workflow']['steps'];by={s['id']:s for s in steps};resources={r['id']:r for r in package['resources']};warnings=[]
 if len(by)!=len(steps) or len(resources)!=len(package['resources']):raise Invalid('Step and resource IDs must be unique')
 for resource in resources.values():
  if resource['kind']=='credential' and 'content' in resource:raise Invalid('Credential slots may contain references only')
  if resource['kind']=='schema' and resource.get('content') is not None:schema(resource['content'])
 for s in steps:
  if any(r not in resources for r in s['resources']):raise Invalid('Unknown resource slot on '+s['id'])
  if set(s['functions'])!=set(FUNCTIONS):raise Invalid('Every step must define all six functions')
  for values in s['functions'].values():
   for value in values.values():
    if isinstance(value,dict) and (set(value)!= {'resource'} or value['resource'] not in s['resources']):raise Invalid('Function resource must reference a slot on its step')
  for key in ('input','output'):
   contract=s['contracts'].get(key)
   if contract:schema(contract)
   else:warnings.append(s['name']+': '+key+' JSON schema needs configuration')
  if s.get('adapter_hint'):warnings.append(s['name']+': runtime adapter must be installed and tested separately')
 edges=package['workflow']['connections'];ids=[e['id'] for e in edges]
 if len(ids)!=len(set(ids)):raise Invalid('Connection IDs must be unique')
 adj={id:[] for id in by};indeg={id:0 for id in by}
 for edge in edges:
  a,b=edge['from']['step'],edge['to']['step']
  if a not in by or b not in by:raise Invalid('Connection references an unknown step')
  if edge['from']['port'] not in ('COMPLETED','VERIFIED','REVIEW_REQUIRED','FAILED','output') or edge['to']['port']!='input':raise Invalid('Unknown handoff port')
  if edge['from']['port'] in ('REVIEW_REQUIRED','FAILED'):warnings.append('Exception handoff needs an approved review/error adapter')
  adj[a].append(b);indeg[b]+=1
  out,inp=by[a]['contracts'].get('output'),by[b]['contracts'].get('input')
  if out and inp and not compatibility(out,inp):raise Invalid('Incompatible JSON contracts: '+a+' → '+b)
 todo=[id for id in by if not indeg[id]];seen=[]
 while todo:
  id=todo.pop();seen.append(id)
  for target in adj[id]:
   indeg[target]-=1
   if not indeg[target]:todo.append(target)
 if len(seen)!=len(by):raise Invalid('Workflow JSON cannot contain cycles')
 if len(by)>1 and any(not adj[id] and not any(e['to']['step']==id for e in edges) for id in by):warnings.append('Workflow has a disconnected step')
 warnings += [r['label']+': map this resource in the destination client' for r in resources.values()]
 return {'valid':True,'steps':len(steps),'connections':len(edges),'resource_slots':len(resources),'warnings':warnings,'execution_enabled':False,'package_hash':digest(package)}
async def export_canvas(canvas):
 if not canvas.get('nodes'):raise Invalid('Open a workflow with at least one agent')
 stored=await studio.store.records('resources');slots=[];slot_map={};steps=[];node_ids={n['id']:'step-'+str(i+1) for i,n in enumerate(canvas['nodes'])}
 embedded=(canvas.get('portable_definition') or {}).get('resources',[])
 async def slot(ref,kind=None):
  key=json.dumps(ref,sort_keys=True)
  if key in slot_map:return slot_map[key]
  content=None;label='';system='';kind=kind or (ref.get('kind') if isinstance(ref,dict) else str(ref).split(':',1)[0])
  if isinstance(ref,dict):
   r=await library.lookup(ref);kind=r['kind'];label=r.get('label',r['id']);system=r.get('system','');content=r.get('content')
  elif ref not in ('none',None,''):
   r=next((r for r in stored if r['kind']+':'+r['id']+'@'+r['version']==ref),None)
   if r:
    from .governance import check
    await check('resource:'+r['id'],'use');content=r.get('content');label=r.get('label',r['id'])
  id='resource-'+str(len(slots)+1);slot_map[key]=id
  r={'id':id,'kind':kind if kind in library.KINDS else 'instructions','label':label or str(ref)[:160]}
  if content is not None and r['kind']!='credential':r['content']=clean(content)
  if system:r['system']=system
  slots.append(r);return id
 for n in canvas['nodes']:
  g=n.get('data',{}).get('guided')
  if not g:raise Invalid('Only configured agent cards can be exported')
  fields=g.get('fields',{});fns=copy.deepcopy(g.get('portable_functions') or {fn:{} for fn in FUNCTIONS});refs=[];contracts=copy.deepcopy(g.get('portable_contracts') or {'input':None,'output':None})
  for k,entry in fields.items():
   fn,_,key=k.partition('.')
   if fn in fns:
    value=entry.get('value') if isinstance(entry,dict) else entry
    if key in ('schema','instructions','rule') and isinstance(value,str) and ':' in value:
     rid=await slot(value);refs.append(rid)
     if key=='schema' and fn in contracts:contracts[fn]=next((s.get('content') for s in slots if s['id']==rid),None)
     value={'resource':rid}
    if value is not None or key not in fns[fn]:fns[fn][key]=clean(value)
  for ref in g.get('reusable_resources',[]):refs.append(await slot(ref))
  for resource in embedded:
   if resource['id'] in g.get('portable_resource_slots',[]):
    key='embedded:'+resource['id']
    if key not in slot_map:
     id='resource-'+str(len(slots)+1);slot_map[key]=id;slots.append({**clean(resource),'id':id})
    refs.append(slot_map[key])
  steps.append({'id':node_ids[n['id']],'name':g.get('name') or n['data'].get('capability','Agent'),'responsibility':g.get('responsibility',''),'capability':g.get('capability') or n['data']['capability'],'functions':clean(fns),'configuration':clean({k:g[k] for k in ('input_config','trigger_config') if k in g}),'bindings':clean({part:{k:v for k,v in val.items() if k!='registry_hash'} for part,val in g.get('bindings',{}).items()}),'contracts':clean(contracts),'resources':list(dict.fromkeys(refs)),'position':{k:n.get('position',{}).get(k,0) for k in ('x','y')},**({'adapter_hint':g['runtime_binding']['adapter']} if g.get('runtime_binding',{}).get('adapter') else {})})
 candidates=copy.deepcopy(canvas.get('edges',[]));pairs={(e['source'],e['target']) for e in candidates}
 # Record bindings define handoffs even when the canvas renders them through the hub.
 for source in canvas['nodes']:
  writes=source['data']['guided'].get('bindings',{}).get('writes',{})
  for target in canvas['nodes']:
   reads=target['data']['guided'].get('bindings',{}).get('reads',{})
   if source['id']==target['id'] or (source['id'],target['id']) in pairs:continue
   for outcome,status in writes.get('outcomes',{}).items():
    if outcome in ('COMPLETED','VERIFIED') and writes.get('record_type') and reads.get('record_type')==writes['record_type'] and reads.get('status')==status:
     candidates.append({'source':source['id'],'target':target['id'],'sourceHandle':outcome,'data':{'record_type':writes['record_type']}});pairs.add((source['id'],target['id']));break
 edges=[]
 for i,e in enumerate(candidates):
  if e['source'] not in node_ids or e['target'] not in node_ids:continue
  sg=next(n['data']['guided'] for n in canvas['nodes'] if n['id']==e['source']);binding=sg.get('bindings',{}).get('writes',{})
  edges.append({'id':'handoff-'+str(i+1),'from':{'step':node_ids[e['source']],'port':e.get('sourceHandle') or 'COMPLETED'},'to':{'step':node_ids[e['target']],'port':'input'},'delivery':'durable_record','record_type':e.get('data',{}).get('record_type') or binding.get('record_type'),'status':binding.get('outcomes',{}).get(e.get('sourceHandle') or 'COMPLETED')})
 package={'format':FORMAT,'schema_version':VERSION,'workflow':{'name':canvas.get('name') or 'Workflow','steps':steps,'connections':edges},'resources':slots};validate(package);return package
@router.get('/schema')
async def get_schema():return PACKAGE_SCHEMA
@router.post('/export')
async def export(b:dict):
 if b.get('id'):
  rows=[w for w in await studio.store.records('workflows') if w['id']==b['id']]
  if not rows:raise Invalid('Saved workflow not found')
  canvas=max(rows,key=lambda w:w.get('created_at',''))
 else:canvas=b.get('canvas',{})
 return {'package':await export_canvas(canvas)}
@router.post('/validate')
async def inspect(b:dict):return validate(b.get('package'))
@router.post('/import')
async def import_package(b:dict):
 c=fresh.CTX.get()
 if not c or c['role'] not in ('owner','editor'):raise Invalid('Builder permission required')
 package=b.get('package');report=validate(package);catalog=await studio.catalog();nodes=[];ids={s['id']:str(uuid.uuid4()) for s in package['workflow']['steps']}
 for s in package['workflow']['steps']:
  fields={f['id']:{'value':None,'source':'missing','why':'Imported draft needs review'} for step in catalog['steps'] for f in step['fields']}
  for fn,values in s['functions'].items():
   for key,value in values.items():
    if fn+'.'+key in fields and not isinstance(value,dict):fields[fn+'.'+key]={'value':value,'source':'imported','why':'Portable workflow definition; review required'}
  for key,value in {'identity.environment':'TEST','identity.company':c['company']['code'],'identity.owner':c['user']['id']}.items():fields[key]={'value':value,'source':'server' if key.endswith('environment') else 'verified_identity','why':'Destination workspace context'}
  g={'id':'draft-'+str(uuid.uuid4()),'version':'0.1.0','name':s['name'],'name_options':[s['name']],'responsibility':s.get('responsibility',''),'responsibility_options':[s.get('responsibility','')],'capability':s['capability'],'catalog_version':catalog['version'],'guide_version':catalog['guide_version'],'fields':fields,'input_config':s.get('configuration',{}).get('input_config',{'kind':'flux'}),'trigger_config':s.get('configuration',{}).get('trigger_config',{}),'bindings':s.get('bindings',{}),'reusable_resources':[],'portable_functions':s['functions'],'portable_contracts':s['contracts'],'portable_resource_slots':s['resources'],'questions_for_user':['Review the imported definition, map its resources, and test before activation.'],'user_edits':[]}
  nodes.append({'id':ids[s['id']],'type':'capability','position':s.get('position',{'x':100,'y':100}),'data':{'capability':s['capability'],'guided':g,'status':'Imported draft'}})
 edges=[{'id':str(uuid.uuid4()),'source':ids[e['from']['step']],'target':ids[e['to']['step']],'sourceHandle':e['from']['port'],'targetHandle':'input','data':{'direct':True,'semantics':'portable_durable_record','record_type':e.get('record_type'),'status':e.get('status'),'compatible':False}} for e in package['workflow']['connections']]
 workflow=await studio.save_canvas({'id':'canvas-'+str(uuid.uuid4()),'version':'0.0.1','name':package['workflow']['name'][:149]+' · imported','binding_mode':'records','nodes':nodes,'edges':edges,'portable_definition':package,'imported_package_hash':report['package_hash']})
 await studio.store.event('workflow.json_imported',{'workflow_id':workflow['id'],'package_hash':report['package_hash'],'runtime_enabled':False,'resource_selections_created':False})
 return {'workflow':workflow,'validation':report,'note':'Imported as a new TEST draft. Resources require mapping; runtime adapters, approvals and activation were not imported.'}
