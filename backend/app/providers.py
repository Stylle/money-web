import math
import asyncio
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote as urlquote
from zoneinfo import ZoneInfo
from .security import request
from .markets import MARKETS, market_state, valid_live_quote

# Discoverability catalog only. No fabricated prices or sample holdings.
CATALOG = [
    {'symbol': '513100.SS', 'name': '国泰纳斯达克100 ETF', 'market': 'CN', 'exchange': 'SSE', 'kind': 'etf'},
    {'symbol': '510880.SS', 'name': '华泰柏瑞上证红利 ETF', 'market': 'CN', 'exchange': 'SSE', 'kind': 'etf'},
    {'symbol': '510300.SS', 'name': '华泰柏瑞沪深300 ETF', 'market': 'CN', 'exchange': 'SSE', 'kind': 'etf'},
    {'symbol': '159915.SZ', 'name': '易方达创业板 ETF', 'market': 'CN', 'exchange': 'SZSE', 'kind': 'etf'},
    {'symbol': '600519.SS', 'name': '贵州茅台', 'market': 'CN', 'exchange': 'SSE', 'kind': 'stock'},
    {'symbol': '0700.HK', 'name': '腾讯控股', 'market': 'HK', 'exchange': 'HKEX', 'kind': 'stock'},
    {'symbol': '9988.HK', 'name': '阿里巴巴', 'market': 'HK', 'exchange': 'HKEX', 'kind': 'stock'},
    {'symbol': '2800.HK', 'name': '盈富基金', 'market': 'HK', 'exchange': 'HKEX', 'kind': 'etf'},
    {'symbol': '3033.HK', 'name': '南方恒生科技 ETF', 'market': 'HK', 'exchange': 'HKEX', 'kind': 'etf'},
    {'symbol': 'QQQ', 'name': 'Invesco 纳斯达克100 ETF', 'market': 'US', 'exchange': 'NASDAQ', 'kind': 'etf'},
    {'symbol': 'SPY', 'name': 'SPDR 标普500 ETF', 'market': 'US', 'exchange': 'NYSEARCA', 'kind': 'etf'},
    {'symbol': 'SCHD', 'name': 'Schwab 美国红利 ETF', 'market': 'US', 'exchange': 'NYSEARCA', 'kind': 'etf'},
    {'symbol': 'AAPL', 'name': '苹果 Apple', 'market': 'US', 'exchange': 'NASDAQ', 'kind': 'stock'},
    {'symbol': 'NVDA', 'name': '英伟达 NVIDIA', 'market': 'US', 'exchange': 'NASDAQ', 'kind': 'stock'},
]


def market_for(symbol):
    return 'HK' if symbol.endswith('.HK') else ('CN' if symbol.endswith(('.SS', '.SZ', '.BJ')) else 'US')


async def search_symbols(query, market, config):
    if market == 'CRYPTO' and config['provider'] != 'custom':
        from .crypto import search_crypto
        return await search_crypto(query)
    local = [x for x in CATALOG if x['market'] == market and (query.casefold() in x['name'].casefold() or query.upper() in x['symbol'])]
    if not query:
        return {'items': local, 'source': '内置标的目录', 'warning': None}
    try:
        if config['provider'] == 'custom':
            r = await request('GET', config['provider_base_url'].rstrip('/') + '/search', params={'q': query, 'market': market}, headers=provider_headers(config))
            from .schemas import WatchInput
            remote = [WatchInput.model_validate(x).model_dump(exclude={'threshold'}) for x in r.json()['items']]
        else:
            r=None
            for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
                try:
                    r=await request('GET',f'https://{host}/v1/finance/search',params={'q':query,'quotesCount':15,'newsCount':0},headers={'User-Agent':'Mozilla/5.0'},timeout=7)
                    break
                except Exception:
                    continue
            if r is None:raise ValueError('Search nodes unavailable')
            remote = [{'symbol': x['symbol'], 'name': x.get('shortname') or x.get('longname') or x['symbol'], 'market': market_for(x['symbol']), 'exchange': x.get('exchange', ''), 'kind': 'etf' if x.get('quoteType') == 'ETF' else 'stock'} for x in r.json().get('quotes', []) if x.get('quoteType') in ('ETF', 'EQUITY')]
        # Keep curated Chinese names and ETF classifications for known symbols;
        # this upstream sometimes labels Chinese ETFs as EQUITY.
        items = {x['symbol']: x for x in remote + local if x['market'] == market}
        return {'items': list(items.values()), 'source': config['provider'], 'warning': None}
    except Exception:
        return {'items': local, 'source': '内置标的目录', 'warning': '在线搜索暂不可用，可使用目录或手动添加完整代码'}


def provider_headers(config):
    return {'Authorization': f'Bearer {config["provider_key"]}'} if config['provider_key'] else {}


