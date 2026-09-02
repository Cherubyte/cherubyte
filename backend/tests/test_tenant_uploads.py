"""Uploaded images, per tenant.

These are photographs somebody took of their own home. They were written to
one shared directory, served from a static mount with no authentication, and
— worst — packed wholesale into whichever tenant asked for a backup. An
unguessable file name was the only thing between one customer's pictures and
another's, and the backup download did not even have to guess.
"""

from __future__ import annotations

import tarfile

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app import database
from app.config import UPLOAD_DIR, settings, upload_dir
from app.services import backup as backup_service
from app.tenancy import TenantMiddleware, current_tenant


@pytest_asyncio.fixture
async def hosted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "tenants_dir", str(tmp_path / "tenants"))
    monkeypatch.setattr("app.config.UPLOAD_DIR", tmp_path / "uploads")
    for tid in ("alpha", "beta"):
        await database.provision_tenant(tid)
    yield tmp_path / "uploads"
    await database.dispose_tenants()


def _write(tenant: str, name: str, body: bytes) -> None:
    token = current_tenant.set(tenant)
    try:
        (upload_dir(create=True) / name).write_bytes(body)
    finally:
        current_tenant.reset(token)


# -- the directory ----------------------------------------------------------


def test_each_tenant_writes_to_its_own_directory(hosted):
    _write("alpha", "dev1-aaaa.png", b"alpha's living room")
    _write("beta", "dev1-bbbb.png", b"beta's kitchen")

    assert (hosted / "alpha" / "dev1-aaaa.png").is_file()
    assert (hosted / "beta" / "dev1-bbbb.png").is_file()
    # The same file name in two tenants is two different files, which it was
    # not before: `dev1-<uuid>` collides only by chance, but nothing stopped it.
    assert not (hosted / "alpha" / "dev1-bbbb.png").exists()


def test_there_is_no_shared_directory_to_fall_back_to(hosted):
    # The fallback is what caused this. With no tenant in scope it raises
    # rather than quietly using the parent every tenant sits under.
    assert current_tenant.get() is None
    with pytest.raises(RuntimeError, match="outside a tenant"):
        upload_dir()


def test_self_hosted_is_the_one_directory_it_always_was(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", False)
    assert upload_dir() == UPLOAD_DIR


# -- serving ----------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    # The real handler, behind the real middleware. main.app decided its own
    # middleware at import time with the flag off, so it cannot stand in for
    # the hosted configuration — but the handler itself is mode-aware and is
    # the thing under test.
    from app.main import serve_upload

    app = FastAPI()
    app.add_middleware(TenantMiddleware)
    app.get("/uploads/{name:path}")(serve_upload)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://panel") as c:
        yield c


@pytest.mark.asyncio
async def test_a_tenant_gets_its_own_image(hosted, client):
    _write("alpha", "dev1-aaaa.png", b"alpha's living room")
    r = await client.get("/uploads/dev1-aaaa.png", headers={settings.tenant_header: "alpha"})
    assert r.status_code == 200
    assert r.content == b"alpha's living room"


@pytest.mark.asyncio
async def test_one_tenant_cannot_fetch_anothers_image(hosted, client):
    _write("beta", "dev1-bbbb.png", b"beta's kitchen")
    # Knowing the exact file name is no longer enough.
    r = await client.get("/uploads/dev1-bbbb.png", headers={settings.tenant_header: "alpha"})
    assert r.status_code == 404
    assert b"kitchen" not in r.content


@pytest.mark.asyncio
async def test_no_tenant_gets_nothing(hosted, client):
    _write("alpha", "dev1-aaaa.png", b"alpha's living room")
    r = await client.get("/uploads/dev1-aaaa.png")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_traversal_out_of_the_tenant_directory_is_refused(hosted, client):
    _write("beta", "dev1-bbbb.png", b"beta's kitchen")
    for name in ("../beta/dev1-bbbb.png", "..%2Fbeta%2Fdev1-bbbb.png", "%2e%2e/beta/dev1-bbbb.png"):
        r = await client.get(f"/uploads/{name}", headers={settings.tenant_header: "alpha"})
        assert r.status_code == 404, name
        assert b"kitchen" not in r.content


# -- backups ----------------------------------------------------------------


def test_a_backup_packs_only_the_tenants_own_images(hosted, tmp_path):
    # The leak that needed no guessing at all: any tenant admin could press
    # Download backup and receive every other tenant's photographs.
    _write("alpha", "dev1-aaaa.png", b"alpha's living room")
    _write("beta", "dev1-bbbb.png", b"beta's kitchen")

    out = tmp_path / "alpha-backup.tar.gz"
    token = current_tenant.set("alpha")
    try:
        backup_service.create(out)
    finally:
        current_tenant.reset(token)

    with tarfile.open(out) as tar:
        names = tar.getnames()
        blobs = b"".join(
            tar.extractfile(n).read() for n in names if n.startswith("uploads/")
        )
    assert any(n.endswith("dev1-aaaa.png") for n in names)
    assert not any(n.endswith("dev1-bbbb.png") for n in names)
    assert b"kitchen" not in blobs


def test_a_backup_snapshots_the_tenants_own_database(hosted, tmp_path):
    token = current_tenant.set("alpha")
    try:
        assert backup_service.db_path() == database.tenant_db_path("alpha")
    finally:
        current_tenant.reset(token)
    # And with nobody in scope there is no database to reach for.
    assert backup_service.db_path() is None
