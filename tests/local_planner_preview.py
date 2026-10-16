"""Isolated local UI preview: no credentials, provider calls or remote storage."""
import copy,os
os.environ.pop('ANTHROPIC_API_KEY',None)
os.environ.pop('STUDIO_PUBLIC_HOST',None)
os.environ['STUDIO_TENANT_ID']='local-preview'
os.environ['STUDIO_TENANT_MEMBERS']='{"local-preview":{"ssh-owner":"owner"}}'
os.environ.pop('STUDIO_VAULT_MASTER_KEY',None)
from app import main,studio
from pathlib import Path
import json,tempfile
ROOT=Path(__file__).resolve().parent.parent/'local-data'/'preview-store'
ROOT.mkdir(parents=True,exist_ok=True)
def target(path):
 p=(ROOT/path).resolve()
 if not p.is_relative_to(ROOT.resolve()):raise ValueError('Invalid local storage path')
 return p
async def put(path,obj):
 p=target(path);p.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.pending-')
 try:
  with os.fdopen(fd,'w') as f:json.dump(obj,f);f.flush();os.fsync(f.fileno())
  os.link(tmp,p) # Atomically create an immutable object; never overwrite.
 finally:os.unlink(tmp)
 return obj
async def get(path):
 p=target(path)
 return json.loads(p.read_text()) if p.exists() else None
async def records(kind):
 folder=target(kind)
 return [json.loads(p.read_text()) for p in folder.glob('*.json')] if folder.exists() else []
async def library_page(prefix,offset,limit):
 folder=target(prefix)
 paths=sorted(folder.glob('*.json')) if folder.exists() else []
 return [json.loads(p.read_text()) for p in paths[offset:offset+limit]]
main.library_page=library_page
async def deployed():return {'agents':[]}
main.put=put;main.get=get;main.records=records;studio.deployed_agents=deployed
for route in main.app.routes:
 if getattr(route,'path','')=='/api/studio/deployed-agents':
  route.endpoint=deployed;route.dependant.call=deployed
if __name__=='__main__':
 import uvicorn
 uvicorn.run(main.app,host='127.0.0.1',port=18498)
