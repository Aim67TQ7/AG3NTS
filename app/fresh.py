"""Fresh Operis on ZODA. User JWTs and database RLS; no legacy service credential."""
import os,json,re,time,uuid
from urllib.parse import quote,urlparse,parse_qs
from contextvars import ContextVar
from collections.abc import Mapping
from fastapi.responses import JSONResponse,HTMLResponse,RedirectResponse,FileResponse
URL='https://ezlmmegowggujpcnzoda.supabase.co'
KEY='sb_publishable_2ndeL5Oo0IKVcuEo-Y30IQ_vzI1AmwB'
CTX=ContextVar('flux_client',default=None)
ACCESS='__Host-flux_access';REFRESH='__Host-flux_refresh';CLIENT_COOKIE='__Host-flux_client';COMPANY_COOKIE='__Host-flux_company'
def enabled():return os.environ.get('FLUX_FRESH')=='1'
class Headers(Mapping):
 def values_map(self):
  token=(CTX.get() or {}).get('token','')
  headers={'apikey':KEY,'x-flux-session':token} if token.startswith('flx_') else {'apikey':KEY,'Authorization':'Bearer '+(token or KEY)}
  company=(CTX.get() or {}).get('company') or {}
  if company.get('id'):headers['x-flux-company']=company['id']
  return headers
 def __iter__(self):return iter(self.values_map())
 def __len__(self):return len(self.values_map())
 def __getitem__(self,k):return self.values_map()[k]
HEAD=Headers()
def physical(path):
 c=CTX.get()
 if not c:raise ValueError('Client sign-in required')
 if '..' in path.split('/') or path.startswith('/'):raise ValueError('Invalid storage path')
 return c['client']['id']+'/'+path
class Scope(Mapping):
 def __iter__(self):return iter(('tenant','company','facility'))
 def __len__(self):return 3
 def __getitem__(self,k):return scope()[k]
def scope():
 c=CTX.get()
 if not c or not c.get('company'):raise ValueError('Add and select a company in Client & users before building agents')
 return {'tenant':c['client']['id'],'company':c['company']['code'],'facility':c['company']['facility']}
async def rest(store,method,path,body=None):
 r=await store.CLIENT.request(method,URL+'/rest/v1/'+path,headers={**HEAD,'Prefer':'return=representation,resolution=merge-duplicates'},json=body)
 if r.status_code>=400:raise ValueError('Client operation denied or unavailable (HTTP '+str(r.status_code)+')')
 return r.json() if r.content else None
async def object_put(store,path,obj):
 c=CTX.get();physical(path)
 r=await store.CLIENT.post(URL+'/rest/v1/flux_app_objects',headers={**HEAD,'Prefer':'return=minimal'},json={'client_id':c['client']['id'],'path':path,'body':obj})
 if r.status_code>=400:raise ValueError('Save failed or this version already exists (HTTP '+str(r.status_code)+')')
 return obj
async def object_get(store,path):
 physical(path);rows=await rest(store,'GET','flux_app_objects?select=body&client_id=eq.'+CTX.get()['client']['id']+'&path=eq.'+quote(path,safe=''))
 return rows[0]['body'] if rows else None
async def objects(store,prefix,offset=0,limit=None):
 physical(prefix);out=[];page=100 if limit is None else limit
 while True:
  rows=await rest(store,'GET','flux_app_objects?select=body&client_id=eq.'+CTX.get()['client']['id']+'&path=like.'+quote(prefix+'/*',safe='')+'&order=path.desc&limit='+str(page)+'&offset='+str(offset))
  out.extend(r['body'] for r in rows)
  if limit is not None or len(rows)<page:return out
  offset+=page
