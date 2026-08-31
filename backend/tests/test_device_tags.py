"""Free-text device tags — set via PATCH, listed for the filter, searchable."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.database import SessionLocal
from app.models import Device, DeviceType
from app.services import auth


@pytest.fixture
def client(session):
    auth._failures.clear()
    c = TestClient(main.app)
    assert c.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"}).status_code == 201
    return c


async def _device(name: str = "Laptop") -> int:
    async with SessionLocal() as s:
        d = Device(name=name, device_type=DeviceType.laptop, approval_status="approved")
        s.add(d)
        await s.commit()
        return d.id


@pytest.mark.asyncio
async def test_patch_sets_normalised_tags(client):
    did = await _device()
    r = client.patch(f"/api/devices/{did}", json={"tags": [" Office ", "office", "#media", ""]})
    assert r.status_code == 200
    assert r.json()["tags"] == ["Office", "media"]  # trimmed, de-duped, '#' stripped


@pytest.mark.asyncio
async def test_tags_endpoint_lists_by_frequency(client):
    a = await _device("A")
    b = await _device("B")
    c = await _device("C")
    client.patch(f"/api/devices/{a}", json={"tags": ["iot", "office"]})
    client.patch(f"/api/devices/{b}", json={"tags": ["iot"]})
    client.patch(f"/api/devices/{c}", json={"tags": ["iot", "media"]})

    r = client.get("/api/devices/tags")
    assert r.status_code == 200
    assert r.json()[0] == "iot"  # most common first
    assert set(r.json()) == {"iot", "office", "media"}


@pytest.mark.asyncio
async def test_tags_endpoint_is_not_a_device_id(client):
    assert client.get("/api/devices/tags").status_code == 200


@pytest.mark.asyncio
async def test_search_matches_a_tag(client):
    did = await _device("Nas Box")
    client.patch(f"/api/devices/{did}", json={"tags": ["storage"]})
    r = client.get("/api/devices?q=storage")
    assert [d["id"] for d in r.json()] == [did]


@pytest.mark.asyncio
async def test_clearing_tags(client):
    did = await _device()
    client.patch(f"/api/devices/{did}", json={"tags": ["x"]})
    r = client.patch(f"/api/devices/{did}", json={"tags": []})
    assert r.json()["tags"] == []
