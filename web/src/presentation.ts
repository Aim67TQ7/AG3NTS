// Presentation labels never change stored IDs, versions, or historical evidence.
export const pages=['Dashboard','Client & users','Overview','Agent Library','Build Agent','Workflows','Resources','Operis Monitor','Human Review','Execution History','Audit & Cost','Email Results'];
export const pageSlug=(page:string)=>page.toLowerCase().replaceAll(' & ','-').replaceAll(' ','-');
export function pageFromLocation(search=location.search){const q=new URLSearchParams(search);return pages.find(p=>pageSlug(p)===q.get('view'))||(q.has('workflow')?'Workflows':'Dashboard')}
export function runtimeLabel(state?:string){return ({checking:'Checking',unavailable:'Unavailable',active:'Running',paused:'Held',held:'Held',stopped:'Stopped',draft:'Draft',not_tested:'Not tested'} as Record<string,string>)[String(state||'').toLowerCase()]||'Unverified'}
export function agentNames(agents:any[]=[]){const m=new Map<string,any>();for(const a of agents)if(!m.has(a.id)||String(a.version).localeCompare(String(m.get(a.id).version),undefined,{numeric:true})>0)m.set(a.id,a);return new Map<string,string>(Array.from(m,([id,a])=>[id,a.name||a.guided?.name||'Unnamed agent']))}
export const displayAgent=(id:string,name:string,names:Map<string,string>)=>names.get(id)||name||'Unnamed agent';
