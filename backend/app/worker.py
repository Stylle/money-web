import asyncio
import logging
from .db import initialize
from .services import tick


async def run():
    initialize()
    while True:
        try:
            await tick()
        except Exception as exc:
            # Exception types only: URLs and request headers may contain secrets.
            logging.error('worker_tick_failed: %s', type(exc).__name__)
        await asyncio.sleep(60)


if __name__ == '__main__':
    asyncio.run(run())
