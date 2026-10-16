import json,unittest,time,hashlib,os,tempfile
from unittest.mock import patch
from starlette.requests import Request
from app import browser_auth as auth

def req(path,method='GET',token='',body=None):
    raw=json.dumps(body or {}).encode();headers=[(b'host',b'flux.by-pete.com')]
    if token:headers.append((b'cookie',(auth.COOKIE+'='+token).encode()))
    async def receive():return {'type':'http.request','body':raw,'more_body':False}
    return Request({'type':'http','method':method,'path':path,'headers':headers,'query_string':b''},receive)
class Store:
    def __init__(self):self.rows={};self.events=[]
    async def get(self,p):return self.rows.get(p)
    async def put(self,p,x):self.rows[p]=x
    async def event(self,a,p,**kw):self.events.append((a,p,kw))
class BrowserAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.store=Store()
    async def test_unauthenticated_data_is_denied(self):
        self.assertEqual((await auth.authorize(req('/api/state'),self.store)).status_code,401)
        self.assertEqual((await auth.authorize(req('/'),self.store)).status_code,303)
    async def test_forged_session_is_denied(self):
        self.assertEqual((await auth.authorize(req('/api/state',token='a'*64),self.store)).status_code,401)
    async def test_expired_session_is_denied(self):
        token='a'*64;self.store.rows['auth-sessions/'+auth.token_hash(token)+'.json']={'expires_at':time.time()-1,'actor':'PETE owner'}
        self.assertEqual((await auth.authorize(req('/api/state',token=token),self.store)).status_code,401)
    async def test_valid_session_then_logout_revokes_it(self):
        token='b'*64;self.store.rows['auth-sessions/'+auth.token_hash(token)+'.json']={'expires_at':time.time()+100,'actor':'PETE owner'}
        r=req('/api/state',token=token);self.assertIsNone(await auth.authorize(r,self.store));self.assertEqual(r.state.actor,'PETE owner')
        await auth.authorize(req('/auth/logout','POST',token),self.store)
        self.assertEqual((await auth.authorize(req('/api/state',token=token),self.store)).status_code,401)
    async def test_persisted_rate_limit_blocks_before_verification(self):
        self.store.rows['auth-state/attempts.json']={'recent':[time.time()]*10,'day':int(time.time()//86400),'count':10}
        with patch.object(auth,'code_matches',side_effect=AssertionError('Must not verify')):
            self.assertEqual((await auth.authorize(req('/auth/login','POST',body={'code':'111222'}),self.store)).status_code,429)
    async def test_login_cookie_is_secure_and_audit_contains_no_code(self):
        async def rate(s,obj):await s.put('auth-state/attempts.json',obj)
        with patch.object(auth,'save_rate',rate),patch.object(auth,'code_matches',return_value=True):
            response=await auth.authorize(req('/auth/login','POST',body={'code':'111222'}),self.store)
        cookie=response.headers['set-cookie'];self.assertIn('Secure',cookie);self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=strict',cookie)
        self.assertNotIn('111222',json.dumps(self.store.events));self.assertNotIn(cookie.split(';')[0].split('=')[1],json.dumps(self.store.rows))
    def test_real_hash_verification_rejects_bad_code(self):
        salt=bytes.fromhex('11'*32);hashed=hashlib.scrypt(b'111222',salt=salt,n=32768,r=8,p=3,dklen=32,maxmem=64*1024*1024)
        with tempfile.NamedTemporaryFile(mode='w') as f:
            json.dump({'salt':salt.hex(),'hash':hashed.hex()},f);f.flush()
            with patch.dict(os.environ,{'STUDIO_PASSCODE_HASH_FILE':f.name}):
                self.assertTrue(auth.code_matches('111222'));self.assertFalse(auth.code_matches('111223'));self.assertFalse(auth.code_matches('bad'))