def number(value, positive=False):
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError('Invalid numeric value')
    return result


def normalize_quote(data):
    for field in ('price', 'previous_close'):
        data[field] = number(data[field], positive=True)
    dt = datetime.fromisoformat(data['as_of'])
    if dt.tzinfo is None:
        raise ValueError('Quote timestamp requires timezone')
    if dt>datetime.now(timezone.utc)+timedelta(seconds=30):
        raise ValueError('Quote timestamp is in the future')
    data['change_pct'] = round((data['price'] / data['previous_close'] - 1) * 100, 4)
    data['fetched_at'] = datetime.now(timezone.utc).isoformat()
    data['currency'] = str(data.get('currency', ''))[:10]
    for key in ('history', 'intraday'):
        bars = data.get(key, [])
        if len(bars) > 2000:
            raise ValueError('Too many bars')
        previous = None
        for bar in bars:
            at=datetime.fromisoformat(bar['time'])
            if at.tzinfo is None:raise ValueError('Bar timestamp requires timezone')
            if previous is not None and bar['time'] <= previous:
                raise ValueError('Bars must be unique and chronological')
            previous = bar['time']
            # Minute line points have no actual OHLC; never fabricate candles.
            fields=('open','high','low','close') if key=='history' or 'open' in bar else ('close',)
            for field in fields:
                bar[field] = number(bar[field], positive=True)
            bar['volume'] = number(bar.get('volume', 0))
            if bar['volume'] < 0 or ('open' in bar and (bar['high'] < max(bar['open'], bar['close'], bar['low']) or bar['low'] > min(bar['open'], bar['close']))):
                raise ValueError('Invalid OHLCV')
    return data


async def fetch_yahoo_quote(watch, config, host='query1.finance.yahoo.com'):
    if config['provider'] == 'custom':
        r = await request('GET', config['provider_base_url'].rstrip('/') + '/quote', params={'symbol': watch.symbol, 'market': watch.market}, headers=provider_headers(config))
        data = r.json()
        data['source'] = '自定义行情接口'
        return normalize_quote(data)
    base = f'https://{host}/v8/finance/chart/' + urlquote(watch.symbol, safe='')
    intraday = (await request('GET', base, params={'interval': '5m', 'range': '1d', 'includePrePost': 'false'}, headers={'User-Agent': 'Mozilla/5.0'},timeout=5)).json()['chart']['result'][0]
    daily = (await request('GET', base, params={'interval': '1d', 'range': '6mo'}, headers={'User-Agent': 'Mozilla/5.0'},timeout=5)).json()['chart']['result'][0]
    meta = intraday['meta']
    local_date = datetime.now(ZoneInfo(MARKETS[watch.market]['tz'])).date().isoformat()

    def bars(result, adjusted=False):
        values = result['indicators']['quote'][0]
        adj = result['indicators'].get('adjclose', [{}])[0].get('adjclose', [])
        output = []
        for i, timestamp in enumerate(result.get('timestamp', [])):
            if any(values.get(k, [None] * (i+1))[i] is None for k in ('open', 'high', 'low', 'close')):
                continue
            time = datetime.fromtimestamp(timestamp, timezone.utc)
            if adjusted and time.astimezone(ZoneInfo(MARKETS[watch.market]['tz'])).date().isoformat() >= local_date:
                continue  # Completed daily bars only.
            factor = adj[i] / values['close'][i] if adjusted and i < len(adj) and adj[i] else 1
            output.append({'time': time.isoformat(), **{k: values[k][i] * factor for k in ('open', 'high', 'low', 'close')}, 'volume': values['volume'][i] or 0})
        return output

    return normalize_quote({'price': meta['regularMarketPrice'], 'previous_close': meta.get('previousClose') or meta['chartPreviousClose'],
        'as_of': datetime.fromtimestamp(meta['regularMarketTime'], timezone.utc).isoformat(), 'currency': meta.get('currency', ''),
        'source': f'Yahoo Finance · {host.split(".")[0]}', 'delay_note': '实验性公开接口；无实时性或可用性保证；信号要求报价在 5 分钟内',
        'history': bars(daily, True), 'intraday': bars(intraday), 'adjustment': '日线使用上游 adjclose 比例调整 OHLC；原始成交量'})


