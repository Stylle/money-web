"""Idempotent local configuration update explicitly requested by the owner."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.db import initialize, DATA_DIR
from app.config import get_config, save_config
from app.news_sources import PUBLIC_HOSTS
from app.providers import QUOTE_HOSTS
from app.services import release

initialize()
config=get_config()
enabled=list(dict.fromkeys(config.get('news_sources',[])+['cls','stcn','jin10','wallstreetcn','tradingview','seekingalpha','cointelegraph','coindesk']))
changes={'news_sources':enabled,'markets':list(dict.fromkeys(config['markets']+['CRYPTO']))}
if config['provider']!='custom':changes['provider']='auto'
save_config(changes)
release('news')
launch=DATA_DIR/'local-launch.json'
if launch.exists():
    data=json.loads(launch.read_text(encoding='utf-8-sig'))
    hosts=set(filter(None,(data.get('trusted_egress_hosts') or '').split(',')))
    data['trusted_egress_hosts']=','.join(sorted(hosts|PUBLIC_HOSTS|QUOTE_HOSTS))
    launch.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'enabled_news':enabled,'quote_mode':changes.get('provider',config['provider']),'custom_feeds_preserved':len(config['feeds']),'xueqiu':'listed_requires_authorized_access'},ensure_ascii=True))
