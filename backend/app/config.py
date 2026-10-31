import os
import json
from cryptography.fernet import Fernet
from .db import Config, DATA_DIR, Session

DEFAULTS = {
    'ai_enabled': False, 'strategy_enabled': False,
    'ai_base_url': 'https://api.openai.com/v1', 'ai_key': '', 'ai_model': '',
    'ai_interface': 'chat', 'ai_daily_limit': 10,
    'webhook_url': '', 'webhook_secret': '', 'webhook_authorization': '',
    'webhook_format': 'auto', 'webhook_method': 'POST', 'webhook_body_type': 'json',
    'webhook_headers': '', 'webhook_body_tpl': '',
    'notify_daily': True, 'notify_alerts': True,
    'markets': ['CN', 'HK', 'US', 'CRYPTO'], 'quiet_start': '', 'quiet_end': '',
    'keywords': ['纳斯达克', '红利', '利率', '科技', 'Nasdaq', 'Federal Reserve'],
    'feeds': [{'name': '美联储 · 官方公告', 'url': 'https://www.federalreserve.gov/feeds/press_all.xml'}],
    'news_sources': ['cls','stcn','jin10','wallstreetcn','tradingview','seekingalpha','cointelegraph','coindesk'],
    'provider': 'auto', 'provider_base_url': '', 'provider_key': '',
}
SECRETS = {'ai_key', 'webhook_secret', 'webhook_authorization', 'provider_key', 'webhook_headers', 'webhook_body_tpl'}


def cipher():
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        path = DATA_DIR / 'secret.key'
        # Exclusive creation avoids workers generating incompatible keys at startup.
        try:
            with path.open('xb') as f:
                f.write(Fernet.generate_key())
            try:
                path.chmod(0o600)
            except OSError:
                pass
        except FileExistsError:
            pass
        key = path.read_bytes()
    return Fernet(key)


def get_config(public=False):
    with Session() as s:
        row = s.get(Config, 'settings')
        values = {**DEFAULTS, **(json.loads(cipher().decrypt(row.value.encode())) if row else {})}
    if public:
        for k in SECRETS:
            values[k + '_configured'] = bool(values.pop(k, ''))
    return values


def save_config(changes):
    values = get_config()
    values.update(changes)
    with Session.begin() as s:
        row = s.get(Config, 'settings')
        encrypted = cipher().encrypt(json.dumps(values, ensure_ascii=False).encode()).decode()
        if row:
            row.value = encrypted
        else:
            s.add(Config(key='settings', value=encrypted))
    return get_config(public=True)
