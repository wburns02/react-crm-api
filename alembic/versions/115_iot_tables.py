"""iot tables — devices, telemetry, alerts, firmware, bindings, alert rules

Revision ID: 115
Revises: 114
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "115"
down_revision = "114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    install_type = sa.Enum(
        "conventional", "atu", name="iot_install_type", create_type=True
    )
    alert_severity = sa.Enum(
        "critical", "high", "medium", "low", name="iot_alert_severity", create_type=True
    )
    alert_type = sa.Enum(
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
        create_type=True,
    )
    alert_status = sa.Enum(
        "open", "acknowledged", "resolved", name="iot_alert_status", create_type=True
    )
    rule_type = sa.Enum(
        "threshold_gt",
        "threshold_lt",
        "rate_of_change",
        "digital_high",
        "missing_heartbeat",
        name="iot_rule_type",
        create_type=True,
    )

    op.create_table(
        "iot_devices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("serial", sa.String(64), nullable=False, unique=True),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("site_address", postgresql.JSONB(), nullable=True),
        sa.Column("install_type", install_type, nullable=True),
        sa.Column("firmware_version", sa.String(32), nullable=True),
        sa.Column("hardware_revision", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manufactured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            onupdate=sa.func.now(),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_iot_devices_serial", "iot_devices", ["serial"])
    op.create_index("ix_iot_devices_customer_id", "iot_devices", ["customer_id"])
    op.create_index(
        "ix_iot_devices_last_seen_at", "iot_devices", ["last_seen_at"]
    )
    op.create_index("ix_iot_devices_archived_at", "iot_devices", ["archived_at"])

    op.create_table(
        "iot_telemetry",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("iot_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sensor_type", sa.String(64), nullable=False),
        sa.Column("value_numeric", sa.Float(), nullable=True),
        sa.Column("value_text", sa.String(255), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_iot_telemetry_device_time",
        "iot_telemetry",
        ["device_id", sa.text("time DESC")],
    )
    op.create_index(
        "ix_iot_telemetry_sensor_type", "iot_telemetry", ["sensor_type"]
    )
    op.create_index("ix_iot_telemetry_time", "iot_telemetry", [sa.text("time DESC")])

    op.create_table(
        "iot_alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("iot_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alert_type", alert_type, nullable=False),
        sa.Column("severity", alert_severity, nullable=False),
        sa.Column(
            "status",
            alert_status,
            nullable=False,
            server_default="open",
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("trigger_payload", postgresql.JSONB(), nullable=True),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "acknowledged_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_iot_alerts_device_id", "iot_alerts", ["device_id"])
    op.create_index("ix_iot_alerts_status", "iot_alerts", ["status"])
    op.create_index(
        "ix_iot_alerts_fired_at", "iot_alerts", [sa.text("fired_at DESC")]
    )
    op.create_index("ix_iot_alerts_alert_type", "iot_alerts", ["alert_type"])

    op.create_table(
        "iot_firmware_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("version", sa.String(32), nullable=False, unique=True),
        sa.Column("signed_image_url", sa.Text(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("image_sha256", sa.String(64), nullable=False),
        sa.Column("target_install_types", postgresql.ARRAY(sa.String(32)), nullable=True),
        sa.Column("min_hardware_revision", sa.String(32), nullable=True),
        sa.Column("release_notes", sa.Text(), nullable=True),
        sa.Column(
            "released_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "released_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_iot_firmware_versions_version", "iot_firmware_versions", ["version"]
    )

    op.create_table(
        "iot_device_bindings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("iot_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("install_type", install_type, nullable=True),
        sa.Column("site_address", postgresql.JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "bound_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "bound_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("unbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "unbound_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("unbind_reason", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_iot_device_bindings_device_id", "iot_device_bindings", ["device_id"]
    )
    op.create_index(
        "ix_iot_device_bindings_customer_id",
        "iot_device_bindings",
        ["customer_id"],
    )

    op.create_table(
        "iot_alert_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rule_type", rule_type, nullable=False),
        sa.Column("sensor_type", sa.String(64), nullable=True),
        sa.Column("alert_type", alert_type, nullable=False),
        sa.Column("severity", alert_severity, nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("message_template", sa.Text(), nullable=True),
        sa.Column("install_types", postgresql.ARRAY(sa.String(32)), nullable=True),
        sa.Column("cold_start_grace_hours", sa.Integer(), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_iot_alert_rules_active", "iot_alert_rules", ["active"]
    )
    op.create_index(
        "ix_iot_alert_rules_alert_type", "iot_alert_rules", ["alert_type"]
    )


def downgrade() -> None:
    op.drop_table("iot_alert_rules")
    op.drop_table("iot_device_bindings")
    op.drop_table("iot_firmware_versions")
    op.drop_table("iot_alerts")
    op.drop_table("iot_telemetry")
    op.drop_table("iot_devices")

    op.execute("DROP TYPE IF EXISTS iot_rule_type")
    op.execute("DROP TYPE IF EXISTS iot_alert_status")
    op.execute("DROP TYPE IF EXISTS iot_alert_type")
    op.execute("DROP TYPE IF EXISTS iot_alert_severity")
    op.execute("DROP TYPE IF EXISTS iot_install_type")
