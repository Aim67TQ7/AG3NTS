import React from 'react';
export function triggerConfig(g:any){if(g.trigger_config)return g.trigger_config;const get=(k:string)=>g.fields?.[k]?.value;let old=get('trigger.type'),kind=old==='schedule'?'schedule':old==='studio_user_action'?'manual':old==='retry'?'retry':['mailbox_message','sharepoint_file'].includes(old)?'listener':'webhook';return {kind,source:old==='mailbox_message'?'mailbox':old==='sharepoint_file'?'folder':'flux',delivery:get('trigger.schedule')&&get('trigger.schedule')!=='not_scheduled'?'poll':'webhook',timezone:'America/Chicago'};}

export function triggerIdentity(config:any){
  const kind=config?.kind;
  if(kind==='webhook')return config.source==='flux'?{shape:'flux',label:'FLUX record'}:{shape:'webhook',label:'External webhook'};
  return ({listener:{shape:'listener',label:'Listener'},schedule:{shape:'schedule',label:'Schedule / Cron'},manual:{shape:'manual',label:'Manual'},retry:{shape:'retry',label:'Retry'}} as any)[kind]||{shape:'unknown',label:'Trigger not set'};
}
export function TriggerShape({config}:any){
  const {shape}=triggerIdentity(config);
  return <svg className="trigger-shape" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {shape==='schedule'&&<circle cx="16" cy="16" r="12"/>}
    {shape==='flux'&&<><ellipse cx="16" cy="7" rx="11" ry="4"/><path d="M5 7v18c0 5.3 22 5.3 22 0V7M5 16c0 5.3 22 5.3 22 0"/></>}
    {shape==='listener'&&<><path d="M16 28V16M10 28h12M9 10a10 10 0 0 0 0 12M23 10a10 10 0 0 1 0 12M5 5a17 17 0 0 0 0 22M27 5a17 17 0 0 1 0 22"/><circle cx="16" cy="15" r="3"/></>}
    {shape==='webhook'&&<><path d="m9 4 14 0 7 12-7 12H9L2 16Z"/><path d="M9 16h14m-5-5 5 5-5 5"/></>}
    {shape==='manual'&&<path d="M7 3v26l22-13Z"/>}
    {shape==='retry'&&<><path d="M7 10a12 12 0 1 1-2 12M7 3v9H1"/></>}
    {shape==='unknown'&&<><path d="m16 3 13 13-13 13L3 16Z"/><path d="M13 12a3 3 0 1 1 4 3v3m0 5h.01"/></>}
  </svg>;
}
export function TriggerBadge({guided,compact=false}:any){
  const config=guided?triggerConfig(guided):null;
  const {label}=triggerIdentity(config);
  const detail=config?.kind==='listener'&&config.delivery==='poll'?' · scheduled polling':'';
  return <span className="trigger-badge" title={label+detail} aria-label={label+detail}><TriggerShape config={config}/>{!compact&&<span>{label}</span>}</span>;
}
