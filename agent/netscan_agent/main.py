"""The agent process: sweep, report, repeat.

It holds no database and serves no UI. The only thing it listens on is a health
endpoint, so a container runtime can tell a wedged agent from a working one.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import dhcp_sniffer, reporter
from .collector import collect
from .config import apply_config, settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("netscan.agent")

_state: dict = {
    "enrolled": False,
    "last_report_at": None,
    "last_report_ok": None,
    "last_hosts": None,
    "last_error": None,
}


async def _ensure_enrolled() -> tuple[int, str] | None:
    stored = reporter.load_credentials()
    if stored:
        _state["enrolled"] = True
        return stored
    try:
        issued = await reporter.enrol()
    except reporter.NotEnrolled as exc:
        _state["last_error"] = str(exc)
        logger.error("%s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        _state["last_error"] = f"enrolment failed: {exc}"
        logger.warning("Enrolment attempt failed: %s", exc)
        return None
    _state["enrolled"] = True
    _state["last_error"] = None
    return issued


async def _cycle() -> None:
    credentials = await _ensure_enrolled()
    if credentials is None:
        return
    agent_id, key = credentials
    report = await collect()
    ack = await reporter.send(report, agent_id, key)
    if ack is not None:
        changed = apply_config(ack.config)
        if changed:
            logger.info("Panel configuration applied: %s", ", ".join(sorted(changed)))
    _state.update(
        last_report_at=datetime.now(timezone.utc).isoformat(),
        last_report_ok=ack is not None,
        last_hosts=len(report.hosts),
    )
    logger.info(
        "Reported %d hosts (%s)",
        len(report.hosts),
        "accepted" if ack is not None else "refused",
    )


async def _loop() -> None:
    # a short delay so the panel has a chance to be up in a compose start
    await asyncio.sleep(3)
    while True:
        try:
            await _cycle()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _state["last_error"] = str(exc)
            logger.exception("Cycle failed")
        await asyncio.sleep(max(15, settings.scan_interval_seconds))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.enable_dhcp_sniffer:
        dhcp_sniffer.start()
    task = asyncio.create_task(_loop())
    logger.info("NetScan agent up; panel=%s", reporter.panel_base())
    yield
    task.cancel()
    dhcp_sniffer.stop()


app = FastAPI(title="NetScan agent", version=reporter.AGENT_VERSION, lifespan=lifespan)


@app.get("/health")
async def health():
    """Healthy means the loop is running and the panel accepted the last report.

    Reporting healthy while every report is being refused would hide the one
    failure that makes the agent useless.
    """
    ok = _state["enrolled"] and _state["last_report_ok"] is not False
    return JSONResponse(
        {"status": "ok" if ok else "degraded", **_state},
        status_code=200 if ok else 503,
    )
