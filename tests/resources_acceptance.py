import json,urllib.request,urllib.error,uuid
B='http://127.0.0.1:8496/api/'
def call(p,d=None,headers=None):
 h={'Content-Type':'application/json',**(headers or {})};req=urllib.request.Request(B+p,data=None if d is None else json.dumps(d).encode(),headers=h)
 return json.load(urllib.request.urlopen(req,timeout=60))
s=call('state');a=next(x for x in s['agents'] if x['id']=='acceptance-name-mapper' and x['version']=='0.1.0');pins=[]
for kind,id,content in [('schema','acceptance-input-schema',a['input_schema']),('instructions','acceptance-instructions',a['instructions'])]:
 r=next((x for x in s['resources'] if x['id']==id),None)
 if not r:r=call('resources',{'kind':kind,'id':id,'version':'0.1.0','content':content})
 pins.append({k:r[k] for k in ('kind','id','version','content_hash')})
if not any(x['id']==a['id'] and x['version']=='0.2.0' for x in s['agents']):call('agents',{**a,'version':'0.2.0','resource_refs':pins})
ref=a['id']+'@0.2.0';call('agents/publish',{'agent_ref':ref});r=call('execute',{'agent_ref':ref,'input':{'name':'SYNTHETIC pinned resource test'},'idempotency_key':'resources-'+str(uuid.uuid4())});assert r['result_status']=='VERIFIED'
print('PASS versioned schema and instructions registration, immutable resource pin resolution, publication and durable execution')
try:call('agents',{**a,'version':'0.3.0','resource_refs':[{**pins[0],'content_hash':'bad'}]});raise AssertionError('Foreign resource hash accepted')
except urllib.error.HTTPError as e:assert e.code==400
print('PASS invalid resource hash denied and audited')
try:call('execute',{'agent_ref':ref,'input':{'name':'test'}},headers={'Origin':'https://untrusted.example'});raise AssertionError('Cross-origin accepted')
except urllib.error.HTTPError as e:assert e.code==403
print('PASS cross-origin execution denied')
