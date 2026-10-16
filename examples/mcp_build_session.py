"""Proposal-only MCP example. HTTP mode requires an explicit endpoint and existing OAuth token.
Run: FLUX_MCP_TOKEN=... python examples/mcp_build_session.py --endpoint URL --session-id UUID
Keep session-id unchanged to retry the identical session without duplicates.
"""
import argparse,asyncio,json,os,urllib.request,uuid

def request_id(session,label):return str(uuid.uuid5(uuid.UUID(session),label))
async def run(call,session):
 catalog=await call('get_catalog');fields={f['id']:f for s in catalog['catalog']['steps'] for f in s['fields']}
 suffix=uuid.UUID(session).hex[:12]
 schema=await call('propose_schema',request_id=request_id(session,'schema'),resource_id='example-invoice-'+suffix,version='1.0.0',label='Synthetic invoice comparison contract',schema={'type':'object','properties':{'amount':{'type':'number'},'expected':{'type':'number'}},'required':['amount','expected'],'additionalProperties':False})
 rule=await call('propose_rule',request_id=request_id(session,'rule'),resource_id='example-tolerance-'+suffix,version='1.0.0',label='Synthetic comparison tolerance',rule=[{'op':'within_tolerance','field':'amount','baseline_field':'expected','absolute_tolerance':0.01}])
 stages=[('READ','Retrieve','Retrieve one source document','system_read'),('DOC','Extract','Extract one document payload','document_extract'),('MAP','Normalize','Normalize one payload','deterministic_map'),('RULE','Compare','Compare one normalized payload','deterministic_rule'),('ROUTE','Route','Choose one review destination','deterministic_rule'),('DOC','Prepare','Prepare one review packet','document_extract'),('RULE','Verify','Verify one packet contract','deterministic_rule')]
 # Resolve execution methods from catalog; missing choices stay null and remain blocked.
 methods={o['id'] for o in fields['execute.method']['options']}
 nodes=[]
 for i,(cap,name,responsibility,method) in enumerate(stages):
  nodes.append({'key':str(i),'agent':{'capability':cap,'name_options':[name,name+' source',name+' item'],'responsibility_options':[responsibility,responsibility+' for review',responsibility+' in TEST'],'fields':{'execute.method':method if method in methods else None,'input.schema':schema['id'],'output.schema':schema['id'],'output.outcomes':'completed_only','execute.rule':'none'}}})
 workflow=await call('propose_connected_workflow',request_id=request_id(session,'workflow'),name='Synthetic seven-step review',nodes=nodes,edges=[{'source':str(i),'target':str(i+1),'on_outcome':'COMPLETED'} for i in range(6)])
 draft=workflow['drafts'][0]
 record_type=next(o['id'] for o in fields['output.record_type']['options'] if not o['id'].startswith('needs_new_'))
 corrected=await call('update_agent_draft',request_id=request_id(session,'correction'),draft_id=draft['draft_id'],expected_hash=draft['content_hash'],fields={'output.record_type':record_type,'execute.rule':rule['id']})
 agent=await call('read_agent_draft',draft_id=draft['draft_id']);saved=await call('read_workflow',workflow_id=workflow['workflow_id']);resources=await call('list_resources',limit=100)
 assert len(saved['nodes'])==7 and len(saved['edges'])==6
 assert agent['draft']['fields']['execute.rule']['value']==rule['id']
 assert any(f['rule_id']=='dependency-not-approved' for f in agent['validation']['findings'])
 return {'session_id':session,'synthetic_example':True,'workflow_id':saved['workflow_id'],'nodes':len(saved['nodes']),'edges':len(saved['edges']),'positions':[n['position'] for n in saved['nodes']],'draft_id':agent['draft_id'],'revision':agent['revision'],'content_hash':agent['content_hash'],'workflow_content_hash':saved['content_hash'],'review_status':agent['review_status'],'corrected_fields':{k:agent['draft']['fields'][k] for k in ('output.record_type','execute.rule')},'schema':{k:schema[k] for k in ('id','content_hash','status')},'rule':{k:rule[k] for k in ('id','content_hash','status')},'validation':agent['validation'],'activation_enabled':False,'next_step':'Human review in FLUX AI connections, then separate Resources approval. No agents were executed.'}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--endpoint',required=True);parser.add_argument('--session-id',required=True,type=str);args=parser.parse_args();uuid.UUID(args.session_id)
 token=os.environ['FLUX_MCP_TOKEN']
 async def call(tool,**arguments):
  payload={'jsonrpc':'2.0','id':str(uuid.uuid4()),'method':'tools/call','params':{'name':tool,'arguments':arguments}}
  request=urllib.request.Request(args.endpoint,data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json','MCP-Protocol-Version':'2025-11-25'})
  with urllib.request.urlopen(request,timeout=60) as response:reply=json.load(response)
  if 'error' in reply:raise RuntimeError(reply['error'])
  result=reply['result'];value=json.loads(result['content'][0]['text'])
  if result.get('isError'):raise RuntimeError(value)
  return value
 print(json.dumps(asyncio.run(run(call,args.session_id)),indent=2))
if __name__=='__main__':main()
