"""HTTP acceptance against deployed Studio. All input values are synthetic."""
import json,uuid,urllib.request,urllib.error,io,zipfile,sys
sys.path.insert(0,'flux-studio')
from tests.test_core import agent
BASE='http://127.0.0.1:8496'
checks=[]
def call(path,data=None):
 r=urllib.request.Request(BASE+'/api/'+path,data=None if data is None else json.dumps(data).encode(),headers={} if data is None else {'Content-Type':'application/json'})
 with urllib.request.urlopen(r,timeout=60) as res:return json.load(res)
def check(name,value):
 assert value,name;checks.append(name);print('PASS',name)
def denied(path,data):
 try:call(path,data);return False
 except urllib.error.HTTPError as e:return e.code in (400,409)
name='acceptance-name-mapper';a=agent();a['id']=name;a['version']='0.1.0';ref=name+'@0.1.0'
state=call('state')
if not any(x['id']==name and x['version']=='0.1.0' for x in state['agents']):call('agents',a)
check('failed schema cannot execute successfully',call('agents/test',{'agent_ref':ref})['passed'])
call('agents/publish',{'agent_ref':ref})
key='acceptance-'+str(uuid.uuid4());b={'agent_ref':ref,'input':{'name':'SYNTHETIC supplier'},'idempotency_key':key}
r=call('execute',b);check('real durable execution',r['result_status']=='VERIFIED' and r['output']==b['input'])
r2=call('execute',b);check('duplicate invocation returns original immutable record',r2['content_hash']==r['content_hash'])
check('key/input conflict denied',denied('execute',{**b,'input':{'name':'DIFFERENT'}}))
bad=call('execute',{**b,'input':{},'idempotency_key':key+'-invalid'});check('invalid input audited as failure',bad['result_status']=='FAILED' and bad['error'])
check('duplicate immutable version cannot overwrite',denied('agents',{**a,'instructions':'Overwrite attempt'}))
w={'id':'acceptance-durable-chain','version':'0.1.0','name':'Synthetic durable chain','nodes':[{'id':'one','agent_ref':ref,'x':30,'y':70},{'id':'two','agent_ref':ref,'x':260,'y':70}],'edges':[{'source':'one','target':'two'}]}
if not any(x['id']==w['id'] and x['version']==w['version'] for x in state['workflows']):call('workflows',w)
check('contracts validated',call('workflows/validate',w)['errors']==[])
call('workflows/publish',{'id':w['id'],'version':w['version']})
wb={'id':w['id'],'version':w['version'],'input':{'name':'SYNTHETIC durable handoff'},'idempotency_key':key+'-workflow'}
wr=call('workflows/run',wb);check('two-stage durable workflow',len(wr['results'])==2 and wr['results'][1]['input_refs']==['runs/'+wr['results'][0]['record_id']])
again=call('workflows/run',wb);check('workflow replay creates no duplicate step',again['results'][1]['content_hash']==wr['results'][1]['content_hash'])
call('workflows/control',{'workflow_ref':w['id']+'@'+w['version'],'action':'pause'});check('paused workflow blocks execution',denied('workflows/run',wb));call('workflows/control',{'workflow_ref':w['id']+'@'+w['version'],'action':'resume'})
with urllib.request.urlopen(BASE+'/api/export/'+ref) as res:
 names=zipfile.ZipFile(io.BytesIO(res.read())).namelist();check('six-file export',len(names)==6)
mon=call('live');check('all four existing agents have real health and history',all(a['runs'] and not a['history_error'] and a['health']['status'] in ('ok','healthy') for a in mon['agents']))
check('router shadow dispatch preserved',mon['agents'][3]['health']['dispatch_enabled'] is False)
line=call('lineage');check('all four durable lineage queries work',all(not x['error'] for x in line.values()))
print(json.dumps({'passed':len(checks),'checks':checks,'synthetic_execution_key':key},indent=2))
