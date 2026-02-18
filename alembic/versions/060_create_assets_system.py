"""Create assets management system tables

Revision ID: 060
Revises: 059
Create Date: 2026-02-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if tables already exist (auto-created by SQLAlchemy model import)
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if "assets" in existing_tables:
        # Tables already exist via auto-creation, skip
        return

    # ---- assets table ----
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Core identification
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("asset_tag", sa.String(50), unique=True, index=True),
        sa.Column("asset_type", sa.String(50), nullable=False, index=True),
        sa.Column("category", sa.String(100)),
        # Description
        sa.Column("description", sa.Text),
        sa.Column("make", sa.String(100)),
        sa.Column("model", sa.String(100)),
        sa.Column("serial_number", sa.String(100)),
        sa.Column("year", sa.Integer),
        # Financial
        sa.Column("purchase_date", sa.Date),
        sa.Column("purchase_price", sa.Float),
        sa.Column("current_value", sa.Float),
        sa.Column("salvage_value", sa.Float, server_default="0"),
        sa.Column("useful_life_years", sa.Integer, server_default="10"),
        sa.Column("depreciation_method", sa.String(50), server_default="straight_line"),
        # Status & condition
        sa.Column("status", sa.String(50), server_default="available", index=True),
        sa.Column("condition", sa.String(50), server_default="good"),
        # Assignment
        sa.Column("assigned_technician_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assigned_technician_name", sa.String(255)),
        sa.Column("assigned_work_order_id", postgresql.UUID(as_uuid=True)),
        # Location & tracking
        sa.Column("location_description", sa.String(255)),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        sa.Column("samsara_vehicle_id", sa.String(100)),
        # Maintenance scheduling
        sa.Column("last_maintenance_date", sa.Date),
        sa.Column("next_maintenance_date", sa.Date),
        sa.Column("maintenance_interval_days", sa.Integer),
        sa.Column("total_hours", sa.Float, server_default="0"),
        sa.Column("odometer_miles", sa.Float),
        # Photos & QR
        sa.Column("photo_url", sa.Text),
        sa.Column("qr_code", sa.String(100), unique=True),
        # Insurance & warranty
        sa.Column("warranty_expiry", sa.Date),
        sa.Column("insurance_policy", sa.String(100)),
        sa.Column("insurance_expiry", sa.Date),
        # Metadata
        sa.Column("notes", sa.Text),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # ---- asset_maintenance_logs table ----
    op.create_table(
        "asset_maintenance_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Maintenance details
        sa.Column("maintenance_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        # Who performed it
        sa.Column("performed_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("performed_by_name", sa.String(255)),
        sa.Column("performed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # Cost tracking
        sa.Column("cost", sa.Float, server_default="0"),
        sa.Column("parts_used", sa.Text),
        # Usage at time of service
        sa.Column("hours_at_service", sa.Float),
        sa.Column("odometer_at_service", sa.Float),
        # Next due
        sa.Column("next_due_date", sa.Date),
        sa.Column("next_due_hours", sa.Float),
        sa.Column("next_due_miles", sa.Float),
        # Condition tracking
        sa.Column("condition_before", sa.String(50)),
        sa.Column("condition_after", sa.String(50)),
        # Photos & notes
        sa.Column("photos", sa.Text),
        sa.Column("notes", sa.Text),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ---- asset_assignments table ----
    op.create_table(
        "asset_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Assignment details
        sa.Column("assigned_to_type", sa.String(50), nullable=False),
        sa.Column("assigned_to_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_to_name", sa.String(255)),
        # Check-out/in
        sa.Column("checked_out_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("checked_in_at", sa.DateTime(timezone=True)),
        # Who checked it out
        sa.Column("checked_out_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("checked_out_by_name", sa.String(255)),
        # Condition tracking
        sa.Column("condition_at_checkout", sa.String(50)),
        sa.Column("condition_at_checkin", sa.String(50)),
        # Notes
        sa.Column("notes", sa.Text),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("asset_assignments")
    op.drop_table("asset_maintenance_logs")
    op.drop_table("assets")
