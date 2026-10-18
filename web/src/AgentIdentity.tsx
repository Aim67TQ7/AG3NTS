import React from 'react';
export function AgentIdentity({name,code,catalog}:any){const type=catalog?.capabilities?.find((c:any)=>c.code===code);return <span className="agent-identity" style={{'--agent-color':type?.color||'#94a3b8'} as React.CSSProperties}>{code&&<span className="agent-code" title={type?.title||code}>{code}</span>}{name&&<strong>{name}</strong>}</span>}
export function agentCode(id:string,agents:any[]=[],canvases:any[]=[]){return agents.find(a=>a.id===id)?.capability||canvases.flatMap(w=>w.nodes||[]).find(n=>n.data?.guided?.id===id)?.data?.capability}
