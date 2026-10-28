import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import httpx
import pytest
from pydantic import ValidationError
from app.markets import market_state, valid_daily_history, valid_live_quote
from app.schemas import WatchInput
from app.crypto import daily_rows


def test_crypto_open_on_weekend_and_daily_schedule_is_utc():
    at = datetime(2026,10,25,0,35,tzinfo=timezone.utc)
    state = market_state('CRYPTO',at)
    assert state['is_open'] and state['daily_due']
    assert state['daily_at'] == '2026-10-25T00:30:00+00:00'
    assert not market_state('CRYPTO',at+timedelta(hours=1))['daily_due']
    assert valid_live_quote({'price':100,'previous_close':99,'as_of':at.isoformat()},state,at)
    assert not valid_live_quote({'price':100,'previous_close':99,'as_of':(at-timedelta(minutes=6)).isoformat()},state,at)


def test_crypto_daily_bars_use_previous_utc_day_even_on_monday():
    at = datetime(2026,10,26,0,35,tzinfo=timezone.utc)
    assert valid_daily_history([{'time':'2026-10-25T00:00:00+00:00'}],'CRYPTO',at)
    assert not valid_daily_history([{'time':'2026-10-24T00:00:00+00:00'}],'CRYPTO',at)
    assert not valid_daily_history([{'time':'2026-10-26T00:00:00+00:00'}],'CRYPTO',at)


@pytest.mark.parametrize('symbol,market,kind', [('BTCUSDT','CRYPTO','crypto'),('BTC-USDT','US','crypto'),('BTC-USDT','CRYPTO','stock'),('BTC-PERP','CRYPTO','crypto')])
def test_crypto_rejects_ambiguous_pairs_and_wrong_market(symbol,market,kind):
    with pytest.raises(ValidationError):WatchInput(symbol=symbol,name='test',market=market,kind=kind)


def test_crypto_watch_api_accepts_pair_without_changing_portfolio(client):
    before = client.get('/api/portfolio').json()
    r = client.post('/api/watchlist',json={'symbol':'BTC-USDT','name':'比特币','market':'CRYPTO','kind':'crypto'})
    assert r.status_code == 201 and r.json()['id']=='CRYPTO:BTC-USDT'
    assert client.get('/api/portfolio').json()==before
    assert len(client.get('/api/dashboard').json()['markets'])==4


def test_current_utc_candle_excluded_and_coinbase_rows_sorted():
    now = datetime(2026,10,28,6,tzinfo=timezone.utc)
    yesterday = int(datetime(2026,10,27,tzinfo=timezone.utc).timestamp())
    rows = [[yesterday+86400,90,110,99,101,12],[yesterday,90,110,99,100,10]]
    bars = daily_rows(rows,'coinbase',now)
    assert len(bars)==1 and bars[0]['close']==100
    assert bars[0]['open']==99 and bars[0]['low']==90


def test_usdt_fallback_keeps_exact_pair(monkeypatch):
    import app.crypto as crypto
    calls = []
    now = datetime.now(timezone.utc)
    async def fetch(w,venue):
        calls.append((w.symbol,venue))
        if venue=='binance':raise httpx.ConnectError('offline')
        return {'price':100,'previous_close':99,'as_of':now.isoformat(),'source':'Coinbase','history':[],'intraday':[]}
    monkeypatch.setattr(crypto,'fetch_spot',fetch)
    q=asyncio.run(crypto.fetch_crypto(SimpleNamespace(symbol='BTC-USDT')))
    assert calls==[('BTC-USDT','binance'),('BTC-USDT','coinbase')]
    assert q['provider_id']=='coinbase'


def test_usd_pair_never_routes_to_usdt_venue(monkeypatch):
    import app.crypto as crypto
    calls=[]
    async def fetch(w,venue):
        calls.append((w.symbol,venue))
        return {'price':100,'previous_close':99,'as_of':datetime.now(timezone.utc).isoformat(),'source':'Coinbase','history':[],'intraday':[]}
    monkeypatch.setattr(crypto,'fetch_spot',fetch)
    asyncio.run(crypto.fetch_crypto(SimpleNamespace(symbol='BTC-USD')))
    assert calls==[('BTC-USD','coinbase')]


def test_crypto_news_topic_filters_sources_and_keywords(client):
    from app.db import Session,Article
    with Session.begin() as s:
        for i,(source,title) in enumerate([('Cointelegraph','Spot exchange developments'),('财联社','比特币行情观察'),('证券时报','上证指数收盘观察')]):
            s.add(Article(id=str(i),source=source,title=title,url='https://example.com/'+str(i),published='',tags=[]))
    items=client.get('/api/news?topic=crypto').json()['items']
    assert {x['id'] for x in items}=={'0','1'}


def test_previous_close_is_completed_utc_close_not_rolling_ticker(monkeypatch):
    import app.crypto as crypto
    now=datetime.now(timezone.utc)
    yesterday=(now-timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
    async def request(method,url,**kwargs):
        if url.endswith('/ticker'):return SimpleNamespace(json=lambda:{'price':'110','time':now.isoformat()})
        return SimpleNamespace(json=lambda:[[yesterday.timestamp(),90,120,95,100,10]])
    async def cached(provider,w,loader):return await loader()
    monkeypatch.setattr(crypto,'request',request)
    monkeypatch.setattr('app.providers.cached_history',cached)
    q=asyncio.run(crypto.fetch_spot(SimpleNamespace(symbol='BTC-USDT',market='CRYPTO'),'coinbase'))
    assert q['previous_close']==100 and q['change_pct']==10
    assert q['currency']=='USDT' and 'UTC' in q['change_basis']


def test_search_only_includes_active_spot_products_and_keeps_quote_units(monkeypatch):
    import app.crypto as crypto
    async def request(method,url,**kwargs):
        if url.endswith('exchangeInfo'):
            assert kwargs['params']['showPermissionSets']=='false'
            return SimpleNamespace(json=lambda:{'symbols':[
                {'status':'TRADING','isSpotTradingAllowed':True,'baseAsset':'BTC','quoteAsset':'USDT'},
                {'status':'HALT','isSpotTradingAllowed':True,'baseAsset':'ETH','quoteAsset':'USDT'},
                {'status':'TRADING','isSpotTradingAllowed':False,'baseAsset':'BTC','quoteAsset':'USDT'},
            ]})
        return SimpleNamespace(json=lambda:[{'id':'BTC-USD','base_currency':'BTC','quote_currency':'USD','status':'online'},
                                           {'id':'BTC-EUR','quote_currency':'EUR','status':'online'}])
    monkeypatch.setattr(crypto,'request',request)
    monkeypatch.setattr(crypto,'_products',None)
    r=asyncio.run(crypto.search_crypto('比特币'))
    assert {x['symbol'] for x in r['items']}=={'BTC-USDT','BTC-USD'} and r['warning'] is None


def test_missing_previous_utc_bar_blocks_quote_instead_of_using_older_close(monkeypatch):
    import app.crypto as crypto
    async def request(*args,**kwargs):return SimpleNamespace(json=lambda:{'price':'110','time':datetime.now(timezone.utc).isoformat()})
    async def cached(*args):return [{'time':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),'close':100}]
    monkeypatch.setattr(crypto,'request',request)
    monkeypatch.setattr('app.providers.cached_history',cached)
    with pytest.raises(ValueError,match='previous UTC'):asyncio.run(crypto.fetch_spot(SimpleNamespace(symbol='BTC-USD',market='CRYPTO'),'coinbase'))
