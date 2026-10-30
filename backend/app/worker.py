import asyncio
import logging
import signal
from .db import Config, Session, initialize, utcnow
from .services import tick


async def monitor():
    while True:
        try:
            await tick()
        except Exception as exc:
            # Exception types only: URLs and request headers may contain secrets.
            logging.error('worker_tick_failed: %s', type(exc).__name__)
        await asyncio.sleep(60)


async def heartbeat():
    while True:
        with Session.begin() as session:
            row = session.get(Config, 'worker_heartbeat')
            if row:
                row.value = utcnow().isoformat()
            else:
                session.add(Config(key='worker_heartbeat', value=utcnow().isoformat()))
        await asyncio.sleep(30)


async def run():
    initialize()
    loop = asyncio.get_running_loop()
    current = asyncio.current_task()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, current.cancel)
        except NotImplementedError:
            pass  # Windows local development uses the default signal behavior.
    tasks = [asyncio.create_task(heartbeat()), asyncio.create_task(monitor())]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == '__main__':
    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass
