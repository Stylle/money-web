"""Public URLs only; prints no settings or credentials."""
import asyncio
import httpx


async def main():
    urls = [
        'https://query1.finance.yahoo.com/v8/finance/chart/QQQ?interval=5m&range=1d',
        'https://query2.finance.yahoo.com/v8/finance/chart/QQQ?interval=5m&range=1d',
        'https://www.federalreserve.gov/feeds/press_all.xml',
    ]
    async with httpx.AsyncClient(timeout=15,trust_env=False,headers={'User-Agent':'Mozilla/5.0'}) as client:
        for url in urls:
            try:
                response = await client.get(url)
                print(url.split('/')[2], response.status_code, len(response.content))
            except Exception as exc:
                print(url.split('/')[2], type(exc).__name__, str(exc))


asyncio.run(main())
