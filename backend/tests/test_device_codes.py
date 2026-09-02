"""Enrolling an agent by approving it, instead of pasting a token.

The property that matters: **the short code identifies a request and does not
collect a key.** It is read off a terminal and typed into a URL bar, so it is
short enough to guess and short enough to shoulder-read. The poll secret is
what actually collects, it never leaves the machine that asked, and only its
hash is stored. Somebody who learns a code can therefore look at an approval
page and do nothing else.

Everything else here is the ways that can be got wrong: a code that outlives
its use, a code collected twice, an unapproved code handing out a key, and an
unauthenticated caller filling the approval page with noise.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models import Account, AccountRole, Agent, DeviceCode, utcnow
from app.services import agents as agent_service


async def _start(session, **kw):
    row, secret = await agent_service.request_device_code(
        session, name=kw.get("name", "kitchen-pi"), version=kw.get("version", "1.0.0"),
        source_ip=kw.get("source_ip", "192.168.1.9"),
    )
    await session.commit()
    return row, secret


# -- the two secrets --------------------------------------------------------


@pytest.mark.asyncio
async def test_the_code_is_short_and_readable(session):
    row, _ = await _start(session)
    # Read aloud and typed. No O/0 or I/1, and grouped so it can be checked
    # against a screen without counting characters.
    assert len(row.code) == 9 and row.code[4] == "-"
    assert not set(row.code) & set("O0I1")


@pytest.mark.asyncio
async def test_the_poll_secret_is_returned_once_and_stored_hashed(session):
    row, secret = await _start(session)
    assert len(secret) > 20
    assert row.poll_hash != secret
    assert row.poll_hash == agent_service.hash_secret(secret)


@pytest.mark.asyncio
async def test_the_code_alone_cannot_collect_a_key(session):
    # The whole reason there are two secrets. Somebody who reads the code off
    # a screen gets to look at a page, and no further.
    row, _secret = await _start(session)
    await agent_service.approve_device_code(session, row.code, account_id=1)
    await session.commit()

    assert await agent_service.collect_device_key(
        session, code=row.code, poll_secret="guessed"
    ) is None
    assert await agent_service.collect_device_key(
        session, code=row.code, poll_secret=""
    ) is None


@pytest.mark.asyncio
async def test_a_wrong_secret_does_not_reveal_whether_it_was_approved(session):
    # Checked before the approval state, so polling with a stolen code tells
    # you nothing about whether somebody just clicked approve.
    row, _ = await _start(session)
    before = await agent_service.collect_device_key(session, code=row.code, poll_secret="no")
    await agent_service.approve_device_code(session, row.code, account_id=1)
    await session.commit()
    after = await agent_service.collect_device_key(session, code=row.code, poll_secret="no")
    assert before is after is None


# -- the flow ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_it_is_pending_until_somebody_approves(session):
    row, secret = await _start(session)
    assert await agent_service.collect_device_key(
        session, code=row.code, poll_secret=secret
    ) == "pending"


@pytest.mark.asyncio
async def test_approving_lets_the_machine_collect_a_key(session):
    row, secret = await _start(session, name="kitchen-pi")
    await agent_service.approve_device_code(session, row.code, account_id=1)
    await session.commit()

    result = await agent_service.collect_device_key(
        session, code=row.code, poll_secret=secret
    )
    await session.commit()
    assert result is not None and result != "pending"
    agent, key = result
    assert agent.name == "kitchen-pi"
    # The key is issued, not stored: only its hash survives.
    assert agent.key_hash == agent_service.hash_secret(key)
    assert await agent_service.authenticate(session, agent.id, key) is not None


@pytest.mark.asyncio
async def test_a_key_can_be_collected_only_once(session):
    # Otherwise one approval admits every machine that has the secret.
    row, secret = await _start(session)
    await agent_service.approve_device_code(session, row.code, account_id=1)
    await session.commit()
    first = await agent_service.collect_device_key(session, code=row.code, poll_secret=secret)
    await session.commit()
    assert first != "pending" and first is not None

    again = await agent_service.collect_device_key(session, code=row.code, poll_secret=secret)
    assert again is None
    assert len((await session.execute(select(Agent))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_an_expired_code_is_refused_however_it_is_reached(session):
    from datetime import timedelta

    row, secret = await _start(session)
    row.expires_at = utcnow() - timedelta(seconds=1)
    await session.commit()

    assert await agent_service.find_device_code(session, row.code) is None
    assert await agent_service.approve_device_code(session, row.code, account_id=1) is None
    assert await agent_service.collect_device_key(
        session, code=row.code, poll_secret=secret
    ) is None


@pytest.mark.asyncio
async def test_an_expired_code_is_refused_even_after_approval(session):
    # A machine that was approved and then went away for an hour has to ask
    # again rather than pick up a key nobody is expecting it to.
    from datetime import timedelta

    row, secret = await _start(session)
    await agent_service.approve_device_code(session, row.code, account_id=1)
    row.expires_at = utcnow() - timedelta(seconds=1)
    await session.commit()

    assert await agent_service.collect_device_key(
        session, code=row.code, poll_secret=secret
    ) is None


@pytest.mark.asyncio
async def test_approving_twice_keeps_the_first_approval(session):
    # A double click must not read as a second machine.
    row, _ = await _start(session)
    first = await agent_service.approve_device_code(session, row.code, account_id=1)
    stamp = first.approved_at
    second = await agent_service.approve_device_code(session, row.code, account_id=2)
    assert second.approved_at == stamp
    assert second.approved_by == 1


@pytest.mark.asyncio
async def test_the_code_is_matched_case_insensitively(session):
    # It gets typed. Rejecting a lowercase paste would be a support ticket for
    # no security gain, since the alphabet has no lowercase letters in it.
    row, _ = await _start(session)
    assert await agent_service.find_device_code(session, row.code.lower()) is not None


@pytest.mark.asyncio
async def test_pending_lists_only_what_is_still_waiting(session):
    from datetime import timedelta

    waiting, _ = await _start(session, name="waiting")
    stale, _ = await _start(session, name="stale")
    stale.expires_at = utcnow() - timedelta(seconds=1)
    done, secret = await _start(session, name="done")
    await agent_service.approve_device_code(session, done.code, account_id=1)
    await session.commit()
    await agent_service.collect_device_key(session, code=done.code, poll_secret=secret)
    await session.commit()

    names = {r.name for r in await agent_service.pending_device_codes(session)}
    assert names == {"waiting"}


@pytest.mark.asyncio
async def test_old_codes_are_purged_but_recent_failures_are_kept(session):
    from datetime import timedelta

    recent, _ = await _start(session, name="recent")
    old, _ = await _start(session, name="old")
    old.created_at = utcnow() - timedelta(days=2)
    await session.commit()

    assert await agent_service.purge_device_codes(session) == 1
    await session.commit()
    left = {r.name for r in (await session.execute(select(DeviceCode))).scalars()}
    # The recent one stays even though it is dead, so somebody looking at why
    # an enrolment failed can still see it was asked for.
    assert left == {"recent"}


# -- over HTTP --------------------------------------------------------------


@pytest.fixture
def api(session, monkeypatch):
    from app.api import agents as agents_api
    from app.main import app

    agents_api._RECENT.clear()
    monkeypatch.setattr("app.config.settings.public_url", "https://app.test")
    return app


@pytest.mark.asyncio
async def test_asking_needs_no_credential_and_says_where_to_go(api):
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://panel") as c:
        r = await c.post("/api/agents/device-code", json={"name": "pi", "version": "1.0.0"})
    assert r.status_code == 200
    body = r.json()
    assert body["verification_url"] == f"https://app.test/a/{body['code']}"
    assert body["poll_secret"] and body["interval"] >= 1


@pytest.mark.asyncio
async def test_polling_an_unapproved_code_says_wait_rather_than_no(api):
    # 202, not 4xx. A polling agent has to be able to tell "not yet" from
    # "never", or it gives up on a code somebody is about to approve.
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://panel") as c:
        started = (await c.post("/api/agents/device-code", json={"name": "pi"})).json()
        r = await c.post(
            "/api/agents/device-token",
            json={"code": started["code"], "poll_secret": started["poll_secret"]},
        )
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_a_flood_of_requests_is_refused(api):
    # Otherwise anybody who can reach the panel can fill the approval page
    # with entries for somebody to mis-click.
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://panel") as c:
        codes = [
            (await c.post("/api/agents/device-code", json={"name": "pi"})).status_code
            for _ in range(12)
        ]
    assert 429 in codes
    assert codes[0] == 200


@pytest.mark.asyncio
async def test_the_approval_page_needs_a_logged_in_person(api, session):
    row, _ = await _start(session)
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://panel") as c:
        r = await c.get(f"/a/{row.code}")
    # Not the SPA fallback, and not the page: a refusal.
    assert r.status_code in (401, 403)


@pytest.fixture
def as_account(api, session):
    """Sign the browser in as somebody, without a real login.

    Through `dependency_overrides` and nothing else. Monkeypatching
    `deps.current_account` first and then using it as the override key does
    not work: FastAPI registered the original function object, so replacing it
    means overriding a key that is no longer in the graph.
    """
    from app.api import deps

    async def _use(account):
        api.dependency_overrides[deps.current_account] = lambda: account

    yield _use
    api.dependency_overrides.clear()


async def _account(session, role=AccountRole.admin, username="sam"):
    account = Account(username=username, password_hash="x", role=role)
    session.add(account)
    await session.commit()
    return account


@pytest.mark.asyncio
async def test_the_page_shows_what_is_needed_to_recognise_the_machine(
    api, session, as_account
):
    await as_account(await _account(session))
    row, _ = await _start(session, name="kitchen-pi", source_ip="192.168.1.9")

    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://panel") as c:
        r = await c.get(f"/a/{row.code}")

    assert r.status_code == 200
    for expected in ("kitchen-pi", "192.168.1.9", row.code):
        assert expected in r.text
    # And it says the machine's own claims are not evidence, because they are
    # set by an unauthenticated caller.
    assert "chose its own name" in r.text


@pytest.mark.asyncio
async def test_approving_from_the_page_admits_the_machine(api, session, as_account):
    await as_account(await _account(session))
    row, secret = await _start(session)

    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://panel") as c:
        r = await c.post(f"/a/{row.code}/approve")
        assert r.status_code == 200 and "Approved" in r.text
        collected = await c.post(
            "/api/agents/device-token", json={"code": row.code, "poll_secret": secret}
        )

    assert collected.status_code == 200
    assert collected.json()["key"]


@pytest.mark.asyncio
async def test_a_viewer_cannot_admit_a_machine(api, session, as_account):
    # Reading the inventory and letting a new machine into it are different
    # powers, and the page is a link anyone can be sent.
    await as_account(await _account(session, role=AccountRole.viewer, username="vic"))
    row, secret = await _start(session)

    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://panel") as c:
        r = await c.post(f"/a/{row.code}/approve")
        still_waiting = await c.post(
            "/api/agents/device-token", json={"code": row.code, "poll_secret": secret}
        )

    assert "Not allowed" in r.text
    assert still_waiting.status_code == 202


@pytest.mark.asyncio
async def test_a_code_that_never_existed_looks_like_one_that_expired(api, session, as_account):
    # Distinguishing them would confirm which codes had been real.
    await as_account(await _account(session))
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://panel") as c:
        r = await c.get("/a/ZZZZ-ZZZZ")
    assert r.status_code == 200
    assert "Nothing to approve" in r.text