PROVIDERS = [
    {'id':'binance','name':'Binance · 公开现货','markets':['CRYPTO'],'note':'仅 USDT 现货；同交易对自动切换，UTC 日线'},
    {'id':'coinbase','name':'Coinbase Exchange · 公开现货','markets':['CRYPTO'],'note':'USD / USDT 独立计价；不做汇率替换'},
    {'id':'tencent','name':'腾讯财经','markets':['CN','HK','US'],'note':'公开网站端点；港美股可能延迟，不保证授权实时行情'},
    {'id':'eastmoney','name':'东方财富','markets':['CN'],'note':'公开网站端点；当前仅启用已验证的 A 股映射'},
    {'id':'yahoo','name':'Yahoo Finance · 主节点','markets':['CN','HK','US'],'note':'实验性端点，主备节点属于同一家提供方'},
    {'id':'yahoo_backup','name':'Yahoo Finance · 备用节点','markets':['CN','HK','US'],'note':'同提供方备用节点，不能视为独立数据机构'},
]
QUOTE_HOSTS={'qt.gtimg.cn','web.ifzq.gtimg.cn','push2.eastmoney.com','push2his.eastmoney.com','query1.finance.yahoo.com','query2.finance.yahoo.com','data-api.binance.vision','api.exchange.coinbase.com'}
_history_cache={}


def tencent_symbol(watch):
    code=watch.symbol
    if watch.market=='CN':
        suffix=code.split('.')[-1]
        return {'SS':'sh','SZ':'sz','BJ':'bj'}[suffix]+code.split('.')[0]
    if watch.market=='HK':return 'hk'+code.split('.')[0].zfill(5)
    return 'us'+code.replace('-','.')


def local_time(value, market):
    value=str(value).strip()
    if re.fullmatch(r'\d{14}',value):dt=datetime.strptime(value,'%Y%m%d%H%M%S')
    else:dt=datetime.fromisoformat(value.replace('/','-'))
    return dt.replace(tzinfo=ZoneInfo(MARKETS[market]['tz'])).astimezone(timezone.utc).isoformat()


def day_bars(rows, market):
    today=datetime.now(ZoneInfo(MARKETS[market]['tz'])).date().isoformat()
    output=[]
    for row in rows:
        if row[0]>=today:continue
        output.append({'time':local_time(row[0]+' 09:30:00',market),'open':number(row[1],True),'close':number(row[2],True),'high':number(row[3],True),'low':number(row[4],True),'volume':number(row[5])})
    return output


async def cached_history(provider, watch, loader):
    key=(provider,watch.market,watch.symbol,datetime.now(ZoneInfo(MARKETS[watch.market]['tz'])).date().isoformat())
    cached=_history_cache.get(key)
    if cached and cached[0]>time.monotonic():return cached[1]
    rows=await loader()
    if len(rows)>=65:
        if len(_history_cache)>200:_history_cache.clear()
        _history_cache[key]=(time.monotonic()+1800,rows)
    return rows


async def fetch_tencent(watch):
    symbol=tencent_symbol(watch)
    response=await request('GET','https://qt.gtimg.cn/q='+urlquote(symbol,safe='.'),timeout=4)
    text=response.content.decode('gbk')
    match=re.search(r'="([^"\n]+)"',text)
    if not match:raise ValueError('No Tencent quote')
    fields=match.group(1).split('~')
    if len(fields)<31:raise ValueError('Incomplete Tencent quote')
    quote={'price':number(fields[3],True),'previous_close':number(fields[4],True),'as_of':local_time(fields[30],watch.market),
           'currency':{'CN':'CNY','HK':'HKD','US':'USD'}[watch.market],'source':'腾讯财经','history':[],'intraday':[],
           'delay_note':'公开网站接口，港美股可能延迟；使用提供方原始时间戳','adjustment':'日线按返回的前复权序列；量单位依市场，量比只在本源序列内计算'}
    async def history():
        endpoint='usfqkline' if watch.market=='US' else 'fqkline'
        r=await request('GET',f'https://web.ifzq.gtimg.cn/appstock/app/{endpoint}/get',params={'param':f'{symbol},day,,,140,qfq'},timeout=4)
        data=r.json().get('data',{}).get(symbol,{})
        return day_bars(data.get('qfqday') or data.get('day') or [],watch.market)
    try:quote['history']=await cached_history('tencent',watch,history)
    except Exception:quote['history_warning']='腾讯日线暂不可用，等待备用日线'
    if watch.market in ('CN','HK'):
        try:
            r=await request('GET','https://web.ifzq.gtimg.cn/appstock/app/minute/query',params={'code':symbol},timeout=4)
            minute=r.json()['data'][symbol]['data']
            day=minute.get('date','')
            if re.fullmatch(r'\d{8}',day):day=f'{day[:4]}-{day[4:6]}-{day[6:]}'
            previous_volume=0
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):
                for row in minute.get('data',[]):
                    at,price,volume,*_=row.split()
                    volume=number(volume)
                    quote['intraday'].append({'time':local_time(day+' '+at[:2]+':'+at[2:]+':00',watch.market),'close':number(price,True),'volume':max(0,volume-previous_volume)})
                    previous_volume=volume
        except Exception:quote['intraday_warning']='分钟线暂不可用'
    return normalize_quote(quote)


def eastmoney_id(watch):
    if watch.market=='CN':return ('1.' if watch.symbol.endswith('.SS') else '0.')+watch.symbol.split('.')[0]
    raise ValueError('Eastmoney non-CN mapping is not verified')


