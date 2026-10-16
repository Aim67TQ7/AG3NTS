"""Bounded, deterministic capability interpreter. No eval, network or filesystem."""
import hashlib,json,re
from jsonschema import Draft202012Validator

CAPS={'DOC','READ','MAP','RULE','CLASS','ROUTE','COMMS','WRITE','REASON'}
FUNCTIONS=('trigger','input','execute','output','error','verify')
class Invalid(ValueError): pass

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def schema(value):
    if not isinstance(value,dict) or value.get('type')!='object': raise Invalid('Contract must be an object JSON Schema')
    if '$ref' in json.dumps(value): raise Invalid('External and recursive schema references are unsupported')
    Draft202012Validator.check_schema(value)
    return Draft202012Validator(value)

def validate_agent(a):
    for key in ('id','name','version','responsibility','capability','input_schema','output_schema','instructions','functions','execution','tests'):
        if key not in a: raise Invalid('Missing '+key)
    if not re.fullmatch(r'[a-z][a-z0-9-]{2,63}',a['id']): raise Invalid('Use a descriptive draft ID of 3-64 lowercase characters')
    if not re.fullmatch(r'\d+\.\d+\.\d+',a['version']): raise Invalid('Semantic version required')
    if a['capability'] not in CAPS: raise Invalid('Unknown capability')
    if a.get('authority','P0')!='P0' or a.get('model_access',False): raise Invalid('Executable builder supports P0 deterministic capabilities only')
    if any(not a['functions'].get(f) for f in FUNCTIONS): raise Invalid('All six execution functions are required')
    schema(a['input_schema']);schema(a['output_schema'])
    if a['execution'].get('kind') not in ('map','rule'): raise Invalid('Select a registered MAP or RULE interpreter')
    if (a['execution']['kind']=='map' and a['capability']!='MAP') or (a['execution']['kind']=='rule' and a['capability']!='RULE'): raise Invalid('Interpreter must match capability')
    e=a['execution']
    if e['kind']=='map':
        if not isinstance(e.get('fields'),dict) or not e['fields']: raise Invalid('Mapping fields required')
        for field,path in e['fields'].items():
            if not isinstance(path,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*',path): raise Invalid('Mapping requires dotted input paths')
    else:
        if not e.get('field') or e.get('operator') not in ('eq','ne','gt','gte','lt','lte','in'): raise Invalid('Rule field/operator required')
        if 'value' not in e: raise Invalid('Rule comparison value required')
    if e.get('on_false') not in (None,'review'):raise Invalid('Unsupported rule review outcome')
    if not isinstance(a['tests'],list) or not a['tests']: raise Invalid('At least one acceptance fixture required')
    return a

def path(data,key):
    for part in key.split('.'):
        if not isinstance(data,dict) or part not in data: raise Invalid('Missing source field '+key)
        data=data[part]
    return data

def execute(a,data):
    validate_agent(a);schema(a['input_schema']).validate(data)
    e=a['execution']
    if e['kind']=='map': out={k:path(data,v) for k,v in e['fields'].items()}
    else:
        left=path(data,e['field']);right=e['value'];op=e['operator']
        ops={'eq':lambda:left==right,'ne':lambda:left!=right,'gt':lambda:left>right,'gte':lambda:left>=right,'lt':lambda:left<right,'lte':lambda:left<=right,'in':lambda:left in right}
        out={'matched':bool(ops[op]())}
    schema(a['output_schema']).validate(out)
    return out

def test_agent(a):
    validate_agent(a);results=[]
    for i,t in enumerate(a['tests']):
        try:
            output=execute(a,t['input']);passed=('expected' in t and output==t['expected'] and not t.get('expect_error'));error=None
        except Exception as exc:
            output=None;error=type(exc).__name__;passed=bool(t.get('expect_error'))
        results.append({'fixture':i+1,'passed':passed,'output':output,'error':error})
    return {'passed':all(x['passed'] for x in results),'fixtures':results}

def compatibility(out,inp):
    if digest(out)==digest(inp):return True
    # Fail closed for constraints this limited static proof cannot establish.
    unsupported={'oneOf','anyOf','allOf','not','if','then','else','patternProperties','dependentRequired','dependentSchemas','$ref'}
    def proof(o,i):
        allowed={'type','properties','required','additionalProperties','items','enum','minimum','maximum','minLength','maxLength','minItems','maxItems','pattern','format','multipleOf','const','uniqueItems','exclusiveMinimum','exclusiveMaximum','title','description','$schema','$id','examples','default'}
        if set(i)-allowed or unsupported & (o.keys()|i.keys()): return False
        ot=o.get('type');it=i.get('type')
        ots=set(ot) if isinstance(ot,list) else {ot};its=set(it) if isinstance(it,list) else {it}
        if None in ots or None in its:return False
        if not all(t in its or t=='integer' and 'number' in its for t in ots):return False
        ot='object' if 'object' in ots else 'array' if 'array' in ots else ot
        if 'enum' in i and ('enum' not in o or not set(map(str,o['enum']))<=set(map(str,i['enum']))): return False
        for k in ('minimum','minLength','minItems'):
            if k in i and (k not in o or o[k]<i[k]): return False
        for k in ('maximum','maxLength','maxItems'):
            if k in i and (k not in o or o[k]>i[k]): return False
        for k in ('pattern','format','multipleOf','const','uniqueItems','exclusiveMinimum','exclusiveMaximum'):
            if k in i and o.get(k)!=i[k]: return False
        if ot=='object':
            if isinstance(i.get('additionalProperties'),dict):return False
            if not set(i.get('required',[]))<=set(o.get('required',[])): return False
            for k,v in i.get('properties',{}).items():
                if k not in o.get('properties',{}):
                    if k in i.get('required',[]) or o.get('additionalProperties',True) is not False: return False
                elif not proof(o['properties'][k],v): return False
            if i.get('additionalProperties') is False:
                if o.get('additionalProperties',True) is not False: return False
                if not set(o.get('properties',{}))<=set(i.get('properties',{})): return False
        if ot=='array' and not proof(o.get('items',{}),i.get('items',{})): return False
        return True
    return proof(out,inp)

def validate_workflow(w,agents):
    nodes=w.get('nodes',[]);edges=w.get('edges',[]);errors=[]
    ids=[n['id'] for n in nodes]
    if not nodes or len(ids)!=len(set(ids)): return ['Unique nodes required']
    resolved={}
    for n in nodes:
        key=n.get('agent_ref')
        if key not in agents: errors.append(n['id']+': unavailable agent version');continue
        a=agents[key]
        if a.get('status')!='published': errors.append(n['id']+': agent must pass tests and be published')
        resolved[n['id']]=a
    adj={k:[] for k in ids};indeg={k:0 for k in ids}
    for e in edges:
        s,t=e.get('source'),e.get('target')
        if s not in adj or t not in adj: errors.append('Unknown edge endpoint');continue
        adj[s].append(t);indeg[t]+=1
        if s in resolved and t in resolved and not compatibility(resolved[s]['output_schema'],resolved[t]['input_schema']): errors.append(s+' -> '+t+': contract compatibility unproven')
    # MVP linear execution only; no implied join or branch behavior.
    if any(len(x)>1 for x in adj.values()) or any(x>1 for x in indeg.values()): errors.append('MVP executable workflows are linear; branches/joins need explicit contracts')
    roots=[x for x in ids if indeg[x]==0];seen=[];todo=roots[:]
    while todo:
        k=todo.pop();seen.append(k)
        for t in adj[k]:
            indeg[t]-=1
            if indeg[t]==0:todo.append(t)
    if len(seen)!=len(ids):errors.append('Cycle detected')
    if len(roots)!=1:errors.append('One connected workflow entry required')
    return errors
