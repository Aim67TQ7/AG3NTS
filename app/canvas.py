"""Canvas topology and design-release gates. No runtime activation."""
from .core import compatibility
NORMAL={'COMPLETED','VERIFIED'}
def field(n,k):return n.get('data',{}).get('guided',{}).get('fields',{}).get(k,{}).get('value')
def validate(w):
 nodes=w.get('nodes',[]);edges=w.get('edges',[]);by={n['id']:n for n in nodes};errors=[];missing=[]
 if not nodes:return {'valid':False,'blockers':[{'message':'Canvas is empty'}],'missing_handoffs':0}
 if len(by)!=len(nodes):errors.append({'message':'Duplicate card IDs'})
 incoming={k:[] for k in by};outgoing={k:[] for k in by}
 for e in edges:
  if e.get('source') not in by or e.get('target') not in by:errors.append({'message':'Unknown handoff endpoint'});continue
  source,target=by[e['source']],by[e['target']];handle=e.get('sourceHandle','COMPLETED')
  if handle in NORMAL:outgoing[e['source']].append(e['target']);incoming[e['target']].append(e['source'])
  elif handle in ('REVIEW_REQUIRED','FAILED_FINAL','REJECTED','OUTCOME_UNKNOWN'):
   if target.get('data',{}).get('review_boundary') is not True:errors.append({'node_id':e['source'],'message':handle+' must stop at an explicit Human Review boundary, not continue normal work'})
  else:errors.append({'message':'Unknown outcome port: '+str(handle)})
  if not e.get('data',{}).get('compatible'):errors.append({'node_id':e['source'],'message':'Handoff record formats are unverified','group':'record_formats'})
 roots=[k for k in by if not incoming[k]]
 if len(roots)!=1:errors.append({'message':'Normal handoffs must form one connected chain'})
 for i,n in enumerate(nodes):
  if n.get('data',{}).get('deployed'):errors.append({'node_id':n['id'],'message':'Deployed agents are monitoring references and cannot enter a new build'})
  if field(n,'output.next')=='chain_to_next_node' or i<len(nodes)-1:
   if not outgoing[n['id']]:missing.append(n['id'])
  if len(incoming[n['id']])>1 or len(outgoing[n['id']])>1:errors.append({'node_id':n['id'],'message':'Branch/join behavior needs a separate certified contract'})
  if n.get('data',{}).get('capability')=='WRITE':
   prior=incoming[n['id']]
   if len(prior)!=1 or by[prior[0]].get('data',{}).get('capability')!='COMMS' or field(by[prior[0]],'verify.approval_gate') not in ('single_approver','two_approvers'):
    errors.append({'node_id':n['id'],'message':'Writer requires a directly connected human approval card','group':'approval_gates'})
   if len(prior)==1 and by[prior[0]].get('data',{}).get('capability')=='COMMS' and field(by[prior[0]],'output.record_type')!='review.decision':errors.append({'node_id':n['id'],'message':'Approval card must produce a durable review decision, not a message receipt','group':'approval_gates'})
   if field(n,'verify.approval_gate') not in ('single_approver','two_approvers'):errors.append({'node_id':n['id'],'message':'Writer approval cannot be disabled','group':'approval_gates'})
  if field(n,'identity.environment')!='TEST':errors.append({'node_id':n['id'],'message':'Build certification is TEST-only'})
 # A cycle cannot count as an approval path or a valid chain.
 seen=set();todo=roots[:]
 while todo:
  k=todo.pop()
  if k in seen:continue
  seen.add(k);todo.extend(outgoing[k])
 if len(seen)!=len(by):errors.append({'message':'Cycle or unreachable cards detected'})
 for k in missing:errors.append({'node_id':k,'message':'Required normal output is not connected','group':'handoffs'})
 return {'valid':not errors,'blockers':errors,'missing_handoffs':len(missing),'scope':'Design validation only; no activation'}
