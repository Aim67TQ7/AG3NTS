"""Isolated schema/rule checker. No adapters, credentials, provider calls or runtime execution."""
import json,math,sys
from decimal import Decimal

def check(payload):
 if any(key in json.dumps(payload['schema']) for key in ('$ref','$dynamicRef')):raise ValueError('Schema references are disabled')
 from jsonschema import Draft202012Validator,FormatChecker
 validator=Draft202012Validator(payload['schema'],format_checker=FormatChecker());results=[]
 def lookup(doc,path):
  for part in path.split('.'):
   if not isinstance(doc,dict) or part not in doc:return False,None
   doc=doc[part]
  return True,doc
 for sample in payload['samples']:
  doc=sample['document'];errors=[{'field_path':'.'.join(map(str,e.absolute_path)),'constraint':e.validator} for e in validator.iter_errors(doc)];checks=[]
  for rule in payload['rules']:
   exists,left=lookup(doc,rule['field']);op=rule['op'];passed=False
   if op=='present':passed=exists and left is not None
   elif op=='equals':passed=exists and type(left)==type(rule['value']) and left==rule['value']
   elif op=='within_tolerance':
    found,right=lookup(doc,rule['baseline_field']);passed=exists and found and type(left) in (int,float) and type(right) in (int,float) and Decimal(str(left)).is_finite() and Decimal(str(right)).is_finite() and abs(Decimal(str(left))-Decimal(str(right)))<=Decimal(str(rule['absolute_tolerance']))
   checks.append({'field_path':rule['field'],'operation':op,'passed':passed})
  actual={'schema_valid':not errors,'rule_passed':all(c['passed'] for c in checks)};expected=sample['expected'];matches=all(actual[k]==v for k,v in expected.items())
  results.append({'name':sample['name'],'expected':expected,'actual':actual,'matches_expected':matches,'schema_errors':errors,'rule_checks':checks})
 return {'mode':'isolated_schema_and_rule_checks','results':results,'all_expectations_met':all(r['matches_expected'] for r in results),'live_actions':False,'publication_authorized':False}
if __name__=='__main__':
 import resource,socket
 resource.setrlimit(resource.RLIMIT_CPU,(2,2))
 if sys.platform!='darwin':resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
 resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
 def denied(*args,**kwargs):raise PermissionError('Network disabled in sample sandbox')
 class NoNetwork(socket.socket):
  def __init__(self,*args,**kwargs):denied()
 socket.socket=NoNetwork;socket.create_connection=denied;socket.getaddrinfo=denied
 print(json.dumps(check(json.load(sys.stdin)),allow_nan=False))
