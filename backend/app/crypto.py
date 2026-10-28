"""Public spot observations only; never substitute USD and USDT or place orders."""
import asyncio
import re
import time
from datetime import datetime, timedelta, timezone
from .security import request, safe_error
from .markets import market_state, valid_live_quote
from .source_health import cooling, record

NAMES = {'BTC':'比特币 Bitcoin','ETH':'以太坊 Ethereum','SOL':'Solana','BNB':'BNB',
         'XRP':'XRP','DOGE':'狗狗币 Dogecoin','ADA':'Cardano','AVAX':'Avalanche','LINK':'Chainlink'}
_products = None


def product(symbol, venue='公开现货'):
    base, unit = symbol.split('-')
    return {'symbol':symbol, 'name':f'{NAMES.get(base,base)} / {unit}', 'market':'CRYPTO', 'exchange':venue, 'kind':'crypto'}


async def search_crypto(query):
    global _products
    warning = None
    if not _products or _products[0] < time.monotonic():
        items = {}
        for venue, url in [('Binance','https://data-api.binance.vision/api/v3/exchangeInfo'),
                           ('Coinbase','https://api.exchange.coinbase.com/products')]:
            try:
                params = {'permissions':'SPOT','showPermissionSets':'false','symbolStatus':'TRADING'} if venue == 'Binance' else None
                r = await request('GET',url,params=params,timeout=6)
                rows = r.json()['symbols'] if venue == 'Binance' else r.json()
                for row in rows:
                    if venue == 'Binance':
                        if row.get('status') != 'TRADING' or not row.get('isSpotTradingAllowed') or row.get('quoteAsset') != 'USDT':continue
                        symbol = row['baseAsset']+'-USDT'
                    else:
                        if row.get('status') != 'online' or row.get('trading_disabled') or row.get('quote_currency') not in ('USD','USDT'):continue
                        symbol = row['id']
                    if re.fullmatch(r'[A-Z0-9]{2,15}-(USD|USDT)',symbol):items.setdefault(symbol,product(symbol,venue))
            except Exception:
                warning = '部分交易所目录暂不可用；仅显示已获取的现货目录，可重试或手动添加'
        if items:_products = (time.monotonic()+(3600 if warning is None else 60),list(items.values()),warning)
        else:
            local = [product(base+'-USDT') for base in NAMES]
            warning = '在线目录暂不可用，以下仅为常用交易对目录，订阅后需验证真实行情'
            return {'items':[x for x in local if query.casefold() in (x['name']+' '+x['symbol']).casefold()], 'source':'内置交易对目录', 'warning':warning}
    words = query.upper().replace('/','-').replace(' ','')
    items = [x for x in _products[1] if query.casefold() in x['name'].casefold() or words in x['symbol'] or words in x['symbol'].replace('-','')]
    items.sort(key=lambda x:(x['symbol'].split('-')[0] not in NAMES,x['symbol'].endswith('-USD'),x['symbol']))
    return {'items':items[:60], 'source':'公开现货交易对目录', 'warning':_products[2]}


def instant(seconds):
    return datetime.fromtimestamp(float(seconds),timezone.utc).isoformat()


def daily_rows(rows, venue, now):
    out = []
    for row in rows:
        if venue == 'binance':
            if float(row[6])/1000 >= now.timestamp():continue
            bar = {'time':instant(float(row[0])/1000),**dict(zip(('open','high','low','close','volume'),map(float,row[1:6])))}
        else:
            if float(row[0])+86400 > now.timestamp():continue
            bar = {'time':instant(row[0]),**dict(zip(('low','high','open','close','volume'),map(float,row[1:6])))}
        out.append(bar)
    return sorted(out,key=lambda x:x['time'])[-140:]


