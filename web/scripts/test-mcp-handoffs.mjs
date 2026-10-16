// Exercise the actual canvas projection. Semantic outcomes persist; only visual handle IDs change.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const source=fs.readFileSync(new URL('../src/RecordBindings.tsx',import.meta.url),'utf8');
const start=source.indexOf('export function recordGraph('),end=source.indexOf('\nasync function api(',start);
const js=ts.transpileModule(source.slice(start,end),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
const {recordGraph}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
const nodes=Array.from({length:7},(_,i)=>({id:String(i),position:{x:100+i*360,y:120}}));
const semantic=nodes.slice(1).map((n,i)=>({id:'edge-'+i,source:String(i),target:n.id,sourceHandle:'COMPLETED',targetHandle:'input',data:{direct:true,semantics:'Durable FLUX handoff; no direct agent call',dispatch_enabled:false}}));
const before=JSON.stringify(semantic),graph=recordGraph(nodes,[],semantic),wires=graph.edges.filter(e=>e.data?.semantics);
assert.equal(graph.cards.length,7);assert.equal(wires.length,6);
for(const e of wires){assert.equal(e.sourceHandle,'output');assert.equal(e.targetHandle,'input');assert.match(e.label,/COMPLETED.*proposed FLUX handoff/);assert.equal(e.data.dispatch_enabled,false);}
assert.equal(JSON.stringify(semantic),before);
console.log('PASS: seven cards, six renderable semantic handoffs, source data unchanged, dispatch Off');
