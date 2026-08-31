"""The Fingerbank diagnostic used by the settings page."""

from __future__ import annotations

import httpx
import pytest

from app.services import fingerbank


@pytest.fixture(autouse=True)
def _clean():
    fingerbank.reset_cache()
    yield
    fingerbank.reset_cache()
    fingerbank.settings.fingerbank_api_key = ""


def _mock_post(monkeypatch, *, status_code: int, payload: dict | None = None):
    class Resp:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return payload or {}

    async def fake_post(self, url, **kwargs):
        return Resp()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


async def test_no_key_reports_no_key(monkeypatch):
    fingerbank.settings.fingerbank_api_key = ""
    assert await fingerbank.check() == {"status": "no_key"}


async def test_a_good_answer_is_parsed(monkeypatch):
    fingerbank.settings.fingerbank_api_key = "k"
    _mock_post(
        monkeypatch,
        status_code=200,
        payload={
            "score": 42,
            "device": {"name": "Android", "parents": [{"name": "Operating System"}]},
        },
    )
    out = await fingerbank.check()
    assert out["status"] == "ok"
    assert out["name"] == "Android"
    assert out["os"] == "Android"
    assert out["score"] == 42


async def test_a_rejected_key(monkeypatch):
    fingerbank.settings.fingerbank_api_key = "bad"
    _mock_post(monkeypatch, status_code=403)
    assert (await fingerbank.check())["status"] == "invalid_key"


async def test_rate_limiting_is_surfaced(monkeypatch):
    fingerbank.settings.fingerbank_api_key = "k"
    _mock_post(monkeypatch, status_code=429)
    assert (await fingerbank.check())["status"] == "rate_limited"


async def test_reset_cache_clears_memoised_answers():
    fingerbank._cache["x"] = {"name": "stale"}
    fingerbank.reset_cache()
    assert fingerbank._cache == {}
