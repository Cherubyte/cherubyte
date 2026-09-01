"""Agent enrolment and reporting.

Agents are machine clients: they cannot do an interactive login, so these
routes are never put behind Cloudflare Access. They carry a bearer key issued
at enrolment instead.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from cherubyte_protocol import (
    PROTOCOL_VERSION,
    AgentReport,
    EnrolRequest,
    EnrolResponse,
    ReportAck,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Agent, HostTempSample, WanSample, iso_utc, utcnow
from ..services import agent_release
from ..services import agents as agent_service
from ..services import wan, wol
from ..scheduler import note_report
from ..services.monitor import ingest_report
from .deps import current_account, enforce_access

logger = logging.getLogger("cherubyte.api.agents")

router = APIRouter(prefix="/agents", tags=["agents"])


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        return ""
    return authorization[7:].strip()


@router.post("/enrol", response_model=EnrolResponse)
async def enrol_agent(payload: EnrolRequest, session: AsyncSession = Depends(get_session)):
    issued = await agent_service.enrol(
        session, token=payload.token, name=payload.name, version=payload.version
    )
    if issued is None:
        # One message for every rejection reason: telling an unenrolled caller
        # whether a token is unknown, spent or merely expired is free
        # reconnaissance.
        raise HTTPException(403, "Invalid enrolment token")
    agent, key = issued
    await session.commit()
    return EnrolResponse(agent_id=agent.id, key=key, name=agent.name)


@router.post("/{agent_id}/report", response_model=ReportAck)
async def receive_report(
    agent_id: int,
    report: AgentReport,
    request: Request,
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
):
    agent = await agent_service.authenticate(session, agent_id, _bearer(authorization))
    if agent is None:
        raise HTTPException(401, "Unknown agent or invalid key")

    if report.protocol_version != PROTOCOL_VERSION:
        # Refuse rather than half-read it: a rejected report is visible in both
        # logs, a partially understood one is invisible in both.
        raise HTTPException(
            409,
            f"Protocol version {report.protocol_version} not supported "
            f"(this panel speaks {PROTOCOL_VERSION})",
        )

    agent.last_seen = utcnow()
    agent.last_hosts = len(report.hosts)
    agent.last_fingerprints = report.dhcp_fingerprints
    agent.last_healthy = report.healthy
    if request.client is not None:
        agent.last_ip = request.client.host
    agent.health_port = report.health_port or 1002
    agent_service.set_subnets(agent, report.subnets)

    # If Sweep was pressed and we could not reach the agent directly, tell it
    # now (on this ack) and clear the request so it fires exactly once.
    wants_sweep = bool(agent.scan_requested)
    agent.scan_requested = False

    for sample in report.wan:
        session.add(
            WanSample(
                ok=sample.ok,
                latency_ms=sample.latency_ms,
                target=sample.target,
                timestamp=sample.at or utcnow(),
            )
        )
        if sample.public_ip:
            agent.public_ip = sample.public_ip
            agent.public_ip_at = sample.at or utcnow()

    if report.host_temp_c is not None:
        session.add(
            HostTempSample(
                agent_id=agent.id,
                temp_c=report.host_temp_c,
                timestamp=report.sent_at or utcnow(),
            )
        )
    await session.commit()
    await wan.record(report.wan)

    note_report()
    result = await ingest_report(report, agent_name=agent.name, agent_id=agent.id)

    # Wake-on-LAN: hand every agent reporting in the pickup window the queued
    # MACs; the one on the target's segment reaches its NIC.
    wake_macs = await wol.take_pending(session)
    await session.commit()

    # The ack carries the configuration the agent should be running, so an
    # install needs nothing but a panel URL and a token.
    return ReportAck(
        ok=True,
        found=result.get("found", 0),
        degraded=bool(result.get("degraded")),
        config=agent_service.desired_config(),
        scan_now=wants_sweep,
        wake=wake_macs,
    )


@router.get("")
async def list_agents(
    session: AsyncSession = Depends(get_session),
    _=Depends(current_account),
):
    rows = (await session.execute(select(Agent).order_by(Agent.id))).scalars().all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "version": a.version,
            "enabled": a.enabled,
            "subnets": agent_service.get_subnets(a),
            "last_seen": iso_utc(a.last_seen),
            "last_hosts": a.last_hosts,
            "last_fingerprints": a.last_fingerprints,
            "last_healthy": a.last_healthy,
            "public_ip": a.public_ip,
            "public_ip_at": iso_utc(a.public_ip_at),
        }
        for a in rows
    ]


@router.get("/release")
async def agent_release_info(_=Depends(current_account)):
    """The latest agent build the panel can hand out — version, per-platform
    download links (served by the panel itself, see below), and the fallbacks."""
    info = await agent_release.latest()
    return {
        "tag": info["tag"],
        "published_at": info["published_at"],
        "platforms": [p for p in agent_release.PLATFORMS if p in info["assets"]],
        "checked_at": info["checked_at"],
        "error": info["error"],
        "repo_url": info["repo_url"],
        "docker_image": info["docker_image"],
    }


@router.get("/download/{platform}")
async def agent_download(platform: str, _=Depends(current_account)):
    """Stream the agent binary for `platform` from the panel's own origin."""
    path = await agent_release.asset_path(platform)
    if path is None:
        raise HTTPException(
            404,
            "No agent build available for this platform yet — "
            f"see {agent_release.REPO_URL}/releases",
        )
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=agent_release.DOWNLOAD_NAME[platform],
    )


@router.get("/installer/{platform}")
async def agent_installer(platform: str, _=Depends(current_account)):
    """The per-platform installer script, proxied from the agent repo — so a
    native install is `curl <panel>/…/installer/linux | sudo bash -s -- …`."""
    script = await agent_release.installer_script(platform)
    if script is None:
        raise HTTPException(404, "No installer for this platform.")
    media = "text/plain" if platform == "windows" else "text/x-shellscript"
    return Response(script, media_type=media)


@router.post("/tokens")
async def create_token(
    label: str | None = None,
    session: AsyncSession = Depends(get_session),
    _=Depends(enforce_access),
):
    """Mint an enrolment token to paste into an agent's environment."""
    token = await agent_service.issue_token(session, label)
    await session.commit()
    return {"token": token, "expires_in_hours": 24}


@router.delete("/{agent_id}", status_code=204)
async def remove_agent(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _=Depends(enforce_access),
):
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    await session.delete(agent)
    await session.commit()
