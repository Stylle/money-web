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
    env = {**os.environ, 'POSTGRES_PASSWORD':secrets.token_hex(24), 'APP_TOKEN':secrets.token_urlsafe(36),
           'IMAGE_TAG':args.tag,'BIND_ADDRESS':'127.0.0.1','PORT':'0','COMPOSE_PROGRESS':'plain'}
    compose = ['docker','compose','-p',project,'-f',str(root/'compose.yaml')]

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
        print('Starting isolated PostgreSQL, web and worker...',flush=True)
        run(compose+['up','-d','--no-build','--wait','--wait-timeout','240'],capture=False)
        web = run(compose+['ps','-q','web']).strip()
        inspected = json.loads(run(['docker','inspect',web]))[0]
        port = inspected['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort']
        base = 'http://127.0.0.1:'+port
        assert inspected['Config']['User'] == 'app'
        assert inspected['HostConfig']['ReadonlyRootfs']
        assert api('health')['status']=='ok'
        with urllib.request.urlopen(base+'/',timeout=10) as r:assert '观澜' in r.read().decode()
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
        print('API, authentication, watchlist and PostgreSQL checks passed; checking restart...',flush=True)
        run(compose+['restart','web'])
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
        report = {'postgresql':True,'web':True,'worker':True,'nonroot':True,'read_only':True,
                  'authentication':True,'crypto_watch_crud':True,'portfolio_unchanged':True,
                  'restart_persistence':True,'user_data_mounted':False}
        print(json.dumps(report),flush=True)
    finally:
        # Explicit random Compose project owns every volume removed here.
        run(compose+['down','--volumes','--remove-orphans'],capture=False)


if __name__=='__main__':main()
