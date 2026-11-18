import React, {useEffect, useState} from 'react';

export default function ExternalDirectoryStatus(){
 const [state,setState]=useState<any>(null);
 useEffect(()=>{let live=true;async function refresh(){try{const r=await fetch('/api/studio/copackers-operator/status');if(!r.ok)throw Error('Unavailable');const d=await r.json();if(live)setState(d)}catch{if(live)setState({available:false})}}refresh();const timer=setInterval(refresh,30000);return()=>{live=false;clearInterval(timer)}},[]);
 const label=state===null?'Checking external runtime':state.available?'External runtime reachable':'External runtime unavailable';
 return <span className="agent-power-wrap" title="This agent runs independently in Docker. AG3NTS observes it; native Studio execution is not enabled."><span className={'agent-power '+(state?.available?'on':state===null?'unknown':'waiting')} role="status"><span className="power-dot"/><span className="power-label">{label}</span></span><a className="text-link" href="https://copackers-operator.by-pete.com/status" target="_blank" rel="noopener noreferrer">Business status</a></span>
}