async def fetch_eastmoney(watch):
    secid=eastmoney_id(watch)
    r=await request('GET','https://push2.eastmoney.com/api/qt/stock/get',params={'secid':secid,'fields':'f43,f60,f86,f59'},timeout=4)
    data=r.json()['data']
    scale=10**int(data['f59'])
    quote={'price':number(data['f43'],True)/scale,'previous_close':number(data['f60'],True)/scale,
           'as_of':datetime.fromtimestamp(number(data['f86'],True),timezone.utc).isoformat(),
           'currency':'HKD' if watch.market=='HK' else 'CNY','source':'东方财富','history':[],'intraday':[],
           'delay_note':'公开网站端点，保留上游行情时间；不保证持续可用','adjustment':'fqt=1 前复权日线；量比只在同源历史序列内计算'}
    async def history():
        r=await request('GET','https://push2his.eastmoney.com/api/qt/stock/kline/get',params={'secid':secid,'klt':101,'fqt':1,'lmt':140,'end':'20500101','fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56'},timeout=4)
        return day_bars([line.split(',') for line in r.json()['data']['klines']],watch.market)
    try:quote['history']=await cached_history('eastmoney',watch,history)
    except Exception:quote['history_warning']='东方财富日线暂不可用'
    return normalize_quote(quote)


async def fetch_quote(watch, config):
    from .source_health import cooling, record
    from .security import safe_error
    if config['provider']=='custom':return await fetch_yahoo_quote(watch,config)
    if watch.market == 'CRYPTO':
        from .crypto import fetch_crypto
        return await fetch_crypto(watch)
    mode=config['provider']
    order=(['tencent','eastmoney','yahoo','yahoo_backup'] if watch.market=='CN' else ['tencent','yahoo','yahoo_backup']) if mode=='auto' else ([mode,'yahoo_backup'] if mode=='yahoo' else [mode])
    state=market_state(watch.market)
    candidates=[];attempts=[]
    deadline=time.monotonic()+24
    for provider in order:
        if deadline-time.monotonic()<1:break
        if provider=='eastmoney' and watch.market!='CN':continue
        key=f'quote:{provider}:{watch.market}'
        if cooling(key):attempts.append({'provider':provider,'status':'cooling'});continue
        started=time.monotonic()
        try:
            async with asyncio.timeout(min(13,deadline-time.monotonic())):
                if provider=='tencent':quote=await fetch_tencent(watch)
                elif provider=='eastmoney':quote=await fetch_eastmoney(watch)
                else:quote=await fetch_yahoo_quote(watch,config,'query2.finance.yahoo.com' if provider=='yahoo_backup' else 'query1.finance.yahoo.com')
            fresh=valid_live_quote(quote,state) if state['is_open'] else True
            record(key,'ok' if fresh else 'degraded',latency_ms=round((time.monotonic()-started)*1000),error=None if fresh else '报价超出五分钟有效窗口；已尝试其他来源')
            attempts.append({'provider':provider,'status':'ok' if fresh else 'delayed','as_of':quote['as_of']})
            quote['provider_id']=provider
            candidates.append(quote)
            if fresh:break
        except Exception as exc:
            record(key,'failed',error=safe_error(exc),breaker=not isinstance(exc,(ValueError,KeyError,IndexError)))
            attempts.append({'provider':provider,'status':'failed','error':safe_error(exc)})
    if not candidates:raise ValueError('No valid provider response')
    quote=max(candidates,key=lambda q:datetime.fromisoformat(q['as_of']))
    quote['history_source']=quote['source'] if quote.get('history') else None
    quote['intraday_source']=quote['source'] if quote.get('intraday') else None
    # Fill missing charts as independent components, never replace the timestamp
    # or mix rows from differently adjusted daily series.
    if len(quote.get('history',[]))<65 or not quote.get('intraday'):
        supplement=next((q for q in candidates if len(q.get('history',[]))>=65),None)
        if supplement is None and quote['provider_id'] not in ('yahoo','yahoo_backup') and deadline-time.monotonic()>1:
            try:
                async with asyncio.timeout(min(9,deadline-time.monotonic())):supplement=await fetch_yahoo_quote(watch,config)
            except Exception:pass
        if supplement:
            if len(quote.get('history',[]))<65:
                quote['history']=supplement.get('history',[]);quote['history_source']=supplement['source']
                quote['adjustment']=supplement.get('adjustment','');quote.pop('history_warning',None)
            if not quote.get('intraday'):
                quote['intraday']=supplement.get('intraday',[]);quote['intraday_source']=supplement['source']
    quote['provider_attempts']=attempts
    quote['resilience_note']='自动切换不改变数据时效要求；没有足够新鲜的数据时暂停操作提示'
    return quote
