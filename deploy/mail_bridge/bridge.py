"""Read-only Maggie source -> immutable client-scoped FLUX artifacts. No provider calls."""
import datetime as dt,hashlib,json,os,pathlib,time,urllib.request,urllib.parse
from convert import convert,digest,VERSION
MAILBOXES=('ap@buntingmagnetics.com','confirmations@buntingmagnetics.com')
SOURCE_TABLES={'a01_messages','a02_document_content'}
ROOT=pathlib.Path(os.environ.get('STATE_DIRECTORY','/var/lib/flux-bunting-mail'))
CONFIG=pathlib.Path(os.environ.get('CREDENTIALS_DIRECTORY','/etc'))/('bridge.json' if os.environ.get('CREDENTIALS_DIRECTORY') else 'flux-bunting-mail.json')
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def request(url,headers,body=None):
 data=None if body is None else json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
 req=urllib.request.Request(url,data=data,headers={**headers,'Content-Type':'application/json'},method='GET' if body is None else 'POST')
 # Do not follow redirects with authenticated headers.
 opener=urllib.request.build_opener(NoRedirect())
 with opener.open(req,timeout=45) as response:return json.load(response)
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise RuntimeError('Redirect denied')
class Bridge:
 def __init__(self):
  self.config=json.loads(CONFIG.read_text());self.base=os.environ['PZLO_SUPABASE_URL'].rstrip('/')
  if self.base!='https://qzwxisdfwswsrbzvpzlo.supabase.co':raise ValueError('Unexpected source project')
  self.source_headers={'apikey':os.environ['PZLO_SUPABASE_SERVICE_KEY'],'Authorization':'Bearer '+os.environ['PZLO_SUPABASE_SERVICE_KEY']}
 def rows(self,table,params):
  if table not in SOURCE_TABLES:raise ValueError('Source table denied')
  return request(self.base+'/rest/v1/'+table+'?'+urllib.parse.urlencode(params),self.source_headers)
 def rpc(self,action,payload):
  return request('https://ezlmmegowggujpcnzoda.supabase.co/rest/v1/rpc/flux_mail_ingest',{'apikey':self.config['publishable_key'],'x-flux-mail':self.config['token']},{'action':action,'payload':payload})
 def capture(self,row):
  p=row['package'];out={**p};identity=digest({'stage':'capture','message_id':row['message_id'],'output':out})
  return {'id':identity,'stage':'capture','message_id':row['message_id'],'attachment_id':'','mailbox':row['mailbox'],'occurred_at':row.get('completed_at') or row['received_at'],'subject':p.get('subject'),'filename':None,'agent_name':'Email Capture · Maggie listener','agent_version':p.get('schema_version','unrecorded'),'status':'completed','input_artifact_id':None,'input':{'source_table':'a01_messages','message_id':row['message_id']},'output':out,'metrics':{'duration_ms':None,'duration_reason':'Upstream duration not recorded per message','input_tokens':0,'output_tokens':0,'model_cost_usd':0,'attempt':row.get('attempts')},'origin':'existing_production_agent'}
 def ingest_document(self,row):
  matches=self.rows('a01_messages',{'message_id':'eq.'+row['message_id'],'mailbox':'in.('+','.join(MAILBOXES)+')','status':'eq.complete','select':'message_id,mailbox,package,completed_at,received_at,attempts','limit':'1'})
  if not matches:raise ValueError('Matching captured email unavailable')
  capture=self.capture(matches[0])
  parsed={**row};aid=digest({'stage':'parse','version':row.get('reader_version'),'output':parsed})
  p={'id':aid,'stage':'parse','message_id':row['message_id'],'attachment_id':row['attachment_id'],'mailbox':row['mailbox'],'occurred_at':row['extracted_at'],'filename':row.get('filename'),'subject':capture['subject'],'agent_name':'Attachment Parser · Document Reader','agent_version':row.get('reader_version','unrecorded'),'status':{'extracted':'completed','error':'failed'}.get(row['status'],row['status']),'input_artifact_id':capture['id'],'input':{'message_id':row['message_id'],'attachment_id':row['attachment_id'],'source_sha256':row.get('sha256')},'output':parsed,'metrics':{'duration_ms':None,'duration_reason':'Upstream duration not recorded per attachment','input_tokens':row.get('llm_tokens_in',0),'output_tokens':row.get('llm_tokens_out',0),'model_cost_usd':row.get('llm_usd',0),'attempt':row.get('attempts')},'origin':'existing_production_agent'}
  # Idempotent converter execution cached by exact parser output/version.
  cache=ROOT/'converted'/(aid+'-'+VERSION+'.json');cache.parent.mkdir(parents=True,exist_ok=True)
  if cache.exists():j=json.loads(cache.read_text())
  else:
   start=time.monotonic();out=convert(parsed)
   j={**p,'id':digest({'stage':'json','parent':aid,'version':VERSION}),'stage':'json','agent_name':'Document JSON Converter','agent_version':VERSION,'status':'review_required' if out['quality']['human_review_required'] else 'completed','input_artifact_id':aid,'input':{'parser_artifact_id':aid},'output':out,'metrics':{'duration_ms':round((time.monotonic()-start)*1000,3),'input_tokens':0,'output_tokens':0,'model_cost_usd':0,'attempt':1},'origin':'flux_json_converter','executed_at':now()}
   tmp=cache.with_suffix('.tmp');tmp.write_text(json.dumps(j,ensure_ascii=False));tmp.replace(cache)
  return self.rpc('commit',{'artifacts':[capture,p,j]})
 def cycle(self):
  state_path=ROOT/'state.json';state=json.loads(state_path.read_text()) if state_path.exists() else {}
  initial=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=24)).isoformat();counters={}
  for table,stamp in [('a01_messages','completed_at'),('a02_document_content','extracted_at')]:
   since=state.get(table,initial);high=since;offset=0;count=0
   while True:
    params={'select':'message_id,mailbox,package,completed_at,received_at,attempts' if table=='a01_messages' else '*','mailbox':'in.('+','.join(MAILBOXES)+')',stamp:'gte.'+since,'order':stamp+'.asc,message_id.asc'+(',attachment_id.asc' if table!='a01_messages' else ''),'limit':'50','offset':str(offset)}
    if table=='a01_messages':params['status']='eq.complete'
    rows=self.rows(table,params)
    for row in rows:
     if table=='a01_messages':self.rpc('commit',{'artifacts':[self.capture(row)]})
     else:self.ingest_document(row)
     high=max(high,row[stamp]);count+=1
     if count%10==0:self.rpc('heartbeat',{'status':'syncing','cycle_at':now(),'source_table':table,'processed':count,'production':True})
    self.rpc('heartbeat',{'status':'syncing','cycle_at':now(),'source_table':table,'processed':count,'production':True,'mailboxes':MAILBOXES,'company_assignment':'unassigned'})
    if len(rows)<50:break
    offset+=len(rows)
   # Overlap handles concurrent commits and timestamp ties without dropping records.
   state[table]=max(since,(dt.datetime.fromisoformat(high.replace('Z','+00:00'))-dt.timedelta(minutes=10)).isoformat());counters[table]=count
   tmp=state_path.with_suffix('.tmp');tmp.write_text(json.dumps(state));tmp.replace(state_path)
  self.rpc('heartbeat',{'status':'ok','cycle_at':now(),'processed':counters,'production':True,'mailboxes':MAILBOXES,'company_assignment':'unassigned','converter_version':VERSION})
if __name__=='__main__':
 ROOT.mkdir(parents=True,exist_ok=True);bridge=Bridge()
 while True:
  try:bridge.cycle();print('mail_bridge cycle completed',flush=True)
  except Exception as e:
   print('mail_bridge cycle failed: '+type(e).__name__,flush=True)
   try:bridge.rpc('heartbeat',{'status':'error','error_type':type(e).__name__,'cycle_at':now(),'production':True})
   except Exception:pass
  time.sleep(30)
