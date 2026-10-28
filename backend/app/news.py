import hashlib
import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit
from defusedxml.ElementTree import fromstring
from .db import Article, Session, Event, utcnow
from .security import request, safe_error


def clean(text):
    return html.unescape(re.sub('<[^>]+>', '', text or '')).strip()[:500]


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
    if not lease('news', 1800):
        return {'status': 'cached', 'added': 0}
    added, failures = 0, []
    for feed in config['feeds']:
        try:
            response = await request('GET', feed['url'], headers={'User-Agent': 'InvestWatch/0.1 RSS Reader'})
            items = parse_feed(response.content, feed['name'])
            with Session.begin() as s:
                for item in items:
                    if not s.get(Article, item['id']):
                        item['tags'] = [k for k in config['keywords'] if k.casefold() in item['title'].casefold()]
                        s.add(Article(**item))
                        added += 1
        except Exception as exc:
            failures.append({'source': feed['name'], 'error': safe_error(exc)})
    with Session.begin() as s:
        s.add(Event(id=hashlib.sha256(('news'+utcnow().isoformat()).encode()).hexdigest(), kind='data', title='资讯源刷新完成', payload={'added': added, 'failures': failures}))
    # Hold the lease until its expiry to avoid repeated RSS polling.
    return {'status': 'ok' if not failures else 'partial', 'added': added, 'failures': failures}
