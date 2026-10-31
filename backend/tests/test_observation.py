import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.config import get_config, save_config
from app.db import Article, Delivery, Event, Session, Watch


NOW = datetime(2026, 10, 28, 2, 0, tzinfo=timezone.utc)


def watches(client, monkeypatch):
    monkeypatch.setattr('app.services.utcnow', lambda: NOW)
    for data in [
        {'symbol': '510300.SS', 'name': '沪深观察', 'market': 'CN', 'kind': 'etf'},
        {'symbol': 'QQQ', 'name': '纳斯达克观察', 'market': 'US', 'kind': 'etf'},
        {'symbol': 'BTC-USDT', 'name': '比特币观察', 'market': 'CRYPTO', 'kind': 'crypto'},
    ]:
        assert client.post('/api/watchlist', json=data).status_code == 201
    with Session.begin() as session:
        session.get(Watch, 'CN:510300.SS').quote = {'price': 4.25, 'previous_close': 4.2, 'change_pct': 1.19,
            'currency': 'CNY', 'source': 'Fixture quote source', 'as_of': (NOW-timedelta(minutes=1)).isoformat()}
        # Fresh timestamp during US non-trading hours must not become actionable.
        session.get(Watch, 'US:QQQ').quote = {'price': 500, 'previous_close': 510, 'change_pct': -1.96,
            'currency': 'USD', 'as_of': NOW.isoformat(), 'source': 'Fixture US quote source'}
        session.add(Article(id='fixture-news', title='Fixture public news', source='Fixture RSS',
            url='https://example.com/news', published=NOW.isoformat(), collected=NOW, tags=[]))


def test_real_portfolio_snapshot_contract_and_repeated_save(client):
    snapshot = client.get('/api/portfolio').json()
    rejected = client.put('/api/portfolio', json=snapshot)
    assert rejected.status_code == 422
    assert any(error['loc'] == ['body', 'updated_at'] and error['type'] == 'extra_forbidden' for error in rejected.json()['detail'])
    editable = {'revision', 'positions', 'cash', 'min_cash', 'max_step', 'risk', 'horizon'}
    for revision in (1, 2):
        saved = client.put('/api/portfolio', json={key: value for key, value in snapshot.items() if key in editable})
        assert saved.status_code == 200
        snapshot = saved.json()
        assert snapshot['revision'] == revision
        assert snapshot['updated_at'] and float(snapshot['cash']) == 100
    assert client.get('/api/portfolio').json() == snapshot
    assert client.put('/api/portfolio', json={key: value for key, value in {**snapshot, 'revision': 0}.items() if key in editable}).status_code == 409
    assert client.put('/api/portfolio', json={**{key: value for key, value in snapshot.items() if key in editable}, 'capital': 1000000}).status_code == 422
    assert client.get('/api/portfolio').json() == snapshot


def test_preview_uses_saved_data_marks_missing_and_closed_without_network_or_ai(client, monkeypatch):
    watches(client, monkeypatch)
    save_config({'strategy_enabled': True, 'ai_enabled': True})
    ai = AsyncMock(side_effect=AssertionError('Manual preview must not call AI'))
    network = AsyncMock(side_effect=AssertionError('Preview must not fetch or send'))
    monkeypatch.setattr('app.ai.generate_report', ai)
    monkeypatch.setattr('app.webhooks.request', network)
    monkeypatch.setattr('app.services.fetch_quote', network)
    before = client.get('/api/portfolio').json()
    response = client.get('/api/webhook/observation-preview')
    assert response.status_code == 200
    preview = response.json()
    assert preview['count'] == 3 and '【测试】' in preview['text']
    assert 'Fixture quote source' in preview['text'] and '报价时间' in preview['text']
    assert '非交易时段' in preview['text'] and '暂无可用报价' in preview['text']
    assert '不调用 AI' in preview['text'] and 'Fixture public news' in preview['text']
    items = {item['market']: item for item in preview['payload']['data']['items']}
    assert items['CN']['data_valid'] and items['CN']['price'] == 4.25
    assert not items['US']['data_valid'] and items['US']['signal']['delta'] == 0
    assert not items['CRYPTO']['data_valid'] and items['CRYPTO']['price'] is None
    assert client.get('/api/portfolio').json() == before
    save_config({'markets': ['CN']})
    selected = client.get('/api/webhook/observation-preview').json()
    assert selected['count'] == 1 and selected['payload']['data']['items'][0]['market'] == 'CN'
    with Session() as session:
        assert session.scalars(select(Delivery)).all() == []
        assert session.scalars(select(Event)).all() == []
    ai.assert_not_called()
    network.assert_not_called()


