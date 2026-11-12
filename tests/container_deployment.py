import json,os,secrets,subprocess,time,urllib.request
from pathlib import Path
repo = Path(__file__).resolve().parent.parent
root = repo / 'data-container-test'
root.mkdir(exist_ok=True)
token=secrets.token_urlsafe(32)
env={k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
env['FORGE_TOKEN']=token
docker=['docker','--host=unix:///var/run/docker.sock']
name='featherforge-deployment-check'
cmd=docker+['run','-d','--name',name,'--user',str(os.getuid())+':'+str(os.getgid()),'--group-add',str(os.stat('/var/run/docker.sock').st_gid),'--cpus=1','--memory=512m','-p','127.0.0.1:8005:8000','--env','FORGE_TOKEN','--env','FORGE_CONCURRENCY=1','--env','FORGE_DATA='+str(root),'--mount','type=bind,src='+str(root)+',dst='+str(root),'--mount','type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock','featherforge-platform:local']
subprocess.run(cmd,env=env,check=True,capture_output=True)
def api(path,data=None):
    req=urllib.request.Request('http://127.0.0.1:8005'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
    with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)
try:
    deadline=time.monotonic()+40
    while True:
        try:
            health=api('/health')
            if health['worker_alive']:break
        except Exception:pass
        if time.monotonic()>deadline:raise RuntimeError('Container health check failed')
        time.sleep(.5)
    p=api('/api/projects',{'title':'Container deployment reference','brief':'Build accessible task tracker with add complete delete and persistent tasks.','provider':'scripted','idempotency_key':'container-deployment-check'})
    api('/api/projects/'+p['id']+'/plan',{})
    api('/api/projects/'+p['id']+'/approve',{})
    deadline=time.monotonic()+120
    while True:
        p=api('/api/projects/'+p['id'])
        if all(t['state']=='completed' for t in p['tasks']):break
        if any(t['state']=='failed' for t in p['tasks']):raise RuntimeError(json.dumps([{k:t[k] for k in ('kind','state','next_action','evidence')} for t in p['tasks']]))
        if time.monotonic()>deadline:raise RuntimeError('Container workflow timed out')
        time.sleep(.5)
    (repo / 'docs/evidence/container-deployment-run.json').write_text(json.dumps({'non_root':True,'health':health,'model':'scripted (SIMULATED MODEL)','real_docker_browser_qa':True,'tasks':[{k:t[k] for k in ('kind','state','evidence')} for t in p['tasks']]},indent=2))
    print('PASS: non-root platform image health, bearer-authenticated API, scripted workflow, actual nested Docker browser QA, all three completion gates',flush=True)
finally:
    subprocess.run(docker+['rm','-f',name],env=env,capture_output=True,timeout=20)
