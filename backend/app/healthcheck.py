"""Probe both the HTTP server and an independently updated worker heartbeat."""
from datetime import datetime, timezone
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import urllib.request


def check():
    from .bootstrap import drop_privileges
    drop_privileges()
    # Local liveness must never depend on an external proxy or NO_PROXY setup.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:8000/api/health', timeout=3) as response:
        assert response.status == 200
    database = os.getenv('DATABASE_URL', 'sqlite:///'+str(Path(os.getenv('DATA_DIR', 'data'))/'invest.db'))
    if database.startswith('sqlite:///'):
        # Keep frequent probes lightweight, including on small ARM machines.
        with closing(sqlite3.connect(database[len('sqlite:///'):], timeout=3)) as connection:
            row = connection.execute("SELECT value FROM config WHERE key='worker_heartbeat'").fetchone()
            value = row[0] if row else None
    else:
        from .db import Config, Session
        with Session() as session:
            row = session.get(Config, 'worker_heartbeat')
            value = row.value if row else None
    if not value or not 0 <= (datetime.now(timezone.utc)-datetime.fromisoformat(value)).total_seconds() < 120:
        raise RuntimeError('Worker heartbeat unavailable or stale')


if __name__ == '__main__':
    check()
