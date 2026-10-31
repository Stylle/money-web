import asyncio
import hashlib
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, update, or_, and_
from sqlalchemy.exc import IntegrityError
from .db import Article, Config, Delivery, Event, Lease, Portfolio, Session, Watch, utcnow
from .config import get_config
from .markets import MARKETS, market_state, valid_live_quote
from .providers import fetch_quote
from .security import safe_error
from .webhooks import send_webhook
from .strategy import analyze, analyze_all


def lease(key, seconds):
    now = time.time()
    try:
        with Session.begin() as s:
            if not s.get(Lease, key):
                s.add(Lease(key=key, until=0))
                s.flush()
            return s.execute(update(Lease).where(Lease.key==key, Lease.until<=now).values(until=now+seconds)).rowcount == 1
    except IntegrityError:
        return False


def release(key, delay=0):
    with Session.begin() as s:
        s.execute(update(Lease).where(Lease.key==key).values(until=time.time()+delay))


def portfolio_data():
    with Session() as s:
        row = s.get(Portfolio, 1)
        return {'revision': row.revision, **row.payload}


def event_data(event):
    return {'id': event.id, 'created': event.created.isoformat(), 'kind': event.kind, 'title': event.title, 'payload': event.payload}


def emit(key, kind, title, payload, config, notify=False, expires_minutes=15):
    event_id = hashlib.sha256(key.encode()).hexdigest()
    now = utcnow()
    try:
        with Session.begin() as s:
            if s.get(Event, event_id):
                return False
            s.add(Event(id=event_id, kind=kind, title=title, payload=payload))
            if notify and config['webhook_url']:
                s.add(Delivery(id=event_id, payload={'id': event_id, 'type': kind, 'title': title, 'timestamp': now.isoformat(), 'expires_at': (now+timedelta(minutes=expires_minutes)).isoformat(), 'data': payload}))
        return True
    except IntegrityError:
        return False


async def refresh_quotes():
    if not lease('refresh', 600):
        return {'status': 'busy', 'message': '刷新进行中或处于 45 秒冷却期'}
    config = get_config()
    try:
        with Session() as s:
            watches = s.scalars(select(Watch)).all()
        sem = asyncio.Semaphore(5)
        results = []

        async def one(watch):
            async with sem:
                try:
                    q = await asyncio.wait_for(fetch_quote(watch, config), timeout=30)
                    with Session.begin() as s:
                        row = s.get(Watch, watch.id)
                        if row:
                            row.quote, row.error = q, None
                    results.append({'symbol': watch.symbol, 'ok': True})
                except Exception as exc:
                    error = safe_error(exc)
                    with Session.begin() as s:
                        row = s.get(Watch, watch.id)
                        if row:
                            row.error = error
                    results.append({'symbol': watch.symbol, 'ok': False, 'error': error})
        try:
            async with asyncio.timeout(150):
                await asyncio.gather(*(one(w) for w in watches))
        except TimeoutError:
            results.append({'ok': False, 'error': '本轮刷新达到 150 秒上限，未完成的标的等待下一轮'})
        scan_alerts(config)
        return {'status': 'ok' if all(r['ok'] for r in results) else 'partial', 'results': results}
    finally:
        release('refresh', 45)


