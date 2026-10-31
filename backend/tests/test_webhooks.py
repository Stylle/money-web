import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
from app.config import get_config, save_config
from app.security import WebhookError, safe_error
from app.webhooks import send_webhook, render_template, template_context, validate_config

PAYLOAD = {'id': 'event-1', 'type': 'alert', 'title': '观澜 "风险" 提醒\n第二行',
           'timestamp': '2026-10-31T01:30:00+00:00',
           'data': {'watch_id': 'US:TEST', 'price': 95, 'change_pct': -5,
                    'signal': {'action_label': '考虑减仓', 'delta': -1,
                               'constraints': ['持仓是手动快照']}}}


def response(status=200, body=None):
    return httpx.Response(status, json=body, request=httpx.Request('POST', 'https://example.com'))


def test_existing_magicpush_url_auto_uses_required_fields_and_text_type(monkeypatch):
    cfg = {**get_config(), 'webhook_url': 'https://push.example.com/api/push/test-token'}
    sent = []
    async def receiver(method, url, **kwargs):
        body = json.loads(kwargs['content'])
        # The previous {type:alert,data:{...}} request fails this receiver contract.
        assert body['type'] == 'text' and body['content']
        assert body['title'] == PAYLOAD['title']
        assert '95' in body['content'] and '-5%' in body['content']
        assert '-1 份' in body['content'] and '100 份' in body['content']
        assert '持仓是手动快照' in body['content']
        sent.append(body)
        return response(body={'success': True, 'data': {'success': True, 'failedCount': 0}})
    monkeypatch.setattr('app.webhooks.request', receiver)
    asyncio.run(send_webhook(cfg, PAYLOAD))
    assert len(sent) == 1


def test_generic_json_receiver_stays_backward_compatible(monkeypatch):
    cfg = {**get_config(), 'webhook_url': 'https://example.com/webhook'}
    async def receiver(method, url, **kwargs):
        assert method == 'POST' and json.loads(kwargs['content']) == PAYLOAD
        return response(204)
    monkeypatch.setattr('app.webhooks.request', receiver)
    asyncio.run(send_webhook(cfg, PAYLOAD))


def test_custom_json_handles_quotes_newlines_and_structured_variables():
    tpl = '{"title":"{{title}}","content":"{{text}}","fields":{{fields}}}'
    result = render_template(tpl, template_context(PAYLOAD))
    assert result['title'] == PAYLOAD['title']
    assert result['fields'] == PAYLOAD['data']
    assert '\n' in result['content']
    assert render_template('{{title}}', template_context(PAYLOAD), False) == PAYLOAD['title']
    with pytest.raises(WebhookError):
        render_template('{"text":"\\{{title}}"}', template_context(PAYLOAD))


def test_unknown_variables_and_malformed_json_fail_before_saving(client):
    for template in ('{"text":{{missing}}}', '{"text":'):
        result = client.put('/api/settings', json={'webhook_format': 'custom', 'webhook_body_tpl': template})
        assert result.status_code == 422
        assert get_config()['webhook_format'] == 'auto'


@pytest.mark.parametrize('headers', ['[]', '{"X-Test":3}', '{"X-Test":"a\\r\\nb"}',
    '{"Host":"other.example"}', '{"Content-Length":"0"}', '{"Authorization":"one","authorization":"two"}',
    '{"X-InvestWatch-Signature":"override"}'])
def test_unsafe_custom_headers_are_rejected(client, headers):
    assert client.put('/api/settings', json={'webhook_headers': headers}).status_code == 422


def test_headers_and_templates_are_encrypted_and_not_echoed(client):
    settings = {'webhook_headers': '{"X-API-Key":"sensitive-key"}',
                'webhook_body_tpl': '{"token":"template-secret","content":"{{text}}"}', 'webhook_format': 'custom'}
    saved = client.put('/api/settings', json=settings)
    assert saved.status_code == 200
    assert 'sensitive-key' not in saved.text and 'template-secret' not in saved.text
    assert saved.json()['webhook_headers_configured'] and saved.json()['webhook_body_tpl_configured']
    client.put('/api/settings', json={'notify_alerts': False})
    assert get_config()['webhook_headers'] == settings['webhook_headers']
    from app.db import Config, Session
    with Session() as session:
        assert 'sensitive-key' not in session.get(Config, 'settings').value


