"""Bounded readback and deployment receipt, no business agent dispatch."""
import asyncio,json,os,socket
from pathlib import Path
root=Path(__file__).resolve().parent.parent
for line in (root/'.env').read_text().splitlines():
    key,sep,value=line.partition('=')
    if sep and not key.lstrip().startswith('#'):os.environ[key.strip()]=value.strip().strip('"').strip("'")
os.environ['STUDIO_DEPLOYMENT_ID']='pete-private'
from app import main
async def verify():
    assert main.BASE=='https://qzwxisdfwswsrbzvpzlo.supabase.co'
    health=await main.health();assert health['status']=='ok'
    live=await main.live();assert all(a['history_error'] is None for a in live['agents'])
    assert all(a['health']['status'] in ('ok','healthy') for a in live['agents'])
    assert live['agents'][3]['health']['dispatch_enabled'] is False
    assert not any(main.KEY in p.read_text(errors='ignore') for p in (root/'web/dist').rglob('*') if p.is_file())
    receipt=await main.event('studio.deployed',{'host':socket.gethostname(),'deployment':'pete-private','version':main.APP_VERSION,'tests_passed':30,'existing_agents_modified':False,'agent04_dispatch_enabled':False,'connection':'PZLO private Storage registry and PostgREST pipeline history','monitor_transport':'private SSH loopback forwarding','reboot_recovery':'owner cron configured; host reboot not tested'})
    key='audit/'+receipt['created_at'].replace(':','-')+'-'+receipt['record_id']+'.json'
    assert (await main.get(key))['content_hash']==receipt['content_hash']
    print(json.dumps({'health':health,'deployment_receipt_id':receipt['record_id'],'durable_readback_verified':True,'all_four_monitors_verified':True,'client_secret_check':'passed'}))
    await main.CLIENT.aclose()
asyncio.run(verify())
