from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from .db import Session, SourceHealth, utcnow


def health(key):
    with Session() as s:
        row = s.get(SourceHealth, key)
        return dict(row.payload) if row else {}


def cooling(key):
    until = health(key).get('retry_after')
    return bool(until and datetime.fromisoformat(until) > utcnow())


def record(key, status, *, error=None, count=None, latency_ms=None, breaker=False):
    # Short, durable status records; never include URLs, payloads or credentials.
    for attempt in range(2):
        try:
            with Session.begin() as s:
                row = s.get(SourceHealth, key)
                data = dict(row.payload) if row else {}
                failures = data.get('consecutive_failures', 0)+1 if status in ('failed','blocked') and breaker else 0
                data.update(status=status, last_attempt=utcnow().isoformat(), last_error=error,
                            consecutive_failures=failures, latency_ms=latency_ms, retry_after=None)
                if status in ('ok','degraded'):
                    data['last_success'] = utcnow().isoformat()
                if count is not None:
                    data['items'] = count
                if breaker and failures >= 2:
                    data['retry_after'] = (utcnow()+timedelta(seconds=min(60*2**min(failures-2,4),900))).isoformat()
                if row:row.payload=data
                else:s.add(SourceHealth(key=key,payload=data))
            return
        except IntegrityError:
            if attempt:raise
