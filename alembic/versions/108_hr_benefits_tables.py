"""hr benefits tables — plans, enrollments, events, eoi requests

Revision ID: 108
Revises: 107
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "108"
down_revision = "107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_benefit_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.String(32), nullable=False),  # medical / dental / vision / fsa / hsa / life / ad_d / ltd / std
        sa.Column("carrier", sa.String(128), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("monthly_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("employee_contribution", sa.Numeric(10, 2), nullable=True),
        sa.Column("employer_contribution", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_benefit_plans_kind", "hr_benefit_plans", ["kind"])

    op.create_table(
        "hr_benefit_enrollments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("employee_title", sa.String(200), nullable=True),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("hr_benefit_plans.id"), nullable=True),
        sa.Column("plan_name", sa.String(200), nullable=True),
        sa.Column("carrier", sa.String(128), nullable=True),
        sa.Column("benefit_type", sa.String(32), nullable=False, server_default="medical"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),  # active / waived / terminated / pending
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("termination_date", sa.Date, nullable=True),
        sa.Column("monthly_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("monthly_deduction", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_hr_benefit_enrollments_type", "hr_benefit_enrollments", ["benefit_type"])
    op.create_index("ix_hr_benefit_enrollments_status", "hr_benefit_enrollments", ["status"])
    op.create_index("ix_hr_benefit_enrollments_effective", "hr_benefit_enrollments", ["effective_date"])

    op.create_table(
        "hr_benefit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("employee_title", sa.String(200), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),  # Demographic Change / New Hire / Termination / QLE / COBRA Enrollment
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),  # pending / completed
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("completion_date", sa.Date, nullable=True),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_benefit_events_status", "hr_benefit_events", ["status"])
    op.create_index("ix_hr_benefit_events_effective", "hr_benefit_events", ["effective_date"])

    op.create_table(
        "hr_benefit_eoi_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("member_name", sa.String(200), nullable=False),
        sa.Column("member_type", sa.String(32), nullable=False, server_default="employee"),  # employee / spouse / dependent
        sa.Column("benefit_type", sa.String(32), nullable=False, server_default="life"),
        sa.Column("plan_name", sa.String(200), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),  # pending / approved / denied / withdrawn
        sa.Column("enrollment_created_at", sa.Date, nullable=True),
        sa.Column("enrollment_ends_at", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_benefit_eoi_status", "hr_benefit_eoi_requests", ["status"])
    op.create_index("ix_hr_benefit_eoi_benefit_type", "hr_benefit_eoi_requests", ["benefit_type"])

    op.create_table(
        "hr_benefit_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("change_type", sa.String(64), nullable=False),  # COBRA Initial Enrollment / Qualifying Life Event / Termination/Loss of Eligibility / COBRA Qualifying Life Event
        sa.Column("affected_lines", sa.Integer, nullable=False, server_default="1"),
        sa.Column("completed_date", sa.Date, nullable=True),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("changed_by", sa.String(128), nullable=True),
        sa.Column("is_terminated", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_benefit_history_completed", "hr_benefit_history", ["completed_date"])


def downgrade() -> None:
    op.drop_index("ix_hr_benefit_history_completed", table_name="hr_benefit_history")
    op.drop_table("hr_benefit_history")
    op.drop_index("ix_hr_benefit_eoi_benefit_type", table_name="hr_benefit_eoi_requests")
    op.drop_index("ix_hr_benefit_eoi_status", table_name="hr_benefit_eoi_requests")
    op.drop_table("hr_benefit_eoi_requests")
    op.drop_index("ix_hr_benefit_events_effective", table_name="hr_benefit_events")
    op.drop_index("ix_hr_benefit_events_status", table_name="hr_benefit_events")
    op.drop_table("hr_benefit_events")
    op.drop_index("ix_hr_benefit_enrollments_effective", table_name="hr_benefit_enrollments")
    op.drop_index("ix_hr_benefit_enrollments_status", table_name="hr_benefit_enrollments")
    op.drop_index("ix_hr_benefit_enrollments_type", table_name="hr_benefit_enrollments")
    op.drop_table("hr_benefit_enrollments")
    op.drop_index("ix_hr_benefit_plans_kind", table_name="hr_benefit_plans")
    op.drop_table("hr_benefit_plans")
