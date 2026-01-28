"""Add created_by column to activities table

Revision ID: 024_add_activities_created_by
Revises: 023_add_septic_permit_tables
Create Date: 2025-01-28

Note: Using IF NOT EXISTS pattern to make migration idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '024_add_activities_created_by'
down_revision = '023_add_septic_permit_tables'
branch_labels = None
depends_on = None


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = :table_name AND column_name = :column_name
        )
    """), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def upgrade():
    """Add created_by column to activities table."""
    conn = op.get_bind()

    if not column_exists(conn, 'activities', 'created_by'):
        op.add_column('activities', sa.Column('created_by', sa.String(100), nullable=True))
        print("Added created_by column to activities table")
    else:
        print("created_by column already exists in activities table, skipping")


def downgrade():
    """Remove created_by column from activities table."""
    op.drop_column('activities', 'created_by')
