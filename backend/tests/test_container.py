import asyncio
import os
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import text
from app.db import Config, Lease, Session, engine, utcnow
from app.container import prepare
from app.worker import run


def test_restart_releases_abandoned_jobs_without_changing_settings():
    with Session.begin() as session:
        session.add(Config(key='preserved', value='original'))
        session.get(Lease, 'worker').until = 9999999999
        session.add(Lease(key='ai', until=9999999999))
    prepare(True)
    with Session() as session:
        assert session.get(Lease, 'worker').until == 0
        assert session.get(Lease, 'ai').until == 0
        assert session.get(Config, 'preserved').value == 'original'


def test_external_database_start_does_not_reset_shared_leases():
    with Session.begin() as session:
        session.get(Lease, 'worker').until = 9999999999
    prepare(False)
    with Session() as session:
        assert session.get(Lease, 'worker').until == 9999999999


@pytest.mark.skipif(os.name != 'posix', reason='Linux container file locking')
def test_same_sqlite_database_cannot_have_two_container_owners():
    from app.container import database_owner, StartupError
    with database_owner():
        with pytest.raises(StartupError, match='sqlite-advisory-lock'):
            with database_owner():
                pytest.fail('A second container took ownership')
    with database_owner():
        pass  # The lock is released on exit.


def test_sqlite_readers_do_not_block_a_worker_write():
    with engine.connect() as reader, engine.connect() as writer:
        assert reader.execute(text('PRAGMA journal_mode')).scalar() == 'wal'
        reader.execute(text('BEGIN'))
        reader.execute(text('SELECT * FROM portfolio')).all()
        writer.execute(text("INSERT INTO config (key,value) VALUES ('concurrent','ok')"))
        writer.commit()
        reader.rollback()
    with Session() as session:
        assert session.get(Config, 'concurrent').value == 'ok'


def test_worker_heartbeat_survives_a_long_running_job_and_cancels_cleanly():
    async def scenario():
        started = asyncio.Event()
        finished = asyncio.Event()

        async def blocked_monitor():
            started.set()
            try:
                await asyncio.Future()
            finally:
                finished.set()

        with patch('app.worker.monitor', blocked_monitor):
            task = asyncio.create_task(run())
            await started.wait()
            with Session() as session:
                assert session.get(Config, 'worker_heartbeat')
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert finished.is_set()
    asyncio.run(scenario())


def test_healthcheck_rejects_stale_worker_even_when_web_is_alive():
    from app.healthcheck import check
    with Session.begin() as session:
        session.add(Config(key='worker_heartbeat', value=(utcnow()-timedelta(minutes=3)).isoformat()))
    with patch('app.healthcheck.urllib.request.build_opener') as opener:
        opener.return_value.open.return_value.__enter__.return_value.status = 200
        with pytest.raises(RuntimeError, match='stale'):
            check()
