"""GET /api/devices/export.csv — the whole inventory as CSV."""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from app import main
from app.database import SessionLocal
from app.models import Device, DeviceType, IpAddress, MacAddress, User
from app.services import auth


@pytest.fixture
def client(session):
    auth._failures.clear()
    c = TestClient(main.app)
    r = c.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"})
    assert r.status_code == 201
    return c


async def _seed():
    async with SessionLocal() as s:
        sam = User(name="Sam")
        s.add(sam)
        await s.flush()
        s.add(
            Device(
                name="Office Laptop",
                device_type=DeviceType.laptop,
                vendor="Dell",
                model="XPS 13",
                os_guess="Windows",
                approval_status="approved",
                is_online=True,
                user_id=sam.id,
                ips=[IpAddress(address="192.168.1.21", is_primary=True)],
                macs=[MacAddress(address="a4:83:e7:1c:2d:9f")],
            )
        )
        s.add(
            Device(
                device_type=DeviceType.unknown,
                approval_status="pending",
                is_online=False,
                macs=[MacAddress(address="b2:9e:44:1a:7f:03", is_random=True)],
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_export_returns_a_csv_attachment(client):
    await _seed()
    r = client.get("/api/devices/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "netscan-devices.csv" in r.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 2
    laptop = next(x for x in rows if x["name"] == "Office Laptop")
    assert laptop["type"] == "laptop"
    assert laptop["vendor"] == "Dell"
    assert laptop["os"] == "Windows"
    assert laptop["online"] == "yes"
    assert laptop["primary_ip"] == "192.168.1.21"
    assert laptop["macs"] == "a4:83:e7:1c:2d:9f"
    assert laptop["owner"] == "Sam"


@pytest.mark.asyncio
async def test_export_needs_a_login(session):
    auth._failures.clear()
    anon = TestClient(main.app)
    # first run: setup required, so any protected GET is 401/403 without a session
    assert anon.get("/api/devices/export.csv").status_code in (401, 403)


@pytest.mark.asyncio
async def test_the_literal_path_wins_over_device_id(client):
    # /export.csv must not be parsed as /devices/{device_id}
    r = client.get("/api/devices/export.csv")
    assert r.status_code == 200
