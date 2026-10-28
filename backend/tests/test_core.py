import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func
from app.schemas import PortfolioInput
from app.db import Delivery, Event, Session
from app.config import get_config, save_config
from app.markets import market_state, valid_live_quote, valid_daily_history
from app.strategy import indicators, analyze
from app.services import emit, scan_alerts, quiet_now, deliver_pending, portfolio_data
from app.ai import Report, validate_report, generate_report
from app.news import parse_feed
from app.providers import normalize_quote


NOW = datetime(2026, 10, 28, 2, 0, tzinfo=timezone.utc)


def portfolio(**kwargs):
    return {'revision': 0, 'positions': [{'watch_id': 'US:QQQ', 'shares': 40, 'target': None, 'cap': 50}], 'cash': 60, 'min_cash': 10, 'max_step': 1, 'risk': 'balanced', 'horizon': 'medium', 'updated_at': NOW.isoformat(), **kwargs}


def watch(**kwargs):
    return SimpleNamespace(id='US:QQQ', symbol='QQQ', name='QQQ', market='US', threshold=5, error=None, quote={'price': 95, 'previous_close': 100, 'change_pct': -5, 'as_of': NOW.isoformat(), 'history': []}, **kwargs)


def report(delta, action='add', sources=None):
    return Report(summary='测试观察', risks=['样本风险'], suggestions=[{'watch_id': 'US:QQQ', 'action': action, 'delta': delta, 'reasons': ['测试依据'], 'sources': sources or [], 'invalidation': '趋势反转'}])


def test_decimal_sum_exact():
    p = portfolio(positions=[{'watch_id': 'US:QQQ', 'shares': '33.33', 'target': None, 'cap': 40}], cash='66.67')
    assert PortfolioInput.model_validate({k:v for k,v in p.items() if k!='updated_at'}).cash == Decimal('66.67')


@pytest.mark.parametrize('change', [{'cash': 61}, {'positions': [{'watch_id':'US:QQQ','shares':40,'cap':30}]}, {'positions': [{'watch_id':'US:QQQ','shares':20,'cap':40}]*2}, {'max_step': float('nan')}, {'cash': '59.999'}])
def test_invalid_portfolios(change):
    with pytest.raises(ValidationError):
        PortfolioInput.model_validate({k:v for k,v in portfolio(**change).items() if k!='updated_at'})


@pytest.mark.parametrize('market,at,expected', [
    ('CN','2026-10-28T02:00:00+00:00','open'),
    ('CN','2026-10-28T04:00:00+00:00','break'),
    ('CN','2026-10-01T02:00:00+00:00','holiday'),
    ('HK','2026-10-28T04:30:00+00:00','break'),
    ('US','2026-07-08T14:00:00+00:00','open'),
    ('US','2026-01-07T15:00:00+00:00','open'),
    ('US','2026-11-26T15:00:00+00:00','holiday'),
])
def test_calendars(market,at,expected):
    assert market_state(market, datetime.fromisoformat(at))['status'] == expected


def test_dst_and_half_day():
    summer=market_state('US',datetime.fromisoformat('2026-07-08T14:00:00+00:00'))
    winter=market_state('US',datetime.fromisoformat('2026-01-07T15:00:00+00:00'))
    half=market_state('US',datetime.fromisoformat('2026-11-27T19:00:00+00:00'))
    assert summer['daily_at'].startswith('2026-07-08T14:00')
    assert winter['daily_at'].startswith('2026-01-07T15:00')
    assert half['close_at'].startswith('2026-11-27T18:00')
    assert not half['is_open']


def test_daily_window_no_stale_catchup():
    assert market_state('CN', NOW)['daily_due']
    assert not market_state('CN', NOW+timedelta(minutes=16))['daily_due']


def test_stale_future_and_live_quote():
    state = market_state('CN', NOW)
    q = {'price': 95, 'previous_close':100, 'as_of': NOW.isoformat()}
    assert valid_live_quote(q,state,NOW)
    assert not valid_live_quote({**q,'as_of':(NOW-timedelta(minutes=6)).isoformat()},state,NOW)
    assert not valid_live_quote({**q,'as_of':(NOW+timedelta(minutes=1)).isoformat()},state,NOW)
    assert not valid_live_quote(q,{**state,'is_open':False},NOW)


def test_current_daily_bar_and_old_history_rejected():
    assert valid_daily_history([{'time':'2026-10-27T01:30:00+00:00'}],'CN',NOW)
    assert not valid_daily_history([{'time':NOW.isoformat()}],'CN',NOW)
    assert not valid_daily_history([{'time':'2026-09-27T01:30:00+00:00'}],'CN',NOW)


def test_flat_market_rsi_and_data_shortage():
    bars=[{'time':str(i),'open':100,'high':100,'low':100,'close':100,'volume':0} for i in range(70)]
    assert indicators(bars)['rsi'] == 50
    assert indicators(bars)['atr'] == 0
    assert indicators(bars)['volume_ratio'] is None
    assert indicators(bars[:30]) is None


