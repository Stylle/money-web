"""Probe both the HTTP server and an independently updated worker heartbeat."""
from datetime import datetime
import urllib.request


def check():
    with urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3) as response:
        assert response.status == 200
    from .db import Config, Session, utcnow
    with Session() as session:
        row = session.get(Config, 'worker_heartbeat')
        if not row or not 0 <= (utcnow()-datetime.fromisoformat(row.value)).total_seconds() < 120:
            raise RuntimeError('Worker heartbeat unavailable or stale')


if __name__ == '__main__':
    check()
