"""Mailbox-parameterized email-to-JSON workflow template; creates drafts only."""
import copy,re
from fastapi import APIRouter
from .core import Invalid
from .mail_runtime import SCHEMAS
from .workflow_json import FORMAT,VERSION,validate,create_draft
router=APIRouter(prefix='/api/studio/email-template')
TEMPLATE_VERSION='1.0.0'
def definition(mailbox):
 if not isinstance(mailbox,str):raise Invalid('Enter an email address')
 mailbox=mailbox.strip()
 if len(mailbox)>254 or not re.fullmatch(r'[^\s/@<>]+@[^\s/@<>]+\.[^\s/@<>]+',mailbox):raise Invalid('Enter a valid mailbox email address')
 steps=[]
 names=['Email Retriever','Attachment Parser','JSON Converter'];caps=['READ','DOC','MAP'];records=['email.captured','document.read','document.read']
 for i in range(3):
  source_record='email.captured' if i<2 else 'document.read';input_slot='resource-'+str(max(1,i));output_slot='resource-'+str(i+1)
  functions={'trigger':{'type':'mailbox_message' if i==0 else 'flux_record','source_record':'none' if i==0 else source_record,'schedule':'not_scheduled','duplicates':'skip_if_key_seen'},'input':{'source_system':'outlook_graph' if i==0 else 'flux','schema':{'resource':input_slot},'freshness':'current_revision_only','when_missing':'review_required'},'execute':{'method':['system_read','document_parse','deterministic_map'][i],'authority':'P2' if i==0 else 'P0','model_access':'off','time_limit':'2m','cost_ceiling':'zero','instructions':'none','rule':'none'},'output':{'record_type':records[i],'schema':{'resource':output_slot},'next':'chain_to_next_node' if i<2 else 'none','outcomes':'completed_review','evidence':'source_refs_hashes'},'error':{'retry':'3x_exponential','retryable':'timeouts_and_5xx','escalation':'human_review_queue','ambiguous_external':'not_applicable'},'verify':{'method':'automatic','approval_gate':'none','postcondition':'record_exists_schema_valid','fixtures':'standard_set'}}
  configuration={'input_config':{'kind':'email','source_system':'outlook_graph','mailbox':mailbox,'folder_id':'Inbox'} if i==0 else {'kind':'flux'},'trigger_config':{'kind':'listener','source':'mailbox','target':mailbox,'folder_id':'Inbox','delivery':'poll'} if i==0 else {'kind':'flux','source':'flux','delivery':'record','record_type':source_record}}
  steps.append({'id':'step-'+str(i+1),'name':names[i],'responsibility':['Capture new email and attachment references from the selected mailbox.','Read attachment text and tables with source evidence.','Convert the parsed document into structured JSON.'][i],'capability':caps[i],'functions':functions,'configuration':configuration,'bindings':{'reads':{'record_type':source_record,'status':'completed'},'writes':{'record_type':records[i],'outcomes':{'COMPLETED':'completed','REVIEW_REQUIRED':'review_required'}}},'contracts':{'input':copy.deepcopy(SCHEMAS[max(0,i-1)]),'output':copy.deepcopy(SCHEMAS[i])},'resources':list(dict.fromkeys([input_slot,output_slot])),'position':{'x':80+380*i,'y':120},'adapter_hint':['approved_mailbox_capture','document_parse_local','document_json_v1'][i]})
 package={'format':FORMAT,'schema_version':VERSION,'workflow':{'name':('Email to JSON · '+mailbox)[:149],'steps':steps,'connections':[{'id':'handoff-'+str(i+1),'from':{'step':'step-'+str(i+1),'port':'COMPLETED'},'to':{'step':'step-'+str(i+2),'port':'input'},'delivery':'durable_record','record_type':records[i],'status':'completed'} for i in range(2)]},'resources':[{'id':'resource-'+str(i+1),'kind':'schema','label':names[i]+' JSON format','content':copy.deepcopy(s)} for i,s in enumerate(SCHEMAS)]}
 validate(package);return package
@router.post('')
async def use_template(b:dict):
 package=definition(b.get('mailbox'));result=await create_draft(package,draft_name=package['workflow']['name'])
 from . import studio
 await studio.store.event('workflow.email_template_created',{'workflow_id':result['workflow']['id'],'template':'email-to-json','template_version':TEMPLATE_VERSION,'execution_enabled':False})
 return {**result,'template_version':TEMPLATE_VERSION,'note':'Email workflow draft created. Check mailbox access before enabling.'}
