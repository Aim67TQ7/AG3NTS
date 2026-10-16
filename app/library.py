"""Tenant resource library and encrypted credential references; no browser secret reads."""
import os,json,time,uuid,asyncio
from fastapi import APIRouter
from cryptography.fernet import Fernet
from . import studio
from .core import Invalid,digest
router=APIRouter(prefix='/api/studio/library')
CONTROL_LOCK=asyncio.Lock()
KINDS={'schema','template','asset','instructions','rules','credential'}

def context(manage=False):
    from . import fresh
    if fresh.enabled():
        c=fresh.CTX.get()
        if not c:raise Invalid("Client sign-in required")
        if manage and c["role"] not in ("owner","editor"):raise Invalid("Admin or builder permission required")
        return c["client"]["id"],c["user"]["id"],c["role"]
    tenant=os.environ.get('STUDIO_TENANT_ID','')
    memberships=json.loads(os.environ.get('STUDIO_TENANT_MEMBERS','{}'))
    actor=studio.store.ACTOR.get();role=memberships.get(tenant,{}).get(actor)
    if not tenant or role not in ('owner','editor','user'):raise Invalid('Tenant membership is not configured for this operator')
    if manage and role not in ('owner','editor'):raise Invalid('Resource management permission required')
    studio.store.ident(tenant);return tenant,actor,role

def cipher():
    key=os.environ.get('STUDIO_VAULT_MASTER_KEY')
    if not key:raise Invalid('Encrypted vault is not configured; no credential was stored')
    try:return Fernet(key.encode())
    except Exception:raise Invalid('Vault encryption configuration is invalid')

def path(tenant,id,version):return 'library-'+tenant+'/'+id+'--'+version+'.json'
def control_key(r):return ('legacy:'+r['kind']+':' if r.get('legacy') else 'library:')+r['id']
async def controls():
    tenant,_,_=context();rows=await studio.store.records('library-controls-'+tenant) if hasattr(studio.store,'records') else [];out={}
    for r in rows:
        if r['tenant']==tenant and r['revision']>out.get(r['key'],{}).get('revision',0):out[r['key']]=r
    return out
async def state_for(key):return (await controls()).get(key,{'locked':False,'archived':False,'revision':0})
async def assert_editable(key):
    try:s=await state_for(key)
    except Invalid:
        if os.environ.get('STUDIO_PUBLIC_HOST'):raise
        return
    if s['locked']:raise Invalid('Resource is locked; an owner must unlock it first')
    if s['archived']:raise Invalid('Resource is deleted; restore it before making changes')
async def lookup(ref,allow_archived=False):
    tenant,actor,role=context();studio.store.ident(ref['id']);studio.store.ident(ref['version'])
    if ref.get('legacy'):
        rows=await studio.store.records('resources')
        r=next((x for x in rows if x['id']==ref['id'] and x['version']==ref['version'] and x['kind']==ref['kind'] and not x.get('library_ref') and (x.get('tenant')==tenant or (not x.get('tenant') and not os.environ.get('STUDIO_PUBLIC_HOST')))),None)
        if r:r={**r,'tenant':tenant,'use_roles':['owner','editor'],'legacy':True}
    else:r=await studio.store.get(path(tenant,ref['id'],ref['version']))
    if not r or r['tenant']!=tenant or r['content_hash']!=ref['content_hash']:raise Invalid('Resource reference is unavailable in this tenant')
    if not __import__('app.fresh',fromlist=['enabled']).enabled() and role not in r['use_roles']:raise Invalid('Resource use permission required')
    from .governance import check
    await check('resource:'+r['id'],'use')
    c=await state_for(control_key(r))
    if c['archived'] and not allow_archived:raise Invalid('Resource is deleted; restore it before new use')
    return r

def metadata(r):return {k:v for k,v in r.items() if k not in ('content','encrypted_value')}
@router.get('/status')
async def status():
    try:tenant,actor,role=context();return {'tenant':tenant,'role':role,'vault_ready':__import__('app.fresh',fromlist=['enabled']).enabled() or bool(os.environ.get('STUDIO_VAULT_MASTER_KEY')),'membership_ready':True}
    except Invalid:return {'membership_ready':False,'vault_ready':False,'blocker':'Configure authenticated tenant membership before storing resources or keys.'}
