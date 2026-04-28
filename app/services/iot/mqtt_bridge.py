"""IoT MQTT bridge — subscribes to device telemetry, persists, evaluates rules.

Connects to an MQTT broker (EMQX in production) over mTLS.
- Listens on `devices/+/telemetry`, `devices/+/heartbeat`, `devices/+/alarm`.
- Persists telemetry to iot_telemetry.
- Updates iot_devices.last_seen_at on every message.
- Calls rule engine + alert dispatch.

Configuration via env vars (none required by default — bridge stays disabled):
- IOT_MQTT_ENABLED=true to start the bridge
- IOT_MQTT_BROKER_HOST, IOT_MQTT_BROKER_PORT, IOT_MQTT_BROKER_TLS=true
- IOT_MQTT_CLIENT_CERT, IOT_MQTT_CLIENT_KEY, IOT_MQTT_CA_CERT (file paths or PEM)
- IOT_MQTT_USERNAME, IOT_MQTT_PASSWORD (fallback if no mTLS)

If the bridge fails to connect, it logs and retries — does not crash the app.
"""
import asyncio
import json
import logging
import os
import ssl
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.database import async_session_maker
from app.models.iot import IoTDevice, IoTTelemetry
from app.services.iot.rule_engine import (
    evaluate_telemetry,
    evaluate_missing_heartbeats,
)
from app.services.iot.alert_dispatch import dispatch_rule_hits

logger = logging.getLogger(__name__)


_bridge_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def _bridge_enabled() -> bool:
    return os.environ.get("IOT_MQTT_ENABLED", "").lower() in ("1", "true", "yes")


def _broker_config() -> dict:
    return {
        "host": os.environ.get("IOT_MQTT_BROKER_HOST", "localhost"),
        "port": int(os.environ.get("IOT_MQTT_BROKER_PORT", "8883")),
        "tls": os.environ.get("IOT_MQTT_BROKER_TLS", "true").lower() in ("1", "true", "yes"),
        "client_cert": os.environ.get("IOT_MQTT_CLIENT_CERT"),
        "client_key": os.environ.get("IOT_MQTT_CLIENT_KEY"),
        "ca_cert": os.environ.get("IOT_MQTT_CA_CERT"),
        "username": os.environ.get("IOT_MQTT_USERNAME"),
        "password": os.environ.get("IOT_MQTT_PASSWORD"),
        "client_id": os.environ.get("IOT_MQTT_CLIENT_ID", "react-crm-bridge"),
    }


def _parse_topic(topic: str) -> tuple[Optional[str], Optional[str]]:
    """devices/{uuid}/{kind} → (uuid, kind). Returns (None, None) on mismatch."""
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "devices":
        return None, None
    return parts[1], parts[2]


async def _persist_telemetry(
    db, device: IoTDevice, payload: dict
) -> list[IoTTelemetry]:
    """Telemetry payload shape: {"time": iso8601, "readings": [{sensor_type, value, value_text, raw}]}"""
    when = payload.get("time")
    when_dt = (
        datetime.fromisoformat(when.replace("Z", "+00:00"))
        if when
        else datetime.now(timezone.utc)
    )
    records = []
    for r in payload.get("readings", []):
        rec = IoTTelemetry(
            id=uuid.uuid4(),
            device_id=device.id,
            time=when_dt,
            sensor_type=r.get("sensor_type", "unknown"),
            value_numeric=r.get("value"),
            value_text=r.get("value_text"),
            raw_payload=r.get("raw"),
        )
        db.add(rec)
        records.append(rec)
    device.last_seen_at = datetime.now(timezone.utc)
    return records


async def _persist_alarm_fire(
    db, device: IoTDevice, payload: dict
) -> Optional[IoTTelemetry]:
    """Alarm-fire payload: {"time": iso8601, "active": bool, "panel_signal": str}"""
    when = payload.get("time")
    when_dt = (
        datetime.fromisoformat(when.replace("Z", "+00:00"))
        if when
        else datetime.now(timezone.utc)
    )
    rec = IoTTelemetry(
        id=uuid.uuid4(),
        device_id=device.id,
        time=when_dt,
        sensor_type="oem_alarm",
        value_numeric=1.0 if payload.get("active") else 0.0,
        value_text=payload.get("panel_signal", "fire" if payload.get("active") else "clear"),
        raw_payload=payload,
    )
    db.add(rec)
    device.last_seen_at = datetime.now(timezone.utc)
    return rec


