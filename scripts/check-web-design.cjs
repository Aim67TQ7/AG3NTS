const assert=require('node:assert/strict');
const ts=require('../web/node_modules/typescript');
const Module=require('node:module');
for(const extension of ['.ts','.tsx'])require.extensions[extension]=(mod,file)=>mod._compile(ts.transpileModule(require('node:fs').readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,esModuleInterop:true,target:ts.ScriptTarget.ES2021}}).outputText,file);
const React=require('../web/node_modules/react');
const {renderToStaticMarkup}=require('../web/node_modules/react-dom/server');
const {runtimeLabel,agentNames,displayAgent,pageFromLocation,pages,pageSlug}=require('../web/src/presentation.ts');
assert.equal(runtimeLabel('paused'),'Held');assert.equal(runtimeLabel('active'),'Running');assert.equal(runtimeLabel(),'Unverified');
for(const page of pages)assert.equal(pageFromLocation('?view='+pageSlug(page)),page);
assert.equal(pageFromLocation('?workflow=known-id'),'Workflows');
const names=agentNames([{id:'a',version:'0.1.9',name:'Old name'},{id:'a',version:'0.1.10',name:'Current name'}]);
assert.equal(displayAgent('a','Canvas name',names),'Current name');assert.equal(displayAgent('other','Historical agent',names),'Historical agent');
const GuidedStep=require('../web/src/GuidedStep.tsx').default;
const catalog=require('../catalog/agent-options.json');
const guided={id:'test',capability:'READ',fields:{'execute.method':{value:'system_read'}},responsibility:'Capture email references.',input_config:{kind:'email'},trigger_config:{kind:'listener',source:'mailbox',target:'test@example.invalid',delivery:'poll'}};
for(const step of ['trigger','input','execute','output','error','verify']){
 const html=renderToStaticMarkup(React.createElement(GuidedStep,{guided,catalog,step,onChange(){},onChoose(){}}));
 assert.ok(html.includes('Technical settings'),step);assert.ok(!html.includes('Portable workflow definition; review required'),step);
 const visible=html.split('<details')[0];
 assert.ok((visible.match(/<select/g)||[]).length<=3,step+' has too many primary choices');
 if(step==='execute'){assert.ok(visible.includes('Allowed access'));assert.ok(!visible.includes('transaction_write'));assert.ok(visible.includes('Agent responsibility'))}
 if(step==='trigger'){assert.ok(visible.includes('Email address'));assert.ok(!visible.includes('Listener delivery'))}
 if(step==='verify')assert.ok(visible.includes('Required approval'));
}
console.log('Web design checks passed: routing, current identity, status labels, six focused builder steps, permission visibility.');
