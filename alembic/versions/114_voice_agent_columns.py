"""voice agent columns — customers.is_test_prospect, call_logs.hallucinations, call_logs.amd_result

Revision ID: 114
Revises: 113
"""
from alembic import op
import sqlalchemy as sa


revision = "114"
down_revision = "113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column(
            "is_test_prospect",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_customers_is_test_prospect",
        "customers",
        ["is_test_prospect"],
    )

    op.add_column(
        "call_logs",
        sa.Column("hallucinations", sa.JSON(), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column("amd_result", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("call_logs", "amd_result")
    op.drop_column("call_logs", "hallucinations")
    op.drop_index("ix_customers_is_test_prospect", table_name="customers")
    op.drop_column("customers", "is_test_prospect")
