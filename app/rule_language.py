"""Versioned, bounded rule semantics shared by the offline fixture checker."""
import re
from decimal import Decimal,InvalidOperation
from datetime import datetime
PATH=r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*'
def lookup(doc,path):
 if not isinstance(path,str) or not re.fullmatch(PATH,path):return False,None
 for key,index in re.findall(r'([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]',path):
  if key:
   if not isinstance(doc,dict) or key not in doc:return False,None
   doc=doc[key]
  else:
   if not isinstance(doc,list) or int(index)>=len(doc):return False,None
   doc=doc[int(index)]
 return True,doc

def validate(checks,depth=0):
 if not isinstance(checks,list) or not 1<=len(checks)<=50 or depth>2:raise ValueError('Use 1–50 rules with an op key; nesting is limited to two levels')
 shapes={'present':{'op','field'},'equals':{'op','field','value'},'equals_field':{'op','field','baseline_field'},'within_tolerance':{'op','field','baseline_field','absolute_tolerance'},'percent_tolerance':{'op','field','baseline_field','percent'},'date_within_days':{'op','field','baseline_field','days'},'for_each':{'op','path','baseline_path','match_by','checks'}}
 for c in checks:
  op=c.get('op') if isinstance(c,dict) else None
  if op not in shapes or set(c)!=shapes[op]:raise ValueError('Every rule requires op and its exact operands: '+', '.join(shapes))
  for k in ('field','baseline_field','path','baseline_path','match_by'):
   if k in c and (not isinstance(c[k],str) or not re.fullmatch(PATH,c[k])):raise ValueError('Use a bounded field path for '+k)
  for k in ('absolute_tolerance','percent','days'):
   if k in c and (type(c[k]) not in (int,float) or not Decimal(str(c[k])).is_finite() or c[k]<0):raise ValueError(k+' must be an explicit finite nonnegative number')
  if op=='for_each':validate(c['checks'],depth+1)
 return checks

def evaluate(doc,checks,baseline=None,prefix=''):
 results=[];baseline=doc if baseline is None else baseline
 for c in checks:
  op=c['op']
  if op=='for_each':
   found,items=lookup(doc,c['path']);other,targets=lookup(baseline,c['baseline_path'])
   if not found or not other or not isinstance(items,list) or not isinstance(targets,list) or not items or len(items)>1000 or len(targets)>1000:
    results.append({'field_path':prefix+c['path'],'operation':op,'passed':False,'reason':'Nonempty bounded arrays required'});continue
   seen=set()
   for i,item in enumerate(items):
    has,key=lookup(item,c['match_by']);identity=(type(key).__name__,repr(key))
    if identity in seen:
     results.append({'field_path':prefix+c['path']+'['+str(i)+']','operation':op,'passed':False,'reason':'Duplicate source match key'});continue
    seen.add(identity);matches=[x for x in targets if has and lookup(x,c['match_by'])[0] and type(lookup(x,c['match_by'])[1])==type(key) and lookup(x,c['match_by'])[1]==key]
    if len(matches)!=1:results.append({'field_path':prefix+c['path']+'['+str(i)+']','operation':op,'passed':False,'reason':'Exactly one baseline match required'})
    else:results.extend(evaluate(item,c['checks'],matches[0],prefix+c['path']+'['+str(i)+'].'))
   continue
  exists,left=lookup(doc,c['field']);found,right=lookup(baseline,c.get('baseline_field',c['field']));passed=False
  try:
   if op=='present':passed=exists and left is not None
   elif op=='equals':passed=exists and type(left)==type(c['value']) and left==c['value']
   elif op=='equals_field':passed=exists and found and type(left)==type(right) and left==right
   elif op in ('within_tolerance','percent_tolerance'):
    if exists and found and type(left) in (int,float) and type(right) in (int,float):
     a,b=Decimal(str(left)),Decimal(str(right));bound=Decimal(str(c['absolute_tolerance'])) if op=='within_tolerance' else abs(b)*Decimal(str(c['percent']))/100
     passed=a.is_finite() and b.is_finite() and abs(a-b)<=bound
   elif op=='date_within_days' and exists and found and isinstance(left,str) and isinstance(right,str):
    a=datetime.fromisoformat(left.replace('Z','+00:00'));b=datetime.fromisoformat(right.replace('Z','+00:00'));passed=abs((a-b).total_seconds())<=c['days']*86400
  except (ValueError,TypeError,InvalidOperation,OverflowError):passed=False
  results.append({'field_path':prefix+c['field'],'operation':op,'passed':bool(passed)})
 return results
