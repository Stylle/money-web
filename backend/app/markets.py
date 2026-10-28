from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo
import exchange_calendars as xcals
import pandas as pd

MARKETS = {
    'CN': {'name': 'A 股', 'tz': 'Asia/Shanghai', 'calendar': 'XSHG'},
    'HK': {'name': '港股', 'tz': 'Asia/Hong_Kong', 'calendar': 'XHKG'},
    'US': {'name': '美股', 'tz': 'America/New_York', 'calendar': 'XNYS'},
    'CRYPTO': {'name': '加密货币', 'tz': 'UTC', 'calendar': None},
}


@lru_cache(maxsize=12)
def calendar(market, year):
    # XSHG publishes finite holiday tables; asking for an unpublished next year
    # would incorrectly disable the current year's valid calendar too.
    return xcals.get_calendar(MARKETS[market]['calendar'], start=f'{year-1}-01-01', end=f'{year}-12-31')


def market_state(market, now=None):
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(MARKETS[market]['tz']))
    result = {**MARKETS[market], 'market': market, 'date': local.date().isoformat(), 'is_open': False, 'status': 'closed', 'daily_due': False}
    if market == 'CRYPTO':
        opened = local.replace(hour=0, minute=0, second=0, microsecond=0)
        due = opened + timedelta(minutes=30)
        return {**result, 'is_open': True, 'status': 'open', 'open_at': opened.isoformat(),
                'close_at': (opened+timedelta(days=1)).isoformat(), 'daily_at': due.isoformat(),
                'daily_due': due <= now < due+timedelta(minutes=15)}
    try:
        cal = calendar(market, local.year)
        day = pd.Timestamp(local.date())
        if not cal.is_session(day):
            result['status'] = 'holiday'
            return result
        opened, closed = cal.session_open(day).to_pydatetime(), cal.session_close(day).to_pydatetime()
        due = opened + timedelta(minutes=30)
        minute = pd.Timestamp(now).floor('min')
        result.update(open_at=opened.isoformat(), close_at=closed.isoformat(), daily_at=due.isoformat(),
                      is_open=bool(cal.is_open_on_minute(minute)), daily_due=due <= now < due + timedelta(minutes=15))
        result['status'] = 'open' if result['is_open'] else ('break' if opened <= now < closed else 'closed')
    except Exception:
        result['status'] = 'unknown'
        result['error'] = '交易日历不可用，已暂停定时信号'
    return result


def valid_live_quote(quote, state, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        at = datetime.fromisoformat(quote['as_of'])
        opened = datetime.fromisoformat(state['open_at'])
        return state['is_open'] and quote['price'] > 0 and quote['previous_close'] > 0 and opened <= at <= now + timedelta(seconds=30) and (now - at).total_seconds() <= 300
    except (KeyError, ValueError, TypeError):
        return False


def valid_daily_history(history, market, now=None):
    now = now or datetime.now(timezone.utc)
    if not history:
        return False
    try:
        local = now.astimezone(ZoneInfo(MARKETS[market]['tz']))
        expected = local.date()-timedelta(days=1) if market == 'CRYPTO' else calendar(market, local.year).previous_session(pd.Timestamp(local.date())).date()
        dates = [datetime.fromisoformat(b['time']).astimezone(ZoneInfo(MARKETS[market]['tz'])).date() for b in history]
        return dates[-1] == expected and all(d < local.date() for d in dates)
    except Exception:
        return False
