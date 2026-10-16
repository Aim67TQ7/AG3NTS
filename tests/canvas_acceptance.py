"""Design-only HTTP acceptance. No agent dispatch or real business payloads."""
import json,uuid,urllib.request,urllib.error,zipfile,io
B='http://127.0.0.1:8496/api/'
def call(p,b=None):
 req=urllib.request.Request(B+p,data=None if b is None else json.dumps(b).encode(),headers={} if b is None else {'Content-Type':'application/json'})
 return json.load(urllib.request.urlopen(req,timeout=75))
def check(label,b):assert b,label;print('PASS',label,flush=True)
c=call('studio/catalog');state=call('state');r=next(x for x in state['resources'] if x['kind']=='schema');ref='schema:'+r['id']+'@'+r['version'];call('studio/resources/publish',{'resource_ref':ref});c=call('studio/catalog')
check('schemas dropdown includes only published versions',any(o['id']==ref for s in c['steps'] for f in s['fields'] if f['id']=='input.schema' for o in f['options']))
fields={f['id']:{'value':f['options'][0]['id'] if f['options'] else None,'source':'user','why':'Synthetic acceptance choice.'} for s in c['steps'] for f in s['fields']}
for key,v in {'identity.company':'BMC','identity.environment':'TEST','execute.authority':'P0','execute.model_access':'off','execute.method':'deterministic_map','input.schema':ref,'output.schema':ref,'output.outcomes':'completed_review','verify.approval_gate':'none'}.items():fields[key]={'value':v,'source':'user','why':'Synthetic acceptance choice.'}
g={'id':'canvas-acceptance-'+str(uuid.uuid4()),'name':'Synthetic Guided Mapper','responsibility':'Reshape a supplied synthetic record into the selected test format.','version':'0.1.0','capability':'MAP','guide_version':'1.0.0','catalog_version':'1.0.0','fields':fields,'name_options':['Synthetic Guided Mapper','Synthetic Field Mapper','Synthetic Record Mapper'],'responsibility_options':['Reshape supplied synthetic fields.']*3,'user_edits':[]}
report=call('studio/validate-agent',{'guided':g});check('complete design validates without running it',report['valid']);a=call('studio/agents',{'guided':g});check('saved design round-trips',next(x for x in call('state')['agents'] if x['id']==a['id'])['guided']==g)
call('studio/agents/publish',{'agent_ref':a['id']+'@'+a['version']})
try:call('execute',{'agent_ref':a['id']+'@'+a['version'],'input':{'name':'synthetic'}});raise AssertionError('Design dispatched')
except urllib.error.HTTPError as e:check('published design cannot execute',e.code==400)
with urllib.request.urlopen(B+'export/'+a['id']+'@'+a['version']) as res:check('guided export still has six files',len(zipfile.ZipFile(io.BytesIO(res.read())).namelist())==6)
t=call('studio/templates/email-capture-read');check('real committed-record replay has matching keys',t['edges'][0]['data']['evidence']['same_message_id']);check('deployed references never dispatch',all(n['data']['deployed'] and not n['data']['execution_enabled'] for n in t['nodes']))
w=call('studio/workflow-draft',{'id':'canvas-http-'+str(uuid.uuid4()),'version':'0.1.0','name':'Synthetic reference canvas','nodes':t['nodes'],'edges':t['edges']});check('canvas persists through existing FLUX workflow storage',any(x['id']==w['id'] and x['format']=='canvas-v2' for x in call('state')['workflows']))
check('unknown schemas stay amber',not call('studio/edge-check',{})['compatible'])
schema={'type':'object','properties':{'name':{'type':['string','null']}},'required':['name'],'additionalProperties':False};check('proven nullable formats turn green',call('studio/edge-check',{'output_schema':schema,'input_schema':schema})['compatible'])
monitor=call('live');check('existing pipeline still observed with dispatch off',all(not x['history_error'] for x in monitor['agents']) and monitor['agents'][3]['health']['dispatch_enabled'] is False)
print('PASS 11 design-only HTTP acceptance checks')