def scan_alerts(config, now=None):
    now = now or utcnow()
    portfolio = portfolio_data()
    with Session() as s:
        watches = s.scalars(select(Watch)).all()
    signals = analyze_all(watches, portfolio, config['strategy_enabled'], now)
    for w in watches:
        state = market_state(w.market, now)
        q = w.quote or {}
        if w.market not in config['markets'] or w.error or not valid_live_quote(q, state, now):
            continue
        pct = q['change_pct']
        level = int(abs(pct)//w.threshold)
        if level < 1:
            continue
        direction = 'up' if pct > 0 else 'down'
        key = f'alert:{w.id}:{state["date"]}:{direction}:{level}:{w.threshold}'
        signal = signals[w.id]
        basis = '较上一 UTC 日收盘' if w.market == 'CRYPTO' else '较昨收'
        title = f'{w.name} {basis}{ "上涨" if pct>0 else "下跌" } {abs(pct):.2f}%'
        emit(key, 'alert', title, {'watch_id': w.id, 'market': w.market, 'price': q['price'], 'currency':q.get('currency'), 'change_basis':q.get('change_basis','昨收'), 'change_pct': pct, 'quote_at': q['as_of'], 'threshold': w.threshold, 'level': level, 'signal': signal}, config, config['notify_alerts'])


def quiet_now(config, now=None):
    at = (now or utcnow()).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%H:%M')
    start, end = config['quiet_start'], config['quiet_end']
    if not start or not end or start == end:
        return False
    return start <= at < end if start < end else at >= start or at < end


async def deliver_pending(config):
    if quiet_now(config):
        return
    now = utcnow()
    with Session() as s:
        items = s.scalars(select(Delivery).where(Delivery.status.in_(['pending', 'sending']), Delivery.due<=now).order_by(Delivery.created).limit(20)).all()
    for item in items:
        if datetime.fromisoformat(item.payload['expires_at']) <= now:
            with Session.begin() as s:
                s.get(Delivery, item.id).status = 'expired'
            continue
        with Session.begin() as s:
            claimed = s.execute(update(Delivery).where(Delivery.id==item.id, Delivery.status.in_(['pending', 'sending']), Delivery.due<=now).values(status='sending', due=now+timedelta(seconds=90), attempts=Delivery.attempts+1)).rowcount
        if not claimed:
            continue
        try:
            if not config['webhook_url']:
                with Session.begin() as s:
                    s.get(Delivery, item.id).status = 'disabled'
                continue
            await send_webhook(config, item.payload)
            with Session.begin() as s:
                row = s.get(Delivery, item.id)
                row.status, row.error = 'sent', None
        except Exception as exc:
            with Session.begin() as s:
                row = s.get(Delivery, item.id)
                row.status = 'failed' if row.attempts >= 3 else 'pending'
                row.due = now+timedelta(seconds=30*2**row.attempts)
                row.error = safe_error(exc)


async def daily_reports(config):
    from .ai import generate_report
    portfolio = portfolio_data()
    with Session() as s:
        watches = s.scalars(select(Watch)).all()
        recent_news = s.scalars(select(Article).where(Article.collected>=utcnow()-timedelta(hours=24)).order_by(Article.published.desc()).limit(8)).all()
    signals = analyze_all(watches, portfolio, config['strategy_enabled'])
    for market in config['markets']:
        state = market_state(market)
        group = [w for w in watches if w.market == market]
        if not state['daily_due'] or not group or not config['notify_daily']:
            continue
        key = f'daily:{market}:{state["date"]}'
        payload = {'market': market, 'date': state['date'], 'portfolio_revision': portfolio['revision'], 'items': [],
                   'news': [{'title': a.title, 'source': a.source, 'url': a.url, 'published': a.published} for a in recent_news]}
        for w in group:
            q = w.quote or {}
            payload['items'].append({'watch_id': w.id, 'name': w.name, 'price': q.get('price'), 'change_pct': q.get('change_pct'), 'quote_at': q.get('as_of'), 'data_valid': not w.error and valid_live_quote(q, state), 'error': w.error, 'signal': signals[w.id]})
        # Reserve and send base report before potentially slow AI calls.
        label = '每日观察 · UTC 00:30' if market == 'CRYPTO' else '开盘 30 分钟观察'
        emitted = emit(key, 'daily', f'{MARKETS[market]["name"]} · {label}', payload, config, True)
        if emitted:
            await deliver_pending(config)
        if emitted and config['ai_enabled']:
            try:
                report = await generate_report(group, portfolio, config)
                emit(key+':ai', 'analysis', f'{MARKETS[market]["name"]} · AI 分析补充', {'report': report.get('report'), 'analysis_id': report['id']}, config, True)
            except Exception as exc:
                emit(key+':ai-failed', 'system', 'AI 分析不可用，行情日报已保留', {'error': safe_error(exc)}, config)


async def tick():
    if not lease('worker', 900):
        return
    try:
        config = get_config()
        await deliver_pending(config)
        if any(market_state(m)['is_open'] for m in config['markets']):
            await refresh_quotes()
        await deliver_pending(config)
        await daily_reports(config)
        await deliver_pending(config)
        from .news import refresh_news
        await refresh_news(config)
        with Session.begin() as s:
            row = s.get(Config, 'worker_heartbeat')
            if row:
                row.value = utcnow().isoformat()
            else:
                s.add(Config(key='worker_heartbeat', value=utcnow().isoformat()))
    finally:
        release('worker')
