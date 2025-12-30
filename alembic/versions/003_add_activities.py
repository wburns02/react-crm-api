"""Add activities table for customer interaction tracking

Revision ID: 003_add_activities
Revises: 002_add_payments_quotes_sms
Create Date: 2024-12-30

Note: Using IF NOT EXISTS pattern to make migration idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '003_add_activities'
down_revision = '002_add_payments_quotes_sms'
branch_labels = None
depends_on = None


def table_exists(conn, table_name):
    """Check if a table exists in the database."""
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"
    ), {"table_name": table_name})
    return result.scalar()


def upgrade():
    """Create activities table."""
    conn = op.get_bind()

    if not table_exists(conn, 'activities'):
        op.create_table(
            'activities',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
            sa.Column('activity_type', sa.String(20), nullable=False, index=True),
            sa.Column('description', sa.Text, nullable=False),
            sa.Column('activity_date', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('created_by', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created activities table")
    else:
        print("activities table already exists, skipping")


def downgrade():
    """Drop activities table."""
    op.drop_table('activities')
