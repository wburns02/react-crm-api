"""add publish_to_indeed to hr_requisitions

Revision ID: 105
Revises: 104
"""
from alembic import op
import sqlalchemy as sa


revision = "105"
down_revision = "104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hr_requisitions",
        sa.Column(
            "publish_to_indeed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("hr_requisitions", "publish_to_indeed")
