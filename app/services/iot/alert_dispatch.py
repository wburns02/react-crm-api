"""IoT alert dispatch — creates IoTAlert rows, sends SMS, broadcasts WebSocket events.

Reuses existing Twilio SMS pipeline (Message rows + APScheduler send loop) and
WebSocket broadcast manager — no new comms plumbing.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.iot import IoTAlert, IoTDevice
from app.models.customer import Customer
from app.models.technician import Technician
from app.services.iot.rule_engine import RuleHit
from app.services.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)


async def _get_oncall_phone(db: AsyncSession) -> list[str]:
    """Return phone numbers for on-call techs. v1: all active techs.

    v2: respect on-call rotation schedule.
    """
    q = select(Technician).where(Technician.is_active.is_(True))
    techs = (await db.execute(q)).scalars().all()
    return [t.phone for t in techs if getattr(t, "phone", None)]


async def _get_homeowner_phone(db: AsyncSession, device: IoTDevice) -> str | None:
    if not device.customer_id:
        return None
    q = select(Customer).where(Customer.id == device.customer_id)
    customer = (await db.execute(q)).scalar_one_or_none()
    return getattr(customer, "phone", None) if customer else None


async def _send_sms(
    db: AsyncSession,
    to_phone: str,
    body: str,
) -> None:
    """Enqueue an SMS via the existing Message + APScheduler + Twilio pipeline.

    The APScheduler job that handles outbound SMS picks up rows where
    direction='outbound', message_type='sms', status='pending'.
    """
    try:
        from app.models.message import Message

        msg = Message(
            id=uuid.uuid4(),
            direction="outbound",
            message_type="sms",
            from_number=None,
            to_number=to_phone,
            content=body,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        db.add(msg)
    except Exception as e:
        logger.warning("Failed to enqueue IoT SMS to %s: %s", to_phone, e)


def _severity_recipients(severity: str) -> tuple[bool, bool]:
    """Return (notify_homeowner, notify_oncall) for a severity."""
    if severity == "critical":
        return True, True
    if severity == "high":
        return False, True
    return False, False


async def dispatch_rule_hits(
    db: AsyncSession,
    hits: list[RuleHit],
) -> list[IoTAlert]:
    """Create IoTAlert rows for each hit, send SMS, broadcast WebSocket."""
    if not hits:
        return []

    created_alerts: list[IoTAlert] = []
    devices_cache: dict[str, IoTDevice] = {}

    for hit in hits:
        device_q = select(IoTDevice).where(IoTDevice.id == hit.device_id)
        device = devices_cache.get(str(hit.device_id))
        if device is None:
            device = (await db.execute(device_q)).scalar_one_or_none()
            if device is None:
                continue
            devices_cache[str(hit.device_id)] = device

        alert = IoTAlert(
            id=uuid.uuid4(),
            device_id=hit.device_id,
            alert_type=hit.rule.alert_type,
            severity=hit.rule.severity,
            status="open",
            message=hit.message,
            trigger_payload=hit.trigger_payload,
            fired_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        created_alerts.append(alert)

        notify_homeowner, notify_oncall = _severity_recipients(hit.rule.severity)
        homeowner_phone = (
            await _get_homeowner_phone(db, device) if notify_homeowner else None
        )
        if notify_homeowner and homeowner_phone:
            await _send_sms(
                db,
                homeowner_phone,
                f"MAC Septic alert for your system: {hit.message}",
            )

        if notify_oncall:
            for tech_phone in await _get_oncall_phone(db):
                await _send_sms(
                    db,
                    tech_phone,
                    f"[IoT {hit.rule.severity.upper()}] {device.serial}: {hit.message}",
                )

        try:
            await ws_manager.broadcast_event(
                "iot_alert",
                {
                    "alert_id": str(alert.id),
                    "device_id": str(hit.device_id),
                    "alert_type": hit.rule.alert_type,
                    "severity": hit.rule.severity,
                    "message": hit.message,
                    "fired_at": alert.fired_at.isoformat(),
                },
            )
        except Exception as e:
            logger.warning("Failed to broadcast iot_alert: %s", e)

    await db.flush()
    return created_alerts
