"""Offline image check, also used under arm64 emulation; no user data required."""
import json
import os
from pathlib import Path
import platform
from app.bootstrap import drop_privileges
drop_privileges()
from fastapi.testclient import TestClient
from app.main import app

assert os.getuid() == 10001
assert not Path('/app/.env').exists()
assert not Path('/app/.git').exists()
assert not list(Path('/data').iterdir())
with TestClient(app) as client:
    assert client.get('/api/health').json()['status']=='ok'
    assert client.get('/').status_code==200
    dashboard = client.get('/api/dashboard').json()
    assert len(dashboard['markets'])==4
    assert dashboard['watchlist']==[]
    assert float(dashboard['portfolio']['cash'])==100
    assert len(client.get('/api/sources').json()['news'])==9
    assert client.get('/api/settings').json()['ai_enabled'] is False
print(json.dumps({'architecture':platform.machine(),'nonroot':True,'health':True,'frontend':True,
                  'four_markets':True,'empty_watchlist':True,'cash_100_units':True,'sources':9,'ai_disabled':True}),flush=True)
