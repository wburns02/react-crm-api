"""Add Microsoft Bookings fields to work_orders

Revision ID: 078_add_ms_bookings_fields
Revises: 077
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

revision = "078_add_ms_bookings_fields"
down_revision = "077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ms_booking_appointment_id to work_orders
    op.add_column(
        "work_orders",
        sa.Column("ms_booking_appointment_id", sa.String(255), nullable=True),
    )
    # Add booking_source to work_orders (web, microsoft_bookings)
    op.add_column(
        "work_orders",
        sa.Column("booking_source", sa.String(50), nullable=True),
    )
    # Index for fast lookup during sync
    op.create_index(
        "ix_work_orders_ms_booking_appt_id",
        "work_orders",
        ["ms_booking_appointment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_work_orders_ms_booking_appt_id", table_name="work_orders")
    op.drop_column("work_orders", "booking_source")
    op.drop_column("work_orders", "ms_booking_appointment_id")
