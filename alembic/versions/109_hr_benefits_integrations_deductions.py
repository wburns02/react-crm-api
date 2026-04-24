"""hr benefits — carrier integrations, account structure, scheduled deductions

Revision ID: 109
Revises: 108
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "109"
down_revision = "108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_benefit_carrier_integrations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("carrier", sa.String(128), nullable=False),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("enrollment_types", sa.String(512), nullable=True),  # comma-joined
        sa.Column("integration_status", sa.String(32), nullable=False, server_default="inactive"),  # active / inactive / pending
        sa.Column("form_forwarding_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("plan_year", sa.Integer, nullable=True),
        sa.Column("is_upcoming", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "hr_benefit_account_structures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("carrier", sa.String(128), nullable=False),
        sa.Column("class_type", sa.String(64), nullable=True),
        sa.Column("employee_group", sa.String(128), nullable=True),
        sa.Column("plan_name", sa.String(200), nullable=True),
        sa.Column("enrollment_tier", sa.String(64), nullable=True),
        sa.Column("class_value", sa.String(128), nullable=True),
        sa.Column("count_of_employees", sa.Integer, nullable=False, server_default="0"),
        sa.Column("group_rules", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "hr_benefit_scheduled_deductions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("benefit_type", sa.String(32), nullable=False, server_default="medical"),
        sa.Column("plan_name", sa.String(200), nullable=True),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("auto_manage", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("ee_rippling", sa.Numeric(10, 2), nullable=True),
        sa.Column("ee_in_payroll", sa.Numeric(10, 2), nullable=True),
        sa.Column("er_rippling", sa.Numeric(10, 2), nullable=True),
        sa.Column("er_in_payroll", sa.Numeric(10, 2), nullable=True),
        sa.Column("taxable_rippling", sa.Numeric(10, 2), nullable=True),
        sa.Column("taxable_in_payroll", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_hr_sched_ded_type", "hr_benefit_scheduled_deductions", ["benefit_type"])
    op.create_index("ix_hr_sched_ded_eff", "hr_benefit_scheduled_deductions", ["effective_date"])


def downgrade() -> None:
    op.drop_index("ix_hr_sched_ded_eff", table_name="hr_benefit_scheduled_deductions")
    op.drop_index("ix_hr_sched_ded_type", table_name="hr_benefit_scheduled_deductions")
    op.drop_table("hr_benefit_scheduled_deductions")
    op.drop_table("hr_benefit_account_structures")
    op.drop_table("hr_benefit_carrier_integrations")