async def library_page(store,prefix,offset,limit):return await objects(store,prefix,offset,limit)
LOGIN='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/png" sizes="32x32" href="/branding/operis-favicon-32.png?v=green-phi-1"><title>OφERIS · Sign in</title><style>body{background:#101923;color:#eef4f6;font:16px system-ui;max-width:420px;margin:10vh auto;padding:24px}input,button{box-sizing:border-box;width:100%;padding:14px;margin:8px 0 20px;border-radius:8px;font:inherit}button{background:#62cdb0;border:0;cursor:pointer}p{line-height:1.6}</style></head><body><h1>OφERIS</h1><p id="login-intro">Sign in to your client workspace.</p><p id="login-steps" hidden>1. Sign in → 2. Choose company and approve → 3. Return to your AI app</p><form><label>Email<input id="email" type="email" autocomplete="username" required></label><label>Password<input id="password" type="password" autocomplete="current-password" required></label><button>Sign in</button></form><p role="alert"></p><script>const returnTo=new URLSearchParams(location.search).get('return_to')||'/';const connecting=returnTo.startsWith('/oauth/authorize?');if(connecting){document.title='OφERIS · Continue your AI connection';document.querySelector('#login-intro').textContent='Sign in to OφERIS to finish connecting your AI app. You will return there after approving the connection.';document.querySelector('#login-steps').hidden=false;document.querySelector('button').textContent='Sign in & continue';}document.querySelector('form').onsubmit=async e=>{e.preventDefault();let s=document.querySelector('[role=alert]'),button=document.querySelector('button');button.disabled=true;s.textContent='Signing in…';try{let r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.querySelector('#email').value,password:document.querySelector('#password').value,return_to:returnTo})});let x=await r.json();if(r.ok){location.href=x.next||'/';}else s.textContent=x.detail||'Sign-in failed.';}catch(e){s.textContent='Sign-in is unavailable. Try again later.';}finally{button.disabled=false;}};</script></body></html>'''

CHANGE_PASSWORD='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/png" sizes="32x32" href="/branding/operis-favicon-32.png?v=green-phi-1"><title>OφERIS · Set your password</title><style>body{background:#101923;color:#eef4f6;font:16px system-ui;max-width:440px;margin:10vh auto;padding:24px}input,button{box-sizing:border-box;width:100%;padding:14px;margin:10px 0 20px;border-radius:8px;font:inherit}button{background:#62cdb0;border:0}</style></head><body><h1>Set your own OφERIS password</h1><p>Replace your temporary password before opening your client workspace. This changes only your OφERIS password.</p><form><label>New password<input id="password" type="password" autocomplete="new-password" minlength="12" required></label><label>Confirm password<input id="confirm" type="password" autocomplete="new-password" minlength="12" required></label><button>Save password and continue</button></form><p role="alert"></p><script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();let p=document.querySelector('#password').value,s=document.querySelector('[role=alert]');if(p!==document.querySelector('#confirm').value){s.textContent='The passwords do not match.';return}let r=await fetch('/auth/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:p})});let x=await r.json();if(r.ok)location.href='/';else s.textContent=x.detail||'Password could not be saved.';}</script></body></html>'''

def cookie(response,name,value,age=3600):response.set_cookie(name,value,max_age=age,secure=True,httponly=True,samesite='strict',path='/')
def login_destination(value):
 if not isinstance(value,str) or len(value)>10000 or '\r' in value or '\n' in value:return '/'
 parsed=urlparse(value)
 return value if not parsed.scheme and not parsed.netloc and parsed.path=='/oauth/authorize' and parsed.query and not parsed.fragment else '/'
async def auth_request(request,store,path):
 if request.method=='GET' and path=='/auth/login':return HTMLResponse(LOGIN,headers={'Cache-Control':'no-store'})
 if request.method!='POST':return JSONResponse({'detail':'Method denied'},405)
 if path=='/auth/logout':
  await store.CLIENT.post(URL+'/rest/v1/rpc/flux_password_signout',headers={'apikey':KEY,'x-flux-session':request.cookies.get(ACCESS,'')},json={})
  response=JSONResponse({'status':'ok'})
  for k in (ACCESS,REFRESH,CLIENT_COOKIE,COMPANY_COOKIE,'__Host-flux_support'):response.delete_cookie(k,secure=True,httponly=True,samesite='strict',path='/')
  return response
 if path!='/auth/login':return JSONResponse({'detail':'Use email and password to sign in'},404)
 body=await request.json();email=body.get('email','').strip().lower();password=body.get('password','')
 if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or not isinstance(password,str) or not 1<=len(password)<=1024:return JSONResponse({'detail':'Enter your email and password'},400)
 result=await store.CLIENT.post(URL+'/rest/v1/rpc/flux_password_signin',headers={'apikey':KEY},json={'email':email,'password':password})
 data=result.json() if result.status_code==200 else {}
 if not data.get('token'):return JSONResponse({'detail':data.get('error','Sign-in failed. Check your email and password.')},401)
 response=JSONResponse({'status':'ok','next':login_destination(body.get('return_to'))});cookie(response,ACCESS,data['token'],data['expires_in']);response.delete_cookie(REFRESH,secure=True,httponly=True,samesite='strict',path='/');return response

