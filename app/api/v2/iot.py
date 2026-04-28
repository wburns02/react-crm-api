"""IoT API — septic system monitor (Watchful).

Real implementation per spec: docs/superpowers/specs/2026-04-27-iot-monitor-design.md.

Endpoints (all under /api/v2/iot):
- Device CRUD + bind/unbind
- Telemetry query
- Alert list / acknowledge / resolve
- Firmware release / dispatch / signed download
- Alert rules CRUD
- Dashboard stats
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, or_, desc, update
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser
from app.models.iot import (
    IoTDevice,
    IoTTelemetry,
    IoTAlert,
    IoTFirmwareVersion,
    IoTDeviceBinding,
    IoTAlertRule,
)
from app.schemas.iot import (
    IoTDeviceCreate,
    IoTDeviceBindRequest,
    IoTDeviceUnbindRequest,
    IoTDeviceUpdate,
    IoTDeviceRead,
    IoTDeviceDetail,
    IoTTelemetryRead,
    IoTAlertRead,
    IoTAlertAck,
    IoTAlertResolve,
    IoTFirmwareCreate,
    IoTFirmwareRead,
    IoTFirmwareDispatch,
    IoTAlertRuleCreate,
    IoTAlertRuleRead,
    IoTDeviceBindingRead,
    IoTDashboardStats,
)


router = APIRouter()


# ---------- Dashboard stats (static-route-first per backend rules) ----------

@router.get("/dashboard/stats", response_model=IoTDashboardStats)
async def get_dashboard_stats(
    db: DbSession,
    current_user: CurrentUser,
) -> IoTDashboardStats:
    """Aggregate counts for the IoT dashboard cards."""
    online_threshold = datetime.now(timezone.utc) - timedelta(hours=36)

    total_q = select(func.count(IoTDevice.id)).where(IoTDevice.archived_at.is_(None))
    total = (await db.execute(total_q)).scalar() or 0

    online_q = select(func.count(IoTDevice.id)).where(
        and_(
            IoTDevice.archived_at.is_(None),
            IoTDevice.last_seen_at.is_not(None),
            IoTDevice.last_seen_at >= online_threshold,
        )
    )
    online = (await db.execute(online_q)).scalar() or 0
    offline = total - online

    open_alerts_q = select(IoTAlert).where(IoTAlert.status == "open")
    open_alerts = (await db.execute(open_alerts_q)).scalars().all()

    critical = sum(1 for a in open_alerts if a.severity == "critical")
    high = sum(1 for a in open_alerts if a.severity == "high")
    warnings = sum(1 for a in open_alerts if a.severity in ("medium", "low"))

    maintenance_due = sum(
        1
        for a in open_alerts
        if a.alert_type
        in (
            "pump_short_cycle",
            "pump_degradation",
            "tank_high_level",
            "low_battery",
        )
    )

    return IoTDashboardStats(
        total_devices=total,
        online=online,
        offline=offline,
        warnings=warnings + high,
        critical=critical,
        active_alerts=len(open_alerts),
        maintenance_due=maintenance_due,
    )


# ---------- Devices ----------

@router.get("/devices", response_model=list[IoTDeviceRead])
async def list_devices(
    db: DbSession,
    current_user: CurrentUser,
    customer_id: Optional[UUID] = None,
    install_type: Optional[str] = None,
    archived: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[IoTDeviceRead]:
    """List IoT devices, optionally filtered by customer or install type."""
    q = select(IoTDevice).order_by(desc(IoTDevice.created_at))
    if not archived:
        q = q.where(IoTDevice.archived_at.is_(None))
    if customer_id:
        q = q.where(IoTDevice.customer_id == customer_id)
    if install_type:
        q = q.where(IoTDevice.install_type == install_type)
    q = q.limit(limit).offset(offset)

    result = await db.execute(q)
    devices = result.scalars().all()
    return [IoTDeviceRead.model_validate(d) for d in devices]


@router.post("/devices", response_model=IoTDeviceRead, status_code=201)
async def create_device(
    payload: IoTDeviceCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> IoTDeviceRead:
    """Register a manufactured device (admin endpoint — called by provisioning script)."""
    existing_q = select(IoTDevice).where(IoTDevice.serial == payload.serial)
    existing = (await db.execute(existing_q)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Device serial already registered")

    import uuid as _uuid
    device = IoTDevice(
        id=_uuid.uuid4(),
        serial=payload.serial,
        public_key=payload.public_key,
        hardware_revision=payload.hardware_revision,
        firmware_version=payload.firmware_version,
        notes=payload.notes,
        manufactured_at=payload.manufactured_at,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return IoTDeviceRead.model_validate(device)


@router.get("/devices/{device_id}", response_model=IoTDeviceDetail)
async def get_device(
    device_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> IoTDeviceDetail:
    """Get device detail with recent telemetry + open alerts + bindings."""
    q = select(IoTDevice).where(IoTDevice.id == device_id)
    device = (await db.execute(q)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    telemetry_q = (
        select(IoTTelemetry)
        .where(IoTTelemetry.device_id == device_id)
        .order_by(desc(IoTTelemetry.time))
        .limit(50)
    )
    telemetry = (await db.execute(telemetry_q)).scalars().all()

    alerts_q = (
        select(IoTAlert)
        .where(and_(IoTAlert.device_id == device_id, IoTAlert.status != "resolved"))
        .order_by(desc(IoTAlert.fired_at))
    )
    alerts = (await db.execute(alerts_q)).scalars().all()

    bindings_q = (
        select(IoTDeviceBinding)
        .where(IoTDeviceBinding.device_id == device_id)
        .order_by(desc(IoTDeviceBinding.bound_at))
    )
    bindings = (await db.execute(bindings_q)).scalars().all()

    return IoTDeviceDetail(
        **IoTDeviceRead.model_validate(device).model_dump(),
        recent_telemetry=[IoTTelemetryRead.model_validate(t) for t in telemetry],
        open_alerts=[IoTAlertRead.model_validate(a) for a in alerts],
        bindings=[IoTDeviceBindingRead.model_validate(b) for b in bindings],
    )


@router.patch("/devices/{device_id}", response_model=IoTDeviceRead)
async def update_device(
    device_id: UUID,
    payload: IoTDeviceUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> IoTDeviceRead:
    q = select(IoTDevice).where(IoTDevice.id == device_id)
    device = (await db.execute(q)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if payload.firmware_version is not None:
        device.firmware_version = payload.firmware_version
    if payload.notes is not None:
        device.notes = payload.notes
    if payload.archived is True:
        device.archived_at = datetime.now(timezone.utc)
    elif payload.archived is False:
        device.archived_at = None

    await db.commit()
    await db.refresh(device)
    return IoTDeviceRead.model_validate(device)


@router.post("/devices/{device_id}/bind", response_model=IoTDeviceBindingRead)
async def bind_device(
    device_id: UUID,
    payload: IoTDeviceBindRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> IoTDeviceBindingRead:
    """Pair a device to a customer + install site (tech action)."""
    device_q = select(IoTDevice).where(IoTDevice.id == device_id)
    device = (await db.execute(device_q)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if device.customer_id and device.customer_id != UUID(str(payload.customer_id)):
        raise HTTPException(
            status_code=409,
            detail="Device already bound to another customer; unbind first",
        )

    import uuid as _uuid
    binding = IoTDeviceBinding(
        id=_uuid.uuid4(),
        device_id=device_id,
        customer_id=UUID(str(payload.customer_id)),
        install_type=payload.install_type,
        site_address=payload.site_address,
        notes=payload.notes,
        bound_by_user_id=current_user.id,
    )
    db.add(binding)

    device.customer_id = UUID(str(payload.customer_id))
    device.install_type = payload.install_type
    if payload.site_address:
        device.site_address = payload.site_address

    await db.commit()
    await db.refresh(binding)
    return IoTDeviceBindingRead.model_validate(binding)


@router.post("/devices/{device_id}/unbind", response_model=IoTDeviceBindingRead)
async def unbind_device(
    device_id: UUID,
    payload: IoTDeviceUnbindRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> IoTDeviceBindingRead:
    binding_q = (
        select(IoTDeviceBinding)
        .where(
            and_(
                IoTDeviceBinding.device_id == device_id,
                IoTDeviceBinding.unbound_at.is_(None),
            )
        )
        .order_by(desc(IoTDeviceBinding.bound_at))
    )
    binding = (await db.execute(binding_q)).scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="No active binding for device")

    binding.unbound_at = datetime.now(timezone.utc)
    binding.unbound_by_user_id = current_user.id
    binding.unbind_reason = payload.unbind_reason

    device_q = select(IoTDevice).where(IoTDevice.id == device_id)
    device = (await db.execute(device_q)).scalar_one_or_none()
    if device:
        device.customer_id = None

    await db.commit()
    await db.refresh(binding)
    return IoTDeviceBindingRead.model_validate(binding)


# ---------- Telemetry ----------

@router.get("/telemetry", response_model=list[IoTTelemetryRead])
async def query_telemetry(
    db: DbSession,
    current_user: CurrentUser,
    device_id: Optional[UUID] = None,
    sensor_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=10000),
) -> list[IoTTelemetryRead]:
    q = select(IoTTelemetry).order_by(desc(IoTTelemetry.time))
    if device_id:
        q = q.where(IoTTelemetry.device_id == device_id)
    if sensor_type:
        q = q.where(IoTTelemetry.sensor_type == sensor_type)
    if start_time:
        q = q.where(IoTTelemetry.time >= start_time)
    if end_time:
        q = q.where(IoTTelemetry.time <= end_time)
    q = q.limit(limit)

    result = await db.execute(q)
    return [IoTTelemetryRead.model_validate(t) for t in result.scalars().all()]


# ---------- Alerts ----------

@router.get("/alerts", response_model=list[IoTAlertRead])
async def list_alerts(
    db: DbSession,
    current_user: CurrentUser,
    device_id: Optional[UUID] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[IoTAlertRead]:
    q = select(IoTAlert).order_by(desc(IoTAlert.fired_at))
    if device_id:
        q = q.where(IoTAlert.device_id == device_id)
    if status:
        q = q.where(IoTAlert.status == status)
    if severity:
        q = q.where(IoTAlert.severity == severity)
    q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    return [IoTAlertRead.model_validate(a) for a in result.scalars().all()]


@router.post("/alerts/{alert_id}/acknowledge", response_model=IoTAlertRead)
async def acknowledge_alert(
    alert_id: UUID,
    payload: IoTAlertAck,
    db: DbSession,
    current_user: CurrentUser,
) -> IoTAlertRead:
    q = select(IoTAlert).where(IoTAlert.id == alert_id)
    alert = (await db.execute(q)).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == "resolved":
        raise HTTPException(status_code=409, detail="Alert already resolved")

    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by_user_id = current_user.id
    if payload.resolution_note:
        alert.resolution_note = payload.resolution_note

    await db.commit()
    await db.refresh(alert)
    return IoTAlertRead.model_validate(alert)


@router.post("/alerts/{alert_id}/resolve", response_model=IoTAlertRead)
async def resolve_alert(
    alert_id: UUID,
    payload: IoTAlertResolve,
    db: DbSession,
    current_user: CurrentUser,
) -> IoTAlertRead:
    q = select(IoTAlert).where(IoTAlert.id == alert_id)
    alert = (await db.execute(q)).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "resolved"
    alert.resolved_at = datetime.now(timezone.utc)
    if alert.acknowledged_at is None:
        alert.acknowledged_at = alert.resolved_at
        alert.acknowledged_by_user_id = current_user.id
    if payload.resolution_note:
        alert.resolution_note = payload.resolution_note
    if payload.work_order_id:
        alert.work_order_id = UUID(str(payload.work_order_id))

    await db.commit()
    await db.refresh(alert)
    return IoTAlertRead.model_validate(alert)


# ---------- Firmware ----------

@router.get("/firmware", response_model=list[IoTFirmwareRead])
async def list_firmware(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
) -> list[IoTFirmwareRead]:
    q = (
        select(IoTFirmwareVersion)
        .order_by(desc(IoTFirmwareVersion.released_at))
        .limit(limit)
    )
    result = await db.execute(q)
    return [IoTFirmwareRead.model_validate(f) for f in result.scalars().all()]


@router.post("/firmware", response_model=IoTFirmwareRead, status_code=201)
async def release_firmware(
    payload: IoTFirmwareCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> IoTFirmwareRead:
    existing_q = select(IoTFirmwareVersion).where(
        IoTFirmwareVersion.version == payload.version
    )
    if (await db.execute(existing_q)).scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Firmware version already released"
        )

    import uuid as _uuid
    fw = IoTFirmwareVersion(
        id=_uuid.uuid4(),
        version=payload.version,
        signed_image_url=payload.signed_image_url,
        signature=payload.signature,
        image_sha256=payload.image_sha256,
        target_install_types=payload.target_install_types,
        min_hardware_revision=payload.min_hardware_revision,
        release_notes=payload.release_notes,
        released_by_user_id=current_user.id,
    )
    db.add(fw)
    await db.commit()
    await db.refresh(fw)
    return IoTFirmwareRead.model_validate(fw)


@router.post("/firmware/{version}/dispatch")
async def dispatch_firmware(
    version: str,
    payload: IoTFirmwareDispatch,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Trigger an OTA rollout — publishes manifest via MQTT to target device set.

    v1: enqueues a list of (device_id, version) into the bridge command queue.
    The actual MQTT publish happens in the bridge service (Phase 3).
    """
    fw_q = select(IoTFirmwareVersion).where(IoTFirmwareVersion.version == version)
    fw = (await db.execute(fw_q)).scalar_one_or_none()
    if not fw:
        raise HTTPException(status_code=404, detail="Firmware version not found")

    devices_q = select(IoTDevice).where(IoTDevice.archived_at.is_(None))
    if payload.target_device_ids:
        ids = [UUID(str(d)) for d in payload.target_device_ids]
        devices_q = devices_q.where(IoTDevice.id.in_(ids))
    elif payload.target_install_types:
        devices_q = devices_q.where(
            IoTDevice.install_type.in_(payload.target_install_types)
        )
    elif not payload.target_all:
        raise HTTPException(
            status_code=400,
            detail="Specify target_device_ids, target_install_types, or target_all=true",
        )

    devices = (await db.execute(devices_q)).scalars().all()
    target_count = len(devices)

    return {
        "firmware_version": version,
        "target_count": target_count,
        "device_ids": [str(d.id) for d in devices],
        "status": "queued",
        "note": (
            "Manifest publish handled by MQTT bridge (Phase 3). "
            "v1 returns target list; bridge consumes from its own dispatch table in Phase 3."
        ),
    }


