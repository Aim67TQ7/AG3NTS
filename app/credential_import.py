"""Owner-only consumption of a short-lived, server-staged encrypted VPS bundle."""
import base64,json,time
from contextvars import ContextVar
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import APIRouter
from . import fresh,library,studio
from .core import Invalid
router=APIRouter(prefix='/api/studio/credential-import')
IMPORT_CONTEXT=ContextVar('credential_import',default=False)
ROOT=Path('/references/.credential-import')
def bundle():
 c=fresh.CTX.get()
 if not c or c['role']!='owner' or c['client']['id']!='bunting':raise Invalid('Bunting administrator sign-in required')
 try:
  envelope=json.loads((ROOT/'bundle.json').read_text())
  private=serialization.load_pem_private_key((ROOT/'key.pem').read_bytes(),password=None)
  key=private.decrypt(base64.b64decode(envelope['key']),padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
  data=json.loads(Fernet(key).decrypt(envelope['payload'].encode()))
 except Exception:raise Invalid('No valid encrypted VPS import is staged') from None
 if data.get('client')!=c['client']['id'] or data.get('requested_by')!=c['user']['id'] or not time.time()<data.get('expires_at',0)<time.time()+86400:raise Invalid('Import owner, client or expiry does not match')
 entries=data.get('entries',[])
 if not 1<=len(entries)<=150 or len({e['id'] for e in entries})!=len(entries):raise Invalid('Invalid import entries')
 for e in entries:
  studio.store.ident(e['id'])
  if not e['id'].startswith('vps-import-') or not isinstance(e.get('secret'),str) or not 1<=len(e['secret'])<=16384:raise Invalid('Invalid import credential')
 return data
@router.get('')
async def preview():
 data=bundle()
 return {'batch':data['batch'],'entries':[{'id':e['id'],'label':e['label'],'company':e.get('company'),'system':e['system']} for e in data['entries']]}
async def import_entry(e,data):
 prior=await studio.store.get(library.path('bunting',e['id'],'1.0.0'))
 if prior:
  if prior.get('import_batch')!=data['batch'] or prior.get('created_by')!=fresh.CTX.get()['user']['id']:raise Invalid('Existing credential conflict; no overwrite performed')
  return {'id':e['id'],'label':e['label'],'status':'already_imported'}
 metadata={k:e[k] for k in ('system','company','sources') if k in e}
 marker=IMPORT_CONTEXT.set(True)
 try:result=await library.save({'kind':'credential','id':e['id'],'version':'1.0.0','label':e['label'],'secret':e['secret'],'use_roles':['owner'],'sharing':{'scope':'company','company':e['company']} if e.get('company') in ('BMC','MAI') else {'scope':'user'},'_import':{'batch':data['batch'],**metadata}})
 finally:IMPORT_CONTEXT.reset(marker)
 saved=await studio.store.get(library.path('bunting',e['id'],'1.0.0'))
 if not saved or not saved.get('encrypted_value') or 'secret' in saved or 'content' in saved:raise Invalid('Encrypted import read-back failed')
 return {'id':result['id'],'label':result['label'],'status':'imported'}
@router.post('')
async def consume(b:dict):
 data=bundle()
 if b.get('batch')!=data['batch']:raise Invalid('Refresh the staged import before importing')
 companies=await fresh.rest(studio.store,'GET','flux_companies?select=*&client_id=eq.bunting')
 by_code={c['code']:c for c in companies};results=[]
 for e in data['entries']:
  context=fresh.CTX.get()
  # Use the actual company's RLS context, preserving the authenticated owner.
  marker=fresh.CTX.set({**context,'company':by_code.get(e.get('company'),context.get('company'))})
  try:results.append(await import_entry(e,data))
  finally:fresh.CTX.reset(marker)
 await studio.store.event('credential.vps_import_completed',{'batch':data['batch'],'count':len(results),'resource_ids':[r['id'] for r in results]},tenant='bunting')
 return {'count':len(results),'items':results,'note':'Encrypted credentials saved; no agent selection or activation performed.'}
