"""hr FSA tables — plans, enrollments, transactions, settings, compliance tests

Revision ID: 110
Revises: 109
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "110"
down_revision = "109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_fsa_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.String(32), nullable=False),  # healthcare / dependent_care / limited_purpose
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("annual_limit_employee", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("annual_limit_family", sa.Numeric(10, 2), nullable=True),
        sa.Column("plan_year_start", sa.Date, nullable=True),
        sa.Column("plan_year_end", sa.Date, nullable=True),
        sa.Column("grace_period_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("grace_period_months", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rollover_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("rollover_max", sa.Numeric(10, 2), nullable=True),
        sa.Column("runout_days", sa.Integer, nullable=False, server_default="90"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_hr_fsa_plans_kind", "hr_fsa_plans", ["kind"])

    op.create_table(
        "hr_fsa_enrollments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("hr_fsa_plans.id"), nullable=True),
        sa.Column("plan_kind", sa.String(32), nullable=False),
        sa.Column("annual_election", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("ytd_contributed", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("ytd_spent", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),  # active / pending / declined / terminated
        sa.Column("enrolled_at", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_fsa_enr_kind", "hr_fsa_enrollments", ["plan_kind"])
    op.create_index("ix_hr_fsa_enr_status", "hr_fsa_enrollments", ["status"])

    op.create_table(
        "hr_fsa_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("plan_kind", sa.String(32), nullable=False),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("merchant", sa.String(200), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="card_swipe"),  # card_swipe / reimbursement / adjustment
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),  # pending / approved / denied / substantiation_required
        sa.Column("notes", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_fsa_tx_date", "hr_fsa_transactions", ["transaction_date"])
    op.create_index("ix_hr_fsa_tx_status", "hr_fsa_transactions", ["status"])
    op.create_index("ix_hr_fsa_tx_kind", "hr_fsa_transactions", ["plan_kind"])

    op.create_table(
        "hr_fsa_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bank_name", sa.String(200), nullable=True),
        sa.Column("bank_account_last4", sa.String(16), nullable=True),
        sa.Column("bank_routing_last4", sa.String(16), nullable=True),
        sa.Column("bank_account_type", sa.String(32), nullable=True),  # checking / savings
        sa.Column("eligibility_waiting_days", sa.Integer, nullable=False, server_default="0"),
        sa.Column("eligibility_min_hours", sa.Integer, nullable=False, server_default="30"),
        sa.Column("eligibility_rule", sa.String(512), nullable=True),
        sa.Column("debit_card_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("auto_substantiation_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "hr_fsa_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),  # summary_plan_description / spd / amendment / notice
        sa.Column("url", sa.String(512), nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("uploaded_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "hr_fsa_compliance_tests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("test_kind", sa.String(64), nullable=False),  # eligibility / benefits_contributions / key_employee_concentration / 55_percent
        sa.Column("plan_year", sa.Integer, nullable=False),
        sa.Column("run_date", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="passed"),  # passed / failed / warning / pending
        sa.Column("highly_compensated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("non_highly_compensated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failure_reason", sa.String(1024), nullable=True),
        sa.Column("report_url", sa.String(512), nullable=True),
    )
    op.create_index("ix_hr_fsa_tests_kind", "hr_fsa_compliance_tests", ["test_kind"])
    op.create_index("ix_hr_fsa_tests_year", "hr_fsa_compliance_tests", ["plan_year"])

    op.create_table(
        "hr_fsa_exclusions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("excluded_from", sa.String(64), nullable=False, server_default="all"),  # all / healthcare / dependent_care
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hr_fsa_exclusions")
    op.drop_index("ix_hr_fsa_tests_year", table_name="hr_fsa_compliance_tests")
    op.drop_index("ix_hr_fsa_tests_kind", table_name="hr_fsa_compliance_tests")
    op.drop_table("hr_fsa_compliance_tests")
    op.drop_table("hr_fsa_documents")
    op.drop_table("hr_fsa_settings")
    op.drop_index("ix_hr_fsa_tx_kind", table_name="hr_fsa_transactions")
    op.drop_index("ix_hr_fsa_tx_status", table_name="hr_fsa_transactions")
    op.drop_index("ix_hr_fsa_tx_date", table_name="hr_fsa_transactions")
    op.drop_table("hr_fsa_transactions")
    op.drop_index("ix_hr_fsa_enr_status", table_name="hr_fsa_enrollments")
    op.drop_index("ix_hr_fsa_enr_kind", table_name="hr_fsa_enrollments")
    op.drop_table("hr_fsa_enrollments")
    op.drop_index("ix_hr_fsa_plans_kind", table_name="hr_fsa_plans")
    op.drop_table("hr_fsa_plans")
