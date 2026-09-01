"""The panel reads the agent's latest GitHub release and serves the binary."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.services import agent_release

_RELEASE = {
    "tag_name": "v1.1.0",
    "published_at": "2026-09-01T18:32:00Z",
    "assets": [
        {"name": "cherubyte-agent-linux-x86_64", "browser_download_url": "https://x/linux", "size": 12},
        {"name": "cherubyte-agent-macos-arm64", "browser_download_url": "https://x/macos", "size": 13},
        {"name": "cherubyte-agent-windows-x86_64.exe", "browser_download_url": "https://x/win", "size": 14},
    ],
}


@pytest.fixture(autouse=True)
def _reset_cache(tmp_path, monkeypatch):
    agent_release._cache.update(
        tag=None, published_at=None, assets={}, checked_at=None, error=None, _fetched_monotonic=0.0
    )
    monkeypatch.setattr(agent_release, "CACHE_DIR", tmp_path / "agent-cache")


def _mock_release(monkeypatch, *, status_code=200, payload=None):
    body = payload if payload is not None else _RELEASE

    class Resp:
        def __init__(self):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("boom", request=None, response=self)

        def json(self):
            return body

    async def fake_get(self, url, **kw):
        return Resp()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


@pytest.fixture
def client():
    return TestClient(main.app)


def _admin(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"})


@pytest.mark.asyncio
async def test_latest_parses_a_release(monkeypatch):
    _mock_release(monkeypatch)
    info = await agent_release.latest()
    assert info["tag"] == "v1.1.0"
    assert set(info["assets"]) == {"linux", "macos", "windows"}
    assert info["assets"]["linux"]["url"] == "https://x/linux"
    assert info["error"] is None


@pytest.mark.asyncio
async def test_no_release_yet_is_a_soft_error(monkeypatch):
    _mock_release(monkeypatch, status_code=404)
    info = await agent_release.latest()
    assert info["tag"] is None
    assert info["error"] == "no release published yet"


@pytest.mark.asyncio
async def test_asset_path_downloads_and_caches(monkeypatch):
    _mock_release(monkeypatch)

    calls = {"n": 0}

    class Stream:
        async def __aenter__(self):
            calls["n"] += 1
            return self

        async def __aexit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        async def aiter_bytes(self, _n):
            yield b"ELF\x7f binary"

    def fake_stream(self, method, url, **kw):
        return Stream()

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    p1 = await agent_release.asset_path("linux")
    assert p1 is not None and p1.read_bytes() == b"ELF\x7f binary"
    p2 = await agent_release.asset_path("linux")
    assert p2 == p1 and calls["n"] == 1  # second call served from cache


@pytest.mark.asyncio
async def test_asset_path_unknown_platform(monkeypatch):
    _mock_release(monkeypatch)
    assert await agent_release.asset_path("solaris") is None


def test_release_endpoint_needs_login(session, client):
    assert client.get("/api/agents/release").status_code in (401, 403)


def test_release_endpoint_reports_no_release(session, client, monkeypatch):
    _admin(client)
    _mock_release(monkeypatch, status_code=404)
    r = client.get("/api/agents/release")
    assert r.status_code == 200
    assert r.json()["tag"] is None
    assert r.json()["error"] == "no release published yet"
    assert r.json()["repo_url"].endswith("/cherubyte-agent")


def test_download_unknown_platform_is_404(session, client, monkeypatch):
    _admin(client)
    _mock_release(monkeypatch)
    assert client.get("/api/agents/download/solaris").status_code == 404
