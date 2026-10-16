"""Owner-private PETE process; secrets loaded only in server memory."""
import os
from pathlib import Path
root=Path(__file__).resolve().parent.parent
for line in (root/'.env').read_text().splitlines():
    if line.strip() and not line.lstrip().startswith('#'):
        key,sep,value=line.partition('=')
        if sep:os.environ[key.strip()]=value.strip().strip('"').strip("'")
os.environ['STUDIO_DEPLOYMENT_ID']='pete-private'
os.environ['STUDIO_REFERENCE_ROOT']=str(root/'references')
os.chdir(root)
os.execv(str(root/'.venv/bin/uvicorn'),['uvicorn','app.main:app','--host','127.0.0.1','--port','8496','--no-access-log','--log-level','warning'])
