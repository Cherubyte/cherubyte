from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from ..config import settings as cfg
from ..database import engine, get_session
from ..models import Setting
from ..schemas import SettingsIn, SettingsOut, SubnetCfg
from ..scheduler import reschedule_digest
from ..services import (
    action_tokens,
    agents as agent_service,
    alerts,
    backup as backup_service,
    fingerbank,
    mqtt,
    notify,
    ntfy,
    retention,
    telegram,
)
from ..services import update as update_service
from .deps import require_admin

logger = logging.getLogger("cherubyte.api.settings")

router = APIRouter(prefix="/settings", tags=["settings"])

_INT_KEYS = (
    "mqtt_port",
    "wan_interval_seconds",
    "weekly_summary_weekday",
    "weekly_summary_hour",
    "scan_interval_seconds",
    "offline_after_seconds",
    "identify_interval_seconds",
    "retention_days",
    "ntfy_priority",
)
_BOOL_KEYS = (
    "ntfy_enabled",
    "telegram_enabled",
    "mqtt_enabled",
    "wan_enabled",
    "weekly_summary_enabled",
    "metrics_enabled",
    "enable_snmp",
    "topology_enabled",
)

_PERSISTED = (
    *_INT_KEYS,
    *_BOOL_KEYS,
    "subnet",
    "telegram_bot_token",
    "telegram_chat_id",
    "ntfy_server",
    "ntfy_topic",
    "ntfy_token",
    "ntfy_username",
    "ntfy_password",
    "fingerbank_api_key",
    "alert_policy",
    "quiet_hours_start",
    "quiet_hours_end",
    "public_base_url",
    "dhcp_allowlist",
    "risky_ports_ignore",
    "action_secret",
    "mqtt_host",
    "mqtt_username",
    "mqtt_password",
    "mqtt_base_topic",
    "mqtt_discovery_prefix",
    "wan_target",
    "metrics_token",
    "snmp_community",
)


def _push_runtime() -> None:
    """Hand the current config to the notification services."""
    telegram.configure(
        cfg.telegram_bot_token, cfg.telegram_chat_id, enabled=cfg.telegram_enabled
    )
    ntfy.configure(
        server=cfg.ntfy_server,
        topic=cfg.ntfy_topic,
        token=cfg.ntfy_token,
        username=cfg.ntfy_username,
        password=cfg.ntfy_password,
        priority=cfg.ntfy_priority,
        enabled=cfg.ntfy_enabled,
    )


async def _load_from_db(session: AsyncSession) -> None:
    res = await session.execute(select(Setting))
    for row in res.scalars():
        if row.key in _INT_KEYS:
            setattr(cfg, row.key, int(row.value))
        elif row.key == "subnets":
            try:
                cfg.subnets = json.loads(row.value or "[]")
            except (ValueError, TypeError):
                cfg.subnets = []
        elif row.key in _BOOL_KEYS:
            setattr(cfg, row.key, row.value.lower() in {"1", "true", "yes", "on"})
        elif row.key == "action_secret":
            action_tokens.configure(row.value)
        elif row.key in _PERSISTED:
            setattr(cfg, row.key, row.value)
    _push_runtime()


def _clean_subnets(raw: list[SubnetCfg]) -> list[dict]:
    out: list[dict] = []
    for entry in raw:
        cidr = (entry.cidr or "").strip()
        if not cidr:
            continue
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            raise HTTPException(422, f"Invalid subnet: {cidr}") from None
        out.append({"cidr": str(net), "label": (entry.label or "").strip()})
    return out


