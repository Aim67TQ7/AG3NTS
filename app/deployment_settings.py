"""Explicit administrator configuration from private server-only FLUX storage."""
import json,os
from .core import Invalid
async def load(store):
    deployment=os.environ.get('STUDIO_DEPLOYMENT_ID','')
    if not os.environ.get('STUDIO_PUBLIC_HOST') or not deployment:return
    store.ident(deployment)
    settings=await store.get('deployment-settings/'+deployment+'.json')
    if not settings:return
    if settings.get('deployment')!=deployment:raise Invalid('Deployment settings identity mismatch')
    tenant=settings['tenant'];store.ident(tenant)
    members=settings['members']
    if not isinstance(members,dict) or any(role not in ('owner','editor','user') for role in members.values()):raise Invalid('Invalid deployment membership')
    os.environ['STUDIO_TENANT_ID']=tenant
    os.environ['STUDIO_TENANT_MEMBERS']=json.dumps({tenant:members})
    os.environ['STUDIO_RECORD_TENANT_ID']=tenant
    os.environ['STUDIO_RECORD_ADMINS']=','.join(actor for actor,role in members.items() if role=='owner')
