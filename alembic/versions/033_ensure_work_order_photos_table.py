"""Ensure work_order_photos table exists (idempotent)

This migration checks if the table exists before creating it.
The table may not exist due to a previous migration that failed silently.

Revision ID: 033_ensure_work_order_photos
Revises: 032_add_work_order_photos_table
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '033_ensure_work_order_photos'
down_revision = '032_add_work_order_photos_table'
branch_labels = None
depends_on = None


def table_exists(conn, table_name):
    """Check if a table exists in the database."""
    result = conn.execute(text(
        """SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :table_name
        )"""
    ), {"table_name": table_name})
    return result.scalar()


def upgrade():
    conn = op.get_bind()

    # Check if table already exists
    if table_exists(conn, 'work_order_photos'):
        print("work_order_photos table already exists, skipping creation")
        return

    print("Creating work_order_photos table...")

    # Create work_order_photos table
    op.create_table(
        'work_order_photos',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('work_order_id', sa.String(36), sa.ForeignKey('work_orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('photo_type', sa.String(50), nullable=False),
        sa.Column('data', sa.Text(), nullable=False),
        sa.Column('thumbnail', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('device_info', sa.String(255), nullable=True),
        sa.Column('gps_lat', sa.Float(), nullable=True),
        sa.Column('gps_lng', sa.Float(), nullable=True),
        sa.Column('gps_accuracy', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes
    op.create_index('ix_work_order_photos_id', 'work_order_photos', ['id'])
    op.create_index('ix_work_order_photos_work_order_id', 'work_order_photos', ['work_order_id'])

    print("work_order_photos table created successfully")


def downgrade():
    conn = op.get_bind()

    if table_exists(conn, 'work_order_photos'):
        op.drop_table('work_order_photos')