@pytest.mark.parametrize('mode', ['magicpush', 'raw', 'custom'])
def test_observation_test_sends_real_snapshot_via_existing_adapter_and_records_result(client, monkeypatch, mode):
    watches(client, monkeypatch)
    snapshot = client.get('/api/portfolio').json()
    body = {key: value for key, value in snapshot.items() if key != 'updated_at'}
    body.update(cash=60, positions=[{'watch_id': 'CN:510300.SS', 'shares': 40, 'target': None, 'cap': 50}])
    assert client.put('/api/portfolio', json=body).status_code == 200
    save_config({'webhook_url': 'https://example.com/api/push/test-token', 'webhook_format': mode,
        'webhook_body_tpl': '{"content":"{{text}}","snapshot":{{fields}}}', 'ai_enabled': True,
        'notify_daily': False, 'quiet_start': '00:00', 'quiet_end': '23:59'})
    sent = []
    async def receiver(method, url, **kwargs):
        import json
        data = json.loads(kwargs['content'])
        sent.append(data)
        if mode == 'magicpush':
            assert data['type'] == 'text' and '【测试】' in data['content']
            assert '持仓 40.0 份' in data['content'] and '现金 60' in data['content']
        elif mode == 'raw':
            assert data['type'] == 'daily' and data['data']['test']
            assert data['data']['portfolio_revision'] == 1
        else:
            assert data['snapshot']['test'] and 'Fixture quote source' in data['content']
        return httpx.Response(200, json={'success': True}, request=httpx.Request(method, url))
    monkeypatch.setattr('app.webhooks.request', receiver)
    ai = AsyncMock(side_effect=AssertionError('Manual test must not call AI'))
    monkeypatch.setattr('app.ai.generate_report', ai)
    before = client.get('/api/portfolio').json()
    result = client.post('/api/webhook/test-observation')
    assert result.status_code == 200 and result.json()['count'] == 3
    assert len(sent) == 1
    event_id = result.json()['id']
    with Session() as session:
        assert session.get(Event, event_id).kind == 'test'
        delivery = session.get(Delivery, event_id)
        assert delivery.status == 'sent' and delivery.attempts == 1
    assert client.get('/api/portfolio').json() == before
    ai.assert_not_called()


def test_manual_test_does_not_reserve_daily_slot_or_enter_retry_queue(client, monkeypatch):
    from app.services import daily_reports, deliver_pending
    watches(client, monkeypatch)
    save_config({'webhook_url': 'https://example.com/hook', 'markets': ['CN'], 'notify_daily': True,
                 'quiet_start': '00:00', 'quiet_end': '23:59'})
    sender = AsyncMock()
    monkeypatch.setattr('app.main.send_webhook', sender)
    assert client.post('/api/webhook/test-observation').status_code == 200
    sender.assert_awaited_once()
    asyncio.run(daily_reports(get_config()))
    with Session() as session:
        assert len(session.scalars(select(Event).where(Event.kind == 'daily')).all()) == 1
        assert len(session.scalars(select(Event).where(Event.kind == 'test')).all()) == 1
    with Session.begin() as session:
        for delivery in session.scalars(select(Delivery).where(Delivery.status == 'pending')):
            delivery.due = NOW
    save_config({'quiet_start': '', 'quiet_end': ''})
    sender.reset_mock()
    monkeypatch.setattr('app.services.send_webhook', sender)
    asyncio.run(deliver_pending(get_config()))
    sender.assert_awaited_once()  # Only the scheduled report, never the manual test.


def test_failed_test_has_safe_record_and_never_auto_retries(client, monkeypatch):
    from app.services import deliver_pending
    watches(client, monkeypatch)
    save_config({'webhook_url': 'https://example.com/api/push/test-token'})
    sender = AsyncMock(side_effect=httpx.ConnectError('SECRET_URL_AND_PASSWORD'))
    monkeypatch.setattr('app.main.send_webhook', sender)
    result = client.post('/api/webhook/test-observation')
    assert result.status_code == 502 and 'SECRET' not in result.text
    with Session() as session:
        delivery = session.scalars(select(Delivery)).one()
        assert delivery.status == 'failed' and delivery.attempts == 1
        assert 'SECRET' not in delivery.error
    assert 'SECRET' not in client.get('/api/events').text
    retry = AsyncMock()
    monkeypatch.setattr('app.services.send_webhook', retry)
    asyncio.run(deliver_pending(get_config()))
    retry.assert_not_called()


def test_preview_and_send_require_saved_watches_and_webhook(client):
    assert client.get('/api/webhook/observation-preview').status_code == 422
    assert client.post('/api/webhook/test-observation').status_code == 422
    save_config({'webhook_url': 'https://example.com/hook', 'markets': []})
    assert client.post('/api/webhook/test-observation').status_code == 422


def test_observation_routes_require_auth(client, monkeypatch):
    monkeypatch.setenv('APP_TOKEN', 'test-auth-token')
    assert client.get('/api/webhook/observation-preview').status_code == 401
    assert client.post('/api/webhook/test-observation').status_code == 401
