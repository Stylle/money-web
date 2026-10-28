import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import httpx
import pytest
from sqlalchemy import select, func
from app.db import Article, Session, SourceHealth
from app.config import get_config
from app.markets import market_state
from app.providers import normalize_quote
from app.news_sources import cls_titles, web_titles, wallstreet_titles, fetch_builtin, AccessRequired
from app.source_health import record, cooling, health


def quote(now,price=100,history=None):
    return {'price':price,'previous_close':99,'change_pct':(price/99-1)*100,'as_of':now.isoformat(),'source':'test','history':history or [],'intraday':[{'time':now.isoformat(),'close':price}]}


def test_cls_parses_embedded_json_without_executing_script():
    data={'props':{'initialState':{'roll_data':[{'id':123,'title':'测试公开市场标题','ctime':1793160000}]}}}
    page='<script>__NEXT_DATA__ = '+json.dumps(data)+'; alert("must never execute");</script>'
    items=cls_titles(page)
    assert len(items)==1 and items[0]['url']=='https://www.cls.cn/detail/123'
    assert items[0]['published'].endswith('+00:00')


def test_web_sources_only_keep_expected_original_links_and_never_invent_dates():
    page='<a href="/article/detail/123.html">公开财经新闻标题</a><a href="https://evil.example/article/detail/1.html">不相关网站的新闻</a>'
    items=web_titles(page,'stcn')
    assert len(items)==1 and items[0]['published']==''
    assert items[0]['url'].startswith('https://www.stcn.com/')


def test_wallstreet_filters_paid_content_and_labels_excerpts():
    data={'code':20000,'data':{'items':[
        {'id':1,'title':'','content_text':'公开快讯内容的第一句。其余正文不应被复制','display_time':1793160000,'is_priced':False},
        {'id':2,'title':'这是付费内容标题','display_time':1793160000,'is_priced':True},
    ]}}
    items=wallstreet_titles(data)
    assert len(items)==1 and items[0]['title'].startswith('快讯摘录｜')
    assert '其余正文' not in items[0]['title']


def test_verification_page_is_not_a_working_news_feed():
    with pytest.raises(AccessRequired):asyncio.run(fetch_builtin('xueqiu'))
    with pytest.raises(ValueError):cls_titles('<html>验证码</html>')


def test_line_points_do_not_fabricate_candles():
    now=datetime.now(timezone.utc)
    q=normalize_quote(quote(now))
    assert 'open' not in q['intraday'][0] and q['intraday'][0]['close']==100


def test_future_provider_timestamps_rejected():
    with pytest.raises(ValueError):normalize_quote(quote(datetime.now(timezone.utc)+timedelta(minutes=2)))


def test_circuit_breaker_recovers_and_data_errors_do_not_open_it():
    key='quote:tencent:CN'
    record(key,'failed',error='timeout',breaker=True)
    assert not cooling(key)
    record(key,'failed',error='timeout',breaker=True)
    assert cooling(key)
    record(key,'ok')
    assert not cooling(key) and health(key)['last_success']
    for _ in range(3):record(key,'failed',error='missing symbol',breaker=False)
    assert not cooling(key)


def test_auto_quote_falls_back_after_primary_failure(monkeypatch):
    import app.providers as providers
    now=datetime.now(timezone.utc)
    calls=[]
    async def bad(w):calls.append('tencent');raise httpx.ConnectError('offline')
    async def good(w):calls.append('eastmoney');return quote(now)
    monkeypatch.setattr(providers,'fetch_tencent',bad)
    monkeypatch.setattr(providers,'fetch_eastmoney',good)
    monkeypatch.setattr(providers,'market_state',lambda m:{'is_open':False})
    async def no_history(*args,**kwargs):raise ValueError('unavailable')
    monkeypatch.setattr(providers,'fetch_yahoo_quote',no_history)
    q=asyncio.run(providers.fetch_quote(SimpleNamespace(market='CN',symbol='510300.SS'),get_config()))
    assert calls==['tencent','eastmoney'] and q['provider_id']=='eastmoney'
    assert q['provider_attempts'][0]['status']=='failed'


