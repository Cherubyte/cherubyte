"""What the panel serves an agent that is updating itself.

The panel is in the path of every update and is the thing most worth
compromising, so its job here is deliberately small: hand over the release's
own signed digest list untouched, and hand over the bytes. It does not sign
anything and cannot vouch for anything. The agent carries the release public
key and refuses whatever does not match.

So what is worth testing here is the boring half — that the endpoints need the
agent's key, that an unsigned release is reported as unsigned rather than
papered over, and that the digest list is passed through byte for byte.
"""

from __future__ import annotations

import base64

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.models import Agent
from app.services import agent_release, agents as agent_service

SUMS = b"a" * 64 + b"  cherubyte-agent-linux-x86_64\n"
SIGNATURE = b"\x01\x02\x03signature"


@pytest_asyncio.fixture
async def enrolled(session):
    key = agent_service.new_secret()
    agent = Agent(name="kitchen-pi", key_hash=agent_service.hash_secret(key))
    session.add(agent)
    await session.commit()
    return agent.id, key


@pytest.fixture
def client():
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://panel")


@pytest.fixture
def release(monkeypatch):
    signed: dict[str, object] = {"value": (SUMS, SIGNATURE)}

    async def latest(**_kw):
        return {"tag": "v2.0.0", "assets": {}, **agent_release._repo_info()}

    async def signed_digests():
        return signed["value"]

    monkeypatch.setattr(agent_release, "latest", latest)
    monkeypatch.setattr(agent_release, "signed_digests", signed_digests)
    return signed


@pytest.mark.asyncio
async def test_the_manifest_needs_the_agents_own_key(client, enrolled, release):
    agent_id, key = enrolled
    async with client as c:
        assert (await c.get(f"/api/agents/{agent_id}/update")).status_code == 401
        assert (
            await c.get(
                f"/api/agents/{agent_id}/update",
                headers={"Authorization": "Bearer not-the-key"},
            )
        ).status_code == 401
        ok = await c.get(
            f"/api/agents/{agent_id}/update", headers={"Authorization": f"Bearer {key}"}
        )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_the_digest_list_is_passed_through_untouched(client, enrolled, release):
    # Byte for byte, because the signature is over exactly these bytes and a
    # panel that reformatted them would break every verification.
    agent_id, key = enrolled
    async with client as c:
        r = await c.get(
            f"/api/agents/{agent_id}/update", headers={"Authorization": f"Bearer {key}"}
        )
    body = r.json()
    assert body["sums"].encode() == SUMS
    assert base64.b64decode(body["signature"]) == SIGNATURE
    assert body["version"] == "2.0.0"


@pytest.mark.asyncio
async def test_an_unsigned_release_is_reported_as_unsigned(client, enrolled, release):
    # Older releases predate signing. Saying so plainly is what lets the agent
    # refuse; inventing a signature here would be the one unforgivable bug.
    agent_id, key = enrolled
    release["value"] = None
    async with client as c:
        r = await c.get(
            f"/api/agents/{agent_id}/update", headers={"Authorization": f"Bearer {key}"}
        )
    body = r.json()
    assert body["sums"] is None and body["signature"] is None


@pytest.mark.asyncio
async def test_a_disabled_agent_cannot_pull_a_binary(client, enrolled, release, session):
    # Removing an agent has to stop it, and "stop it" includes not handing it
    # executables.
    agent_id, key = enrolled
    agent = await session.get(Agent, agent_id)
    agent.enabled = False
    await session.commit()

    async with client as c:
        r = await c.get(
            f"/api/agents/{agent_id}/update/download?platform=linux",
            headers={"Authorization": f"Bearer {key}"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_an_unknown_platform_is_a_refusal_not_a_guess(client, enrolled, release, monkeypatch):
    agent_id, key = enrolled

    async def no_asset(_platform):
        return None

    monkeypatch.setattr(agent_release, "asset_path", no_asset)
    async with client as c:
        r = await c.get(
            f"/api/agents/{agent_id}/update/download?platform=solaris",
            headers={"Authorization": f"Bearer {key}"},
        )
    assert r.status_code == 404
