"""Add work_order_photos table

Revision ID: 032_add_work_order_photos_table
Revises: 031_fix_pay_rates_columns
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '032_add_work_order_photos_table'
down_revision = '031_fix_pay_rates_columns'
branch_labels = None
depends_on = None


def upgrade():
    # Create work_order_photos table
    op.create_table(
        'work_order_photos',
        sa.Column('id', sa.String(36), primary_key=True, index=True),
        sa.Column('work_order_id', sa.String(36), sa.ForeignKey('work_orders.id', ondelete='CASCADE'), nullable=False, index=True),
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


def downgrade():
    op.drop_table('work_order_photos')