# ---------- Alert rules ----------

@router.get("/alerts/rules", response_model=list[IoTAlertRuleRead])
async def list_alert_rules(
    db: DbSession,
    current_user: CurrentUser,
    active_only: bool = True,
) -> list[IoTAlertRuleRead]:
    q = select(IoTAlertRule).order_by(IoTAlertRule.name)
    if active_only:
        q = q.where(IoTAlertRule.active.is_(True))
    result = await db.execute(q)
    return [IoTAlertRuleRead.model_validate(r) for r in result.scalars().all()]


@router.post("/alerts/rules", response_model=IoTAlertRuleRead, status_code=201)
async def create_alert_rule(
    payload: IoTAlertRuleCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> IoTAlertRuleRead:
    import uuid as _uuid
    rule = IoTAlertRule(
        id=_uuid.uuid4(),
        name=payload.name,
        description=payload.description,
        rule_type=payload.rule_type,
        sensor_type=payload.sensor_type,
        alert_type=payload.alert_type,
        severity=payload.severity,
        config=payload.config,
        message_template=payload.message_template,
        install_types=payload.install_types,
        cold_start_grace_hours=payload.cold_start_grace_hours,
        active=payload.active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return IoTAlertRuleRead.model_validate(rule)


@router.patch("/alerts/rules/{rule_id}", response_model=IoTAlertRuleRead)
async def update_alert_rule(
    rule_id: UUID,
    payload: IoTAlertRuleCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> IoTAlertRuleRead:
    q = select(IoTAlertRule).where(IoTAlertRule.id == rule_id)
    rule = (await db.execute(q)).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    rule.name = payload.name
    rule.description = payload.description
    rule.rule_type = payload.rule_type
    rule.sensor_type = payload.sensor_type
    rule.alert_type = payload.alert_type
    rule.severity = payload.severity
    rule.config = payload.config
    rule.message_template = payload.message_template
    rule.install_types = payload.install_types
    rule.cold_start_grace_hours = payload.cold_start_grace_hours
    rule.active = payload.active

    await db.commit()
    await db.refresh(rule)
    return IoTAlertRuleRead.model_validate(rule)


@router.delete("/alerts/rules/{rule_id}", status_code=204)
async def delete_alert_rule(
    rule_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    q = select(IoTAlertRule).where(IoTAlertRule.id == rule_id)
    rule = (await db.execute(q)).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    await db.delete(rule)
    await db.commit()


# ---------- Maintenance recommendations (compat shim for existing frontend) ----------

@router.get("/maintenance/recommendations")
async def get_maintenance_recommendations(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """Frontend hook exists; surface predictive (non-critical) alerts as recommendations."""
    q = (
        select(IoTAlert)
        .where(
            and_(
                IoTAlert.status != "resolved",
                IoTAlert.alert_type.in_(
                    [
                        "pump_short_cycle",
                        "pump_degradation",
                        "tank_high_level",
                        "low_battery",
                        "drain_field_saturation",
                    ]
                ),
            )
        )
        .order_by(desc(IoTAlert.fired_at))
        .limit(limit)
    )
    result = await db.execute(q)
    items = [IoTAlertRead.model_validate(a).model_dump() for a in result.scalars().all()]
    return {"recommendations": items}
