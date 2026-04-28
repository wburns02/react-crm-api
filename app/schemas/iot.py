"""IoT Pydantic schemas — devices, telemetry, alerts, firmware, bindings, rules.

See docs/superpowers/specs/2026-04-27-iot-monitor-design.md.
"""
from datetime import datetime
from typing import Optional, Literal, Any
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.types import UUIDStr


InstallType = Literal["conventional", "atu"]
AlertSeverity = Literal["critical", "high", "medium", "low"]
AlertType = Literal[
    "oem_alarm_fire",
    "power_loss",
    "pump_overcurrent",
    "pump_dry_run",
    "pump_short_cycle",
    "pump_degradation",
    "drain_field_saturation",
    "tank_high_level",
    "missing_heartbeat",
    "low_battery",
    "tamper",
]
AlertStatus = Literal["open", "acknowledged", "resolved"]
RuleType = Literal[
    "threshold_gt",
    "threshold_lt",
    "rate_of_change",
    "digital_high",
    "missing_heartbeat",
]


class IoTDeviceCreate(BaseModel):
    serial: str = Field(..., max_length=64)
    public_key: str
    hardware_revision: Optional[str] = Field(None, max_length=32)
    firmware_version: Optional[str] = Field(None, max_length=32)
    notes: Optional[str] = None
    manufactured_at: Optional[datetime] = None


class IoTDeviceBindRequest(BaseModel):
    customer_id: UUIDStr
    install_type: InstallType
    site_address: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class IoTDeviceUnbindRequest(BaseModel):
    unbind_reason: Optional[str] = Field(None, max_length=255)


class IoTDeviceUpdate(BaseModel):
    firmware_version: Optional[str] = Field(None, max_length=32)
    notes: Optional[str] = None
    archived: Optional[bool] = None


class IoTDeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    serial: str
    customer_id: Optional[UUIDStr] = None
    site_address: Optional[dict[str, Any]] = None
    install_type: Optional[InstallType] = None
    firmware_version: Optional[str] = None
    hardware_revision: Optional[str] = None
    notes: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    manufactured_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None


class IoTTelemetryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    device_id: UUIDStr
    time: datetime
    sensor_type: str
    value_numeric: Optional[float] = None
    value_text: Optional[str] = None
    raw_payload: Optional[dict[str, Any]] = None
    ingested_at: datetime


class IoTTelemetryQuery(BaseModel):
    device_id: Optional[UUIDStr] = None
    sensor_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(100, ge=1, le=10000)


class IoTAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    device_id: UUIDStr
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    message: Optional[str] = None
    trigger_payload: Optional[dict[str, Any]] = None
    fired_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by_user_id: Optional[int] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    work_order_id: Optional[UUIDStr] = None
    created_at: datetime


class IoTAlertAck(BaseModel):
    resolution_note: Optional[str] = None


class IoTAlertResolve(BaseModel):
    resolution_note: Optional[str] = None
    work_order_id: Optional[UUIDStr] = None


class IoTFirmwareCreate(BaseModel):
    version: str = Field(..., max_length=32)
    signed_image_url: str
    signature: str
    image_sha256: str = Field(..., min_length=64, max_length=64)
    target_install_types: Optional[list[str]] = None
    min_hardware_revision: Optional[str] = Field(None, max_length=32)
    release_notes: Optional[str] = None


class IoTFirmwareRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    version: str
    signed_image_url: str
    signature: str
    image_sha256: str
    target_install_types: Optional[list[str]] = None
    min_hardware_revision: Optional[str] = None
    release_notes: Optional[str] = None
    released_at: datetime
    released_by_user_id: Optional[int] = None


class IoTFirmwareDispatch(BaseModel):
    target_device_ids: Optional[list[UUIDStr]] = None
    target_install_types: Optional[list[InstallType]] = None
    target_all: bool = False


class IoTAlertRuleCreate(BaseModel):
    name: str = Field(..., max_length=128)
    description: Optional[str] = None
    rule_type: RuleType
    sensor_type: Optional[str] = Field(None, max_length=64)
    alert_type: AlertType
    severity: AlertSeverity
    config: dict[str, Any]
    message_template: Optional[str] = None
    install_types: Optional[list[str]] = None
    cold_start_grace_hours: Optional[int] = Field(None, ge=0)
    active: bool = True


class IoTAlertRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    name: str
    description: Optional[str] = None
    rule_type: RuleType
    sensor_type: Optional[str] = None
    alert_type: AlertType
    severity: AlertSeverity
    config: dict[str, Any]
    message_template: Optional[str] = None
    install_types: Optional[list[str]] = None
    cold_start_grace_hours: Optional[int] = None
    active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class IoTDeviceBindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    device_id: UUIDStr
    customer_id: UUIDStr
    install_type: Optional[InstallType] = None
    site_address: Optional[dict[str, Any]] = None
    notes: Optional[str] = None
    bound_at: datetime
    bound_by_user_id: Optional[int] = None
    unbound_at: Optional[datetime] = None
    unbound_by_user_id: Optional[int] = None
    unbind_reason: Optional[str] = None


class IoTDeviceDetail(IoTDeviceRead):
    """Device detail with recent telemetry + open alerts."""

    recent_telemetry: list[IoTTelemetryRead] = Field(default_factory=list)
    open_alerts: list[IoTAlertRead] = Field(default_factory=list)
    bindings: list[IoTDeviceBindingRead] = Field(default_factory=list)


class IoTDashboardStats(BaseModel):
    total_devices: int
    online: int
    offline: int
    warnings: int
    critical: int
    active_alerts: int
    maintenance_due: int
