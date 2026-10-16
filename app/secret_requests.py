"""Browser-only secret fulfillment. Plaintext never enters MCP proposals or audit."""
import json,uuid
from . import fresh,library,mcp_builder as b,mcp_v2,studio
from .core import Invalid,digest

async def fulfill(store,args):
 c=fresh.CTX.get()
 if not c or c['role']!='owner' or c['token'].startswith('fmca_'):raise Invalid('Browser company owner required')
 snap=await b.rpc(store,'snapshot');s=b.Session(store,snap);kind,r=mcp_v2.find_proposal(s,args['proposal_id']);content=r['body'].get('content',{})
 if kind!='resources' or content.get('format')!='flux-secret-request-v1' or r.get('review_status')!='applied':raise Invalid('Apply and review this secret request before entering a credential')
 values=args.get('values');required=content['fields_required']
 if not isinstance(values,dict) or set(values)!=set(required) or any(not isinstance(v,str) or not v.strip() or len(v)>8192 for v in values.values()):raise Invalid('Complete the registered credential fields only')
 ref=r['resource_ref'];path='secret-request-fulfillments/'+digest(ref)+'.json'
 if await store.get(path):raise Invalid('This request is already fulfilled; rotate the credential through Resources')
 kind=content['secret_kind'];credential=dict(values)
 if kind=='graph_app':credential['connection_type']='entra'
 elif kind=='epicor_rest_basic':credential['connection_type']='epicor'
 else:credential['connection_type']=kind;credential['connection_verified']=False
 rid='request-'+digest(ref)[:24]
 saved=await library.save({'id':rid,'version':'1.0.0','label':r['body']['label'],'kind':'credential','secret':json.dumps(credential),'use_roles':['owner','editor']})
 cid=str(uuid.uuid4());result=await b.rpc(store,'approve_connection',{'id':cid,'credential_id':rid,'credential_version':'1.0.0','system':mcp_v2.SECRET_KINDS[kind][2],'capabilities':content['scopes'],'environment':content['environment']})
 safe={'request_ref':ref,'connection_id':cid,'status':'owner_approved_design_access','environment':content['environment'],'company':c['company']['code'],'tenant':c['client']['id'],'created_by':c['user']['id'],'created_at':store.now(),'authentication_verified':False}
 await store.put(path,safe);await store.event('secret_request.fulfilled',safe)
 return safe