def test_strategy_constraints(monkeypatch):
    import app.strategy as strategy
    monkeypatch.setattr(strategy,'valid_live_quote',lambda *a:True)
    monkeypatch.setattr(strategy,'valid_daily_history',lambda *a:True)
    monkeypatch.setattr(strategy,'indicators',lambda *a:{'trend_up':True,'trend_down':False,'rsi':55,'macd':2,'macd_signal':1,'volume_ratio':1.5})
    assert analyze(watch(),portfolio(),True,NOW)['delta'] == 1
    assert analyze(watch(),portfolio(cash=10),True,NOW)['delta'] == 0
    assert analyze(watch(),portfolio(risk='conservative'),True,NOW)['delta'] == .5
    assert analyze(watch(),portfolio(positions=[{'watch_id':'US:QQQ','shares':40,'cap':40,'target':None}]),True,NOW)['delta'] == 0
    assert analyze(watch(),portfolio(),False,NOW)['delta'] == 0


def test_reduce_cannot_exceed_holdings(monkeypatch):
    import app.strategy as strategy
    monkeypatch.setattr(strategy,'valid_live_quote',lambda *a:True)
    monkeypatch.setattr(strategy,'valid_daily_history',lambda *a:True)
    monkeypatch.setattr(strategy,'indicators',lambda *a:{'trend_up':False,'trend_down':True,'rsi':30,'macd':0,'macd_signal':1,'volume_ratio':1})
    p=portfolio(positions=[{'watch_id':'US:QQQ','shares':.25,'cap':50,'target':None}])
    assert analyze(watch(),p,True,NOW)['delta'] == -.25


def test_ai_cannot_invent_citations():
    with pytest.raises(ValueError):
        validate_report(report(0,'observe',['fake']),[watch()],portfolio(),[],NOW)


@pytest.mark.parametrize('delta,action', [(2,'add'),(-41,'reduce'),(1,'reduce'),(.001,'add')])
def test_ai_rejects_invalid_adjustments(delta,action,monkeypatch):
    monkeypatch.setattr('app.ai.valid_live_quote',lambda *a:True)
    with pytest.raises(ValueError):
        validate_report(report(delta,action),[watch()],portfolio(),[],NOW)


def test_ai_aggregate_cash_and_existing_risk(monkeypatch):
    monkeypatch.setattr('app.ai.valid_live_quote',lambda *a:True)
    monkeypatch.setattr('app.ai.analyze',lambda *a:{'action':'observe'})
    p=portfolio(cash=10.5)
    with pytest.raises(ValueError):
        validate_report(report(1),[watch()],p,[],NOW)
    assert validate_report(report(.5),[watch()],p,[],NOW)
    monkeypatch.setattr('app.ai.analyze',lambda *a:{'action':'reduce'})
    with pytest.raises(ValueError):
        validate_report(report(.5),[watch()],p,[],NOW)


def test_ai_disabled_never_calls_api(monkeypatch):
    async def should_not_call(*args,**kwargs):
        pytest.fail('Disabled AI made a network call')
    monkeypatch.setattr('app.ai.completion',should_not_call)
    with pytest.raises(ValueError):
        asyncio.run(generate_report([],portfolio(),get_config()))


def test_encrypted_config_and_masking():
    from app.db import Config
    save_config({'ai_key':'secret-for-test'})
    assert get_config()['ai_key']=='secret-for-test'
    assert 'ai_key' not in get_config(public=True)
    assert get_config(public=True)['ai_key_configured']
    with Session() as s:
        assert 'secret-for-test' not in s.get(Config,'settings').value


def test_atomic_outbox_deduplication():
    cfg={**get_config(),'webhook_url':'https://example.com/hook'}
    assert emit('same-event','alert','test',{},cfg,True)
    assert not emit('same-event','alert','test',{},cfg,True)
    with Session() as s:
        assert s.scalar(select(func.count()).select_from(Event))==1
        assert s.scalar(select(func.count()).select_from(Delivery))==1


def test_alert_once_per_market_day_and_band():
    from app.db import Watch
    cfg={**get_config(),'webhook_url':'https://example.com/hook'}
    q={'price':94,'previous_close':100,'change_pct':-6,'as_of':NOW.isoformat()}
    with Session.begin() as s:
        s.add(Watch(id='CN:510300.SS',symbol='510300.SS',name='ETF',market='CN',exchange='SSE',threshold=5,quote=q))
    scan_alerts(cfg,NOW);scan_alerts(cfg,NOW)
    with Session() as s:
        assert s.scalar(select(func.count()).select_from(Delivery))==1
    with Session.begin() as s:
        s.get(Watch,'CN:510300.SS').quote={**q,'price':89,'change_pct':-11}
    scan_alerts(cfg,NOW)
    with Session() as s:
        assert s.scalar(select(func.count()).select_from(Delivery))==2


def test_quiet_hours_cross_midnight():
    cfg={**get_config(),'quiet_start':'22:00','quiet_end':'08:00'}
    assert quiet_now(cfg,datetime(2026,10,28,15,tzinfo=timezone.utc))
    assert not quiet_now(cfg,NOW)