def test_hmac_covers_actual_transformed_body_and_custom_authorization(monkeypatch):
    cfg = {**get_config(), 'webhook_url': 'https://example.com/hook', 'webhook_format': 'custom',
           'webhook_body_tpl': '{"content":"{{text}}"}', 'webhook_secret': 'test-signing-secret',
           'webhook_headers': '{"authorization":"old","X-API-Key":"custom"}',
           'webhook_authorization': 'Bearer actual'}
    async def receiver(method, url, **kwargs):
        headers = kwargs['headers']
        expected = hmac.new(b'test-signing-secret', headers['X-InvestWatch-Timestamp'].encode()+b'.'+kwargs['content'], hashlib.sha256).hexdigest()
        assert headers['X-InvestWatch-Signature'] == 'sha256='+expected
        assert headers['Authorization'] == 'Bearer actual'
        assert headers['X-API-Key'] == 'custom'
        assert headers['Idempotency-Key'] == PAYLOAD['id']
        return response(204)
    monkeypatch.setattr('app.webhooks.request', receiver)
    asyncio.run(send_webhook(cfg, PAYLOAD))


def test_get_encodes_content_and_preserves_existing_query(monkeypatch):
    cfg = {**get_config(), 'webhook_url': 'https://example.com/api/push/test?keep=yes', 'webhook_method': 'GET'}
    async def receiver(method, url, **kwargs):
        params = httpx.URL(url).params
        assert method == 'GET' and kwargs['content'] is None
        assert params['keep'] == 'yes' and params['title'] == PAYLOAD['title']
        assert params['content'] and params['type'] == 'text'
        return response(body={'success': True})
    monkeypatch.setattr('app.webhooks.request', receiver)
    asyncio.run(send_webhook(cfg, PAYLOAD))
    with pytest.raises(WebhookError):
        validate_config({**cfg, 'webhook_format': 'custom', 'webhook_body_type': 'text'})


@pytest.mark.parametrize('status, body, expected', [
    (400, {'message': '该接口未绑定任何渠道'}, '未绑定渠道'),
    (400, {'message': '无效的接口令牌'}, '令牌无效'),
    (400, {'message': '部分推送失败', 'data': {'error': 'SECRET_TOKEN'}}, '下游渠道'),
    (200, {'success': False, 'message': '部分推送失败'}, '下游渠道'),
    (200, {'success': True, 'data': {'failedCount': 1}}, '未确认'),
    (400, {'message': 'SECRET_TOKEN https://private.example/token'}, 'HTTP 400'),
    (200, {'unexpected': 'SECRET_TOKEN'}, '未确认'),
])
def test_magicpush_business_errors_are_safe_and_do_not_fake_success(monkeypatch, status, body, expected):
    cfg = {**get_config(), 'webhook_url': 'https://example.com/api/push/token'}
    async def receiver(*args, **kwargs):
        return response(status, body)
    monkeypatch.setattr('app.webhooks.request', receiver)
    with pytest.raises(WebhookError) as failure:
        asyncio.run(send_webhook(cfg, PAYLOAD))
    assert expected in safe_error(failure.value)
    assert 'SECRET' not in safe_error(failure.value) and 'private.example' not in safe_error(failure.value)


def test_connection_test_and_outbox_use_identical_magicpush_adapter(client, monkeypatch):
    from datetime import timedelta
    from app.db import Delivery, Session, utcnow
    from app.services import deliver_pending
    save_config({'webhook_url': 'https://example.com/api/push/token'})
    calls = []
    async def receiver(*args, **kwargs):
        body = json.loads(kwargs['content'])
        assert body['content'] and body['type'] == 'text'
        calls.append(body)
        return response(body={'success': True})
    monkeypatch.setattr('app.webhooks.request', receiver)
    assert client.post('/api/webhook/test').json()['ok']
    with Session.begin() as session:
        session.add(Delivery(id=PAYLOAD['id'], payload={**PAYLOAD, 'expires_at': (utcnow()+timedelta(minutes=10)).isoformat()}))
    asyncio.run(deliver_pending(get_config()))
    with Session() as session:
        assert session.get(Delivery, PAYLOAD['id']).status == 'sent'
    assert len(calls) == 2


def test_real_http_wrapper_buffers_error_only_for_fixed_magicpush_diagnostics(monkeypatch):
    from app import security
    client_type = httpx.AsyncClient
    async def checked(url, resolve=True):
        assert url == 'https://example.com/api/push/token'
    def receiver(request):
        assert json.loads(request.content)['content']
        return httpx.Response(400, json={'success': False, 'message': '该接口未绑定任何渠道',
                                        'data': {'error': 'SECRET_UPSTREAM_BODY'}})
    monkeypatch.setattr(security, 'validate_url', checked)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(receiver), **kwargs))
    with pytest.raises(WebhookError, match='未绑定渠道') as failure:
        asyncio.run(send_webhook({**get_config(), 'webhook_url': 'https://example.com/api/push/token'}, PAYLOAD))
    assert 'SECRET_UPSTREAM_BODY' not in safe_error(failure.value)
