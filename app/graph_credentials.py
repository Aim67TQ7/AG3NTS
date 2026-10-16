"""Validate stored app-only Graph mail settings without contacting Microsoft."""
import json,re,uuid
from datetime import date
from .core import Invalid

def normalize(secret):
 try:config=json.loads(secret)
 except (ValueError,TypeError):return secret
 if not isinstance(config,dict) or config.get('connection_type')!='entra':return secret
 for key in ('tenant_id','client_id'):
  try:uuid.UUID(str(config.get(key,'')))
  except (ValueError,TypeError,AttributeError):raise Invalid('Graph '+key.replace('_',' ')+' must be a Microsoft directory/application ID')
 if not isinstance(config.get('client_secret'),str) or not config['client_secret'].strip():raise Invalid('Graph client-secret value is required')
 mailbox=config.get('mailbox','')
 if not isinstance(mailbox,str) or not re.fullmatch(r'[^\s/@]+@[^\s/@]+\.[^\s/@]+',mailbox):raise Invalid('Graph mailbox email address is required')
 folder=config.get('folder_id','')
 if not isinstance(folder,str) or not folder.strip() or len(folder)>512 or any(c in folder for c in '/?#'):raise Invalid('Choose a Graph folder name or ID')
 expiry=config.get('secret_expires_on','')
 if expiry:
  try:date.fromisoformat(expiry)
  except (ValueError,TypeError):raise Invalid('Use a valid Graph secret expiry date')
 config.update({'auth_mode':'application','authority_url':'https://login.microsoftonline.com/'+config['tenant_id'],'resource_url':'https://graph.microsoft.com','scope':'https://graph.microsoft.com/.default','requested_permission':'Mail.Read','allowed_mailboxes':[mailbox],'permission_verified':False})
 return json.dumps(config)
