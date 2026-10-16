import json,hashlib
old=json.load(open('/root/flux-caddy-before.json'));new=json.load(open('/root/flux-caddy-after.json'))
def normalized(value):
 if isinstance(value,dict):return {k:normalized(v) for k,v in value.items() if k!='group'}
 if isinstance(value,list):return [normalized(v) for v in value]
 return value
def routes(config):
 return {hashlib.sha256(json.dumps(normalized(r),sort_keys=True).encode()).hexdigest() for server in config['apps']['http']['servers'].values() for r in server.get('routes',[]) if r.get('match')}
a,b=routes(old),routes(new)
assert a<=b,'An existing matched route changed'
print(json.dumps({'original_matched_routes':len(a),'matched_routes_after':len(b),'existing_matched_routes_unchanged':True}))