def test_auto_tries_fresh_source_when_primary_quote_delayed(monkeypatch):
    import app.providers as providers
    now=datetime.now(timezone.utc)
    async def old(w):return quote(now-timedelta(minutes=15),99)
    async def recent(w):return quote(now,100)
    monkeypatch.setattr(providers,'fetch_tencent',old)
    monkeypatch.setattr(providers,'fetch_eastmoney',recent)
    monkeypatch.setattr(providers,'market_state',lambda m:{'is_open':True,'open_at':(now-timedelta(hours=1)).isoformat()})
    async def no_history(*a,**kw):raise ValueError('unavailable')
    monkeypatch.setattr(providers,'fetch_yahoo_quote',no_history)
    q=asyncio.run(providers.fetch_quote(SimpleNamespace(market='CN',symbol='510300.SS'),get_config()))
    assert q['provider_id']=='eastmoney' and q['price']==100
    assert q['provider_attempts'][0]['status']=='delayed'


def test_yahoo_search_uses_backup_node(monkeypatch):
    import app.providers as providers
    called=[]
    async def request(method,url,**kwargs):
        called.append(url)
        if 'query1' in url:raise httpx.ConnectError('offline')
        return httpx.Response(200,json={'quotes':[{'symbol':'ABC','shortname':'Example','quoteType':'EQUITY'}]})
    monkeypatch.setattr(providers,'request',request)
    result=asyncio.run(providers.search_symbols('ABC','US',get_config()))
    assert result['items'][0]['symbol']=='ABC' and len(called)==2


def test_one_failed_news_source_does_not_hide_successes(monkeypatch):
    import app.news_sources as adapters
    import app.news as news
    async def fetch(sid):
        if sid=='stcn':raise httpx.ConnectError('offline')
        return [{'title':'某公司公开财经新闻标题','url':'https://example.com/news/1','source':'财联社','published':''}]
    monkeypatch.setattr(adapters,'fetch_builtin',fetch)
    config={**get_config(),'news_sources':['cls','stcn'],'feeds':[]}
    result=asyncio.run(news.refresh_news(config))
    assert result['status']=='partial' and result['added']==1
    assert health('news:cls')['status']=='ok' and health('news:stcn')['status']=='failed'
    with Session() as s:assert s.scalar(select(func.count()).select_from(Article))==1


def test_undated_headlines_keep_stable_identity():
    from app.news import identify
    item={'title':'没有发布时间的公开标题','url':'https://example.com/news/1','published':''}
    assert identify(item)==identify(dict(item))


def test_source_catalog_reports_access_limits_honestly(client):
    data=client.get('/api/sources').json()
    assert {s['id'] for s in data['news']} == {'cls','stcn','jin10','wallstreetcn','xueqiu','tradingview','seekingalpha','coindesk','cointelegraph'}
    snow=next(x for x in data['news'] if x['id']=='xueqiu')
    assert not snow['enabled'] and snow['health']['status']=='requires_access'
    assert data['mode']=='auto'
    assert next(x for x in data['quotes'] if x['id']=='eastmoney')['markets']==['CN']


def test_source_selection_validation_and_persistence(client):
    assert client.put('/api/settings',json={'news_sources':['cls','seekingalpha'],'provider':'auto'}).status_code==200
    assert client.get('/api/settings').json()['news_sources']==['cls','seekingalpha']
    assert client.put('/api/settings',json={'news_sources':['invented-source']}).status_code==422


def test_refresh_preserves_last_quote_when_all_providers_fail(monkeypatch):
    import app.services as services
    from app.db import Watch
    snapshot=quote(datetime.now(timezone.utc))
    with Session.begin() as s:
        s.add(Watch(id='CN:510300.SS',symbol='510300.SS',name='ETF',market='CN',exchange='SSE',quote=snapshot))
    async def fail(*args):raise ValueError('No sources available')
    monkeypatch.setattr(services,'fetch_quote',fail)
    result=asyncio.run(services.refresh_quotes())
    assert result['status']=='partial'
    with Session() as s:
        row=s.get(Watch,'CN:510300.SS')
        assert row.quote==snapshot and row.error


def test_news_round_deadline_retains_completed_sources(monkeypatch):
    import app.news as news
    import app.news_sources as adapters
    monkeypatch.setattr(news,'ROUND_TIMEOUT',0.02)
    async def fetch(sid):
        if sid=='stcn':await asyncio.sleep(10)
        return [{'title':'已经获取的公开资讯标题','url':'https://example.com/1','source':'财联社','published':''}]
    monkeypatch.setattr(adapters,'fetch_builtin',fetch)
    result=asyncio.run(news.refresh_news({**get_config(),'news_sources':['cls','stcn'],'feeds':[]}))
    assert result['status']=='partial' and result['added']==1
    assert result['failures'][0]['source']=='本轮未完成来源'
