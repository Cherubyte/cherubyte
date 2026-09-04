"""Device file attachments — upload with type sniffing, authenticated download
with a safe filename, delete, and cleanup when the device goes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api import devices as devices_api
from app.database import SessionLocal
from app.config import attachment_dir
from app.models import Device, DeviceType
from app.services import auth


@pytest.fixture
def client(session, tmp_path, monkeypatch):
    auth._failures.clear()
    # attachment_dir() reads this at call time in single-tenant mode
    monkeypatch.setattr("app.config.ATTACHMENT_DIR", tmp_path / "attachments")
    c = TestClient(main.app)
    assert c.post(
        "/api/auth/setup", json={"username": "admin", "password": "hunter2!!"}
    ).status_code == 201
    return c


async def _device(name: str = "NAS") -> int:
    async with SessionLocal() as s:
        d = Device(name=name, device_type=DeviceType.nas, approval_status="approved")
        s.add(d)
        await s.commit()
        return d.id


PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
ELF = b"\x7fELF" + b"\x00" * 40


@pytest.mark.asyncio
async def test_upload_then_download_a_pdf(client):
    did = await _device()
    r = client.post(
        f"/api/devices/{did}/attachments",
        files={"file": ("Router manual.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["attachments"]) == 1
    att = body["attachments"][0]
    assert att["original_name"] == "Router manual.pdf"
    assert att["content_type"] == "application/pdf"
    assert att["size"] == len(PDF)
    assert att["url"] == f"/api/devices/{did}/attachments/{att['id']}"

    got = client.get(att["url"])
    assert got.status_code == 200
    assert got.content == PDF
    assert got.headers["content-type"].startswith("application/pdf")
    cd = got.headers["content-disposition"]
    assert cd.startswith("attachment")
    assert "Router%20manual.pdf" in cd or "Router manual.pdf" in cd
    assert got.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_type_is_sniffed_not_taken_from_the_name(client):
    did = await _device()
    # an executable wearing a .pdf name
    r = client.post(
        f"/api/devices/{did}/attachments",
        files={"file": ("totally.pdf", ELF, "application/pdf")},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_a_text_file_is_accepted(client):
    did = await _device()
    r = client.post(
        f"/api/devices/{did}/attachments",
        files={"file": ("notes.txt", "warranty until 2028\n".encode(), "text/plain")},
    )
    assert r.status_code == 200
    assert r.json()["attachments"][0]["content_type"].startswith("text/plain")


@pytest.mark.asyncio
async def test_download_name_cannot_smuggle_a_path(client):
    did = await _device()
    r = client.post(
        f"/api/devices/{did}/attachments",
        files={"file": ("../../etc/passwd", PDF, "application/pdf")},
    )
    assert r.status_code == 200
    name = r.json()["attachments"][0]["original_name"]
    assert "/" not in name and ".." not in name


@pytest.mark.asyncio
async def test_delete_removes_row_and_file(client):
    did = await _device()
    att = client.post(
        f"/api/devices/{did}/attachments",
        files={"file": ("m.pdf", PDF, "application/pdf")},
    ).json()["attachments"][0]

    stored = attachment_dir()
    on_disk = next(stored.iterdir())
    assert on_disk.is_file()

    r = client.delete(f"/api/devices/{did}/attachments/{att['id']}")
    assert r.status_code == 200
    assert r.json()["attachments"] == []
    assert not on_disk.exists()


@pytest.mark.asyncio
async def test_deleting_the_device_takes_its_attachments(client):
    did = await _device()
    client.post(
        f"/api/devices/{did}/attachments",
        files={"file": ("m.pdf", PDF, "application/pdf")},
    )
    stored = attachment_dir()
    assert list(stored.iterdir())

    assert client.delete(f"/api/devices/{did}").status_code == 204
    assert not list(stored.iterdir())


@pytest.mark.asyncio
async def test_oversized_upload_is_refused(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 8)
    did = await _device()
    r = client.post(
        f"/api/devices/{did}/attachments",
        files={"file": ("big.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 413
    assert list(attachment_dir().iterdir()) == []