async def _on_message(topic: str, payload_bytes: bytes) -> None:
    device_uuid_str, kind = _parse_topic(topic)
    if not device_uuid_str:
        logger.warning("Ignoring unmatched topic: %s", topic)
        return

    try:
        device_uuid = uuid.UUID(device_uuid_str)
    except ValueError:
        logger.warning("Ignoring invalid device UUID in topic: %s", topic)
        return

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("Bad payload on %s: %s", topic, e)
        return

    async with async_session_maker() as db:
        try:
            device_q = select(IoTDevice).where(IoTDevice.id == device_uuid)
            device = (await db.execute(device_q)).scalar_one_or_none()
            if not device:
                logger.warning("Telemetry from unknown device %s", device_uuid_str)
                return

            if kind == "telemetry":
                recs = await _persist_telemetry(db, device, payload)
                await db.flush()
                all_hits = []
                for rec in recs:
                    hits = await evaluate_telemetry(db, device, rec)
                    all_hits.extend(hits)
                if all_hits:
                    await dispatch_rule_hits(db, all_hits)
            elif kind == "alarm":
                rec = await _persist_alarm_fire(db, device, payload)
                if rec:
                    await db.flush()
                    hits = await evaluate_telemetry(db, device, rec)
                    if hits:
                        await dispatch_rule_hits(db, hits)
            elif kind == "heartbeat":
                device.last_seen_at = datetime.now(timezone.utc)
            else:
                logger.info("Unhandled message kind '%s' on %s", kind, topic)

            await db.commit()
        except Exception as e:
            logger.exception("Error processing %s: %s", topic, e)
            await db.rollback()


async def _build_tls_context(cfg: dict) -> Optional[ssl.SSLContext]:
    if not cfg["tls"]:
        return None
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    if cfg["ca_cert"]:
        if cfg["ca_cert"].startswith("-----"):
            ctx.load_verify_locations(cadata=cfg["ca_cert"])
        else:
            ctx.load_verify_locations(cafile=cfg["ca_cert"])
    if cfg["client_cert"] and cfg["client_key"]:
        ctx.load_cert_chain(certfile=cfg["client_cert"], keyfile=cfg["client_key"])
    return ctx


async def _run_bridge_loop() -> None:
    """Main bridge loop — connects to broker, subscribes, dispatches messages.

    Uses aiomqtt if available; falls back to a no-op log if missing.
    """
    cfg = _broker_config()
    try:
        import aiomqtt
    except ImportError:
        logger.error(
            "aiomqtt not installed — IoT MQTT bridge disabled. "
            "Add 'aiomqtt>=2.0' to requirements.txt to enable."
        )
        return

    backoff = 5
    assert _stop_event is not None
    while not _stop_event.is_set():
        try:
            tls_ctx = await _build_tls_context(cfg)
            logger.info("IoT bridge connecting to %s:%s (tls=%s)",
                        cfg["host"], cfg["port"], cfg["tls"])
            client_kwargs = {
                "hostname": cfg["host"],
                "port": cfg["port"],
                "identifier": cfg["client_id"],
                "tls_context": tls_ctx,
            }
            if cfg["username"]:
                client_kwargs["username"] = cfg["username"]
                client_kwargs["password"] = cfg["password"]

            async with aiomqtt.Client(**client_kwargs) as client:
                logger.info("IoT bridge connected; subscribing to devices/+/+")
                await client.subscribe("devices/+/+")
                backoff = 5
                async for message in client.messages:
                    if _stop_event.is_set():
                        break
                    await _on_message(message.topic.value, message.payload)
        except Exception as e:
            logger.exception("IoT bridge error: %s — reconnecting in %ds", e, backoff)
            try:
                await asyncio.wait_for(_stop_event.wait(), timeout=backoff)
                if _stop_event.is_set():
                    break
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 300)


async def _heartbeat_check_loop() -> None:
    """Cron-driven check for missing heartbeats. Runs every 15 minutes."""
    interval = 900
    assert _stop_event is not None
    while not _stop_event.is_set():
        try:
            async with async_session_maker() as db:
                hits = await evaluate_missing_heartbeats(db)
                if hits:
                    await dispatch_rule_hits(db, hits)
                await db.commit()
        except Exception as e:
            logger.exception("Heartbeat check error: %s", e)
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def start_bridge() -> None:
    """Start the IoT MQTT bridge + heartbeat check loop. Idempotent."""
    global _bridge_task, _stop_event
    if _bridge_task and not _bridge_task.done():
        return
    if not _bridge_enabled():
        logger.info("IoT MQTT bridge disabled (set IOT_MQTT_ENABLED=true to start)")
        return

    _stop_event = asyncio.Event()

    async def _both():
        await asyncio.gather(_run_bridge_loop(), _heartbeat_check_loop())

    _bridge_task = asyncio.create_task(_both(), name="iot_mqtt_bridge")
    logger.info("IoT MQTT bridge started")


async def stop_bridge() -> None:
    global _bridge_task, _stop_event
    if _stop_event:
        _stop_event.set()
    if _bridge_task:
        try:
            await asyncio.wait_for(_bridge_task, timeout=10)
        except asyncio.TimeoutError:
            _bridge_task.cancel()
        _bridge_task = None
    _stop_event = None
    logger.info("IoT MQTT bridge stopped")
