import asyncio
import ipaddress
import os
import socket
from urllib.parse import urlsplit
import httpx


async def validate_url(url, resolve=True):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('需要不含账号、密码和片段的 HTTP(S) 地址')
    # Explicit operator override for private, self-hosted API endpoints.
    private_allowed = os.getenv('ALLOW_PRIVATE_ENDPOINTS', 'false').lower() == 'true'
    if parsed.scheme != 'https' and not private_allowed:
        raise ValueError('外部接口必须使用 HTTPS')
    if not resolve:
        return url
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    except OSError as e:
        raise ValueError('接口域名无法解析') from e
    trusted_hosts = {h.strip().lower() for h in os.getenv('TRUSTED_EGRESS_HOSTS', '').split(',') if h.strip()}
    def permitted(address):
        ip = ipaddress.ip_address(address)
        # Some operator-managed DNS proxies return benchmark-range synthetic IPs.
        # Allow only exact, explicitly configured hostnames and this one range.
        fake_ip = ip.version == 4 and ip in ipaddress.ip_network('198.18.0.0/15')
        return ip.is_global or (parsed.hostname.lower() in trusted_hosts and fake_ip)
    if not private_allowed and any(not permitted(a[4][0]) for a in addresses):
        raise ValueError('默认禁止访问私网、环回和保留地址')
    return url


async def request(method, url, **kwargs):
    await validate_url(url)
    # No redirects, no ambient proxy credentials; restrict response sizes.
    # DNS rebinding cannot be completely mitigated by preflight validation;
    # production deployments must also use an egress firewall (see SECURITY.md).
    timeout = kwargs.pop('timeout', 20)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        async with client.stream(method, url, **kwargs) as response:
            response.raise_for_status()
            parts, size = [], 0
            async for part in response.aiter_bytes():
                size += len(part)
                if size > 4 * 1024 * 1024:
                    raise ValueError('接口响应超过 4MB 限制')
                parts.append(part)
            # aiter_bytes already decodes gzip/br. Keeping Content-Encoding here
            # would make httpx decode the buffered body a second time.
            headers = {k: v for k, v in response.headers.items() if k.lower() not in ('content-encoding', 'content-length', 'transfer-encoding')}
            return httpx.Response(response.status_code, headers=headers, content=b''.join(parts), request=response.request)


def safe_error(exc):
    if isinstance(exc, httpx.HTTPStatusError):
        return f'上游接口返回 HTTP {exc.response.status_code}'
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return '上游接口超时'
    if isinstance(exc, httpx.RequestError):
        return '上游网络连接失败'
    if isinstance(exc, ValueError):
        # Do not echo provider response text, URLs or secrets.
        return '接口配置或响应数据无效'
    return '处理失败，请检查配置和服务日志'
