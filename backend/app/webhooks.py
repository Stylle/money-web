"""Webhook request templates and MagicPush's documented push protocol."""
import hashlib
import hmac
import json
import re
import time
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from .security import request, WebhookError

VARIABLE = re.compile(r'\{\{([a-zA-Z0-9_]+)\}\}')
BLOCKED_HEADERS = {'host', 'content-length', 'transfer-encoding', 'connection', 'proxy-authorization',
                   'proxy-connection', 'upgrade', 'te', 'trailer', 'keep-alive', 'idempotency-key',
                   'x-investwatch-timestamp', 'x-investwatch-signature'}
MAGICPUSH_ERRORS = {
    '缺少接口令牌': 'MagicPush 缺少接口令牌，请填写完整推送地址或 Authorization 请求头',
    '无效的接口令牌': 'MagicPush 接口令牌无效，请核对接口管理中的推送令牌',
    '接口已禁用': 'MagicPush 接口已禁用，请在接口管理中启用',
    '该接口未绑定任何渠道': 'MagicPush 接口未绑定渠道，请先绑定并测试通知渠道',
    '部分推送失败': 'MagicPush 下游渠道投递失败，请查看 MagicPush 的推送记录',
    '推送失败': 'MagicPush 下游渠道投递失败，请查看 MagicPush 的推送记录',
    '消息内容不能为空': 'MagicPush 缺少 content 正文，请选择 MagicPush 格式或修改模板',
    '内容不能为空': 'MagicPush 缺少 content 正文，请选择 MagicPush 格式或修改模板',
    '未包含合法内容': 'MagicPush 白名单过滤未通过，请检查接口关键词过滤规则',
    '包含不合法内容': 'MagicPush 黑名单过滤未通过，请检查接口关键词过滤规则',
}


def magicpush_url(url):
    return bool(re.search(r'/api/push(?:/[^/]+|/by-(?:endpoint|channel)/[0-9]+)?/?$', urlsplit(url).path))


def notification_text(payload):
    lines = [str(payload.get('title', '观澜通知'))]
    stamp = payload.get('timestamp', '')
    if stamp:
        try:
            at = datetime.fromisoformat(stamp)
            if at.tzinfo is not None:
                stamp = at.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S 北京时间')
        except (ValueError, TypeError):
            pass
        lines.append('时间：'+str(stamp))
    data = payload.get('data') or {}
    if not isinstance(data, dict):
        lines.append(json.dumps(data, ensure_ascii=False))
        return '\n'.join(lines)
    if data.get('message'):
        lines.append(str(data['message']))
    if 'cash' in data:
        lines.append('现金 '+str(data['cash'])+' 份（总资金 100 份）；持仓为手动快照')
    def item_text(item):
        parts = [str(item.get('name') or item.get('watch_id') or '')]
        if item.get('market_name'):
            parts.append(str(item['market_name']))
        if item.get('market_status'):
            parts.append({'open': '交易中', 'closed': '非交易时段', 'holiday': '休市', 'break': '午间休市', 'unknown': '交易日历待确认'}.get(item['market_status'], '交易状态待确认'))
        if item.get('price') is not None:
            parts.append('价格 '+str(item['price'])+(' '+str(item['currency']) if item.get('currency') else ''))
        else:
            parts.append('暂无可用报价')
        if item.get('change_pct') is not None:
            parts.append('涨跌幅 '+str(item['change_pct'])+'%')
        if item.get('data_valid') is False:
            parts.append('数据不可用或过期，仅供查看')
        if 'quote_at' in item:
            parts.append('报价时间 '+str(item.get('quote_at') or '未知'))
        if item.get('source'):
            parts.append('来源 '+str(item['source']))
        if item.get('error'):
            parts.append(str(item['error']))
        signal = item.get('signal') or {}
        if isinstance(signal, dict):
            if 'held' in signal:
                parts.append('持仓 '+str(signal['held'])+' 份')
            if signal.get('action_label'):
                parts.append(str(signal['action_label']))
            if signal.get('delta'):
                parts.append('调整 '+str(signal['delta'])+' 份（总资金 100 份）')
            for key in ('reasons', 'constraints'):
                if isinstance(signal.get(key), list):
                    parts.extend(str(reason) for reason in signal[key])
        return '；'.join(part for part in parts if part)
    if payload.get('type') == 'alert':
        lines.append(item_text(data))
    for item in data.get('items', []):
        if isinstance(item, dict):
            lines.append(item_text(item))
    if data.get('report'):
        lines.append('分析：'+json.dumps(data['report'], ensure_ascii=False))
    for article in data.get('news', []):
        if isinstance(article, dict):
            lines.append('资讯：'+str(article.get('title', ''))+' '+str(article.get('url', '')))
    if len(lines) <= (2 if stamp else 1) and data:
        lines.append(json.dumps(data, ensure_ascii=False))
    return '\n'.join(lines)


def template_context(payload):
    text = notification_text(payload)
    return {'title': payload.get('title', ''), 'text': text, 'content': text, 'message': text,
            'id': payload.get('id', ''), 'event': payload.get('type', ''), 'type': payload.get('type', ''),
            'timestamp': payload.get('timestamp', ''), 'time': payload.get('timestamp', ''),
            'fields': payload.get('data', {}), 'data': payload.get('data', {}), 'payload': payload}


