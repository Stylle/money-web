"""Public title/link adapters. No login, challenge bypass or paid article bodies."""
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from .security import request

CATALOG = [
    {'id':'cointelegraph','name':'Cointelegraph','url':'https://cointelegraph.com/rss','kind':'加密货币 RSS','note':'加密资产公开新闻标题与原文链接；内容观点需自行核验'},
    {'id':'coindesk','name':'CoinDesk','url':'https://www.coindesk.com/arc/outboundfeeds/rss','kind':'加密货币 RSS','note':'官方 RSS，公开标题与原文链接；失败时保留状态并自动退避'},
    {'id':'cls','name':'财联社','url':'https://m.cls.cn/telegraph','kind':'公开电报标题','note':'移动公开页适配；页面变化时会明确报错'},
    {'id':'stcn','name':'证券时报','url':'https://www.stcn.com/','kind':'公开新闻标题','note':'仅索引公开标题和原文链接，不抓取正文'},
    {'id':'jin10','name':'金十数据','url':'https://xnews.jin10.com/','kind':'公开市场参考标题','note':'旧免费快讯引用接口已停止；不包含 VIP、付费快讯或正文'},
    {'id':'wallstreetcn','name':'华尔街见闻','url':'https://wallstreetcn.com/live/global','kind':'公开快讯标题','note':'公开网站接口，非授权 SLA 服务'},
    {'id':'xueqiu','name':'雪球','url':'https://xueqiu.com/','kind':'需授权订阅','note':'当前返回访问验证页，未启用抓取；可配置获授权的 RSS / 标准化适配器'},
    {'id':'tradingview','name':'TradingView · 社区观点','url':'https://www.tradingview.com/feed/','kind':'RSS / 社区观点','note':'用户发布的交易观点，不等于新闻事实，也不是行情 API'},
    {'id':'seekingalpha','name':'Seeking Alpha · 市场快讯','url':'https://seekingalpha.com/market_currents.xml','kind':'官方 RSS','note':'标题和链接；付费分析需到原网站阅读'},
]
BY_ID = {s['id']:s for s in CATALOG}
PUBLIC_HOSTS = {'m.cls.cn','www.cls.cn','www.stcn.com','xnews.jin10.com','api-one.wallstcn.com','www.tradingview.com','seekingalpha.com','www.coindesk.com','cointelegraph.com'}


class AccessRequired(ValueError):
    pass


class PublicHTML(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.current=None;self.scripts=[];self.script=None
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='a':self.current={'href':attrs.get('href',''),'title':attrs.get('title',''),'text':''}
        if tag=='script':self.script={'attrs':attrs,'text':''}
    def handle_data(self, data):
        if self.current is not None:self.current['text']+=data
        if self.script is not None:self.script['text']+=data
    def handle_endtag(self, tag):
        if tag=='a' and self.current is not None:self.links.append(self.current);self.current=None
        if tag=='script' and self.script is not None:self.scripts.append(self.script);self.script=None


def timestamp(value):
    try:
        date=datetime.fromtimestamp(float(value),timezone.utc) if isinstance(value,(float,int)) else datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return date.astimezone(timezone.utc).isoformat() if date.tzinfo else ''
    except (ValueError,TypeError,OverflowError,OSError):return ''


def headline(title, url, source, published=''):
    from .news import clean
    title=clean(title)
    if len(title)<6 or len(title)>300 or urlsplit(url).scheme not in ('http','https'):
        return None
    if any(w in title for w in ('解锁专享','验证码','订阅后查看')):return None
    return {'title':title,'url':url,'source':source,'published':published}


def excerpt(content):
    from .news import clean
    text=clean(content)
    line=re.split(r'[。\n]',text,1)[0].strip()
    return '快讯摘录｜'+line[:100]+('…' if len(line)>100 else '') if len(line)>=6 else ''


def cls_titles(content):
    page=PublicHTML();page.feed(content)
    data=None
    for script in page.scripts:
        if script['attrs'].get('id')=='__NEXT_DATA__':data=json.loads(script['text'])
        marker=re.search(r'(?:window\.)?__NEXT_DATA__\s*=\s*',script['text'])
        if marker:data=json.JSONDecoder().raw_decode(script['text'][marker.end():])[0]
    if not data:raise ValueError('Public page schema changed')
    props=data.get('props',{})
    initial=props.get('initialState') or props.get('pageProps',{}).get('initialState',{})
    items=[]
    for row in initial.get('roll_data',[]):
        if row.get('is_ad') or row.get('type') in ('ad','advertisement'):continue
        # Prefer the publisher's short title; a bracketed heading is also a title.
        title=row.get('title') or ''
        if not title:
            match=re.search(r'【([^】]{6,180})】',row.get('content',''))
            title=match.group(1) if match else excerpt(row.get('content',''))
        if row.get('id') and title:
            item=headline(title,f'https://www.cls.cn/detail/{row["id"]}','财联社',timestamp(row.get('ctime')))
            if item:items.append(item)
    return items[:30]


def web_titles(content, source_id):
    page=PublicHTML();page.feed(content)
    source=BY_ID[source_id]
    expected=r'^https://www\.stcn\.com/article/detail/\d+\.html$' if source_id=='stcn' else r'^https://xnews\.jin10\.com/details/\d+$'
    seen=set();items=[]
    for link in page.links:
        url=urljoin(source['url'],link['href']).split('#')[0]
        if not re.match(expected,url) or url in seen:continue
        text=(link['title'] or link['text']).strip().split('\n')[0].strip()
        text=re.sub(r'\s*(NEW|VIP|原创|精选)\s*$','',text).strip()
        item=headline(text,url,source['name'])
        if item:items.append(item);seen.add(url)
    return items[:25]


def wallstreet_titles(data):
    items=[]
    if data.get('code')!=20000:raise ValueError('Public API error')
    for row in data.get('data',{}).get('items',[]):
        if row.get('is_priced'):continue
        title=row.get('title') or ''
        if not title:
            match=re.search(r'【([^】]{6,180})】',row.get('content_text',''))
            title=match.group(1) if match else excerpt(row.get('content_text',''))
        item=headline(title,row.get('uri') or f'https://wallstreetcn.com/live/{row["id"]}','华尔街见闻',timestamp(row.get('display_time')))
        if item:items.append(item)
    return items[:30]


async def fetch_builtin(source_id):
    from .news import parse_feed
    source=BY_ID[source_id]
    if source_id=='xueqiu':
        raise AccessRequired('雪球当前需要访问验证或获授权接口；未抓取登录/验证后的内容')
    url='https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=30' if source_id=='wallstreetcn' else source['url']
    response=await request('GET',url,headers={'User-Agent':'Mozilla/5.0'},timeout=12)
    if source_id=='cls':items=cls_titles(response.content.decode('utf-8'))
    elif source_id in ('stcn','jin10'):items=web_titles(response.content.decode('utf-8'),source_id)
    elif source_id=='wallstreetcn':items=wallstreet_titles(response.json())
    else:items=parse_feed(response.content,source['name'])
    if not items:raise ValueError('No parseable public headlines; layout or access changed')
    return items
