"""IoT models — devices, telemetry, alerts, firmware, bindings, alert rules.

See docs/superpowers/specs/2026-04-27-iot-monitor-design.md for design.
"""
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, ENUM

from app.database import Base


IoTInstallTypeEnum = ENUM(
    "conventional",
    "atu",
    name="iot_install_type",
    create_type=False,
)

IoTAlertSeverityEnum = ENUM(
    "critical",
    "high",
    "medium",
    "low",
    name="iot_alert_severity",
    create_type=False,
)

IoTAlertTypeEnum = ENUM(
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
    name="iot_alert_type",
    create_type=False,
)

IoTAlertStatusEnum = ENUM(
    "open",
    "acknowledged",
    "resolved",
    name="iot_alert_status",
    create_type=False,
)

IoTRuleTypeEnum = ENUM(
    "threshold_gt",
    "threshold_lt",
    "rate_of_change",
    "digital_high",
    "missing_heartbeat",
    name="iot_rule_type",
    create_type=False,
)


class IoTDevice(Base):
    __tablename__ = "iot_devices"

    id = Column(UUID(as_uuid=True), primary_key=True)
    serial = Column(String(64), nullable=False, unique=True, index=True)
    public_key = Column(Text, nullable=False)
    customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    site_address = Column(JSONB, nullable=True)
    install_type = Column(IoTInstallTypeEnum, nullable=True)
    firmware_version = Column(String(32), nullable=True)
    hardware_revision = Column(String(32), nullable=True)
    notes = Column(Text, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True, index=True)
    manufactured_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True, index=True)

    customer = relationship("Customer", foreign_keys=[customer_id])
    telemetry = relationship(
        "IoTTelemetry",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    alerts = relationship(
        "IoTAlert",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    bindings = relationship(
        "IoTDeviceBinding",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class IoTTelemetry(Base):
    __tablename__ = "iot_telemetry"

    id = Column(UUID(as_uuid=True), primary_key=True)
    device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    time = Column(DateTime(timezone=True), nullable=False)
    sensor_type = Column(String(64), nullable=False, index=True)
    value_numeric = Column(Float, nullable=True)
    value_text = Column(String(255), nullable=True)
    raw_payload = Column(JSONB, nullable=True)
    ingested_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    device = relationship("IoTDevice", back_populates="telemetry")


class IoTAlert(Base):
    __tablename__ = "iot_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True)
    device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alert_type = Column(IoTAlertTypeEnum, nullable=False, index=True)
    severity = Column(IoTAlertSeverityEnum, nullable=False)
    status = Column(IoTAlertStatusEnum, nullable=False, server_default="open", index=True)
    message = Column(Text, nullable=True)
    trigger_payload = Column(JSONB, nullable=True)
    fired_at = Column(DateTime(timezone=True), nullable=False, index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by_user_id = Column(
        Integer,
        ForeignKey("api_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(Text, nullable=True)
    work_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    device = relationship("IoTDevice", back_populates="alerts")
    acknowledged_by = relationship(
        "User",
        primaryjoin="IoTAlert.acknowledged_by_user_id == User.id",
        foreign_keys="[IoTAlert.acknowledged_by_user_id]",
    )
    work_order = relationship(
        "WorkOrder",
        primaryjoin="IoTAlert.work_order_id == WorkOrder.id",
        foreign_keys="[IoTAlert.work_order_id]",
    )


class IoTFirmwareVersion(Base):
    __tablename__ = "iot_firmware_versions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    version = Column(String(32), nullable=False, unique=True, index=True)
    signed_image_url = Column(Text, nullable=False)
    signature = Column(Text, nullable=False)
    image_sha256 = Column(String(64), nullable=False)
    target_install_types = Column(ARRAY(String(32)), nullable=True)
    min_hardware_revision = Column(String(32), nullable=True)
    release_notes = Column(Text, nullable=True)
    released_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    released_by_user_id = Column(
        Integer,
        ForeignKey("api_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    released_by = relationship("User", foreign_keys=[released_by_user_id])


class IoTDeviceBinding(Base):
    __tablename__ = "iot_device_bindings"

    id = Column(UUID(as_uuid=True), primary_key=True)
    device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    install_type = Column(IoTInstallTypeEnum, nullable=True)
    site_address = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)
    bound_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    bound_by_user_id = Column(
        Integer,
        ForeignKey("api_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    unbound_at = Column(DateTime(timezone=True), nullable=True)
    unbound_by_user_id = Column(
        Integer,
        ForeignKey("api_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    unbind_reason = Column(String(255), nullable=True)

    device = relationship("IoTDevice", back_populates="bindings")
    customer = relationship("Customer", foreign_keys=[customer_id])
    bound_by = relationship("User", foreign_keys=[bound_by_user_id])
    unbound_by = relationship("User", foreign_keys=[unbound_by_user_id])


class IoTAlertRule(Base):
    __tablename__ = "iot_alert_rules"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    rule_type = Column(IoTRuleTypeEnum, nullable=False)
    sensor_type = Column(String(64), nullable=True)
    alert_type = Column(IoTAlertTypeEnum, nullable=False, index=True)
    severity = Column(IoTAlertSeverityEnum, nullable=False)
    config = Column(JSONB, nullable=False)
    message_template = Column(Text, nullable=True)
    install_types = Column(ARRAY(String(32)), nullable=True)
    cold_start_grace_hours = Column(Integer, nullable=True)
    active = Column(Boolean, nullable=False, server_default="true", index=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
