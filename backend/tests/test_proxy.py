import asyncio
from datetime import datetime, timedelta, timezone
import json
import socketserver
import ssl
import threading
from contextlib import contextmanager

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app import security


@pytest.mark.parametrize('key', ['HTTPS_PROXY', 'https_proxy', 'https-proxy', 'HTTPS-PROXY', 'ALL_PROXY'])
def test_proxy_environment_variants(monkeypatch, key):
    monkeypatch.setenv(key, 'http://proxy.example:7890')
    assert security.proxy_route('https://api.example/').url == 'http://proxy.example:7890'


def test_protocol_selection_and_explicit_empty_override(monkeypatch):
    monkeypatch.setenv('HTTP_PROXY', 'http://http.example:80')
    monkeypatch.setenv('HTTPS_PROXY', 'http://https.example:81')
    monkeypatch.setenv('ALL_PROXY', 'http://fallback.example:82')
    assert security.proxy_route('http://api.example/').url == 'http://http.example:80'
    assert security.proxy_route('https://api.example/').url == 'http://https.example:81'
    monkeypatch.setenv('HTTPS_PROXY', '')
    assert security.proxy_route('https://api.example/').url is None


@pytest.mark.skipif(__import__('os').name == 'nt', reason='Windows environment names are case insensitive')
def test_lowercase_wins_including_empty(monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://upper.example:80')
    monkeypatch.setenv('https_proxy', '')
    assert security.proxy_route('https://api.example/').url is None


@pytest.mark.parametrize(('exclusion', 'target', 'bypass'), [
    ('*', 'https://any.example', True),
    ('example.com', 'https://example.com', True),
    ('.example.com', 'https://api.example.com', True),
    ('*.example.com', 'https://example.com', True),
    ('example.com', 'https://badexample.com', False),
    ('example.com', 'https://example.com.evil.test', False),
    ('example.com:443', 'https://example.com', True),
    ('example.com:8080', 'https://example.com', False),
    ('https://example.com', 'http://example.com', False),
    ('https://example.com', 'https://api.example.com', True),
    ('localhost, 127.0.0.1, ::1', 'http://[::1]:8000', True),
    ('[::1]:8000', 'http://[::1]:8000', True),
    ('[::1]:8000', 'http://[::1]:8001', False),
    ('192.168.0.0/16', 'http://192.168.2.3:3000', True),
    ('192.168.0.0/16', 'http://192.169.2.3', False),
    ('fc00::/7', 'http://[fd00::1]', True),
    ('192.168.0.0/16', 'http://nas.example', False),
    ('EXAMPLE.COM.', 'https://API.Example.Com.', True),
])
def test_no_proxy_boundaries(monkeypatch, exclusion, target, bypass):
    monkeypatch.setenv('ALL_PROXY', 'http://proxy.example:7890')
    monkeypatch.setenv('NO_PROXY', exclusion)
    route = security.proxy_route(target)
    assert route.bypass is bypass
    assert bool(route.url) is not bypass


@pytest.mark.parametrize('proxy', ['socks5://127.0.0.1:7891', '127.0.0.1:7890', 'http://host:bad', 'http://host:0', 'http://user:secret@host/path', 'http://host/#secret'])
def test_invalid_proxy_reports_only_fixed_error(monkeypatch, proxy):
    monkeypatch.setenv('HTTPS_PROXY', proxy)
    with pytest.raises(security.NetworkError) as caught:
        security.proxy_route('https://api.example')
    assert 'secret' not in security.safe_error(caught.value)
    assert proxy not in repr(caught.value)


def test_private_proxy_does_not_allow_private_target(monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:7890')
    monkeypatch.setenv('NO_PROXY', '*')
    with pytest.raises(ValueError, match='默认禁止'):
        asyncio.run(security.request('GET', 'https://127.0.0.1/private'))


def test_summary_and_repr_hide_proxy_credentials(monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://user:supersecret@127.0.0.1:7890')
    summary = security.proxy_summary('https://api.example')
    assert summary['proxy_is_loopback'] is True
    assert summary['mode'] == 'proxy'
    assert 'supersecret' not in json.dumps(summary)+repr(security.proxy_route('https://api.example'))


@pytest.fixture
def tls_contexts(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'api.public.test')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
            .not_valid_after(now+timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('api.public.test')]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_file, key_file = tmp_path/'cert.pem', tmp_path/'key.pem'
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(cert_file, key_file)
    client = ssl.create_default_context(cafile=str(cert_file))
    return server, client


@contextmanager
def local_proxy(tls=None, status=200):
    received = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            first = self.rfile.readline().decode().strip()
            headers = []
            while (line := self.rfile.readline()) not in (b'\r\n', b''):
                headers.append(line.decode().strip())
            received.append((first, headers))
            stream = self.connection
            if first.startswith('CONNECT ') and status == 200:
                stream.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
                try:
                    stream = tls.wrap_socket(stream, server_side=True)
                except ssl.SSLError:
                    return
                data = b''
                while b'\r\n\r\n' not in data:
                    part = stream.recv(4096)
                    if not part:
                        return
                    data += part
                received.append((data.split(b'\r\n')[0].decode(), data.decode().split('\r\n')[1:]))
            body = b'{"via":"local-test-proxy"}'
            stream.sendall(f'HTTP/1.1 {status} Test\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode()+body)
            if stream is not self.connection:
                stream.close()

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    with Server(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_address[1]}', received
        finally:
            server.shutdown()
            thread.join(timeout=3)


def public_dns(monkeypatch):
    # Local DNS preflight is isolated; the target server exists only inside the
    # local test proxy. No public network or user account is contacted.
    async def resolve(*args, **kwargs):
        return [(2, 1, 6, '', ('93.184.216.34', 443))]
    monkeypatch.setattr(security.asyncio, 'to_thread', resolve)


def test_real_http_forward_proxy(monkeypatch):
    public_dns(monkeypatch)
    monkeypatch.setenv('ALLOW_PRIVATE_ENDPOINTS', 'true')
    with local_proxy() as (proxy, received):
        monkeypatch.setenv('HTTP_PROXY', proxy)
        response = asyncio.run(security.request('GET', 'http://api.public.test/news'))
    assert response.json() == {'via': 'local-test-proxy'}
    assert received[0][0] == 'GET http://api.public.test/news HTTP/1.1'


def test_real_https_connect_and_proxy_auth_not_sent_to_target(monkeypatch, tls_contexts):
    public_dns(monkeypatch)
    original = httpx.AsyncClient
    monkeypatch.setattr(security.httpx, 'AsyncClient', lambda **kwargs: original(**kwargs, verify=tls_contexts[1]))
    with local_proxy(tls_contexts[0]) as (proxy, received):
        monkeypatch.setenv('HTTPS_PROXY', proxy.replace('://', '://test-user:test-password@'))
        response = asyncio.run(security.request('GET', 'https://api.public.test/news'))
    assert response.json() == {'via': 'local-test-proxy'}
    assert received[0][0] == 'CONNECT api.public.test:443 HTTP/1.1'
    assert any(header.startswith('Proxy-Authorization:') for header in received[0][1])
    assert received[1][0] == 'GET /news HTTP/1.1'
    assert not any(header.lower().startswith('proxy-authorization:') for header in received[1][1])


def test_proxy_keeps_tls_verification(monkeypatch, tls_contexts):
    public_dns(monkeypatch)
    with local_proxy(tls_contexts[0]) as (proxy, received):
        monkeypatch.setenv('HTTPS_PROXY', proxy)
        with pytest.raises(security.NetworkError):
            asyncio.run(security.request('GET', 'https://api.public.test/news'))
    assert len(received) == 1  # Untrusted TLS never reaches an HTTP request.


@pytest.mark.parametrize('scheme', ['http', 'https'])
def test_real_proxy_407_is_safe_and_never_falls_back(monkeypatch, scheme):
    public_dns(monkeypatch)
    monkeypatch.setenv('ALLOW_PRIVATE_ENDPOINTS', 'true')
    with local_proxy(status=407) as (proxy, received):
        monkeypatch.setenv('ALL_PROXY', proxy)
        with pytest.raises(security.NetworkError) as caught:
            asyncio.run(security.request('GET', scheme+'://api.public.test/', raise_status=False))
    assert len(received) == 1
    assert '407' in security.safe_error(caught.value)


def test_real_no_proxy_bypasses_unreachable_proxy(monkeypatch):
    monkeypatch.setenv('ALLOW_PRIVATE_ENDPOINTS', 'true')
    monkeypatch.setenv('ALL_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('NO_PROXY', '127.0.0.1')
    with local_proxy() as (server, received):
        assert asyncio.run(security.request('GET', server+'/direct')).status_code == 200
    assert received[0][0] == 'GET /direct HTTP/1.1'


def test_healthcheck_always_ignores_proxy(monkeypatch):
    from app import healthcheck
    from app.db import Config, Session, utcnow
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('NO_PROXY', '')
    with Session.begin() as session:
        session.add(Config(key='worker_heartbeat', value=utcnow().isoformat()))
    handlers = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Opener:
        def open(self, url, timeout): return Response()
    def build(handler):
        handlers.append(handler)
        return Opener()
    monkeypatch.setattr(healthcheck.urllib.request, 'build_opener', build)
    healthcheck.check()
    assert handlers[0].proxies == {}


def test_diagnostics_uses_only_fixed_public_probe_and_masks_credentials(monkeypatch):
    from app import networkcheck
    monkeypatch.setenv('HTTPS_PROXY', 'http://secretuser:secretpass@127.0.0.1:7890')
    calls = []
    async def probe(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return httpx.Response(200)
    monkeypatch.setattr(networkcheck, 'request', probe)
    report = asyncio.run(networkcheck.diagnose())
    assert len(calls) == 1 and calls[0][1] == 'https://www.example.com/'
    assert report['routes'][1]['proxy_is_loopback']
    assert 'secret' not in json.dumps(report)
