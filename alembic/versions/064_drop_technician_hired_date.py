"""Drop legacy hired_date duplicate column from technicians table.

hire_date is the canonical column. hired_date was a legacy duplicate.

Revision ID: 064
Revises: 063
Create Date: 2026-02-20
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("technicians", "hired_date")


def downgrade() -> None:
    op.add_column(
        "technicians",
        sa.Column("hired_date", sa.Date(), nullable=True),
    )
