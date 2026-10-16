"""Human-readable review projection over existing records; no pipeline mutation."""
import asyncio
from fastapi import APIRouter
from . import studio
from .core import Invalid,digest
router=APIRouter(prefix='/api/studio/review')
LOCK=asyncio.Lock()
def synthetic(r):return r.get('test_run',False) or r.get('synthetic',False) or any(x in str(r).lower() for x in ('synthetic','review-acceptance','acceptance-review'))
async def queue(show_tests=False,offset=0):
 s=studio.store;items=[];has_more=False;audit=await s.records('audit')
 async def project(kind,rows):
  for r in rows:
   if kind in ('studio','harness'):
    key=r['record_id'];name=r.get('agent_ref','Shared harness');inp=r.get('input',{});reasons=[r.get('error',{}).get('message','') if isinstance(r.get('error'),dict) else str(r.get('error') or '')];summary='Rule found no match. Your decision is required.' if (r.get('output') if isinstance(r.get('output'),dict) else {}).get('matched') is False else 'This result needs your decision.';confidence=None;created=r['created_at']
   elif kind=='jev':
    key='jev-'+r['message_id'];name='Agent 03 · JEV';inp={'message_id':r['message_id'],'suggested_class':r['primary_classification']};reasons=r.get('review_reasons',[]);summary='Classification needs review: '+r['primary_classification'].replace('_',' ');confidence=r.get('confidence');created=r.get('classified_at') or r['created_at']
   else:
    key='invoice-'+digest({'route':r['route_id'],'attachment':r['attachment_id']})[:32];name='Agent 05 · Invoice';inp={k:r.get(k) for k in ('company','vendor_name','invoice_no','total','filename','message_id')};reasons=r.get('verdict_reasons',[]);summary='Invoice '+str(r.get('invoice_no') or '(number unresolved)')+' needs '+r['verdict'];confidence=r.get('extraction_confidence');created=r['updated_at']
   evidence=digest(r);decisions=[a for a in audit if (a.get('action')=='pipeline.review.decided' and a['payload'].get('key')==key and a['payload'].get('evidence_hash')==evidence) or (kind=='studio' and a.get('action')=='review.decided' and a['payload'].get('record_id')==key and a['payload'].get('result_hash')==r.get('content_hash'))]
   latest=max(decisions,key=lambda a:a['created_at']) if decisions else None
   if latest and latest['payload']['decision'] in ('approve','reject'):continue
   if not show_tests and synthetic(r):continue
   items.append({'key':key,'kind':kind,'agent_name':name,'summary':summary,'input':inp,'reasons':[x.replace('_',' ').capitalize() for x in reasons if x],'confidence':confidence,'created_at':created,'evidence_hash':evidence,'suggestion':None,'source_message_id':r.get('message_id'),'technical':r,'escalated':bool(latest)})
 await project('studio',[r for r in await s.records('runs') if r.get('result_status')=='REVIEW_REQUIRED'])
 await project('harness',[r for r in await s.records('harness-results') if r.get('human_review_required')])
 if s.BASE:
  specs=[('jev','a03_classifications',{'requires_review':'eq.true','order':'classified_at.desc','select':'message_id,primary_classification,confidence,review_reasons,classifier_version,taxonomy_version,evidence,classified_at,updated_at,created_at,status'}),('invoice','a05_invoices',{'verdict':'in.(review,exception)','order':'updated_at.desc','select':'route_id,attachment_id,message_id,company,vendor_name,invoice_no,total,filename,verdict,verdict_reasons,extraction_confidence,processor_version,updated_at'})]
  for kind,table,p in specs:
   r=await s.CLIENT.get(s.BASE+'/rest/v1/'+table,headers=s.HEAD,params={**p,'limit':'50','offset':str(offset)})
   if r.status_code!=200:raise Invalid('Live review queue unavailable: '+table)
   has_more=has_more or len(r.json())==50
   await project(kind,r.json())
 return {'items':items,'bounded':True,'limit_per_pipeline':50,'next_offset':offset+50 if has_more else None,'scope':'Review receipts only; existing processing and ERP writes remain unchanged'}
@router.get('/queue')
async def get_queue(show_tests:bool=False,offset:int=0):
 if offset<0:raise Invalid('Invalid queue page')
 return await queue(show_tests,offset)
@router.post('/decision')
async def decision(b:dict):
 async with LOCK:
  if b.get('decision') not in ('approve','reject','escalate'):raise Invalid('Unknown decision')
  reason=str(b.get('reason') or '').strip()
  if b['decision']!='approve' and not reason:raise Invalid('Reject and Escalate require a reason')
  row=next((r for r in (await queue(True,int(b.get('offset',0))))['items'] if r['key']==b.get('key')),None)
  if not row or row['evidence_hash']!=b.get('evidence_hash'):raise Invalid('Evidence changed or review already closed; reload before deciding')
  payload={'key':row['key'],'evidence_hash':row['evidence_hash'],'decision':b['decision'],'reason':reason,'scope':'Review receipt; no external action','reviewer':studio.store.ACTOR.get()}
  if row['kind']=='studio':
   return await studio.store.event('review.decided',{'record_id':row['key'],'result_hash':row['technical']['content_hash'],**payload})
  return await studio.store.event('pipeline.review.decided',payload)

@router.get('/source/{message_id}')
async def source(message_id:str):
 studio.store.ident(message_id);s=studio.store
 if not s.BASE:raise Invalid('Live source evidence is unavailable in the local preview')
 r=await s.CLIENT.get(s.BASE+'/rest/v1/a01_messages',headers=s.HEAD,params={'select':'message_id,mailbox,received_at,package','message_id':'eq.'+message_id,'limit':'1'})
 if r.status_code!=200 or not r.json():raise Invalid('Source message unavailable')
 row=r.json()[0];p=row.get('package',{})
 return {'message_id':row['message_id'],'mailbox':row['mailbox'],'received_at':row['received_at'],'source_fields':{k:v for k,v in p.items() if k in ('subject','sender','from','body_text','body','body_html','attachments','received_at')}}
