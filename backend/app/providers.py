import math
from datetime import datetime, timezone
from urllib.parse import quote as urlquote
from zoneinfo import ZoneInfo
from .security import request
from .markets import MARKETS

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
    local = [x for x in CATALOG if x['market'] == market and (query.casefold() in x['name'].casefold() or query.upper() in x['symbol'])]
    if not query:
        return {'items': local, 'source': '内置标的目录', 'warning': None}
    try:
        if config['provider'] == 'custom':
            r = await request('GET', config['provider_base_url'].rstrip('/') + '/search', params={'q': query, 'market': market}, headers=provider_headers(config))
            from .schemas import WatchInput
            remote = [WatchInput.model_validate(x).model_dump(exclude={'threshold'}) for x in r.json()['items']]
        else:
            r = await request('GET', 'https://query1.finance.yahoo.com/v1/finance/search', params={'q': query, 'quotesCount': 15, 'newsCount': 0}, headers={'User-Agent': 'Mozilla/5.0'})
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
    data['change_pct'] = round((data['price'] / data['previous_close'] - 1) * 100, 4)
    data['fetched_at'] = datetime.now(timezone.utc).isoformat()
    data['currency'] = str(data.get('currency', ''))[:10]
    for key in ('history', 'intraday'):
        bars = data.get(key, [])
        if len(bars) > 2000:
            raise ValueError('Too many bars')
        previous = None
        for bar in bars:
            if previous is not None and bar['time'] <= previous:
                raise ValueError('Bars must be unique and chronological')
            previous = bar['time']
            for field in ('open', 'high', 'low', 'close'):
                bar[field] = number(bar[field], positive=True)
            bar['volume'] = number(bar.get('volume', 0))
            if bar['volume'] < 0 or bar['high'] < max(bar['open'], bar['close'], bar['low']) or bar['low'] > min(bar['open'], bar['close']):
                raise ValueError('Invalid OHLCV')
    return data


async def fetch_quote(watch, config):
    if config['provider'] == 'custom':
        r = await request('GET', config['provider_base_url'].rstrip('/') + '/quote', params={'symbol': watch.symbol, 'market': watch.market}, headers=provider_headers(config))
        data = r.json()
        data['source'] = '自定义行情接口'
        return normalize_quote(data)
    base = 'https://query1.finance.yahoo.com/v8/finance/chart/' + urlquote(watch.symbol, safe='')
    intraday = (await request('GET', base, params={'interval': '5m', 'range': '1d', 'includePrePost': 'false'}, headers={'User-Agent': 'Mozilla/5.0'})).json()['chart']['result'][0]
    daily = (await request('GET', base, params={'interval': '1d', 'range': '6mo'}, headers={'User-Agent': 'Mozilla/5.0'})).json()['chart']['result'][0]
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
        'source': 'Yahoo Finance · 实验性非官方接口', 'delay_note': '无实时性或可用性保证；信号要求报价在 5 分钟内',
        'history': bars(daily, True), 'intraday': bars(intraday), 'adjustment': '日线使用上游 adjclose 比例调整 OHLC；原始成交量'})
