"""iot — add air_pump_failure / air_pump_degradation to alert types

Adds two new values to the iot_alert_type enum to support ATU air
compressor monitoring via the new MPRLS pressure sensor.

Revision ID: 116
Revises: 115
"""
from alembic import op


revision = "116"
down_revision = "115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE iot_alert_type ADD VALUE IF NOT EXISTS 'air_pump_failure'")
    op.execute("ALTER TYPE iot_alert_type ADD VALUE IF NOT EXISTS 'air_pump_degradation'")


def downgrade() -> None:
    # Postgres does not support removing enum values cleanly. To downgrade:
    # 1) Verify no rows reference these enum values: SELECT alert_type, COUNT(*)
    #    FROM iot_alerts WHERE alert_type IN ('air_pump_failure',
    #    'air_pump_degradation') GROUP BY alert_type;
    # 2) If counts are zero, recreate the enum:
    #      CREATE TYPE iot_alert_type_old AS ENUM (existing values);
    #      ALTER TABLE iot_alerts ALTER COLUMN alert_type TYPE iot_alert_type_old
    #        USING alert_type::text::iot_alert_type_old;
    #      ALTER TABLE iot_alert_rules ALTER COLUMN alert_type TYPE iot_alert_type_old
    #        USING alert_type::text::iot_alert_type_old;
    #      DROP TYPE iot_alert_type;
    #      ALTER TYPE iot_alert_type_old RENAME TO iot_alert_type;
    pass