@router.get('')
async def listing(offset:int=0,limit:int=25,kind:str='',show_deleted:bool=False):
    tenant,actor,role=context()
    if not 0<=offset or not 1<=limit<=100 or (kind and kind not in KINDS):raise Invalid('Invalid resource page')
    # Storage pages are bounded; encrypted payloads never become list results.
    prefix='library-'+tenant
    if hasattr(studio.store,'library_page'):
        rows=await studio.store.library_page(prefix,offset,limit)
    else:
        r=await studio.store.CLIENT.post(studio.store.BASE+'/storage/v1/object/list/'+studio.store.BUCKET,headers=studio.store.HEAD,json={'prefix':prefix,'limit':limit,'offset':offset,'sortBy':{'column':'name','order':'asc'}})
        if r.status_code!=200:raise Invalid('Resource index unavailable')
        rows=[await studio.store.get(prefix+'/'+x['name']) for x in r.json() if x.get('id')]
    legacy=await studio.store.records('resources') if hasattr(studio.store,'records') and offset==0 else []
    rows += [{**r,'tenant':tenant,'use_roles':['owner','editor'],'legacy':True} for r in legacy if not r.get('library_ref') and (r.get('tenant')==tenant or (not r.get('tenant') and not os.environ.get('STUDIO_PUBLIC_HOST')))]
    states=await controls();items=[];access={}
    if __import__('app.fresh',fromlist=['enabled']).enabled():
        from .governance import rpc
        access={a['object_key']:a for a in (await rpc('list'))['items']}
    for x in rows:
        if not x or (kind and x['kind']!=kind):continue
        acl=access.get('resource:'+x['id'])
        if role not in (acl['use_roles'] if acl else x['use_roles']):continue
        c=states.get(control_key(x),{'locked':False,'archived':False,'revision':0})
        if c['archived'] and not show_deleted:continue
        items.append({**metadata(x),**({'sharing':{'scope':acl['scope'],'company':acl['company_code']},'use_roles':acl['use_roles'],'accountable_owner':acl['owner_id']} if acl else {}),'locked':c['locked'],'deleted':c['archived'],'control_revision':c['revision']})
    return {'items':items,'next_offset':offset+limit if len(rows)>=limit else None,'tenant':tenant}

@router.post('')
async def save(b:dict):
    tenant,actor,role=context(True);start=time.monotonic()
    if b.get('kind') not in KINDS:raise Invalid('Unknown resource type')
    id=b.get('id') or 'res-'+str(uuid.uuid4());version=b.get('version','1.0.0')
    studio.store.ident(id);studio.store.ident(version)
    await assert_editable('library:'+id)
    label=b.get('label','')
    if not isinstance(label,str) or not 1<=len(label)<=160:raise Invalid('Resource name is required')
    roles=b.get('use_roles',['owner','editor','user'])
    if not isinstance(roles,list) or not roles or any(x not in ('owner','editor','user') for x in roles):raise Invalid('Invalid use permissions')
    if __import__('app.fresh',fromlist=['enabled']).enabled():
        # New versions require separate secret-management authority, not just use.
        prior=await studio.store.get(path(tenant,id,version))
        existing=[x for x in await studio.store.records('library-'+tenant) if x.get('id')==id]
        if existing:
            from .governance import check
            await check('resource:'+id,'manage_secret' if b['kind']=='credential' else 'edit')
    r={'id':id,'version':version,'tenant':tenant,'label':label,'kind':b['kind'],'created_by':actor,'created_at':studio.store.now(),'use_roles':roles,'status':'draft','schema_version':'1.0.0'}
    if b.get('sharing'):r['sharing']=b['sharing']
    if b['kind']=='credential':
        secret=b.get('secret')
        if not isinstance(secret,str) or not 1<=len(secret)<=16384:raise Invalid('Credential value is required')
        from .credential_setup import normalize
        secret=normalize(secret)
        # Only non-secret connection hints are exposed to credential pickers.
        try:connection=json.loads(secret)
        except (ValueError,TypeError):connection={}
        if isinstance(connection,dict) and connection.get('connection_type')=='entra':
            r['system']='outlook_graph'
            r['connection_metadata']={k:connection[k] for k in ('mailbox','folder_id') if isinstance(connection.get(k),str)}
        elif isinstance(connection,dict) and connection.get('connection_type')=='epicor':
            r['system']='epicor_rest';r['connection_metadata']={'company_code':connection['company_code']}
        # Tenant and immutable identity are inside authenticated ciphertext as well.
        from . import fresh
        if fresh.enabled():
            r['encrypted_value']=await fresh.rest(studio.store,'POST','rpc/flux_encrypt_credential',{'client':tenant,'resource':id,'version':version,'secret':secret})
            r['key_version']='zoda-vault-1'
        else:
            r['encrypted_value']=cipher().encrypt(json.dumps({'tenant':tenant,'id':id,'version':version,'value':secret}).encode()).decode()
            r['key_version']=os.environ.get('STUDIO_VAULT_KEY_VERSION','1')
    else:
        content=b.get('content')
        if content is None or len(json.dumps(content).encode())>700000:raise Invalid('Supply content under 700 KB')
        if b['kind']=='schema':
            from .core import schema
            schema(content)
        r['content']=content
    r['content_hash']=digest(r)
    # Intent audit contains only safe metadata; no plaintext or ciphertext.
    await studio.store.event('library.save_requested',metadata(r),tenant=tenant,duration_ms=int((time.monotonic()-start)*1000))
    await studio.store.put(path(tenant,id,version),r)
    await studio.store.event('library.saved',metadata(r),tenant=tenant,duration_ms=int((time.monotonic()-start)*1000))
    return metadata(r)