async def fetch_spot(watch, venue):
    from .providers import normalize_quote, cached_history
    now = datetime.now(timezone.utc)
    base, unit = watch.symbol.split('-')
    if venue == 'binance':
        if unit != 'USDT':raise ValueError('Binance adapter only supports exact USDT pairs')
        url = 'https://data-api.binance.vision/api/v3/'
        ticker = (await request('GET',url+'trades',params={'symbol':base+unit,'limit':1},timeout=4)).json()[-1]
        price, at = ticker['price'], instant(float(ticker['time'])/1000)
        async def history():
            r = await request('GET',url+'klines',params={'symbol':base+unit,'interval':'1d','limit':141},timeout=4)
            return daily_rows(r.json(),venue,datetime.now(timezone.utc))
    else:
        url = 'https://api.exchange.coinbase.com/products/'+watch.symbol
        ticker = (await request('GET',url+'/ticker',timeout=4)).json()
        price, at = ticker['price'], ticker['time'].replace('Z','+00:00')
        async def history():
            r = await request('GET',url+'/candles',params={'granularity':86400},timeout=4)
            return daily_rows(r.json(),venue,datetime.now(timezone.utc))
    bars = await cached_history(venue,watch,history)
    yesterday = (now.date()-timedelta(days=1)).isoformat()
    if not bars or bars[-1]['time'][:10] != yesterday:
        raise ValueError('Missing previous UTC daily close')
    intraday = []
    try:
        if venue == 'binance':
            rows = (await request('GET',url+'klines',params={'symbol':base+unit,'interval':'5m','limit':96},timeout=4)).json()
            intraday = [{'time':instant(float(r[0])/1000),**dict(zip(('open','high','low','close','volume'),map(float,r[1:6])))} for r in rows]
        else:
            rows = (await request('GET',url+'/candles',params={'granularity':300},timeout=4)).json()
            intraday = sorted([{'time':instant(r[0]),**dict(zip(('low','high','open','close','volume'),map(float,r[1:6])))} for r in rows],key=lambda x:x['time'])[-96:]
    except Exception:pass
    source = 'Binance · 现货' if venue == 'binance' else 'Coinbase Exchange · 现货'
    return normalize_quote({'price':price,'as_of':at,'previous_close':bars[-1]['close'],'currency':unit,
        'source':source,'venue':venue,'pair':watch.symbol,'history':bars,'intraday':intraday,
        'change_basis':'上一 UTC 日收盘（北京时间 08:00），不是滚动 24 小时涨跌幅',
        'delay_note':'7×24 小时公开现货观察；交易所价格有差异，信号仍需五分钟内报价',
        'adjustment':'未复权；UTC 完整日线；不拼接不同交易所历史'})


async def fetch_crypto(watch):
    candidates, attempts = [], []
    deadline = time.monotonic()+24
    order = ['binance','coinbase'] if watch.symbol.endswith('-USDT') else ['coinbase']
    for venue in order:
        key = f'quote:{venue}:CRYPTO'
        if cooling(key):
            attempts.append({'provider':venue,'status':'cooling'});continue
        started = time.monotonic()
        try:
            async with asyncio.timeout(max(.1,min(12,deadline-time.monotonic()))):quote = await fetch_spot(watch,venue)
            fresh = valid_live_quote(quote,market_state('CRYPTO'))
            status = 'ok' if fresh else 'degraded'
            record(key,status,latency_ms=round((time.monotonic()-started)*1000),error=None if fresh else '现货成交时间已超过五分钟')
            attempts.append({'provider':venue,'status':status,'as_of':quote['as_of']})
            quote['provider_id'] = venue
            candidates.append(quote)
            if fresh:break
        except Exception as exc:
            record(key,'failed',error=safe_error(exc),breaker=not isinstance(exc,(ValueError,KeyError,IndexError)))
            attempts.append({'provider':venue,'status':'failed','error':safe_error(exc)})
    if not candidates:raise ValueError('加密现货数据源暂不可用或交易对不受支持')
    quote = max(candidates,key=lambda x:datetime.fromisoformat(x['as_of']))
    quote.update(history_source=quote['source'],intraday_source=quote['source'] if quote['intraday'] else None,provider_attempts=attempts)
    return quote
