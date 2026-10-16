"""Validate credential setup locally; never authenticate or contact provider URLs."""
import json
from urllib.parse import urlsplit
from .core import Invalid
from .graph_credentials import normalize as graph_normalize

def required(c,key):
 value=c.get(key)
 if not isinstance(value,str) or not value.strip():raise Invalid('Enter '+key.replace('_',' '))
 return value

def https(value):
 try:u=urlsplit(value);port=u.port
 except ValueError:raise Invalid('Enter a valid HTTPS service URL')
 if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or any(ch.isspace() for ch in value):raise Invalid('Use an HTTPS service URL without embedded credentials, queries or fragments')
 return value.rstrip('/')

def normalize(secret):
 try:c=json.loads(secret)
 except (ValueError,TypeError):return secret
 if not isinstance(c,dict):return secret
 kind=c.get('connection_type')
 if kind=='entra':return graph_normalize(secret)
 if kind=='epicor':
  c['base_url']=https(required(c,'base_url'));c['company_code']=required(c,'company_code').strip();required(c,'api_key');required(c,'username');required(c,'password')
  paths=[p.strip() for p in required(c,'allowed_paths').split(',')]
  if any(not p.startswith('/') or p=='/' or p.startswith('//') or '..' in p or any(x in p for x in ('?','#','*','://')) for p in paths):raise Invalid('Use approved comma-separated relative read paths beginning with /')
  c['allowed_paths']=','.join(paths)
 elif kind=='key':
  required(c,'api_key')
  if c.get('url'):c['url']=https(c['url'])
 elif kind=='custom':
  c['url']=https(required(c,'url'));method=c.get('auth_method')
  fields={'api_key':['api_key'],'basic':['username','password'],'bearer':['access_token'],'oauth_client_credentials':['client_id','client_secret','token_url']}
  if method not in fields:raise Invalid('Choose the service authentication method')
  for key in fields[method]:required(c,key)
  if method=='oauth_client_credentials':c['token_url']=https(c['token_url'])
 else:return secret # Preserve historical credential formats; adapters still validate their own contract.
 c['connection_verified']=False
 return json.dumps(c)
