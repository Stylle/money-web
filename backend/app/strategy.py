from datetime import datetime, timezone
from copy import deepcopy
from .markets import market_state, valid_live_quote, valid_daily_history


def ema(values, period):
    alpha, result = 2 / (period + 1), [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def analyze_all(watches, portfolio, enabled, now=None):
    """Share the existing cash budget; proposed sales never finance proposed buys."""
    remaining = deepcopy(portfolio)
    results = {}
    for watch in sorted(watches, key=lambda w: w.id):
        result = analyze(watch, remaining, enabled, now)
        if result['delta'] > 0:
            remaining['cash'] = round(float(remaining['cash'])-result['delta'], 2)
            result['constraints'].append('同批建议共用现有现金预算，按标的代码顺序分配；未执行的减仓不计入可用现金')
        results[watch.id] = result
    return results


def indicators(history):
    if len(history) < 65:
        return None
    closes = [b['close'] for b in history]
    gains, losses = [], []
    for a, b in zip(closes, closes[1:]):
        gains.append(max(b-a, 0))
        losses.append(max(a-b, 0))
    gain, loss = sum(gains[:14])/14, sum(losses[:14])/14
    for g, l in zip(gains[14:], losses[14:]):
        gain, loss = (gain*13+g)/14, (loss*13+l)/14
    rsi = 50 if gain == loss == 0 else (100 if loss == 0 else 100-100/(1+gain/loss))
    macd = [a-b for a, b in zip(ema(closes, 12), ema(closes, 26))]
    signal = ema(macd, 9)
    tr = [max(b['high']-b['low'], abs(b['high']-a['close']), abs(b['low']-a['close'])) for a, b in zip(history, history[1:])]
    atr = sum(tr[:14])/14
    for value in tr[14:]:
        atr = (atr*13+value)/14
    volumes = [b['volume'] for b in history]
    avg_volume = sum(volumes[-21:-1])/20
    ma20, ma60 = sum(closes[-20:])/20, sum(closes[-60:])/60
    return {'ma20': round(ma20, 4), 'ma60': round(ma60, 4), 'rsi': round(rsi, 2), 'macd': round(macd[-1], 4),
            'macd_signal': round(signal[-1], 4), 'atr': round(atr, 4), 'last_close': closes[-1],
            'volume_ratio': round(volumes[-1]/avg_volume, 2) if avg_volume else None,
            'trend_up': closes[-1] > ma20 > ma60 and ma20 > sum(closes[-25:-5])/20,
            'trend_down': closes[-1] < ma20 < ma60, 'bar_at': history[-1]['time']}


def analyze(watch, portfolio, enabled, now=None):
    now = now or datetime.now(timezone.utc)
    q = watch.quote or {}
    metrics = indicators(q.get('history', []))
    position = next((p for p in portfolio['positions'] if p['watch_id'] == watch.id), None)
    held = float(position['shares']) if position else 0
    result = {'watch_id': watch.id, 'symbol': watch.symbol, 'name': watch.name, 'action': 'observe', 'action_label': '继续观察',
              'delta': 0, 'held': held, 'reasons': [], 'metrics': metrics, 'rule_version': 'rules-v1', 'quote_at': q.get('as_of'),
              'portfolio_updated_at': portfolio['updated_at'], 'generated_at': now.isoformat(), 'constraints': []}
    if not enabled:
        result['reasons'] = ['程序建议未启用，当前仅展示行情与风险事件']
        return result
    if watch.error or not valid_live_quote(q, market_state(watch.market, now), now):
        result['reasons'] = ['当前不在有效交易时段，或报价超过 5 分钟，暂停操作建议']
        return result
    if not metrics or not valid_daily_history(q.get('history', []), watch.market, now):
        result['reasons'] = ['至少需要 65 根完整日 K 线且覆盖上一交易日，当前数据不足或过期']
        return result
    # Never treat correlated RSI and MACD as independent votes.
    m = metrics
    bullish = m['trend_up'] and 40 <= m['rsi'] <= 65 and m['macd'] > m['macd_signal'] and m['volume_ratio'] is not None and m['volume_ratio'] >= 1.2
    bearish = m['trend_down'] and m['macd'] < m['macd_signal']
    step = float(portfolio['max_step'])
    target = float(position['target']) if position and position.get('target') is not None else None
    if bearish and held:
        result.update(action='reduce', action_label='考虑减仓', delta=-round(min(step, held), 2))
        result['reasons'] = ['完整日线收盘价低于 MA20 与 MA60，趋势走弱', 'MACD 低于信号线，动量未恢复']
    elif bullish and position:
        capacity = max(0, min(float(position['cap'])-held, float(portfolio['cash'])-float(portfolio['min_cash']), target-held if target is not None else 100))
        if portfolio['risk'] == 'conservative':
            step = min(step, 0.5)
        delta = round(min(step, capacity), 2)
        result['reasons'] = ['MA20 高于 MA60 且向上，完整日线趋势偏强', '动量与历史成交量满足确认条件']
        if delta > 0:
            result.update(action='add', action_label='考虑加仓', delta=delta)
        else:
            result['constraints'].append('受目标仓位、仓位上限或最低现金限制，本次不加仓')
    else:
        result['reasons'] = ['多维条件未同时满足，暂不调整']
        if bullish and not position:
            result['constraints'].append('未配置该标的的仓位上限；请先在持仓中添加 0 份仓位')
    result['cash_after'] = round(float(portfolio['cash'])-result['delta'], 2)
    result['held_after'] = round(held+result['delta'], 2)
    result['constraints'].append('比例是手动快照，不包含价格变化造成的实际仓位漂移')
    if portfolio.get('horizon') == 'long' and result['delta']:
        result['constraints'].append('长期持有模式：本提示仅供复核，不代表需要频繁调仓')
    return result
