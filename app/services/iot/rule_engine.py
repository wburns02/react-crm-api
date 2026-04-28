"""IoT rule engine v1 — threshold/rate-of-change/digital-high evaluation.

Evaluates active rules against incoming telemetry and returns alerts to fire.
v2 will add ML-based predictive rules.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.iot import (
    IoTAlertRule,
    IoTAlert,
    IoTDevice,
    IoTTelemetry,
)


class RuleHit:
    """Result of a rule evaluation that fired."""

    def __init__(
        self,
        rule: IoTAlertRule,
        device_id: UUID,
        message: str,
        trigger_payload: dict,
    ):
        self.rule = rule
        self.device_id = device_id
        self.message = message
        self.trigger_payload = trigger_payload


async def _is_in_cold_start(
    db: AsyncSession, device: IoTDevice, grace_hours: Optional[int]
) -> bool:
    """Suppress predictive rules for first N hours after device first sees data."""
    if not grace_hours:
        return False
    if device.last_seen_at is None:
        return True
    earliest_q = (
        select(IoTTelemetry.time)
        .where(IoTTelemetry.device_id == device.id)
        .order_by(IoTTelemetry.time)
        .limit(1)
    )
    earliest = (await db.execute(earliest_q)).scalar_one_or_none()
    if earliest is None:
        return True
    age_hours = (datetime.now(timezone.utc) - earliest).total_seconds() / 3600
    return age_hours < grace_hours


def _eval_threshold(
    rule: IoTAlertRule, value: Optional[float]
) -> bool:
    if value is None:
        return False
    threshold = rule.config.get("threshold")
    if threshold is None:
        return False
    if rule.rule_type == "threshold_gt":
        return value > threshold
    if rule.rule_type == "threshold_lt":
        return value < threshold
    return False


async def _eval_rate_of_change(
    db: AsyncSession,
    rule: IoTAlertRule,
    device_id: UUID,
    sensor_type: str,
    current_value: Optional[float],
) -> bool:
    if current_value is None:
        return False
    window_hours = rule.config.get("window_hours", 168)
    pct_threshold = rule.config.get("pct_change", 5.0)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    q = (
        select(IoTTelemetry.value_numeric)
        .where(
            and_(
                IoTTelemetry.device_id == device_id,
                IoTTelemetry.sensor_type == sensor_type,
                IoTTelemetry.time >= cutoff,
                IoTTelemetry.value_numeric.is_not(None),
            )
        )
        .order_by(IoTTelemetry.time)
        .limit(1)
    )
    baseline = (await db.execute(q)).scalar_one_or_none()
    if baseline is None or baseline == 0:
        return False
    pct_delta = ((current_value - baseline) / abs(baseline)) * 100
    direction = rule.config.get("direction", "up")
    if direction == "up":
        return pct_delta > pct_threshold
    if direction == "down":
        return pct_delta < -pct_threshold
    return abs(pct_delta) > pct_threshold


def _eval_digital_high(value: Optional[float], value_text: Optional[str]) -> bool:
    if value is not None and value > 0.5:
        return True
    if value_text and value_text.lower() in ("high", "1", "true", "on", "fire"):
        return True
    return False


def _format_message(template: Optional[str], device: IoTDevice, value: Optional[float], default: str) -> str:
    if not template:
        return default
    try:
        return template.format(
            device_serial=device.serial,
            value=value,
            install_type=device.install_type,
        )
    except (KeyError, IndexError):
        return template


async def evaluate_telemetry(
    db: AsyncSession,
    device: IoTDevice,
    telemetry_record: IoTTelemetry,
) -> list[RuleHit]:
    """Evaluate every active rule against a single telemetry record."""
    rules_q = select(IoTAlertRule).where(IoTAlertRule.active.is_(True))
    if telemetry_record.sensor_type:
        rules_q = rules_q.where(
            (IoTAlertRule.sensor_type.is_(None))
            | (IoTAlertRule.sensor_type == telemetry_record.sensor_type)
        )
    rules = (await db.execute(rules_q)).scalars().all()

    hits: list[RuleHit] = []

    for rule in rules:
        if rule.rule_type == "missing_heartbeat":
            continue

        if rule.install_types and device.install_type not in rule.install_types:
            continue

        if rule.cold_start_grace_hours and await _is_in_cold_start(
            db, device, rule.cold_start_grace_hours
        ):
            continue

        fired = False
        if rule.rule_type in ("threshold_gt", "threshold_lt"):
            fired = _eval_threshold(rule, telemetry_record.value_numeric)
        elif rule.rule_type == "rate_of_change":
            fired = await _eval_rate_of_change(
                db,
                rule,
                device.id,
                telemetry_record.sensor_type,
                telemetry_record.value_numeric,
            )
        elif rule.rule_type == "digital_high":
            fired = _eval_digital_high(
                telemetry_record.value_numeric, telemetry_record.value_text
            )

        if not fired:
            continue

        existing_q = select(IoTAlert).where(
            and_(
                IoTAlert.device_id == device.id,
                IoTAlert.alert_type == rule.alert_type,
                IoTAlert.status != "resolved",
            )
        ).order_by(desc(IoTAlert.fired_at)).limit(1)
        existing = (await db.execute(existing_q)).scalar_one_or_none()
        if existing:
            continue

        message = _format_message(
            rule.message_template,
            device,
            telemetry_record.value_numeric,
            f"{rule.name} triggered on {device.serial}",
        )
        hits.append(
            RuleHit(
                rule=rule,
                device_id=device.id,
                message=message,
                trigger_payload={
                    "sensor_type": telemetry_record.sensor_type,
                    "value_numeric": telemetry_record.value_numeric,
                    "value_text": telemetry_record.value_text,
                    "telemetry_time": telemetry_record.time.isoformat(),
                    "rule_type": rule.rule_type,
                    "rule_config": rule.config,
                },
            )
        )

    return hits


async def evaluate_missing_heartbeats(db: AsyncSession) -> list[RuleHit]:
    """Cron-driven check for devices that haven't checked in within expected window.

    Called by APScheduler every 15 minutes. Returns RuleHits for devices whose
    last_seen_at is older than the rule's window.
    """
    rules_q = select(IoTAlertRule).where(
        and_(
            IoTAlertRule.active.is_(True),
            IoTAlertRule.rule_type == "missing_heartbeat",
        )
    )
    rules = (await db.execute(rules_q)).scalars().all()
    if not rules:
        return []

    hits: list[RuleHit] = []
    devices_q = select(IoTDevice).where(IoTDevice.archived_at.is_(None))
    devices = (await db.execute(devices_q)).scalars().all()
    now = datetime.now(timezone.utc)

    for rule in rules:
        max_silence_hours = rule.config.get("max_silence_hours", 36)
        cutoff = now - timedelta(hours=max_silence_hours)
        for device in devices:
            if device.last_seen_at is None:
                continue
            if device.last_seen_at >= cutoff:
                continue
            if rule.install_types and device.install_type not in rule.install_types:
                continue

            existing_q = select(IoTAlert).where(
                and_(
                    IoTAlert.device_id == device.id,
                    IoTAlert.alert_type == rule.alert_type,
                    IoTAlert.status != "resolved",
                )
            )
            if (await db.execute(existing_q)).scalar_one_or_none():
                continue

            silence_hours = (now - device.last_seen_at).total_seconds() / 3600
            message = _format_message(
                rule.message_template,
                device,
                silence_hours,
                f"Device {device.serial} hasn't checked in for {silence_hours:.1f} hours",
            )
            hits.append(
                RuleHit(
                    rule=rule,
                    device_id=device.id,
                    message=message,
                    trigger_payload={
                        "last_seen_at": device.last_seen_at.isoformat(),
                        "silence_hours": silence_hours,
                        "max_silence_hours": max_silence_hours,
                    },
                )
            )

    return hits
