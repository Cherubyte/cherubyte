"""The endpoint behind a notification button. It has no session to rely on, so
the signed token is the only thing standing between the internet and approval.
"""

import pytest
from fastapi.testclient import TestClient

from app.models import ApprovalStatus, Device
from app.services import action_tokens


@pytest.fixture
def client():
    import app.main

    return TestClient(app.main.app)


@pytest.fixture(autouse=True)
def _secret():
    action_tokens._secret = ""
    action_tokens.ensure_secret()
    yield
    action_tokens._secret = ""


async def _pending_device(session) -> int:
    device = Device(name="Intruso", approval_status=ApprovalStatus.pending)
    session.add(device)
    await session.commit()
    return device.id


@pytest.mark.asyncio
async def test_a_valid_token_approves_the_device(session, client):
    device_id = await _pending_device(session)
    token = action_tokens.make("approve", device_id)

    response = client.post(f"/api/actions/approve/{device_id}?t={token}")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    session.expire_all()
    assert (await session.get(Device, device_id)).approval_status is ApprovalStatus.approved


@pytest.mark.asyncio
async def test_a_valid_token_can_ignore(session, client):
    device_id = await _pending_device(session)
    token = action_tokens.make("ignore", device_id)

    assert client.post(f"/api/actions/ignore/{device_id}?t={token}").status_code == 200
    session.expire_all()
    assert (await session.get(Device, device_id)).approval_status is ApprovalStatus.ignored


@pytest.mark.asyncio
async def test_no_token_changes_nothing(session, client):
    device_id = await _pending_device(session)

    assert client.post(f"/api/actions/approve/{device_id}").status_code == 403

    session.expire_all()
    assert (await session.get(Device, device_id)).approval_status is ApprovalStatus.pending


@pytest.mark.asyncio
async def test_a_token_for_another_device_is_refused(session, client):
    device_id = await _pending_device(session)
    token = action_tokens.make("approve", device_id + 999)

    assert client.post(f"/api/actions/approve/{device_id}?t={token}").status_code == 403
    session.expire_all()
    assert (await session.get(Device, device_id)).approval_status is ApprovalStatus.pending


@pytest.mark.asyncio
async def test_an_approve_token_cannot_be_replayed_as_ignore(session, client):
    device_id = await _pending_device(session)
    token = action_tokens.make("approve", device_id)

    assert client.post(f"/api/actions/ignore/{device_id}?t={token}").status_code == 403


@pytest.mark.asyncio
async def test_an_expired_token_is_refused(session, client):
    device_id = await _pending_device(session)
    token = action_tokens.make("approve", device_id, ttl=-1)

    assert client.post(f"/api/actions/approve/{device_id}?t={token}").status_code == 403


@pytest.mark.asyncio
async def test_an_unknown_action_is_not_routed(session, client):
    device_id = await _pending_device(session)
    token = action_tokens.make("approve", device_id)

    assert client.post(f"/api/actions/delete/{device_id}?t={token}").status_code == 404


@pytest.mark.asyncio
async def test_a_valid_token_for_a_deleted_device_is_a_404(client):
    token = action_tokens.make("approve", 987654)
    assert client.post(f"/api/actions/approve/987654?t={token}").status_code == 404


def test_buttons_are_omitted_without_a_reachable_url(monkeypatch):
    """No public URL means the buttons would go nowhere, so they are left out."""
    from app.services import monitor

    monkeypatch.setattr(monitor.settings, "public_base_url", "")
    assert monitor._approval_actions(1) == []


def test_buttons_carry_a_token_bound_to_the_device(monkeypatch):
    from app.services import monitor

    monkeypatch.setattr(monitor.settings, "public_base_url", "http://192.168.1.9:1001/")
    buttons = monitor._approval_actions(42)

    assert [b["label"] for b in buttons] == ["Aprovar", "Ignorar"]
    for button in buttons:
        assert button["url"].startswith("http://192.168.1.9:1001/api/actions/")
        assert "/42?t=" in button["url"]
        assert button["method"] == "POST"