def profile(user):
 metadata=user.get('user_metadata') or {}
 if not isinstance(metadata,dict):metadata={}
 names=[user.get(k) for k in ('display_name','full_name','name')]+[metadata.get(k) for k in ('display_name','full_name','name')]
 name=next((n.strip()[:160] for n in names if isinstance(n,str) and n.strip()),user.get('email',''))
 avatars=[user.get(k) for k in ('avatar_url','picture')]+[metadata.get(k) for k in ('avatar_url','picture')]
 avatar=None
 for value in avatars:
  if not isinstance(value,str) or len(value)>2048:continue
  parsed=urlparse(value)
  if parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password:
   avatar=value;break
 return {'display_name':name,'avatar_url':avatar}

async def boundary(request,call_next,store):
 path=request.url.path;host=os.environ.get('STUDIO_PUBLIC_HOST','flux.by-pete.com')
 if request.url.hostname!=host:return JSONResponse({'detail':'Host denied'},403)
 from . import mcp_connection
 if mcp_connection.managed(path):
  if len(await request.body())>262144:return JSONResponse({'detail':'Request too large'},413)
  try:
   public=await mcp_connection.public(request,store)
   if public is not None:return public
  except (ValueError,KeyError,TypeError):return JSONResponse({'error':'invalid_request'},400)
 if request.method not in ('GET','HEAD'):
  if request.headers.get('origin')!='https://'+host or request.headers.get('sec-fetch-site')=='cross-site':return JSONResponse({'detail':'Origin denied'},403)
  if request.headers.get('content-type','').split(';')[0]!='application/json':return JSONResponse({'detail':'JSON required'},415)
  if len(await request.body())>(8*1024*1024 if path=='/api/studio/draft-agent' else 1048576):return JSONResponse({'detail':'Request too large'},413)
 if request.method in ('GET','HEAD') and path in ('/branding/operis-ophi-emblem.png','/branding/operis-favicon-32.png','/branding/operis-favicon-180.png'):
  return FileResponse(store.WEB_ROOT/'branding'/path.rsplit('/',1)[1],media_type='image/png')
 if path=='/overview' and request.method=='GET':
  from .public_overview import OVERVIEW
  return HTMLResponse(OVERVIEW,headers={'Cache-Control':'no-store'})
 if path=='/readyz':
  r=await store.CLIENT.get(URL+'/auth/v1/settings',headers={'apikey':KEY});return JSONResponse({'status':'ok' if r.status_code==200 else 'unavailable'},200 if r.status_code==200 else 503)
 if path in ('/auth/login','/auth/signup','/auth/verify','/auth/logout','/auth/change-password','/auth/password'):return await auth_request(request,store,path)
 token=request.cookies.get(ACCESS,'');new_tokens=None
 u=None
 if token.startswith('flx_'):
  checked=await store.CLIENT.post(URL+'/rest/v1/rpc/flux_session_user',headers={'apikey':KEY,'x-flux-session':token},json={})
  if checked.status_code==200 and isinstance(checked.json(),dict) and checked.json().get('id'):u=checked
 elif token:u=await store.CLIENT.get(URL+'/auth/v1/user',headers={'apikey':KEY,'Authorization':'Bearer '+token})
 if u is None or u.status_code!=200:
  refresh=request.cookies.get(REFRESH,'')
  if refresh:
   rr=await store.CLIENT.post(URL+'/auth/v1/token?grant_type=refresh_token',headers={'apikey':KEY},json={'refresh_token':refresh})
   if rr.status_code==200:
    new_tokens=rr.json();token=new_tokens['access_token'];u=await store.CLIENT.get(URL+'/auth/v1/user',headers={'apikey':KEY,'Authorization':'Bearer '+token})
 if u is None or u.status_code!=200:
  if path=='/' and request.method=='GET':
   from .public_overview import OVERVIEW
   return HTMLResponse(OVERVIEW,headers={'Cache-Control':'no-store'})
  return JSONResponse({'detail':'Sign-in required'},401) if path.startswith('/api/') else RedirectResponse('/auth/login'+('?return_to='+quote(path+'?'+request.url.query,safe='') if path=='/oauth/authorize' else ''),303)
 user=u.json()
 marker=CTX.set({'token':token});actor_marker=store.ACTOR.set(user['id'])
 try:
  memberships=await rest(store,'GET','flux_memberships?select=client_id,role&user_id=eq.'+user['id']);clients=await rest(store,'GET','flux_clients?select=id,name,client_code&order=name')
  roles={m['client_id']:m['role'] for m in memberships};clients=[c for c in clients if c['id'] in roles]
  if not clients:return JSONResponse({'detail':'Your account is verified. Ask your administrator to grant client access.'},403)
  wanted=request.cookies.get(CLIENT_COOKIE,'');client=next((c for c in clients if c['id']==wanted),clients[0]);companies=await rest(store,'GET','flux_companies?select=*&client_id=eq.'+client['id']+'&order=name')
  company=next((c for c in companies if c['id']==request.cookies.get(COMPANY_COOKIE)),companies[0] if companies else None)
  CTX.set({'token':token,'user':user,'client':client,'role':roles[client['id']],'company':company})
  from . import discovery,owner_support
  if path.startswith(('/owner-support','/api/owner-support')) or path in ('/guidance','/api/support-guidance'):response=await owner_support.browser(request,store)
  elif path in ('/welcome','/api/discovery'):response=await discovery.browser(request,store)
  elif path=='/' and request.method=='GET':
   onboarding=await discovery.rpc(store,'get') if company else {'assigned':False}
   response=RedirectResponse('/welcome',303) if onboarding.get('assigned') and not onboarding.get('submitted') else await call_next(request)
  elif mcp_connection.managed(path):response=await mcp_connection.browser(request,store)
  elif path=='/api/account':
   response=JSONResponse({'email':user['email'],**profile(user),'user_id':user['id'],'client':client,'clients':[dict(c,role=roles[c['id']]) for c in clients],'role':roles[client['id']],'companies':companies,'company':company,'vault_ready':True})
  elif path=='/api/account/switch':
   b=await request.json()
   if b.get('client') not in roles:return JSONResponse({'detail':'Client access denied'},403)
   response=JSONResponse({'status':'ok'});cookie(response,CLIENT_COOKIE,b['client'],86400*7)
   response.delete_cookie(COMPANY_COOKIE,secure=True,httponly=True,samesite='strict',path='/')
  elif path=='/api/account/company':
   b=await request.json()
   if b.get('id') not in {c['id'] for c in companies}:return JSONResponse({'detail':'Company access denied'},403)
   response=JSONResponse({'status':'ok'});cookie(response,COMPANY_COOKIE,b['id'],86400*7)
  elif path=='/api/account/credential-selection':
   if roles[client['id']] not in ('owner','editor'):return JSONResponse({'detail':'Builder permission required'},403)
   from . import library
   b=await request.json();agent_id=b['agent_id'];store.ident(agent_id)
   resource=await library.lookup(b['resource'])
   if resource['kind']!='credential':raise ValueError('Choose an encrypted credential')
   consent={'id':str(uuid.uuid4()),'agent_id':agent_id,'client':client['id'],'selected_by':user['id'],'company':company['code'],'resource_id':resource['id'],'resource_version':resource['version'],'resource_hash':resource['content_hash'],'created_at':store.now()}
   await store.put('credential-selections/'+consent['id']+'.json',consent)
   await store.event('credential.selected',consent,tenant=client['id'])
   response=JSONResponse({'selection_id':consent['id'],'selected_by':user['id']})
  elif path.startswith('/api/account/'):
   if roles[client['id']]!='owner':return JSONResponse({'detail':'Admin permission required'},403)
   if path=='/api/account/companies' and request.method=='POST':
    b=await request.json()
    if not re.fullmatch('[A-Za-z0-9_-]{1,30}',b.get('code','')) or not 1<=len(b.get('name',''))<=120:raise ValueError('Supply a company code and name')
    response=JSONResponse(await rest(store,'POST','flux_companies',{'client_id':client['id'],'code':b['code'],'name':b['name'],'facility':b.get('facility','')[:40]}))
   elif path=='/api/account/users':
    if request.method=='GET':response=JSONResponse(await rest(store,'GET','flux_access_grants?select=email,role&client_id=eq.'+client['id']))
    else:
     b=await request.json();email=b.get('email','').strip().lower()
     if email==user['email'].lower():raise ValueError('Your own administrator grant cannot be changed here')
     if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or b.get('role') not in ('owner','editor','user'):raise ValueError('Supply an email and valid role')
     if b.get('revoke'):
      response=JSONResponse(await rest(store,'DELETE','flux_access_grants?client_id=eq.'+client['id']+'&email=eq.'+quote(email,safe='')))
     else:
      existing_grants=await rest(store,'GET','flux_access_grants?select=email&client_id=eq.'+client['id']+'&email=eq.'+quote(email,safe=''))
      response=JSONResponse(await rest(store,'POST','flux_access_grants',{'client_id':client['id'],'email':email,'role':b['role']}))
      if company and not existing_grants:
       from . import governance
       await governance.rpc('company_set',{'email':email,'company':company['code'],'enabled':True})
   else:return JSONResponse({'detail':'Unknown account operation'},404)
  elif path=='/api/studio/users':response=JSONResponse({'users':[{'id':user['id'],'label':user['email']}],'roles':['designer','publisher'],'workspace_key':'zoda:'+client['id']+':'+(company or {}).get('id','none')+':'+user['id'],'identity_source':'Supabase Auth','directory_connected':True})
  elif path=='/api/studio/deployed-agents':response=JSONResponse({'agents':[]})
  elif path=='/api/studio/review/queue':
   from . import runtime_reviews
   query=dict(request.query_params)
   response=JSONResponse(await runtime_reviews.queue(query.get('show_tests','false').lower()=='true',int(query.get('offset','0'))))
  elif path=='/api/studio/review/decision' and request.method=='POST':
   if roles[client['id']] not in ('owner','editor'):return JSONResponse({'detail':'Admin or builder permission required to review'},403)
   from . import runtime_reviews
   response=JSONResponse(await runtime_reviews.decision(await request.json()))
  elif path=='/api/studio/records' or path=='/api/studio/records/rows' or path=='/api/studio/records/registry':response=await call_next(request)
  elif path.startswith(('/api/studio/records','/api/studio/review','/api/studio/templates','/api/live','/api/lineage','/api/execute','/api/workflows/run','/api/workflows/control','/api/review','/agent-results')):response=JSONResponse({'detail':'No operational integration is configured for this fresh client workspace'},409)
  elif request.method not in ('GET','HEAD') and roles[client['id']]=='user':response=JSONResponse({'detail':'Builder or administrator permission required'},403)
  elif path=='/health':response=JSONResponse({'status':'ok','project':URL,'deployment':'flux-zoda-fresh','version':store.APP_VERSION})
  else:response=await call_next(request)
  if path.startswith('/api/') and not path.startswith('/api/owner-support') and request.method not in ('GET','HEAD'):
   await store.event('client.action',{'path':path,'http_status':response.status_code,'client':client['id']},tenant=client['id'],duration_ms=None)
  if new_tokens:
   cookie(response,ACCESS,new_tokens['access_token'],int(new_tokens.get('expires_in',3600)));cookie(response,REFRESH,new_tokens['refresh_token'],86400*7)
  response.headers['Cache-Control']='no-store'
  return response
 except (ValueError,KeyError,TypeError) as e:return JSONResponse({'detail':str(e)},400)
 finally:CTX.reset(marker);store.ACTOR.reset(actor_marker)

async def verify_selection(store,ref,agent_id):
 c=CTX.get()
 if not c or not ref.get('selection_id'):raise ValueError('Manually select the encrypted credential for this agent')
 consent=await store.get('credential-selections/'+ref['selection_id']+'.json')
 if not consent or any(consent.get(k)!=v for k,v in {'agent_id':agent_id,'client':c['client']['id'],'selected_by':ref.get('selected_by',c['user']['id']),'resource_id':ref['id'],'resource_version':ref['version'],'resource_hash':ref['content_hash']}.items()):raise ValueError('Credential selection does not belong to this agent, user or client')
 return consent
