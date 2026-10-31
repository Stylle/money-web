"""Linux container entry point: own, monitor and reap both application processes."""
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from contextlib import contextmanager


class StartupError(RuntimeError):
    pass


@contextmanager
def startup_step(stage):
    try:
        yield
    except StartupError:
        raise
    except Exception as exc:
        logging.error('container_start_failed: stage=%s error=%s errno=%s uid=%s gid=%s',
                      stage, type(exc).__name__, getattr(exc, 'errno', None),
                      getattr(os, 'getuid', lambda: 'unknown')(),
                      getattr(os, 'getgid', lambda: 'unknown')())
        raise StartupError(stage) from None


@contextmanager
def database_owner():
    with startup_step('data-directory-and-database-configuration'):
        from .db import engine
    if engine.dialect.name != 'sqlite':
        yield False
        return
    import fcntl
    database = engine.url.database
    if not database or database == ':memory:':
        raise RuntimeError('Container requires a persistent SQLite file')
    with startup_step('sqlite-lock-file'):
        lock = Path(database + '.lock').open('a')
    with lock:
        with startup_step('sqlite-advisory-lock'):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield True


def prepare(reset_leases):
    from sqlalchemy import update
    from .db import initialize, Session, Lease
    from .config import cipher
    with startup_step('database-initialization'):
        initialize()
    with startup_step('encryption-key'):
        cipher()
    if reset_leases:
        with Session.begin() as session:
            session.execute(update(Lease).values(until=0))


def supervise(commands, *, grace=8):
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    result = 1
    state = Path('/tmp/money-web-runtime.json')
    try:
        for name, command in commands.items():
            children.append((name, subprocess.Popen(command, start_new_session=True)))
        with startup_step('runtime-state-in-tmp'):
            state.write_text(json.dumps({name: child.pid for name, child in children}))
        while not stopping:
            if any(child.poll() is not None for _, child in children):
                logging.error('Application process exited; restarting container')
                break
            time.sleep(0.2)
        else:
            result = 0
    finally:
        for _, child in children:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + grace
        for _, child in children:
            try:
                child.wait(timeout=max(0, deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        state.unlink(missing_ok=True)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return result


def main():
    try:
        with database_owner() as owned:
            prepare(owned)
            return supervise({
                'web': [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0',
                        '--port', '8000', '--no-access-log', '--timeout-graceful-shutdown', '6'],
                'worker': [sys.executable, '-m', 'app.worker'],
            })
    except StartupError:
        return 1
    except Exception as exc:
        logging.error('container_start_failed: %s', type(exc).__name__)
        return 1


if __name__ == '__main__':
    sys.exit(main())
