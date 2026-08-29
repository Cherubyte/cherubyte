"""MQTT publishing, with Home Assistant auto-discovery.

Presence is already computed here; publishing it turns NetScan into a presence
source the rest of the house can use. Each person becomes a HA `device_tracker`
and each device a connectivity `binary_sensor`, created automatically through
the discovery topics — no YAML on the Home Assistant side.

Everything is best-effort: a broker that is down must never hold up a scan.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from ..config import settings

logger = logging.getLogger("netscan.mqtt")

_QUEUE: asyncio.Queue | None = None
_WORKER: asyncio.Task | None = None
_announced: set[str] = set()


def is_configured() -> bool:
    return bool(settings.mqtt_enabled and settings.mqtt_host)


def slug(value: str) -> str:
    """A topic/object_id-safe token: MQTT wildcards and spaces break both."""
    out = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip()).strip("_").lower()
    return out or "unknown"


def base_topic() -> str:
    return (settings.mqtt_base_topic or "netscan").strip("/")


def availability_topic() -> str:
    return f"{base_topic()}/status"


def user_topic(user_id: int) -> str:
    return f"{base_topic()}/user/{user_id}/state"


def device_topic(device_id: int) -> str:
    return f"{base_topic()}/device/{device_id}/state"


def _origin() -> dict:
    return {"name": "NetScan", "sw_version": "0.1.0"}


def user_discovery(user_id: int, name: str) -> tuple[str, dict]:
    """(topic, payload) that makes Home Assistant create a person tracker."""
    object_id = f"netscan_user_{user_id}"
    topic = f"{settings.mqtt_discovery_prefix}/device_tracker/{object_id}/config"
    payload = {
        "name": name,
        "unique_id": object_id,
        "state_topic": user_topic(user_id),
        "payload_home": "home",
        "payload_not_home": "not_home",
        "source_type": "router",
        "availability_topic": availability_topic(),
        "device": {
            "identifiers": ["netscan"],
            "name": "NetScan",
            "manufacturer": "NetScan",
        },
        "origin": _origin(),
    }
    return topic, payload


def device_discovery(device_id: int, name: str) -> tuple[str, dict]:
    object_id = f"netscan_device_{device_id}"
    topic = f"{settings.mqtt_discovery_prefix}/binary_sensor/{object_id}/config"
    payload = {
        "name": name,
        "unique_id": object_id,
        "state_topic": device_topic(device_id),
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "connectivity",
        "availability_topic": availability_topic(),
        "device": {
            "identifiers": ["netscan"],
            "name": "NetScan",
            "manufacturer": "NetScan",
        },
        "origin": _origin(),
    }
    return topic, payload


def publish(topic: str, payload: str | dict, *, retain: bool = True) -> None:
    """Queue a message. Never blocks and never raises — callers are on the scan path."""
    if not is_configured() or _QUEUE is None:
        return
    body = json.dumps(payload) if isinstance(payload, dict) else payload
    try:
        _QUEUE.put_nowait((topic, body, retain))
    except asyncio.QueueFull:
        logger.warning("MQTT queue full; dropping %s", topic)


def announce_user(user_id: int, name: str) -> None:
    key = f"user:{user_id}"
    if key in _announced:
        return
    topic, payload = user_discovery(user_id, name)
    publish(topic, payload)
    _announced.add(key)


def announce_device(device_id: int, name: str) -> None:
    key = f"device:{device_id}"
    if key in _announced:
        return
    topic, payload = device_discovery(device_id, name)
    publish(topic, payload)
    _announced.add(key)


def publish_user_presence(user_id: int, name: str, present: bool) -> None:
    announce_user(user_id, name)
    publish(user_topic(user_id), "home" if present else "not_home")


def publish_device_state(device_id: int, name: str, online: bool) -> None:
    announce_device(device_id, name)
    publish(device_topic(device_id), "ON" if online else "OFF")


def forget_announcements() -> None:
    """Re-announce discovery on the next publish (after a config change)."""
    _announced.clear()


async def _run() -> None:
    import aiomqtt

    assert _QUEUE is not None
    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_host,
                port=settings.mqtt_port,
                username=settings.mqtt_username or None,
                password=settings.mqtt_password or None,
                will=aiomqtt.Will(availability_topic(), b"offline", retain=True),
            ) as client:
                logger.info("MQTT connected to %s:%s", settings.mqtt_host, settings.mqtt_port)
                await client.publish(availability_topic(), b"online", retain=True)
                forget_announcements()  # a fresh session needs discovery again
                while True:
                    topic, body, retain = await _QUEUE.get()
                    await client.publish(topic, body.encode(), retain=retain)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001  (aiomqtt raises many shapes)
            logger.warning("MQTT connection lost (%s); retrying in 30s", exc)
            await asyncio.sleep(30)


def start() -> None:
    global _QUEUE, _WORKER
    if not is_configured() or _WORKER is not None:
        return
    _QUEUE = asyncio.Queue(maxsize=1000)
    _WORKER = asyncio.create_task(_run())
    logger.info("MQTT publisher started")


def stop() -> None:
    global _QUEUE, _WORKER
    if _WORKER is not None:
        _WORKER.cancel()
    _WORKER = None
    _QUEUE = None
    _announced.clear()


def restart() -> None:
    stop()
    start()
