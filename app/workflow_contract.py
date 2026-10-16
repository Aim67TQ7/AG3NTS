"""Whole-design graph checks and navigable findings; never execute a node."""
from .core import compatibility

def field(g,key):return g.get('fields',{}).get(key,{}).get('value')
def dependency(session,pin,field_path):
 r=session.resources.get(pin);proposal=session.state['resources'].get(pin,{})
 parent=proposal.get('review_parent_id') if r and r['status']=='proposed' else None
 proposal_id=parent or proposal.get('proposal_id')
 return {'resource_id':pin,'field_path':field_path,'status':r['status'] if r else 'missing','content_hash':r.get('content_hash') if r else None,'proposal_id':proposal_id,'review_url':'/ai-connections#proposal-'+proposal_id if proposal_id else '/ai-connections','read':({'tool':'read_change_set','arguments':{'change_set_id':proposal['change_set_id']}} if parent else {'tool':'read_resource','arguments':{'id':pin}}) if r else None,'resolve':{'tool':'propose_schema' if 'schema' in field_path else 'propose_rule','required_action':'Propose the missing artifact, then complete human Resources approval'}}
def enrich(session,findings,g=None,node_id=None,workflow_id=None):
 out=[]
 for original in findings:
  f=dict(original);f.update(workflow_id=workflow_id,node_id=node_id or f.get('node_id'),draft_id=g.get('id') if g else f.get('draft_id'))
  f.setdefault('field_paths',[]);f.setdefault('dependencies',[])
  if g:
   for path in f['field_paths']:
    pin=field(g,path)
    if path in ('input.schema','output.schema','execute.rule','execute.instructions') and pin not in (None,'none'):
     d=dependency(session,pin,path)
     if d not in f['dependencies']:f['dependencies'].append(d)
  f.setdefault('resource_id',next((d['resource_id'] for d in f['dependencies'] if 'resource_id' in d),None))
  f['location']={'workflow_id':workflow_id,'node_id':f.get('node_id'),'draft_id':f.get('draft_id'),'field_paths':f['field_paths'],'resource_id':f.get('resource_id'),'edge_id':f.get('edge_id')}
  out.append(f)
 return out

