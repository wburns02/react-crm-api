"""hr COBRA tables — enrollments, payments, notices, settings, pre-plans

Revision ID: 111
Revises: 110
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "111"
down_revision = "110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_cobra_enrollments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("employee_label", sa.String(64), nullable=True),  # terminated / active etc.
        sa.Column("beneficiary_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="pending_election"),
        sa.Column("qualifying_event", sa.String(128), nullable=True),
        sa.Column("eligibility_date", sa.Date, nullable=True),
        sa.Column("exhaustion_date", sa.Date, nullable=True),
        sa.Column("bucket", sa.String(16), nullable=False, server_default="current"),  # current / upcoming / pending / past
        sa.Column("notice_sent_at", sa.DateTime, nullable=True),
        sa.Column("notes", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_hr_cobra_enr_bucket", "hr_cobra_enrollments", ["bucket"])
    op.create_index("ix_hr_cobra_enr_status", "hr_cobra_enrollments", ["status"])

    op.create_table(
        "hr_cobra_payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enrollment_id", UUID(as_uuid=True), sa.ForeignKey("hr_cobra_enrollments.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("beneficiary_name", sa.String(200), nullable=False),
        sa.Column("month", sa.String(16), nullable=False),  # e.g. 2026-05
        sa.Column("employee_charge_date", sa.Date, nullable=True),
        sa.Column("charged_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("company_reimbursement_date", sa.Date, nullable=True),
        sa.Column("reimbursement_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_cobra_pay_status", "hr_cobra_payments", ["status"])

    op.create_table(
        "hr_cobra_notices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enrollment_id", UUID(as_uuid=True), sa.ForeignKey("hr_cobra_enrollments.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("beneficiary_name", sa.String(200), nullable=False),
        sa.Column("type_of_notice", sa.String(200), nullable=False),
        sa.Column("addressed_to", sa.String(400), nullable=True),
        sa.Column("notice_url", sa.String(512), nullable=True),
        sa.Column("tracking_status", sa.String(64), nullable=False, server_default="In Production"),
        sa.Column("updated_on", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_cobra_notice_status", "hr_cobra_notices", ["tracking_status"])

    op.create_table(
        "hr_cobra_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("payment_method_label", sa.String(200), nullable=True),  # "ABC Inc. ****7890"
        sa.Column("bank_last4", sa.String(16), nullable=True),
        sa.Column("country_code", sa.String(8), nullable=True, server_default="US"),
        sa.Column("grace_period_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("election_window_days", sa.Integer, nullable=False, server_default="60"),
        sa.Column("send_election_notices_automatically", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "hr_cobra_pre_rippling_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("carrier", sa.String(200), nullable=False),
        sa.Column("plan_name", sa.String(200), nullable=False),
        sa.Column("plan_kind", sa.String(32), nullable=False, server_default="medical"),
        sa.Column("monthly_premium", sa.Numeric(10, 2), nullable=True),
        sa.Column("effective_from", sa.Date, nullable=True),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hr_cobra_pre_rippling_plans")
    op.drop_table("hr_cobra_settings")
    op.drop_index("ix_hr_cobra_notice_status", table_name="hr_cobra_notices")
    op.drop_table("hr_cobra_notices")
    op.drop_index("ix_hr_cobra_pay_status", table_name="hr_cobra_payments")
    op.drop_table("hr_cobra_payments")
    op.drop_index("ix_hr_cobra_enr_status", table_name="hr_cobra_enrollments")
    op.drop_index("ix_hr_cobra_enr_bucket", table_name="hr_cobra_enrollments")
    op.drop_table("hr_cobra_enrollments")
