"""Isolated Docker Compose acceptance check; uses fresh disposable volumes only.

Run in Linux with Docker/Compose installed, after building the requested image.
No user database or credentials are mounted. Never prints generated secrets.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = 'money-smoke-'+secrets.token_hex(4)
    env = {**os.environ, 'APP_TOKEN':secrets.token_urlsafe(36),
           'COMPOSE_PROGRESS':'plain'}
    # An isolated override leaves the documented copy-paste file minimal.
    override = root/'artifacts'/('smoke-'+project+'.yaml')
    override.parent.mkdir(exist_ok=True)
    override.write_text('services:\n  money-web:\n    image: stylle/money-web:'+args.tag+'\n    ports: !override ["127.0.0.1:0:8000"]\n    environment:\n      APP_TOKEN: "'+env['APP_TOKEN']+'"\n    read_only: true\n    tmpfs: ["/tmp:size=64M,mode=1777"]\n    security_opt: ["no-new-privileges:true"]\n    cap_drop: [ALL]\n    cap_add: [CHOWN, FOWNER, DAC_OVERRIDE, SETUID, SETGID]\n')
    compose = ['docker','compose','-p',project,'-f',str(root/'compose.yaml'),'-f',str(override)]

    def run(command, *, capture=True):
        result = subprocess.run(command,env=env,cwd=root,text=True,capture_output=capture)
        if result.returncode:
            # Do not include compose environment/configuration in errors.
            print('Docker command failed: '+str(result.returncode),flush=True)
            raise RuntimeError('Container acceptance command failed')
        return result.stdout if capture else ''

    def api(path, data=None, method=None):
        headers = {'Authorization':'Bearer '+env['APP_TOKEN']}
        if data is not None:headers['Content-Type']='application/json'
        req = urllib.request.Request(base+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)

    try:
        print('Starting isolated single container (SQLite, web and worker)...',flush=True)
        run(compose+['up','-d','--no-build','--wait','--wait-timeout','240'],capture=False)
        web = run(compose+['ps','-q','money-web']).strip()
        inspected = json.loads(run(['docker','inspect',web]))[0]
        assert len(run(compose+['ps','-q']).splitlines()) == 1
        port = inspected['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort']
        base = 'http://127.0.0.1:'+port
        status = run(['docker','exec',web,'cat','/proc/1/status'])
        assert all(int(value)==10001 for value in next(line for line in status.splitlines() if line.startswith('Uid:')).split()[1:])
        assert int(next(line for line in status.splitlines() if line.startswith('CapEff:')).split()[1],16)==0
        assert inspected['HostConfig']['ReadonlyRootfs']
        assert api('health')['status']=='ok'
        with urllib.request.urlopen(base+'/',timeout=10) as r:assert '\u89c2\u6f9c' in r.read().decode()
        try:
            urllib.request.urlopen(base+'/api/settings',timeout=10)
            raise AssertionError('Unauthenticated API was accepted')
        except urllib.error.HTTPError as exc:assert exc.code==401
        api('settings',{'news_sources':[],'feeds':[],'markets':[]},'PUT')
        initial = api('portfolio')
        assert float(initial['cash'])==100 and initial['positions']==[]
        assert len(api('dashboard')['markets'])==4
        watch = {'symbol':'BTC-USDT','name':'Container test','market':'CRYPTO','kind':'crypto'}
        assert api('watchlist',watch,'POST')['id']=='CRYPTO:BTC-USDT'
        assert api('portfolio')==initial
        assert any(w['id']=='CRYPTO:BTC-USDT' for w in api('dashboard')['watchlist'])
        api('watchlist/CRYPTO:BTC-USDT',method='DELETE')
        assert not api('dashboard')['watchlist']
        assert len(api('sources')['news'])==9
        assert len(api('settings')['markets'])==0
        print('API, authentication, watchlist and SQLite checks passed; checking restart...',flush=True)
        run(compose+['restart','money-web'])
        # A Docker binding with host port 0 can receive a new port on restart.
        restarted = json.loads(run(['docker','inspect',web]))[0]
        base = 'http://127.0.0.1:'+restarted['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort']
        deadline = time.monotonic()+90
        while True:
            try:
                if api('health')['status']=='ok':break
            except (OSError,urllib.error.URLError):pass
            if time.monotonic()>deadline:raise RuntimeError('Restart did not recover')
            time.sleep(1)
        assert api('portfolio')==initial
        assert api('settings')['news_sources']==[]
        assert api('dashboard')['worker_heartbeat']
        print('Checking child failure, container recovery and abandoned lease reset...',flush=True)
        # Mark an abandoned lease, kill just the worker, then require automatic restart.
        run(['docker','exec',web,'python','-c',"from app.db import Session,Lease; s=Session(); r=s.get(Lease,'worker'); r.until=9999999999; s.commit()"])
        before = restarted['RestartCount']
        run(['docker','exec',web,'python','-c',"import json,os,signal; os.kill(json.load(open('/tmp/money-web-runtime.json'))['worker'],signal.SIGKILL)"])
        deadline = time.monotonic()+120
        while True:
            restarted = json.loads(run(['docker','inspect',web]))[0]
            if restarted['RestartCount']>before and restarted['State'].get('Health',{}).get('Status')=='healthy':break
            if time.monotonic()>deadline:raise RuntimeError('Worker failure did not recover')
            time.sleep(1)
        base = 'http://127.0.0.1:'+restarted['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort']
        assert api('portfolio')==initial
        assert api('settings')['news_sources']==[]
        run(['docker','exec',web,'python','-c',"from app.db import Session,Lease; s=Session(); assert s.get(Lease,'worker').until<9999999999"])
        # SIGTERM must stop both children promptly and leave a successful exit.
        started = time.monotonic()
        run(compose+['stop','-t','12','money-web'])
        stopped = json.loads(run(['docker','inspect',web]))[0]
        assert stopped['State']['ExitCode']==0 and time.monotonic()-started<12
        report = {'single_container':True,'sqlite':True,'web':True,'worker':True,'nonroot':True,'read_only':True,
                  'authentication':True,'crypto_watch_crud':True,'portfolio_unchanged':True,
                  'restart_persistence':True,'child_failure_recovery':True,'lease_recovery':True,
                  'graceful_shutdown':True,'user_data_mounted':False}
        print(json.dumps(report),flush=True)
    finally:
        # Explicit random Compose project owns every volume removed here.
        run(compose+['down','--volumes','--remove-orphans'],capture=False)
        override.unlink(missing_ok=True)


if __name__=='__main__':main()
