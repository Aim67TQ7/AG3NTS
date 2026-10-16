"""Owner sign-in reuses PETE's existing scrypt passcode hash; Operis holds sessions."""
import asyncio,hashlib,hmac,json,os,re,secrets,time
from pathlib import Path
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse
COOKIE='__Host-flux_session'
LOCK=asyncio.Lock()
LOGIN='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>An Agent a Day · Sign in</title><style>body{background:#111820;color:#eef3f7;font:16px system-ui;max-width:380px;margin:12vh auto;padding:24px}input,button{font:inherit;width:100%;box-sizing:border-box;padding:14px;margin:10px 0;border-radius:8px}button{background:#9cdcc5;border:0}small{color:#abb8c6}</style></head><body><h1>An Agent a Day</h1><p>Sign in with your existing PETE passcode.</p><form><label>Passcode<input type="password" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="current-password" required></label><button>Sign in</button><p role="alert"></p></form><small>Agent designs, evidence and monitoring are private.</small><script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();let b=document.querySelector('button');b.disabled=true;try{let r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:document.querySelector('input').value})});if(r.ok)location.href='/';else document.querySelector('[role=alert]').textContent=r.status===429?'Too many attempts. Try again later.':'Sign-in failed. Check your PETE passcode.';}catch(e){document.querySelector('[role=alert]').textContent='Sign-in is unavailable. Try again later.';}finally{b.disabled=false;document.querySelector('input').value='';}};</script></body></html>'''

def code_matches(code):
    if not isinstance(code,str) or not re.fullmatch('[0-9]{6}',code):return False
    data=json.loads(Path(os.environ['STUDIO_PASSCODE_HASH_FILE']).read_text())
    if set(data)!={'salt','hash'} or any(not re.fullmatch('[0-9a-f]{64}',data[k]) for k in data):raise ValueError('Invalid sign-in configuration')
    actual=hashlib.scrypt(code.encode('ascii'),salt=bytes.fromhex(data['salt']),n=32768,r=8,p=3,dklen=32,maxmem=64*1024*1024)
    return hmac.compare_digest(actual,bytes.fromhex(data['hash']))

def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()

async def save_rate(store,obj):
    r=await store.CLIENT.post(store.BASE+'/storage/v1/object/'+store.BUCKET+'/auth-state/attempts.json',headers={**store.HEAD,'Content-Type':'application/json','x-upsert':'true'},content=json.dumps(obj))
    if r.status_code not in (200,201):raise ValueError('Sign-in rate state unavailable')

async def authorize(request,store):
    path=request.url.path;now=time.time();token=request.cookies.get(COOKIE,'')
    if path=='/auth/login':
        if request.method=='GET':return HTMLResponse(LOGIN,headers={'Cache-Control':'no-store'})
        if request.method!='POST':return JSONResponse({'detail':'Method denied'},405)
        # Persist attempts before expensive verification; restart cannot reset the limit.
        async with LOCK:
            rate=await store.get('auth-state/attempts.json') or {'recent':[],'day':int(now//86400),'count':0}
            rate['recent']=[t for t in rate.get('recent',[]) if t>now-600]
            if rate['day']!=int(now//86400):rate['day']=int(now//86400);rate['count']=0
            if len(rate['recent'])>=10 or rate['count']>=50:return JSONResponse({'detail':'Try again later'},429,headers={'Retry-After':'600'})
            rate['recent'].append(now);rate['count']+=1;await save_rate(store,rate)
        try:body=await request.json();valid=set(body)=={'code'} and await asyncio.to_thread(code_matches,body['code'])
        except (ValueError,KeyError,TypeError):valid=False
        await store.event('studio.sign_in',{'status':'completed' if valid else 'denied','credential_recorded':False},actor='PETE owner' if valid else 'unauthenticated',duration_ms=None)
        if not valid:return JSONResponse({'detail':'Sign-in failed'},401)
        token=secrets.token_hex(32)
        await store.put('auth-sessions/'+token_hash(token)+'.json',{'expires_at':now+28800,'actor':'PETE owner'})
        response=JSONResponse({'status':'ok'},headers={'Cache-Control':'no-store'})
        response.set_cookie(COOKIE,token,max_age=28800,secure=True,httponly=True,samesite='strict',path='/')
        return response
    if path=='/auth/logout':
        if request.method!='POST':return JSONResponse({'detail':'Method denied'},405)
        if re.fullmatch('[0-9a-f]{64}',token):
            ref=token_hash(token)
            if not await store.get('auth-revoked/'+ref+'.json'):await store.put('auth-revoked/'+ref+'.json',{'revoked_at':now})
        await store.event('studio.sign_out',{'status':'completed'},actor='PETE owner')
        response=JSONResponse({'status':'ok'});response.delete_cookie(COOKIE,path='/',secure=True,httponly=True,samesite='strict');return response
    if re.fullmatch('[0-9a-f]{64}',token):
        ref=token_hash(token);session,revoked=await asyncio.gather(store.get('auth-sessions/'+ref+'.json'),store.get('auth-revoked/'+ref+'.json'))
        if session and session.get('expires_at',0)>now and not revoked:
            request.state.actor=session['actor'];return None
    if path.startswith('/api/') or path=='/health':return JSONResponse({'detail':'Sign-in required'},401,headers={'Cache-Control':'no-store'})
    return RedirectResponse('/auth/login',status_code=303,headers={'Cache-Control':'no-store'})
