"""hr payroll — pay runs + people status

Revision ID: 113
Revises: 112
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "113"
down_revision = "112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_pay_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("pay_schedule_name", sa.String(200), nullable=True),
        sa.Column("entity", sa.String(200), nullable=True),
        sa.Column("pay_run_type", sa.String(32), nullable=False, server_default="regular"),
        sa.Column("pay_date", sa.Date, nullable=True),
        sa.Column("approve_by", sa.DateTime, nullable=True),
        sa.Column("funding_method", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="upcoming"),
        sa.Column("action_text", sa.String(128), nullable=True),
        sa.Column("failure_reason", sa.String(512), nullable=True),
        sa.Column("archived_by", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_hr_pay_runs_status", "hr_pay_runs", ["status"])
    op.create_index("ix_hr_pay_runs_pay_date", "hr_pay_runs", ["pay_date"])

    op.create_table(
        "hr_payroll_people_status",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("employee_title", sa.String(200), nullable=True),
        sa.Column("pay_schedule", sa.String(200), nullable=True),
        sa.Column("status", sa.String(64), nullable=False, server_default="payroll_ready"),
        sa.Column("bucket", sa.String(32), nullable=False, server_default="payroll_ready"),
        sa.Column("critical_missing_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("missing_fields", sa.String(1024), nullable=True),
        sa.Column("signatory_status", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_hr_payroll_people_bucket", "hr_payroll_people_status", ["bucket"])


def downgrade() -> None:
    op.drop_index("ix_hr_payroll_people_bucket", table_name="hr_payroll_people_status")
    op.drop_table("hr_payroll_people_status")
    op.drop_index("ix_hr_pay_runs_pay_date", table_name="hr_pay_runs")
    op.drop_index("ix_hr_pay_runs_status", table_name="hr_pay_runs")
    op.drop_table("hr_pay_runs")