def validate(session,w):
 nodes={n['id']:n for n in w.get('nodes',[])};edges=list(w.get('edges',[]));
 # Durable FLUX record/status producers establish handoffs even without visual wires.
 for aid,a in nodes.items():
  writes=a.get('data',{}).get('guided',{}).get('bindings',{}).get('writes',{})
  for bid,target in nodes.items():
   reads=target.get('data',{}).get('guided',{}).get('bindings',{}).get('reads',{})
   if aid==bid or not writes.get('record_type') or writes.get('record_type')!=reads.get('record_type') or not writes.get('registry_hash') or writes['registry_hash']!=reads.get('registry_hash'):continue
   for outcome,status in writes.get('outcomes',{}).items():
    if status==reads.get('status') and not any(e.get('source')==aid and e.get('target')==bid and e.get('sourceHandle')==outcome for e in edges):edges.append({'id':'record:'+aid+':'+bid+':'+outcome,'source':aid,'target':bid,'sourceHandle':outcome})
 findings=[];incoming={k:[] for k in nodes};adj={k:[] for k in nodes}
 def add(rule,message,node=None,paths=None,**kw):
  g=nodes.get(node,{}).get('data',{}).get('guided',{})
  findings.extend(enrich(session,[{'rule_id':rule,'message':message,'field_paths':paths or [],'blocks_publish':True,**kw}],g,node,w['id']))
 if any(n['data']['guided'].get('builder_version')==2 for n in nodes.values()) and len(w.get('entry_nodes') or list(nodes)[:1])!=1:add('single-entry-required','Choose exactly one entry node',paths=['entry_nodes'])
 if not nodes:add('workflow-empty','Add at least one agent before publication',paths=['nodes'])
 for e in edges:
  a,b=e.get('source'),e.get('target');outcome=e.get('sourceHandle')
  if a not in nodes or b not in nodes:add('unknown-edge-endpoint','Both edge endpoints must belong to this workflow',paths=['edges'],edge_id=e.get('id'));continue
  adj[a].append(b);incoming[b].append(e)
  left=nodes[a]['data']['guided'];right=nodes[b]['data']['guided'];lp=field(left,'output.schema');rp=field(right,'input.schema');ls=session.resources.get(lp);rs=session.resources.get(rp)
  allowed=session.catalog().get('outcomes',{}).get(field(left,'output.outcomes'),[])
  if outcome not in allowed:add('undeclared-outcome','Select an outcome declared by the source agent',a,['output.outcomes'],edge_id=e['id'])
  deps=[dependency(session,lp,'output.schema'),dependency(session,rp,'input.schema')];contract={'source_schema':{'id':lp,'content_hash':ls.get('content_hash') if ls else None},'target_schema':{'id':rp,'content_hash':rs.get('content_hash') if rs else None},'source':a,'target':b}
  if not ls or not rs:add('unverified-connection-contract','Choose both versioned schemas for this edge',b,['input.schema'],edge_id=e['id'],dependencies=deps)
  elif not compatibility(ls['content'],rs['content']):
   absent=[x for x in rs['content'].get('required',[]) if x not in ls['content'].get('required',[])]
   add('incompatible-connection','Source output does not guarantee the target input contract',b,['input.schema'],edge_id=e['id'],dependencies=deps,missing_required_inputs=absent,**contract)
 bindings={}
 for nid,node in nodes.items():
  guide=node['data']['guided'];record=field(guide,'output.record_type');pin=field(guide,'output.schema');resource=session.resources.get(pin)
  if not record or record in ('none','custom_needs_schema') or not resource:continue
  previous=bindings.get(record)
  if previous and previous['content_hash']!=resource['content_hash']:
   add('record-type-schema-conflict',record+' is already bound to schema '+previous['schema_id']+' by node '+previous['node_id'],nid,['output.record_type'],record_type=record,source_schema={'id':previous['schema_id'],'content_hash':previous['content_hash']},target_schema={'id':pin,'content_hash':resource['content_hash']},conflicting_node_id=previous['node_id'])
  else:bindings[record]={'node_id':nid,'schema_id':pin,'content_hash':resource['content_hash']}
 roots=w.get('entry_nodes') or list(nodes)[:1]
 for root in roots:
  if root not in nodes:add('invalid-entry-node','Entry node is not part of this workflow',paths=['entry_nodes'])
 reached=set();todo=[r for r in roots if r in nodes]
 while todo:
  n=todo.pop()
  if n in reached:continue
  reached.add(n);todo.extend(adj[n])
 for n in nodes:
  if n not in reached:add('unreachable-node','Connect this agent to an entry node or explicitly designate it as an entry',n,['trigger.type','input.schema'])
  if n not in roots and not incoming[n]:add('missing-required-input','This non-entry agent has no upstream input producer',n,['input.schema'])
 colors={}
 def visit(n):
  if colors.get(n)==1:add('workflow-cycle','Resolve the workflow cycle before publication',n,['edges']);return
  if colors.get(n)==2:return
  colors[n]=1
  for target in adj[n]:visit(target)
  colors[n]=2
 for n in nodes:visit(n)
 terminals={(x['node'],x['outcome']):x['destination'] for x in w.get('terminal_outcomes',[])}
 for (n,o),dest in terminals.items():
  if n not in nodes or o not in session.catalog()['outcomes'].get(field(nodes.get(n,{}).get('data',{}).get('guided',{}),'output.outcomes'),[]):add('invalid-terminal-outcome','Terminal routes must name a workflow member and a declared outcome',n,['terminal_outcomes'])
  if dest not in ('terminal','human_review'):add('invalid-terminal-destination','Choose terminal or human_review',n,['terminal_outcomes'])
 for n,node in nodes.items():
  g=node['data']['guided'];findings.extend(enrich(session,session.validation(g)['findings'],g,n,w['id']))
  if not g.get('bindings'):add('durable-record-binding-required','Bind approved durable FLUX input/output records before publication',n,['bindings'])
  for o in session.catalog()['outcomes'].get(field(g,'output.outcomes'),[]):
   matches=[e for e in edges if e.get('source')==n and e.get('sourceHandle')==o]
   if not matches and (n,o) not in terminals:add('outcome-without-destination','Connect '+o+' or explicitly route it to a terminal or human review',n,['output.outcomes'],outcome=o)
   if len(matches)>1 or matches and (n,o) in terminals:add('ambiguous-outcome-destination','Use exactly one destination for this outcome',n,['output.outcomes'],outcome=o)
 return {'valid':not findings,'blocks_publish':bool(findings),'findings':findings,'entry_nodes':roots,'reachable_node_ids':sorted(reached),'catalog_rule_count':len(session.catalog()['rules']),'runtime_certified':False,'pending_proposals':session.pending_proposals(w)}
