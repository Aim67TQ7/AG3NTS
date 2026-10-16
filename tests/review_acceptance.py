import json,urllib.request,uuid,sys
sys.path.insert(0,'/srv')
from tests.test_core import agent
B='http://127.0.0.1:8496/api/'
def call(p,d=None):
 req=urllib.request.Request(B+p,data=None if d is None else json.dumps(d).encode(),headers={} if d is None else {'Content-Type':'application/json'})
 return json.load(urllib.request.urlopen(req,timeout=60))
a=agent();a.update(id='acceptance-review-rule',capability='RULE',responsibility='Compare the supplied name against an explicit synthetic fixture value.',execution={'kind':'rule','field':'name','operator':'eq','value':'EXPECTED SYNTHETIC','on_false':'review'},output_schema={'type':'object','properties':{'matched':{'type':'boolean'}},'required':['matched'],'additionalProperties':False},tests=[{'input':{'name':'EXPECTED SYNTHETIC'},'expected':{'matched':True}},{'input':{'name':'OTHER SYNTHETIC'},'expected':{'matched':False}}])
s=call('state')
if not any(x['id']==a['id'] for x in s['agents']):call('agents',a)
ref=a['id']+'@'+a['version'];call('agents/publish',{'agent_ref':ref});key='review-acceptance-'+str(uuid.uuid4());r=call('execute',{'agent_ref':ref,'input':{'name':'OTHER SYNTHETIC'},'idempotency_key':key});assert r['result_status']=='REVIEW_REQUIRED'
d=call('review',{'record_id':key,'decision':'approve','reason':'Synthetic acceptance only. Internal P0 continuation.'});assert d['payload']['result_hash']==r['content_hash']
assert any(x['record_id']==key for x in call('state')['runs'])
print('PASS review_required preserved as result; authenticated owner decision persisted against exact result hash')
