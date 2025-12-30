"""Add tickets, equipment, and inventory tables

Revision ID: 004_add_tickets_equipment_inventory
Revises: 003_add_activities
Create Date: 2024-12-30

Note: Using IF NOT EXISTS pattern to make migration idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '004_add_tickets_equipment_inventory'
down_revision = '003_add_activities'
branch_labels = None
depends_on = None


def table_exists(conn, table_name):
    """Check if a table exists in the database."""
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"
    ), {"table_name": table_name})
    return result.scalar()


def upgrade():
    """Create tickets, equipment, and inventory_items tables."""
    conn = op.get_bind()

    # Create tickets table
    if not table_exists(conn, 'tickets'):
        op.create_table(
            'tickets',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
            sa.Column('work_order_id', sa.String(36), sa.ForeignKey('work_orders.id'), nullable=True, index=True),
            sa.Column('subject', sa.String(255), nullable=False),
            sa.Column('description', sa.Text, nullable=False),
            sa.Column('category', sa.String(50), nullable=True),
            sa.Column('status', sa.String(30), default='open', index=True),
            sa.Column('priority', sa.String(20), default='normal'),
            sa.Column('assigned_to', sa.String(100), nullable=True),
            sa.Column('resolution', sa.Text, nullable=True),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_by', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created tickets table")
    else:
        print("tickets table already exists, skipping")

    # Create equipment table
    if not table_exists(conn, 'equipment'):
        op.create_table(
            'equipment',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
            sa.Column('equipment_type', sa.String(100), nullable=False, index=True),
            sa.Column('manufacturer', sa.String(100), nullable=True),
            sa.Column('model', sa.String(100), nullable=True),
            sa.Column('serial_number', sa.String(100), nullable=True),
            sa.Column('capacity_gallons', sa.Integer, nullable=True),
            sa.Column('size_description', sa.String(255), nullable=True),
            sa.Column('install_date', sa.Date, nullable=True),
            sa.Column('installed_by', sa.String(100), nullable=True),
            sa.Column('warranty_expiry', sa.Date, nullable=True),
            sa.Column('warranty_notes', sa.Text, nullable=True),
            sa.Column('last_service_date', sa.Date, nullable=True),
            sa.Column('next_service_date', sa.Date, nullable=True),
            sa.Column('service_interval_months', sa.Integer, nullable=True),
            sa.Column('location_description', sa.String(255), nullable=True),
            sa.Column('latitude', sa.Float, nullable=True),
            sa.Column('longitude', sa.Float, nullable=True),
            sa.Column('condition', sa.String(50), nullable=True),
            sa.Column('notes', sa.Text, nullable=True),
            sa.Column('is_active', sa.String(10), default='active'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created equipment table")
    else:
        print("equipment table already exists, skipping")

    # Create inventory_items table
    if not table_exists(conn, 'inventory_items'):
        op.create_table(
            'inventory_items',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('sku', sa.String(50), unique=True, nullable=False, index=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('category', sa.String(100), nullable=True, index=True),
            sa.Column('unit_price', sa.Float, nullable=True),
            sa.Column('cost_price', sa.Float, nullable=True),
            sa.Column('markup_percent', sa.Float, nullable=True),
            sa.Column('quantity_on_hand', sa.Integer, default=0),
            sa.Column('quantity_reserved', sa.Integer, default=0),
            sa.Column('reorder_level', sa.Integer, default=0),
            sa.Column('reorder_quantity', sa.Integer, nullable=True),
            sa.Column('unit', sa.String(20), default='each'),
            sa.Column('supplier_name', sa.String(255), nullable=True),
            sa.Column('supplier_sku', sa.String(100), nullable=True),
            sa.Column('supplier_phone', sa.String(20), nullable=True),
            sa.Column('warehouse_location', sa.String(100), nullable=True),
            sa.Column('vehicle_id', sa.String(36), nullable=True),
            sa.Column('is_active', sa.Boolean, default=True),
            sa.Column('is_taxable', sa.Boolean, default=True),
            sa.Column('notes', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created inventory_items table")
    else:
        print("inventory_items table already exists, skipping")


def downgrade():
    """Drop tickets, equipment, and inventory_items tables."""
    op.drop_table('inventory_items')
    op.drop_table('equipment')
    op.drop_table('tickets')
