"""manage.py's `create-agent-token` — mints a real, spendable enrolment token
without going through the HTTP API, so a whole install can be scripted from a
terminal with no browser session (see #60)."""

from __future__ import annotations

import pytest

import manage
from app.services import agents as agent_service


@pytest.mark.asyncio
async def test_create_agent_token_mints_a_spendable_token(session):
    token = await manage._create_agent_token("cli-test")
    assert token

    issued = await agent_service.enrol(session, token=token, name="cli-agent")
    assert issued is not None
    agent, key = issued
    assert agent.name == "cli-agent"
    assert key


@pytest.mark.asyncio
async def test_create_agent_token_works_without_a_label(session):
    token = await manage._create_agent_token(None)
    issued = await agent_service.enrol(session, token=token, name="cli-agent")
    assert issued is not None