async def _set(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value


def _current(history: dict[str, int] | None = None) -> SettingsOut:
    history = history or {}
    return SettingsOut(
        subnet=cfg.subnet or "",
        subnets=[SubnetCfg(**s) for s in cfg.subnets],
        scan_interval_seconds=cfg.scan_interval_seconds,
        offline_after_seconds=cfg.offline_after_seconds,
        identify_interval_seconds=cfg.identify_interval_seconds,
        retention_days=cfg.retention_days,
        stored_events=history.get("events", 0),
        stored_connections=history.get("connections", 0),
        telegram_enabled=telegram.is_enabled(),
        telegram_configured=telegram.is_configured(),
        telegram_token_saved=bool(cfg.telegram_bot_token),
        telegram_chat_id=cfg.telegram_chat_id or None,
        ntfy_configured=ntfy.is_configured(),
        ntfy_enabled=ntfy.is_enabled(),
        ntfy_server=ntfy.server_url(),
        ntfy_topic=ntfy.topic(),
        ntfy_username=cfg.ntfy_username or "",
        ntfy_priority=ntfy.priority(),
        ntfy_auth_configured=ntfy.has_auth(),
        fingerbank_configured=bool(cfg.fingerbank_api_key),
        dhcp_fingerprints=history.get("fingerprints", 0),
        alert_policy=alerts.effective_policy(),
        quiet_hours_start=cfg.quiet_hours_start or "",
        quiet_hours_end=cfg.quiet_hours_end or "",
        dhcp_allowlist=cfg.dhcp_allowlist or "",
        risky_ports_ignore=cfg.risky_ports_ignore or "",
        alert_kinds=[
            {"key": k.key, "label": k.label, "urgent": k.urgent} for k in alerts.KINDS
        ],
        public_base_url=cfg.public_base_url or "",
        notification_actions_ready=bool(cfg.public_base_url),
        mqtt_enabled=cfg.mqtt_enabled,
        mqtt_host=cfg.mqtt_host or "",
        mqtt_port=cfg.mqtt_port,
        mqtt_username=cfg.mqtt_username or "",
        mqtt_base_topic=cfg.mqtt_base_topic or "cherubyte",
        mqtt_discovery_prefix=cfg.mqtt_discovery_prefix or "homeassistant",
        mqtt_auth_configured=bool(cfg.mqtt_password),
        wan_enabled=cfg.wan_enabled,
        wan_target=cfg.wan_target or "1.1.1.1",
        wan_interval_seconds=cfg.wan_interval_seconds,
        metrics_enabled=cfg.metrics_enabled,
        metrics_token_set=bool(cfg.metrics_token),
        metrics_path="/api/metrics",
        enable_snmp=cfg.enable_snmp,
        snmp_community=cfg.snmp_community or "public",
        topology_enabled=cfg.topology_enabled,
        weekly_summary_enabled=cfg.weekly_summary_enabled,
        weekly_summary_weekday=cfg.weekly_summary_weekday,
        weekly_summary_hour=cfg.weekly_summary_hour,
    )


@router.get("", response_model=SettingsOut)
async def get_settings(session: AsyncSession = Depends(get_session)):
    return _current(await retention.counts(session))


@router.patch("", response_model=SettingsOut)
async def update_settings(
    payload: SettingsIn, session: AsyncSession = Depends(get_session)
):
    data = payload.model_dump(exclude_unset=True)

    # Scan cadence is the agent's to run, but the panel stores it: an agent asks
    # the panel for its configuration, so this stays the one place to set it.
    if "scan_interval_seconds" in data and data["scan_interval_seconds"]:
        secs = max(15, int(data["scan_interval_seconds"]))
        cfg.scan_interval_seconds = secs
        await _set(session, "scan_interval_seconds", str(secs))
    if "offline_after_seconds" in data and data["offline_after_seconds"]:
        secs = max(30, int(data["offline_after_seconds"]))
        cfg.offline_after_seconds = secs
        await _set(session, "offline_after_seconds", str(secs))
    if (
        "identify_interval_seconds" in data
        and data["identify_interval_seconds"] is not None
    ):
        secs = max(0, int(data["identify_interval_seconds"]))
        cfg.identify_interval_seconds = secs
        await _set(session, "identify_interval_seconds", str(secs))
    if "retention_days" in data and data["retention_days"] is not None:
        days = max(0, int(data["retention_days"]))
        cfg.retention_days = days
        await _set(session, "retention_days", str(days))
    if "subnet" in data:
        cfg.subnet = data["subnet"] or ""
        await _set(session, "subnet", cfg.subnet)
    if "subnets" in data and payload.subnets is not None:
        cfg.subnets = _clean_subnets(payload.subnets)
        await _set(session, "subnets", json.dumps(cfg.subnets))
    if "telegram_enabled" in data:
        cfg.telegram_enabled = bool(data["telegram_enabled"])
        await _set(session, "telegram_enabled", "true" if cfg.telegram_enabled else "false")
    if "telegram_bot_token" in data:
        cfg.telegram_bot_token = data["telegram_bot_token"] or ""
        await _set(session, "telegram_bot_token", cfg.telegram_bot_token)
    if "telegram_chat_id" in data:
        cfg.telegram_chat_id = data["telegram_chat_id"] or ""
        await _set(session, "telegram_chat_id", cfg.telegram_chat_id)
    if "ntfy_enabled" in data:
        cfg.ntfy_enabled = bool(data["ntfy_enabled"])
        await _set(session, "ntfy_enabled", "true" if cfg.ntfy_enabled else "false")
    if "ntfy_server" in data:
        cfg.ntfy_server = (data["ntfy_server"] or "").strip() or ntfy.DEFAULT_SERVER
        await _set(session, "ntfy_server", cfg.ntfy_server)
    if "ntfy_topic" in data:
        cfg.ntfy_topic = (data["ntfy_topic"] or "").strip()
        await _set(session, "ntfy_topic", cfg.ntfy_topic)
    if "ntfy_token" in data:
        cfg.ntfy_token = (data["ntfy_token"] or "").strip()
        await _set(session, "ntfy_token", cfg.ntfy_token)
    if "ntfy_username" in data:
        cfg.ntfy_username = (data["ntfy_username"] or "").strip()
        await _set(session, "ntfy_username", cfg.ntfy_username)
    if "ntfy_password" in data:
        cfg.ntfy_password = data["ntfy_password"] or ""
        await _set(session, "ntfy_password", cfg.ntfy_password)
    if "ntfy_priority" in data and data["ntfy_priority"]:
        prio = min(5, max(1, int(data["ntfy_priority"])))
        cfg.ntfy_priority = prio
        await _set(session, "ntfy_priority", str(prio))
    if "alert_policy" in data and data["alert_policy"] is not None:
        import json as _json

        cfg.alert_policy = _json.dumps(data["alert_policy"])
        await _set(session, "alert_policy", cfg.alert_policy)
    for key in (
        "quiet_hours_start",
        "quiet_hours_end",
        "public_base_url",
        "dhcp_allowlist",
        "risky_ports_ignore",
    ):
        if key in data:
            value = (data[key] or "").strip()
            setattr(cfg, key, value)
            await _set(session, key, value)
    if "public_base_url" in data and cfg.public_base_url:
        # the buttons only work if a signing secret exists; make one now
        await _set(session, "action_secret", action_tokens.ensure_secret())

    mqtt_touched = False
    for key in (
        "mqtt_host",
        "mqtt_username",
        "mqtt_password",
        "mqtt_base_topic",
        "mqtt_discovery_prefix",
    ):
        if key in data:
            value = (data[key] or "").strip()
            setattr(cfg, key, value)
            await _set(session, key, value)
            mqtt_touched = True
    if "mqtt_port" in data and data["mqtt_port"]:
        cfg.mqtt_port = int(data["mqtt_port"])
        await _set(session, "mqtt_port", str(cfg.mqtt_port))
        mqtt_touched = True
    if "mqtt_enabled" in data and data["mqtt_enabled"] is not None:
        cfg.mqtt_enabled = bool(data["mqtt_enabled"])
        await _set(session, "mqtt_enabled", "true" if cfg.mqtt_enabled else "false")
        mqtt_touched = True

    if "wan_enabled" in data and data["wan_enabled"] is not None:
        cfg.wan_enabled = bool(data["wan_enabled"])
        await _set(session, "wan_enabled", "true" if cfg.wan_enabled else "false")
    if "wan_target" in data:
        cfg.wan_target = (data["wan_target"] or "").strip() or "1.1.1.1"
        await _set(session, "wan_target", cfg.wan_target)
    if "wan_interval_seconds" in data and data["wan_interval_seconds"]:
        secs = max(30, int(data["wan_interval_seconds"]))
        cfg.wan_interval_seconds = secs
        await _set(session, "wan_interval_seconds", str(secs))

    if "metrics_enabled" in data and data["metrics_enabled"] is not None:
        cfg.metrics_enabled = bool(data["metrics_enabled"])
        await _set(session, "metrics_enabled", "true" if cfg.metrics_enabled else "false")
    if "metrics_token" in data:
        cfg.metrics_token = (data["metrics_token"] or "").strip()
        await _set(session, "metrics_token", cfg.metrics_token)

    if "enable_snmp" in data and data["enable_snmp"] is not None:
        cfg.enable_snmp = bool(data["enable_snmp"])
        await _set(session, "enable_snmp", "true" if cfg.enable_snmp else "false")
    if "snmp_community" in data:
        cfg.snmp_community = (data["snmp_community"] or "").strip() or "public"
        await _set(session, "snmp_community", cfg.snmp_community)
    if "topology_enabled" in data and data["topology_enabled"] is not None:
        cfg.topology_enabled = bool(data["topology_enabled"])
        await _set(session, "topology_enabled", "true" if cfg.topology_enabled else "false")

    digest_touched = False
    if "weekly_summary_enabled" in data and data["weekly_summary_enabled"] is not None:
        cfg.weekly_summary_enabled = bool(data["weekly_summary_enabled"])
        await _set(
            session,
            "weekly_summary_enabled",
            "true" if cfg.weekly_summary_enabled else "false",
        )
    if "weekly_summary_weekday" in data and data["weekly_summary_weekday"] is not None:
        cfg.weekly_summary_weekday = max(0, min(6, int(data["weekly_summary_weekday"])))
        await _set(session, "weekly_summary_weekday", str(cfg.weekly_summary_weekday))
        digest_touched = True
    if "weekly_summary_hour" in data and data["weekly_summary_hour"] is not None:
        cfg.weekly_summary_hour = max(0, min(23, int(data["weekly_summary_hour"])))
        await _set(session, "weekly_summary_hour", str(cfg.weekly_summary_hour))
        digest_touched = True
    if digest_touched:
        reschedule_digest(cfg.weekly_summary_weekday, cfg.weekly_summary_hour)

    if "fingerbank_api_key" in data:
        cfg.fingerbank_api_key = data["fingerbank_api_key"] or ""
        await _set(session, "fingerbank_api_key", cfg.fingerbank_api_key)
        fingerbank.reset_cache()

    _push_runtime()
    await session.commit()
    if mqtt_touched:
        mqtt.restart()
    return _current(await retention.counts(session))


@router.post("/telegram/test")
async def test_telegram():
    ok = await telegram.send("✅ Cherubyte: Telegram test notification.")
    return {"ok": ok}


@router.post("/purge-history", response_model=SettingsOut)
async def purge_history(session: AsyncSession = Depends(get_session)):
    """Apply the retention policy now instead of waiting for the daily job."""
    await retention.purge(session)
    await session.commit()
    return _current(await retention.counts(session))


@router.post("/digest/test")
async def test_digest(session: AsyncSession = Depends(get_session)):
    """Build and send the weekly summary now, whatever the schedule says."""
    from ..services import digest

    data = await digest.collect(session)
    sent = await notify.broadcast(
        "weekly_summary",
        "Cherubyte weekly digest",
        digest.format_lines(data),
        emoji="📊",
        tags=["bar_chart"],
        prio=2,
    )
    return {"ok": bool(sent), "channels": sent, "summary": digest.format_lines(data)}


@router.post("/fingerbank/test")
async def test_fingerbank():
    """Check that the configured Fingerbank key is accepted and reachable."""
    return await fingerbank.check()


@router.post("/ntfy/test")
async def test_ntfy():
    ok = await ntfy.send(
        "ntfy test notification — if you got this, everything is working.",
        title="✅ Cherubyte",
        tags=["white_check_mark"],
    )
    return {"ok": ok}


# --- update check (admin to trigger a check or apply one; anyone can read) --


def _update_payload() -> dict:
    st = update_service.status()
    latest = st["latest"]
    return {
        **st,
        "deploy_mode": update_service.deploy_mode(),
        "repo_url": update_service.REPO_URL,
        "update_available": bool(latest and update_service.is_newer(latest, st["current"])),
        "apply": update_service.apply_status(),
    }


@router.get("/update")
async def get_update():
    return _update_payload()


@router.post("/update/check")
async def check_update(_=Depends(require_admin)):
    await update_service.check()
    return _update_payload()


@router.post("/update/apply")
async def apply_update(_=Depends(require_admin)):
    st = update_service.status()
    if not st["latest"]:
        raise HTTPException(400, "Check for updates first")
    if update_service.deploy_mode() != "git":
        raise HTTPException(
            409,
            "This is a container deployment — pull the new image instead "
            "(docker compose pull panel && docker compose up -d panel).",
        )
    try:
        await update_service.apply()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from None
    return _update_payload()


# --- backup / restore (admin) --------------------------------------------

_MAX_RESTORE_BYTES = 512 * 1024 * 1024


@router.get("/backup")
async def download_backup(_=Depends(require_admin)):
    """A gzipped tar of the database and the uploads. Admin only."""
    tmp = Path(tempfile.mkdtemp(prefix="cherubyte-backup-")) / backup_service.default_name()
    try:
        backup_service.create(tmp)
    except FileNotFoundError as exc:
        raise HTTPException(409, str(exc)) from None
    return FileResponse(
        tmp,
        media_type="application/gzip",
        filename=tmp.name,
        background=BackgroundTask(lambda: _cleanup(tmp)),
    )


def _cleanup(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
        path.parent.rmdir()
    except OSError:
        pass


@router.post("/restore")
async def restore_backup(file: UploadFile, _=Depends(require_admin)):
    """Replace the database and uploads with a backup, then exit to reload it.

    Every supported deployment restarts the process automatically (systemd
    `Restart=always`, Docker `restart: unless-stopped`). A hand-run `start.sh`
    does not — restart it yourself.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="cherubyte-restore-"))
    staged = tmp_dir / "upload.tar.gz"
    size = 0
    with staged.open("wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > _MAX_RESTORE_BYTES:
                _cleanup(staged)
                raise HTTPException(413, "backup file too large")
            out.write(chunk)

    try:
        summary = backup_service.restore(staged)
    except backup_service.BackupError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        _cleanup(staged)

    async def _reload() -> None:
        await asyncio.sleep(1.0)
        logger.warning("Exiting to reload the restored database")
        await engine.dispose()
        os._exit(0)

    asyncio.create_task(_reload())
    return {"ok": True, "restarting": True, **summary}
