#!/usr/bin/python3
"""Keep the existing Caddy-only Operis firewall rule aligned to Docker identity."""
import ipaddress,json,os,pathlib,re,subprocess
from datetime import datetime,timezone
CONTAINER='hub-caddy'
NETWORK='hub-net'
TARGET='172.18.0.1'
PORT='8498'
COMMENT='Operis Studio Caddy only'
RULE=re.compile(r'^172\.18\.0\.1\s+8498/tcp\s+ALLOW(?: IN)?\s+(\S+)\s+#\s+(?:FLUX Studio Caddy only|Operis Studio Caddy only)\s*$')
def command(args):
 p=subprocess.run(args,text=True,capture_output=True,timeout=12,env={**os.environ,'LC_ALL':'C'})
 if p.returncode:raise RuntimeError('Command failed: '+args[0]+' '+p.stderr.strip()[:250])
 return p.stdout

def proxy_address(info):
 if info.get('Name')!='/'+CONTAINER or not info.get('State',{}).get('Running'):raise ValueError('Expected running Caddy container')
 if 'caddy-docker-proxy' not in info.get('Config',{}).get('Image',''):raise ValueError('Unexpected proxy image')
 network=info['NetworkSettings']['Networks'][NETWORK]
 address=ipaddress.ip_address(network['IPAddress'])
 if address.version!=4 or address not in ipaddress.ip_network('172.18.0.0/16') or network.get('Gateway')!=TARGET or str(address)==TARGET:raise ValueError('Unexpected proxy network')
 return str(address)

def managed_sources(status):
 if not status.startswith('Status: active'):raise ValueError('Firewall must already be active')
 found=set()
 for line in status.splitlines():
  match=RULE.fullmatch(line.strip())
  if match:
   value=ipaddress.ip_address(match[1])
   if value not in ipaddress.ip_network('172.18.0.0/16'):raise ValueError('Unexpected managed rule source')
   found.add(str(value))
 return found

def sync():
 source=proxy_address(json.loads(command(['docker','inspect',CONTAINER]))[0])
 existing=managed_sources(command(['ufw','status']))
 if source not in existing:command(['ufw','allow','from',source,'to',TARGET,'port',PORT,'proto','tcp','comment',COMMENT])
 # Confirm the intended proxy can reach the app before removing an obsolete rule.
 health=json.loads(command(['docker','exec',CONTAINER,'wget','-qO-','-T','5','--header=Host: flux.by-pete.com','http://'+TARGET+':'+PORT+'/readyz']))
 if health.get('status')!='ok':raise RuntimeError('Proxy-to-app health check failed')
 for old in sorted(existing-{source}):command(['ufw','--force','delete','allow','from',old,'to',TARGET,'port',PORT,'proto','tcp'])
 record={'checked_at':datetime.now(timezone.utc).isoformat(),'proxy':CONTAINER,'source':source,'destination':TARGET+':'+PORT,'proxy_to_app':'ok','removed_obsolete_sources':sorted(existing-{source})}
 directory=pathlib.Path('/var/lib/operis-proxy-firewall');directory.mkdir(mode=0o755,exist_ok=True)
 temp=directory/'status.tmp';temp.write_text(json.dumps(record,indent=2));temp.chmod(0o644);temp.replace(directory/'status.json')
 print(json.dumps(record))
if __name__=='__main__':sync()