@router.post('/inspect')
async def inspect(b:dict):
    r=await lookup(b,allow_archived=True)
    if r['kind']=='credential':return metadata(r)
    return {**metadata(r),'content':r['content']}

async def resolve_credential(ref,*,workflow_id,adapter):
    """Internal runtime hook only. Never registered as an HTTP/model tool."""
    from . import fresh
    if fresh.enabled():raise Invalid('Credential execution requires a separately approved runtime adapter')
    r=await lookup(ref)
    if r['kind']!='credential':raise Invalid('Reference is not a credential')
    if r['key_version']!=os.environ.get('STUDIO_VAULT_KEY_VERSION','1'):raise Invalid('Credential key version is unavailable')
    if not workflow_id or adapter not in json.loads(os.environ.get('STUDIO_VAULT_ALLOWED_ADAPTERS','[]')):raise Invalid('Runtime adapter is not authorized')
    payload=json.loads(cipher().decrypt(r['encrypted_value'].encode()))
    if any(payload[k]!=r[k] for k in ('tenant','id','version')):raise Invalid('Credential binding mismatch')
    await studio.store.event('credential.used',{'reference':metadata(r),'workflow_id':workflow_id,'adapter':adapter},tenant=r['tenant'],duration_ms=0)
    return payload['value']

@router.post('/approve')
async def approve(b:dict):
    tenant,actor,role=context(True);r=await lookup(b)
    from .governance import check
    await check('resource:'+r['id'],'approve')
    await assert_editable(control_key(r))
    if r.get('legacy'):
        ref=r['kind']+':'+r['id']+'@'+r['version'];await studio.approve_resource({'resource_ref':ref});return {'resource_ref':ref,'status':'approved'}
    if r['kind'] not in ('schema','rules','instructions'):raise Invalid('This resource does not need agent-contract approval')
    if r['kind']=='schema':
        from .core import schema
        schema(r['content'])
    canonical_id=tenant+'.'+r['id'];ref=r['kind']+':'+canonical_id+'@'+r['version'];p='resources/'+canonical_id+'--'+r['version']+'.json'
    canonical={'id':canonical_id,'version':r['version'],'kind':r['kind'],'label':r['label'],'tenant':tenant,'content':r['content'],'content_hash':digest(r['content']),'library_ref':metadata(r)}
    old=await studio.store.get(p)
    if old and old['content_hash']!=canonical['content_hash']:raise Invalid('Resource version conflict')
    if not old:await studio.store.put(p,canonical)
    await studio.store.event('resource.published',{'resource_ref':ref,'definition_hash':canonical['content_hash'],'decision':'operator-approved','library_ref':metadata(r)},tenant=tenant)
    await studio.store.event('library.approved',{'id':r['id'],'version':r['version'],'resource_ref':ref},tenant=tenant)
    return {'resource_ref':ref,'status':'approved','runtime_enabled':False}

@router.post('/control')
async def control(b:dict):
    async with CONTROL_LOCK:
        tenant,actor,role=context(True);r=await lookup(b,allow_archived=True)
        from .governance import check
        await check('resource:'+r['id'],'manage_secret' if r['kind']=='credential' else 'edit')
        key=control_key(r);s=await state_for(key)
        if b.get('control_revision',0)!=s['revision']:raise Invalid('Resource controls changed; reload first')
        action=b.get('action')
        if action not in ('lock','unlock','archive','restore'):raise Invalid('Unknown resource control')
        if action=='unlock' and role!='owner':raise Invalid('Only a tenant owner can unlock a resource')
        if action in ('archive','restore') and s['locked']:raise Invalid('Unlock this resource before deleting or restoring it')
        n={'tenant':tenant,'key':key,'revision':s['revision']+1,'locked':action=='lock' if action in ('lock','unlock') else s['locked'],'archived':action=='archive' if action in ('archive','restore') else s['archived'],'actor':actor,'created_at':studio.store.now()}
        await studio.store.put('library-controls-'+tenant+'/'+digest(key)+'--'+str(n['revision']).zfill(8)+'.json',n)
        await studio.store.event('library.'+action,{'key':key,'resource_hash':r['content_hash'],'control_revision':n['revision']},tenant=tenant)
        return n

async def active_resources(rows):
    try:
        tenant,_,_=context();states=await controls()
    except Invalid:
        if os.environ.get('STUDIO_PUBLIC_HOST'):raise
        return rows
    if __import__('app.fresh',fromlist=['enabled']).enabled():
        from .governance import rpc
        access={a['object_key']:a for a in (await rpc('list'))['items']}
        role=context()[2]
        rows=[r for r in rows if role in access.get('resource:'+(r.get('library_ref') or r)['id'],{}).get('use_roles',r.get('use_roles',['owner','editor','user']))]
    return [r for r in rows if not states.get(control_key(r['library_ref']) if r.get('library_ref') else 'legacy:'+r['kind']+':'+r['id'],{}).get('archived')]
