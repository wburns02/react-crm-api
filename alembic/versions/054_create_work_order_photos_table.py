"""Create work_order_photos table

Revision ID: 054
Revises: 053
Create Date: 2026-02-11

Creates the work_order_photos table for storing photos captured by technicians.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade():
    # Check if table already exists before creating
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'work_order_photos')"
        )
    )
    if result.scalar():
        return

    op.create_table(
        "work_order_photos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "work_order_id",
            UUID(as_uuid=True),
            sa.ForeignKey("work_orders.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("photo_type", sa.String(50), nullable=False),
        sa.Column("data", sa.Text, nullable=False),
        sa.Column("thumbnail", sa.Text),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_info", sa.String(255)),
        sa.Column("gps_lat", sa.Float),
        sa.Column("gps_lng", sa.Float),
        sa.Column("gps_accuracy", sa.Float),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("work_order_photos")
