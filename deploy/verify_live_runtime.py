import asyncio,json
from app import main
async def verify():
    h=await main.health();assert h['status']=='ok';assert h['project']=='https://qzwxisdfwswsrbzvpzlo.supabase.co'
    live=await main.live();assert all(a['health']['status'] in ('ok','healthy') and a['history_error'] is None for a in live['agents'])
    assert live['agents'][3]['health']['dispatch_enabled'] is False
    r=await main.event('studio.https_deployed',{'url':'https://flux.by-pete.com','deployment':'pete-https','runtime_version':main.APP_VERSION,'tests_passed':37,'auth':'existing PETE scrypt hash; durable FLUX sessions','public_browser_sign_in_verified':False,'helper':'fixed Studio update/status/restart only','agent04_dispatch_enabled':False,'existing_agents_modified':False,'proxy_source_allowed':'172.18.0.3','upstream':'172.18.0.1:8498'})
    path='audit/'+r['created_at'].replace(':','-')+'-'+r['record_id']+'.json'
    assert (await main.get(path))['content_hash']==r['content_hash']
    print(json.dumps({'deployment':'pete-https','version':main.APP_VERSION,'FLUX':'verified','all_four_agent_monitors':'verified','durable_receipt':r['record_id']}))
    await main.CLIENT.aclose()
asyncio.run(verify())