def test_expired_notification_not_sent(monkeypatch):
    cfg={**get_config(),'webhook_url':'https://example.com'}
    with Session.begin() as s:
        s.add(Delivery(id='expired',payload={'id':'expired','expires_at':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()}))
    async def forbidden(*args):pytest.fail('Expired notification sent')
    monkeypatch.setattr('app.services.send_webhook',forbidden)
    asyncio.run(deliver_pending(cfg))
    with Session() as s:assert s.get(Delivery,'expired').status=='expired'


def test_feed_dedup_timestamp_and_safe_link():
    xml=b'<rss><channel><item><title>Rate decision</title><link>https://example.com/a</link><pubDate>Wed, 28 Oct 2026 01:00:00 GMT</pubDate></item><item><title>Bad</title><link>javascript:alert(1)</link></item></channel></rss>'
    items=parse_feed(xml,'official')
    assert len(items)==1
    assert items[0]['id']==parse_feed(xml,'other')[0]['id']
    assert items[0]['published']=='2026-10-28T01:00:00+00:00'


def test_quote_invalid_numbers_and_ohlc():
    with pytest.raises(ValueError):normalize_quote({'price':float('nan'),'previous_close':1})
    with pytest.raises(ValueError):normalize_quote({'price':100,'previous_close':0})


def test_portfolio_conflict_and_api_validation(client):
    w={'symbol':'QQQ','name':'ETF','market':'US','kind':'etf'}
    assert client.post('/api/watchlist',json=w).status_code==201
    assert client.post('/api/watchlist',json=w).status_code==409
    p={k:v for k,v in portfolio().items() if k!='updated_at'}
    assert client.put('/api/portfolio',json=p).status_code==200
    assert client.put('/api/portfolio',json=p).status_code==409
    assert client.delete('/api/watchlist/US:QQQ').status_code==409
    assert client.put('/api/portfolio',json={**p,'revision':1,'cash':59}).status_code==422


def test_authentication_and_health(client,monkeypatch):
    monkeypatch.setenv('APP_TOKEN','correct-test-token')
    assert client.get('/api/health').status_code==200
    assert client.get('/api/dashboard').status_code==401
    assert client.get('/api/dashboard',headers={'Authorization':'Bearer correct-test-token'}).status_code==200


def test_cross_site_write_blocked(client):
    assert client.post('/api/refresh',headers={'Origin':'https://attacker.example'}).status_code==403


def test_market_code_mismatch(client):
    assert client.post('/api/watchlist',json={'symbol':'QQQ','name':'ETF','market':'CN'}).status_code==422


def test_private_endpoint_blocked():
    from app.security import validate_url
    with pytest.raises(ValueError):asyncio.run(validate_url('https://127.0.0.1/hook'))
    with pytest.raises(ValueError):asyncio.run(validate_url('http://example.com/hook'))


def test_no_seeded_prices_or_holdings(client):
    data=client.get('/api/dashboard').json()
    assert data['watchlist']==[]
    assert data['portfolio']['cash']==100
    assert data['portfolio']['positions']==[]


def test_compressed_response_is_not_decoded_twice(monkeypatch):
    import gzip
    import httpx
    import app.security as security
    async def allow(*args,**kwargs):return args[0]
    monkeypatch.setattr(security,'validate_url',allow)
    original_client=httpx.AsyncClient
    def mock_client(**kwargs):
        return original_client(**kwargs,transport=httpx.MockTransport(lambda request:httpx.Response(200,content=gzip.compress(b'{"price":100}'),headers={'Content-Encoding':'gzip'})))
    monkeypatch.setattr(security.httpx,'AsyncClient',mock_client)
    response=asyncio.run(security.request('GET','https://example.com/quote'))
    assert response.json()=={'price':100}


def test_batch_strategy_shares_one_cash_budget(monkeypatch):
    import app.strategy as strategy
    monkeypatch.setattr(strategy,'valid_live_quote',lambda *a:True)
    monkeypatch.setattr(strategy,'valid_daily_history',lambda *a:True)
    monkeypatch.setattr(strategy,'indicators',lambda *a:{'trend_up':True,'trend_down':False,'rsi':55,'macd':2,'macd_signal':1,'volume_ratio':1.5})
    second=watch();second.id='US:SPY'
    p=portfolio(cash=10.5,positions=[{'watch_id':'US:QQQ','shares':40,'cap':50,'target':None},{'watch_id':'US:SPY','shares':49.5,'cap':60,'target':None}])
    signals=strategy.analyze_all([watch(),second],p,True,NOW)
    assert sum(max(0,s['delta']) for s in signals.values())==.5


def test_webhook_retry_records_failure_without_leaking_url(monkeypatch):
    import app.services as services
    cfg={**get_config(),'webhook_url':'https://example.com/?secret=hidden'}
    emit('retry','alert','risk',{},cfg,True)
    async def fail(*a):raise ValueError('secret=hidden')
    monkeypatch.setattr(services,'send_webhook',fail)
    asyncio.run(services.deliver_pending(cfg))
    with Session() as s:
        d=s.scalars(select(Delivery)).first()
        assert d.status=='pending' and d.attempts==1
        assert 'hidden' not in d.error
