import asyncio
import ipaddress
import os
import socket
from dataclasses import dataclass, field
from urllib.parse import urlsplit
import httpx


class WebhookError(ValueError):
    """Only fixed, locally authored user-facing diagnostics may be passed here."""


class NetworkError(ValueError):
    """Fixed local diagnostics only; never include proxy URLs or credentials."""


@dataclass(frozen=True)
class ProxyRoute:
    source: str = ''
    url: str | None = field(default=None, repr=False)
    bypass: bool = False


def _proxy_env(name):
    # Lowercase takes precedence, including an explicitly empty value. Hyphen
    # aliases accommodate NAS UIs; underscore names remain the documented form.
    for key in (name.lower(), name, name.lower().replace('_', '-'), name.replace('_', '-')):
        if key in os.environ:
            return key, os.environ[key].strip()
    return '', ''


def _no_proxy(url, value):
    target = urlsplit(url)
    host = target.hostname.rstrip('.').encode('idna').decode().lower()
    port = target.port or (443 if target.scheme == 'https' else 80)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    for entry in value.split(','):
        entry = entry.strip()
        if not entry:
            continue
        if entry == '*':
            return True
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            network = None
        if network is not None:
            if address is not None and address in network:
                return True
            continue
        try:
            pattern = urlsplit(entry if '://' in entry else '//'+entry)
            pattern_port = pattern.port
            domain = (pattern.hostname or '').removeprefix('*.').lstrip('.').rstrip('.').encode('idna').decode().lower()
            if not domain or '*' in domain or pattern.username or pattern.password or pattern.path not in ('', '/') or pattern.query or pattern.fragment:
                raise ValueError
        except (ValueError, UnicodeError):
            raise NetworkError('NO_PROXY 配置无效；请使用逗号分隔的域名、IP 或 IP 网段') from None
        if pattern.scheme and pattern.scheme != target.scheme:
            continue
        if pattern_port is not None and pattern_port != port:
            continue
        if host == domain or (address is None and host.endswith('.'+domain)):
            return True
    return False


def proxy_route(url):
    """Select only operator-configured proxies, without ambient OS settings."""
    _, exclusions = _proxy_env('NO_PROXY')
    if _no_proxy(url, exclusions):
        return ProxyRoute(bypass=True)
    name = 'HTTPS_PROXY' if urlsplit(url).scheme == 'https' else 'HTTP_PROXY'
    source, proxy = _proxy_env(name)
    if not source:
        source, proxy = _proxy_env('ALL_PROXY')
    if not proxy:
        return ProxyRoute()
    try:
        parsed = urlsplit(proxy)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.fragment or parsed.query or parsed.path not in ('', '/'):
            raise ValueError
        if parsed.port is not None and parsed.port == 0:
            raise ValueError
        httpx.Proxy(proxy)  # Validate credentials/host syntax without connecting.
    except (ValueError, httpx.InvalidURL):
        raise NetworkError('代理配置无效；请填写完整 http://主机:端口，使用 HTTP 或 Mixed 代理端口') from None
    return ProxyRoute(source, proxy)


def proxy_summary(url):
    """Safe diagnostics: deliberately omit the address and account information."""
    route = proxy_route(url)
    result = {'mode': 'proxy' if route.url else 'direct', 'environment': route.source, 'no_proxy_match': route.bypass}
    if route.url:
        host = urlsplit(route.url).hostname
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host.lower().rstrip('.') == 'localhost'
        result['proxy_is_loopback'] = loopback
    return result


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
    route = proxy_route(url)
    # Explicit env proxy routing only; retain certificate verification, URL
    # checks and size limits. Never fall back to direct on a proxy failure.
    # DNS rebinding cannot be completely mitigated by preflight validation;
    # production deployments must also use an egress firewall (see SECURITY.md).
    timeout = kwargs.pop('timeout', 20)
    raise_status = kwargs.pop('raise_status', True)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False, proxy=route.url) as client:
            async with client.stream(method, url, **kwargs) as response:
                if response.status_code == 407 and route.url:
                    raise NetworkError('代理认证失败（HTTP 407）；请检查代理账号和密码')
                if raise_status:
                    response.raise_for_status()
                parts, size = [], 0
                async for part in response.aiter_bytes():
                    size += len(part)
                    if size > 4 * 1024 * 1024:
                        raise ValueError('接口响应超过 4MB 限制')
                    parts.append(part)
                # aiter_bytes already decodes gzip/br. Keeping Content-Encoding
                # would make httpx decode the buffered body a second time.
                headers = {k: v for k, v in response.headers.items() if k.lower() not in ('content-encoding', 'content-length', 'transfer-encoding')}
                return httpx.Response(response.status_code, headers=headers, content=b''.join(parts), request=response.request)
    except httpx.ProxyError as exc:
        # CONNECT failures expose the status in the exception rather than an
        # HTTP response. Classify only; never return the remote reason phrase.
        if str(exc).startswith('407 '):
            raise NetworkError('代理认证失败（HTTP 407）；请检查代理账号和密码') from None
        raise NetworkError('代理握手失败；请检查 HTTP/Mixed 端口、认证及代理的目标访问规则') from None
    except httpx.TimeoutException:
        if route.url:
            raise NetworkError('经代理请求超时；请检查代理连通性及目标访问规则') from None
        raise
    except httpx.RequestError:
        if route.url:
            raise NetworkError('经代理连接失败；请检查地址、端口和允许局域网访问；容器的 127.0.0.1 指向自身') from None
        raise


def safe_error(exc):
    if isinstance(exc, (WebhookError, NetworkError)):
        return str(exc)
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