def render_template(template, context, json_body=True):
    # Interpolate values only: no expressions, eval, network, or recursive substitution.
    out, quoted, escaped, at = [], False, False, 0
    while at < len(template):
        match = VARIABLE.match(template, at)
        if match:
            if json_body and quoted and escaped:
                raise WebhookError('JSON 模板变量前不能放置反斜杠，请直接使用占位符')
            if match[1] not in context:
                raise WebhookError('Webhook 模板包含不支持的变量，请查看变量说明')
            value = context[match[1]]
            string = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
            out.append(json.dumps(string, ensure_ascii=False)[1:-1] if json_body and quoted
                       else json.dumps(value, ensure_ascii=False, allow_nan=False) if json_body else string)
            at = match.end()
            continue
        char = template[at]
        out.append(char)
        if escaped:
            escaped = False
        elif quoted and char == '\\':
            escaped = True
        elif char == '"':
            quoted = not quoted
        at += 1
    rendered = ''.join(out)
    if json_body:
        try:
            result = json.loads(rendered)
            json.dumps(result, allow_nan=False)
            return result
        except (ValueError, TypeError):
            raise WebhookError('Webhook 正文模板不是合法 JSON，请检查引号和变量位置') from None
    return rendered


def custom_headers(raw):
    if not raw:
        return {}
    try:
        values = json.loads(raw)
        if not isinstance(values, dict) or len(values) > 30:
            raise ValueError()
        seen = set()
        for key, value in values.items():
            if not re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", key) or not isinstance(value, str):
                raise ValueError()
            if key.lower() in BLOCKED_HEADERS or key.lower() in seen:
                raise ValueError()
            if any(char in value for char in ('\r', '\n', '\0')):
                raise ValueError()
            value.encode('ascii')
            seen.add(key.lower())
        return values
    except (ValueError, TypeError, UnicodeError):
        raise WebhookError('自定义请求头需为 JSON 字符串对象；禁止换行、重复名称及传输/签名/去重请求头') from None


def request_body(config, payload):
    mode = config.get('webhook_format', 'auto')
    if mode == 'auto':
        mode = 'magicpush' if magicpush_url(config['webhook_url']) else 'raw'
    if mode == 'magicpush':
        return {'title': payload['title'], 'content': notification_text(payload), 'type': 'text'}, True, mode
    if mode == 'custom':
        json_body = config.get('webhook_body_type', 'json') == 'json'
        template = config.get('webhook_body_tpl', '')
        if template:
            return render_template(template, template_context(payload), json_body), json_body, mode
        return (payload if json_body else notification_text(payload)), json_body, mode
    return payload, True, mode


def validate_config(config):
    custom_headers(config.get('webhook_headers', ''))
    body, is_json, mode = request_body(config, {'id': 'validation', 'title': '模板校验',
        'type': 'test', 'timestamp': '2026-01-01T00:00:00+00:00', 'data': {'message': '模板校验'}})
    if mode == 'magicpush' and config.get('webhook_method', 'POST') == 'PUT':
        raise WebhookError('MagicPush 标准推送接口使用 POST 或 GET，请修改请求方法')
    if config.get('webhook_method', 'POST') == 'GET' and (not is_json or not isinstance(body, dict)):
        raise WebhookError('GET 推送需要 JSON 对象，字段将编码到查询参数；纯文本请用 POST/PUT')


async def send_webhook(config, payload):
    body, is_json, mode = request_body(config, payload)
    method = config.get('webhook_method', 'POST')
    raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode() if is_json else body.encode()
    url = config['webhook_url']
    if method == 'GET':
        if not is_json or not isinstance(body, dict):
            raise WebhookError('GET 推送需要 JSON 对象作为查询参数')
        params = {key: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False) for key, value in body.items()}
        url = str(httpx.URL(url).copy_merge_params(params))
        raw = b''
    headers = httpx.Headers(custom_headers(config.get('webhook_headers', '')))
    if 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/json' if is_json else 'text/plain; charset=utf-8'
    headers['Idempotency-Key'] = payload['id']
    stamp = str(int(time.time()))
    headers['X-InvestWatch-Timestamp'] = stamp
    if config.get('webhook_secret'):
        headers['X-InvestWatch-Signature'] = 'sha256='+hmac.new(config['webhook_secret'].encode(), stamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
    if config.get('webhook_authorization'):
        headers['Authorization'] = config['webhook_authorization']
    response = await request(method, url, content=raw if method != 'GET' else None,
                             headers=headers, raise_status=False, timeout=12)
    result = None
    try:
        result = response.json()
    except ValueError:
        pass
    if mode == 'magicpush':
        if isinstance(result, dict):
            # Match known messages to fixed diagnostics; never expose response text, URLs or keys.
            known = MAGICPUSH_ERRORS.get(result.get('message')) if isinstance(result.get('message'), str) else None
            if known and (response.status_code >= 300 or result.get('success') is not True):
                raise WebhookError(known)
            data = result.get('data')
            if response.is_success and result.get('success') is True and not (
                    isinstance(data, dict) and (data.get('success') is False or data.get('failedCount', 0))):
                return
        if not response.is_success:
            raise WebhookError(f'MagicPush 返回 HTTP {response.status_code}；请核对推送令牌、接口及下游渠道记录')
        raise WebhookError('MagicPush 未确认完整投递成功，请查看 MagicPush 推送记录')
    if not response.is_success:
        raise WebhookError(f'Webhook 返回 HTTP {response.status_code}；请检查请求方法、正文模板和鉴权配置')
    if isinstance(result, dict) and result.get('success') is False:
        raise WebhookError('接收端返回投递失败，请查看接收端记录；HTTP 2xx 不代表下游发送成功')
