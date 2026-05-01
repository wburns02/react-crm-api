"""quote → workorder estimate support.

Adds three columns to the `quotes` table to support the new "workorder
estimate" concept:

- `kind`: distinguishes a sales quote from a workorder estimate
  (constrained to 'sales_quote' | 'wo_estimate').
- `work_order_id`: optional FK to `work_orders.id` for estimates that
  belong to a specific workorder.
- `converted_to_invoice_id`: optional FK to `invoices.id` set when an
  estimate is converted into an invoice (which is then pushed to QBO).

Indexes are added on `work_order_id` alone and on
`(work_order_id, status)` so the active-estimate-for-WO lookup is cheap.

Revision ID: 119
Revises: 118
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "119"
down_revision = "118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quotes",
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default="sales_quote",
        ),
    )
    op.create_check_constraint(
        "ck_quotes_kind",
        "quotes",
        "kind IN ('sales_quote', 'wo_estimate')",
    )
    op.create_index("ix_quotes_kind", "quotes", ["kind"])

    # quotes.work_order_id and its FK to work_orders already exist
    # (added in migration 046). We add only the indexes here.
    op.create_index(
        "ix_quotes_work_order_id",
        "quotes",
        ["work_order_id"],
    )
    op.create_index(
        "ix_quotes_work_order_id_status",
        "quotes",
        ["work_order_id", "status"],
    )

    op.add_column(
        "quotes",
        sa.Column(
            "converted_to_invoice_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_quotes_converted_to_invoice_id_invoices",
        "quotes",
        "invoices",
        ["converted_to_invoice_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_quotes_converted_to_invoice_id_invoices",
        "quotes",
        type_="foreignkey",
    )
    op.drop_column("quotes", "converted_to_invoice_id")

    op.drop_index("ix_quotes_work_order_id_status", table_name="quotes")
    op.drop_index("ix_quotes_work_order_id", table_name="quotes")
    # work_order_id column + FK predate migration 119; do not drop here.

    op.drop_index("ix_quotes_kind", table_name="quotes")
    op.drop_constraint("ck_quotes_kind", "quotes", type_="check")
    op.drop_column("quotes", "kind")
