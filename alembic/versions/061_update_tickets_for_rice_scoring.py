"""Update tickets table for RICE scoring and frontend alignment.

Adds title, type, RICE scoring columns. Makes customer_id nullable.

Revision ID: 061_update_tickets_for_rice_scoring
Revises: 060_create_assets_system
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in the table."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name):
    """Check if a table exists."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if not table_exists("tickets"):
        # Create the full table if it doesn't exist
        op.create_table(
            "tickets",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("customer_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("work_order_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("work_orders.id"), nullable=True),
            sa.Column("title", sa.String(255), nullable=True),
            sa.Column("subject", sa.String(255), nullable=True),
            sa.Column("description", sa.Text, nullable=False),
            sa.Column("type", sa.String(50), nullable=True),
            sa.Column("category", sa.String(50), nullable=True),
            sa.Column("status", sa.String(30), default="open"),
            sa.Column("priority", sa.String(20), default="medium"),
            sa.Column("reach", sa.Float, nullable=True),
            sa.Column("impact", sa.Float, nullable=True),
            sa.Column("confidence", sa.Float, nullable=True),
            sa.Column("effort", sa.Float, nullable=True),
            sa.Column("rice_score", sa.Float, nullable=True),
            sa.Column("assigned_to", sa.String(100), nullable=True),
            sa.Column("resolution", sa.Text, nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_tickets_id", "tickets", ["id"])
        op.create_index("ix_tickets_customer_id", "tickets", ["customer_id"])
        op.create_index("ix_tickets_status", "tickets", ["status"])
        return

    # Table exists - add missing columns
    if not column_exists("tickets", "title"):
        op.add_column("tickets", sa.Column("title", sa.String(255), nullable=True))

    if not column_exists("tickets", "type"):
        op.add_column("tickets", sa.Column("type", sa.String(50), nullable=True))

    if not column_exists("tickets", "reach"):
        op.add_column("tickets", sa.Column("reach", sa.Float, nullable=True))

    if not column_exists("tickets", "impact"):
        op.add_column("tickets", sa.Column("impact", sa.Float, nullable=True))

    if not column_exists("tickets", "confidence"):
        op.add_column("tickets", sa.Column("confidence", sa.Float, nullable=True))

    if not column_exists("tickets", "effort"):
        op.add_column("tickets", sa.Column("effort", sa.Float, nullable=True))

    if not column_exists("tickets", "rice_score"):
        op.add_column("tickets", sa.Column("rice_score", sa.Float, nullable=True))

    # Make customer_id nullable (was NOT NULL before)
    op.alter_column("tickets", "customer_id", nullable=True)

    # Make subject nullable (title is now the primary field)
    op.alter_column("tickets", "subject", nullable=True)

    # Copy existing subject values to title for existing rows
    op.execute("UPDATE tickets SET title = subject WHERE title IS NULL AND subject IS NOT NULL")


def downgrade():
    if table_exists("tickets"):
        for col in ["title", "type", "reach", "impact", "confidence", "effort", "rice_score"]:
            if column_exists("tickets", col):
                op.drop_column("tickets", col)
