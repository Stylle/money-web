"""Real network capability probe. No prices are inserted into the application DB."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.providers import fetch_quote, search_symbols
from app.config import DEFAULTS
from app.news import parse_feed
from app.security import request, safe_error
from app.markets import market_state
from app.db import utcnow


async def main():
    config = dict(DEFAULTS)
    result = {'checked_at': utcnow().isoformat(), 'quotes': [], 'feeds': [], 'search': [], 'calendars': []}
    for market, symbol in [('CN','510300.SS'),('HK','0700.HK'),('US','QQQ')]:
        try:
            quote = await asyncio.wait_for(fetch_quote(SimpleNamespace(symbol=symbol,market=market), config),35)
            result['quotes'].append({'market':market,'symbol':symbol,'status':'ok','as_of':quote['as_of'],'history_bars':len(quote['history']),'intraday_bars':len(quote['intraday'])})
        except Exception as exc:
            result['quotes'].append({'market':market,'symbol':symbol,'status':'failed','error':safe_error(exc)})
        result['calendars'].append(market_state(market))
        search = await search_symbols(symbol,market,config)
        result['search'].append({'market':market,'items':len(search['items']),'source':search['source'],'warning':search['warning']})
    for feed in config['feeds']:
        try:
            response = await request('GET',feed['url'])
            articles = parse_feed(response.content,feed['name'])
            result['feeds'].append({'name':feed['name'],'status':'ok','items':len(articles)})
        except Exception as exc:
            result['feeds'].append({'name':feed['name'],'status':'failed','error':safe_error(exc)})
    output = Path(__file__).resolve().parents[1] / 'docs' / 'source-probe.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))


asyncio.run(main())
