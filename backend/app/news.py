import hashlib
import asyncio
import html
import re
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit
from defusedxml.ElementTree import fromstring
from .db import Article, Session, Event, utcnow
from .security import request, safe_error

ROUND_TIMEOUT = 65


def clean(text):
    return html.unescape(re.sub('<[^>]+>', '', text or '')).strip()[:500]


def identify(item):
    fingerprint = re.sub(r'[^\w\u4e00-\u9fff]', '', item['title'].casefold())
    day = item['published'][:10] if item['published'] else 'undated:'+item['url']
    return hashlib.sha256((fingerprint+day).encode()).hexdigest()


def parse_feed(content, source):
    root = fromstring(content)
    nodes = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
    articles = []
    for node in nodes[:100]:
        def text(name):
            found = node.find(name)
            if found is None:
                found = node.find('{http://www.w3.org/2005/Atom}' + name)
            return (found.text or found.get('href', '')) if found is not None else ''
        title, url = clean(text('title')), text('link').strip()
        parsed = urlsplit(url)
        if not title or parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            continue
        url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))
        raw_date = text('pubDate') or text('published') or text('updated')
        try:
            at = parsedate_to_datetime(raw_date) if ',' in raw_date else datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
            if at.tzinfo is None:
                raise ValueError('Missing timezone')
            published = at.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            published = ''  # Unknown publication time cannot become AI evidence.
        # Identical headlines across feeds are one event, with original source preserved.
        fingerprint = re.sub(r'[^\w\u4e00-\u9fff]', '', title.casefold())
        day = published[:10] if published else utcnow().date().isoformat()
        articles.append({'id': hashlib.sha256((fingerprint+day).encode()).hexdigest(), 'title': title, 'url': url,
                         'source': source, 'published': published})
    return articles


async def refresh_news(config):
    from .services import lease, release
    from .news_sources import BY_ID, AccessRequired, fetch_builtin
    from .source_health import health, cooling, record
    if not lease('news', 120):
        return {'status': 'cached', 'added': 0}
    added, failures, checked = 0, [], []
    sem=asyncio.Semaphore(4)
    sources=[{'id':sid,'name':BY_ID[sid]['name'],'builtin':True,'interval':600 if sid in ('tradingview','seekingalpha') else 300} for sid in config.get('news_sources',[]) if sid in BY_ID]
    sources += [{**f,'id':'rss-'+hashlib.sha256(f['url'].encode()).hexdigest()[:16],'builtin':False,'interval':1800} for f in config['feeds']]
    async def one(source):
        nonlocal added
        key='news:'+source['id']
        previous=health(key)
        if cooling(key):return
        if previous.get('last_attempt') and utcnow()-datetime.fromisoformat(previous['last_attempt']) < timedelta(seconds=source['interval']):return
        async with sem:
            started=time.monotonic()
            try:
                async with asyncio.timeout(18):
                    if source['builtin']:items=await fetch_builtin(source['id'])
                    else:
                        response=await request('GET',source['url'],headers={'User-Agent':'InvestWatch/0.1 RSS Reader'},timeout=12)
                        items=parse_feed(response.content,source['name'])
                        if not items:raise ValueError('No RSS or Atom items found')
                with Session.begin() as s:
                    for item in items:
                        item['title']=clean(item['title'])
                        item['id']=identify(item)
                        if not s.get(Article,item['id']):
                            item['tags']=[k for k in config['keywords'] if k.casefold() in item['title'].casefold()]
                            s.add(Article(**item));added+=1
                record(key,'ok',count=len(items),latency_ms=round((time.monotonic()-started)*1000))
                checked.append({'source':source['name'],'items':len(items)})
            except Exception as exc:
                error=str(exc) if isinstance(exc,AccessRequired) else safe_error(exc)
                record(key,'blocked' if isinstance(exc,AccessRequired) else 'failed',error=error,breaker=True)
                failures.append({'source':source['name'],'error':error})
    try:
        try:
            async with asyncio.timeout(ROUND_TIMEOUT):
                await asyncio.gather(*(one(source) for source in sources))
        except TimeoutError:
            failures.append({'source':'本轮未完成来源','error':'达到本轮资讯刷新时限，已保留成功结果，下一轮自动重试'})
        if checked or failures:
            with Session.begin() as s:
                s.add(Event(id=hashlib.sha256(('news'+utcnow().isoformat()).encode()).hexdigest(),kind='data',title='资讯源刷新完成',payload={'added':added,'sources':checked,'failures':failures}))
        return {'status':('partial' if failures else 'ok') if checked or failures else 'cached','added':added,'sources':checked,'failures':failures}
    finally:
        release('news',15)
