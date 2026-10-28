"""Probe configured public sources; store health only, never change holdings/watchlist."""
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.db import initialize, utcnow
from app.config import get_config
from app.news_sources import CATALOG, PUBLIC_HOSTS, fetch_builtin, AccessRequired
from app.providers import QUOTE_HOSTS, fetch_quote
from app.security import safe_error


async def main():
    initialize()
    os.environ['TRUSTED_EGRESS_HOSTS']=','.join(sorted(PUBLIC_HOSTS|QUOTE_HOSTS|{'www.federalreserve.gov'}))
    results={'checked_at':utcnow().isoformat(),'news':[],'quotes':[]}
    for source in CATALOG:
        try:
            items=await fetch_builtin(source['id'])
            results['news'].append({'id':source['id'],'items':len(items),'dated':sum(bool(i['published']) for i in items),'status':'ok'})
        except Exception as exc:results['news'].append({'id':source['id'],'status':'blocked' if isinstance(exc,AccessRequired) else 'failed','error':str(exc) if isinstance(exc,AccessRequired) else safe_error(exc)})
    for market,symbol in [('CN','510300.SS'),('HK','0700.HK'),('US','QQQ')]:
        for provider in ['tencent','eastmoney','yahoo']:
            if market!='CN' and provider=='eastmoney':continue
            try:
                config={**get_config(),'provider':provider}
                async with asyncio.timeout(27):q=await fetch_quote(SimpleNamespace(symbol=symbol,market=market),config)
                results['quotes'].append({'market':market,'symbol':symbol,'provider':provider,'status':'ok','as_of':q['as_of'],'history':len(q.get('history',[])),'intraday':len(q.get('intraday',[])),'history_source':q.get('history_source')})
            except Exception as exc:results['quotes'].append({'market':market,'symbol':symbol,'provider':provider,'status':'failed','error':safe_error(exc)})
    from app.crypto import fetch_spot
    from app.markets import market_state, valid_live_quote, valid_daily_history
    for symbol,provider in [('BTC-USDT','binance'),('BTC-USDT','coinbase'),('ETH-USD','coinbase')]:
        try:
            q=await fetch_spot(SimpleNamespace(symbol=symbol,market='CRYPTO'),provider)
            results['quotes'].append({'market':'CRYPTO','symbol':symbol,'provider':provider,'status':'ok','as_of':q['as_of'],'currency':q['currency'],'history':len(q['history']),'intraday':len(q['intraday']),'live':valid_live_quote(q,market_state('CRYPTO')),'daily_history_valid':valid_daily_history(q['history'],'CRYPTO'),'change_basis':q['change_basis']})
        except Exception as exc:results['quotes'].append({'market':'CRYPTO','symbol':symbol,'provider':provider,'status':'failed','error':safe_error(exc)})
    output=Path(__file__).resolve().parents[1]/'docs'/'integration-check.json'
    output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=True,indent=2))


asyncio.run(main())
