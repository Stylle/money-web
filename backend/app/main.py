import hashlib
import hmac
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update, func, or_
from .db import Article, Config, Delivery, Event, Portfolio, Session, Watch, SourceHealth, initialize, utcnow
from .config import get_config, save_config, cipher
from .schemas import PortfolioInput, SettingsInput, WatchInput
from .providers import search_symbols
from .markets import market_state, valid_live_quote
from .services import event_data, portfolio_data, refresh_quotes, send_webhook
from .strategy import analyze, analyze_all
from .security import safe_error, validate_url


@asynccontextmanager
async def lifespan(app):
    initialize()
    cipher()
    yield


app = FastAPI(title='观澜 Invest Watch', version='0.1.0', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def security(request: Request, call_next):
    if request.url.path.startswith('/api') and request.url.path != '/api/health':
        token = os.getenv('APP_TOKEN', '')
        given = request.headers.get('authorization', '').removeprefix('Bearer ')
        if token and not hmac.compare_digest(given, token):
            return JSONResponse({'detail': '请输入访问口令'}, status_code=401)
        if not token and request.client and request.client.host not in ('127.0.0.1', '::1', 'testclient'):
            return JSONResponse({'detail': '外部访问必须配置 APP_TOKEN'}, status_code=403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if origin and urlsplit(origin).netloc != request.headers.get('host'):
                return JSONResponse({'detail': '不允许跨站写入'}, status_code=403)
            if int(request.headers.get('content-length', '0')) > 131072:
                return JSONResponse({'detail': '请求过大'}, status_code=413)
    response = await call_next(request)
    response.headers.update({'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY'})
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/health')
def health():
    try:
        with Session() as s:
            s.execute(select(1))
        return {'status': 'ok', 'version': '0.1.0'}
    except Exception:
        raise HTTPException(503, '数据库不可用')


@app.get('/api/dashboard')
def dashboard():
    config = get_config()
    p = portfolio_data()
    with Session() as s:
        watches = s.scalars(select(Watch).order_by(Watch.market, Watch.symbol)).all()
        signals = analyze_all(watches, p, config['strategy_enabled'])
        events = s.scalars(select(Event).order_by(Event.created.desc()).limit(15)).all()
        heartbeat = s.get(Config, 'worker_heartbeat')
        result = {'watchlist': [], 'markets': [market_state(m) for m in ('CN', 'HK', 'US', 'CRYPTO')], 'portfolio': p,
                  'events': [event_data(e) for e in events], 'worker_heartbeat': heartbeat.value if heartbeat else None,
                  'mode': {'ai': config['ai_enabled'], 'strategy': config['strategy_enabled']}, 'keywords': config['keywords']}
        for w in watches:
            quote = w.quote or {}
            result['watchlist'].append({'id': w.id, 'symbol': w.symbol, 'name': w.name, 'market': w.market, 'exchange': w.exchange, 'kind': w.kind, 'threshold': w.threshold,
                'quote': {k: v for k, v in quote.items() if k != 'history'}, 'error': w.error, 'live': not w.error and valid_live_quote(quote, market_state(w.market)), 'signal': signals[w.id]})
    return result


@app.get('/api/search')
async def search(q: str = Query(default='', max_length=80), market: str = Query(pattern='^(CN|HK|US|CRYPTO)$')):
    return await search_symbols(q.strip(), market, get_config())


@app.post('/api/watchlist', status_code=201)
def add_watch(data: WatchInput):
    wid = data.market+':'+data.symbol
    with Session.begin() as s:
        if s.get(Watch, wid):
            raise HTTPException(409, '已订阅此标的')
        if s.scalar(select(func.count()).select_from(Watch)) >= 50:
            raise HTTPException(422, '个人版最多订阅 50 个标的')
        s.add(Watch(id=wid, **data.model_dump(), quote={}))
    return {'id': wid}


@app.patch('/api/watchlist/{wid}')
def change_watch(wid: str, threshold: float = Query(ge=0.5, le=50)):
    with Session.begin() as s:
        w = s.get(Watch, wid)
        if not w:
            raise HTTPException(404, '标的不存在')
        w.threshold = threshold
    return {'ok': True}


@app.delete('/api/watchlist/{wid}')
def delete_watch(wid: str):
    with Session.begin() as s:
        portfolio = s.get(Portfolio, 1)
        if any(p['watch_id'] == wid for p in portfolio.payload['positions']):
            raise HTTPException(409, '请先从持仓配置移除此标的')
        w = s.get(Watch, wid)
        if not w:
            raise HTTPException(404, '标的不存在')
        s.delete(w)
    return {'ok': True}


@app.post('/api/refresh')
async def refresh():
    return await refresh_quotes()


@app.get('/api/watchlist/{wid}/history')
def history(wid: str):
    with Session() as s:
        w = s.get(Watch, wid)
        if not w:
            raise HTTPException(404, '标的不存在')
        return w.quote or {}


@app.get('/api/portfolio')
def get_portfolio():
    return portfolio_data()


@app.put('/api/portfolio')
def put_portfolio(data: PortfolioInput):
    with Session.begin() as s:
        ids = set(s.scalars(select(Watch.id)).all())
        if not {p.watch_id for p in data.positions} <= ids:
            raise HTTPException(422, '持仓标的必须先添加到自选')
        payload = data.model_dump(mode='json', exclude={'revision'})
        payload['updated_at'] = utcnow().isoformat()
        updated = s.execute(update(Portfolio).where(Portfolio.id==1, Portfolio.revision==data.revision).values(payload=payload, revision=data.revision+1)).rowcount
        if not updated:
            raise HTTPException(409, '持仓已被其他页面修改，请刷新后重试')
        s.add(Event(id=hashlib.sha256(('portfolio'+utcnow().isoformat()).encode()).hexdigest(), kind='portfolio', title='持仓比例已更新', payload={'revision': data.revision+1, 'snapshot': payload}))
    return portfolio_data()


@app.get('/api/news')
def news(q: str = Query(default='', max_length=100), subscribed: bool = False, symbol: str = Query(default='', max_length=40), topic: str = Query(default='',pattern='^$|^crypto$')):
    config = get_config()
    with Session() as s:
        query = select(Article)
        if topic == 'crypto':
            terms = ('比特币','以太坊','加密货币','加密资产','数字资产','稳定币','Bitcoin','Ethereum','crypto','BTC','USDT','Solana')
            query = query.where(or_(Article.source.in_(['CoinDesk','Cointelegraph']),*[Article.title.ilike('%'+term+'%') for term in terms]))
        items = s.scalars(query.order_by(Article.collected.desc()).limit(500)).all()
    items.sort(key=lambda a:a.published or a.collected.isoformat(),reverse=True)
    result = []
    for a in items:
        tags = [k for k in config['keywords'] if k.casefold() in a.title.casefold()]
        if q and q.casefold() not in a.title.casefold() and q not in a.source:
            continue
        if symbol and symbol.casefold() not in a.title.casefold():
            continue
        if subscribed and not tags:
            continue
        result.append({'id': a.id, 'title': a.title, 'url': a.url, 'source': a.source, 'published': a.published, 'tags': tags, 'association': '关键词匹配' if tags else ''})
    return {'items': result[:100]}


@app.post('/api/news/refresh')
async def refresh_news_route():
    from .news import refresh_news
    return await refresh_news(get_config())


@app.get('/api/events')
def events():
    with Session() as s:
        items = s.scalars(select(Event).order_by(Event.created.desc()).limit(100)).all()
        deliveries = s.scalars(select(Delivery).order_by(Delivery.created.desc()).limit(100)).all()
    return {'items': [event_data(e) for e in items], 'deliveries': [{'id': d.id, 'status': d.status, 'attempts': d.attempts, 'error': d.error, 'created': d.created.isoformat()} for d in deliveries]}


@app.get('/api/settings')
def settings():
    return get_config(public=True)


@app.get('/api/sources')
def sources():
    from .news_sources import CATALOG
    from .providers import PROVIDERS
    from .source_health import health
    config=get_config()
    news=[]
    for item in CATALOG:
        enabled=item['id'] in config.get('news_sources',[])
        current=health('news:'+item['id'])
        if not enabled:current={**current,'status':'requires_access' if item['id']=='xueqiu' else 'disabled'}
        news.append({**item,'enabled':enabled,'health':current})
    quotes=[{**provider,'health':{m:health(f'quote:{provider["id"]}:{m}') for m in provider['markets']}} for provider in PROVIDERS]
    return {'news':news,'quotes':quotes,'mode':config['provider'],'checked_at':utcnow().isoformat(),
            'routing':{'CN':['tencent','eastmoney','yahoo','yahoo_backup'],'HK':['tencent','yahoo','yahoo_backup'],'US':['tencent','yahoo','yahoo_backup'],'CRYPTO':['binance (USDT)','coinbase (同一 USD/USDT 交易对)']}}


@app.put('/api/settings')
async def put_settings(data: SettingsInput):
    changes = data.model_dump(exclude_none=True)
    for key in ('ai_base_url', 'webhook_url', 'provider_base_url'):
        if changes.get(key):
            try:
                await validate_url(changes[key], resolve=False)
            except ValueError as exc:
                raise HTTPException(422, str(exc))
    if 'feeds' in changes:
        for feed in changes['feeds']:
            try:
                await validate_url(feed['url'], resolve=False)
            except ValueError as exc:
                raise HTTPException(422, str(exc))
        from .services import release
        release('news')
    if 'news_sources' in changes:
        from .services import release
        release('news')
    merged = {**get_config(), **changes}
    if merged['ai_enabled'] and not (merged['ai_key'] and merged['ai_model']):
        raise HTTPException(422, '开启 AI 前请配置密钥与模型')
    if merged['provider'] == 'custom' and not merged['provider_base_url']:
        raise HTTPException(422, '请选择自定义行情接口地址')
    return save_config(changes)


@app.post('/api/webhook/test')
async def test_webhook():
    config = get_config()
    if not config['webhook_url']:
        raise HTTPException(422, '请先保存 Webhook 地址')
    try:
        await send_webhook(config, {'id': 'test-'+str(time.time_ns()), 'type': 'test', 'title': '观澜通知连接测试', 'timestamp': utcnow().isoformat(), 'data': {'message': 'Webhook 已成功连接'}})
        return {'ok': True}
    except Exception as exc:
        raise HTTPException(502, safe_error(exc))


@app.post('/api/ai/analyze')
async def ai_analyze():
    from .ai import generate_report
    config = get_config()
    with Session() as s:
        watches = s.scalars(select(Watch)).all()
    if not watches:
        raise HTTPException(422, '请先订阅标的')
    try:
        return await generate_report(watches, portfolio_data(), config)
    except Exception as exc:
        raise HTTPException(422, safe_error(exc))


@app.post('/api/ai/test')
async def ai_test():
    from .ai import generate_report
    try:
        return await generate_report([], portfolio_data(), get_config(), test=True)
    except Exception as exc:
        raise HTTPException(422, safe_error(exc))


WEB = Path(os.getenv('WEB_DIR', 'frontend/dist'))
if WEB.is_dir():
    app.mount('/assets', StaticFiles(directory=WEB/'assets'), name='assets')


@app.get('/{path:path}')
def index(path: str):
    if path.startswith('api/'):
        raise HTTPException(404, '接口不存在')
    if WEB.is_dir():
        return FileResponse(WEB/'index.html')
    return JSONResponse({'message': '前端尚未构建；开发时请启动 Vite，生产环境运行 npm run build'})
