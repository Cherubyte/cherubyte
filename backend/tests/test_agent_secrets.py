"""Tenant-prefixed agent secrets.

Hosted, the edge routes an agent's report on the key it presents, with no
lookup: the key says which tenant it belongs to. What is worth pinning is
that the prefix appears exactly when there is a tenant, that a prefixed secret
still authenticates against the hash it was stored under, and that reading
the tenant back out is exact — including for tenant ids and random parts that
both contain the characters a naive separator would have tripped on.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from app import database
from app.config import settings
from app.services import agents as agent_service
from app.tenancy import current_tenant, tenant_from_secret


@pytest_asyncio.fixture
async def hosted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "tenants_dir", str(tmp_path / "tenants"))
    yield
    await database.dispose_tenants()


@pytest.fixture
def as_tenant():
    token = current_tenant.set("alpha")
    yield "alpha"
    current_tenant.reset(token)


R = "x" * 43  # the length token_urlsafe(32) produces


# ── the prefix ─────────────────────────────────────────────────────────────


def test_a_secret_minted_for_a_tenant_names_it(as_tenant):
    secret = agent_service.new_secret()
    assert secret.startswith("t.alpha.")
    assert tenant_from_secret(secret) == "alpha"
    # Still 32 random bytes after the address.
    assert len(secret) - len("t.alpha.") >= 43


def test_a_secret_minted_with_no_tenant_is_plain():
    assert current_tenant.get() is None
    secret = agent_service.new_secret()
    assert not secret.startswith("t.")
    assert "." not in secret
    assert tenant_from_secret(secret) is None


def test_two_secrets_for_one_tenant_differ(as_tenant):
    assert agent_service.new_secret() != agent_service.new_secret()


# ── reading the tenant back out ────────────────────────────────────────────


def test_the_separator_is_a_character_neither_part_can_contain():
    # This is the whole reason it is a dot. Both of these would be ambiguous
    # under `_`: is it tenant `abc_d`, or tenant `abc` with a random part that
    # happens to start `d_`? With a dot there is exactly one reading.
    assert tenant_from_secret("t.abc_d." + R) == "abc_d"
    assert tenant_from_secret("t.abc.d_" + R) == "abc"
    # And the random part is free to contain both of the characters a tenant
    # id can, without any of them being read as a boundary.
    assert tenant_from_secret("t.my-home.ab_cd-ef_gh" + "x" * 30) == "my-home"


@pytest.mark.parametrize(
    "bad",
    [
        "t.alpha.",  # no random part
        "t.alpha.short",  # too short to be one of ours
        "t.." + R,  # empty tenant
        "t.ab." + R,  # tenant too short to be valid
        "t.Alpha." + R,  # not a tenant id we would ever mint
        "t.alpha.beta." + R,  # a second dot: not our shape
        "t_alpha_" + R,  # the old shape, never issued
        "talpha." + R,
        "",
        None,
        42,
    ],
)
def test_a_malformed_prefix_routes_nowhere(bad):
    # None, never a partial tenant: the edge then has nothing to forward and
    # the origin refuses.
    assert tenant_from_secret(bad) is None


# ── the round trip ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_prefixed_token_enrols_and_a_prefixed_key_authenticates(hosted, as_tenant):
    # The hash is of the whole string, prefix included, so the prefix is not
    # a way to move one tenant's key onto another's row: `t.beta.<same random>`
    # hashes to something nobody stored.
    await database.provision_tenant("alpha")
    session = await database.session_for("alpha")
    async with session:
        token = await agent_service.issue_token(session, label="test")
        await session.commit()
        assert tenant_from_secret(token) == "alpha"

        issued = await agent_service.enrol(session, token=token, name="rig", version="1")
        await session.commit()
        assert issued is not None
        agent, key = issued
        assert tenant_from_secret(key) == "alpha"

        assert await agent_service.authenticate(session, agent.id, key) is not None
        forged = key.replace("t.alpha.", "t.beta.", 1)
        assert await agent_service.authenticate(session, agent.id, forged) is None
