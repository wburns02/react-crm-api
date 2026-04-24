"""hr ACA + benefits settings

Revision ID: 112
Revises: 111
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "112"
down_revision = "111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_aca_filings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_year", sa.Integer, nullable=False),
        sa.Column("form_1094c_status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("form_1095c_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("irs_deadline", sa.Date, nullable=True),
        sa.Column("employee_deadline", sa.Date, nullable=True),
        sa.Column("filed_at", sa.DateTime, nullable=True),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_aca_filings_year", "hr_aca_filings", ["plan_year"])

    op.create_table(
        "hr_aca_lookback_policy",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("standard_measurement_months", sa.Integer, nullable=False, server_default="12"),
        sa.Column("stability_months", sa.Integer, nullable=False, server_default="12"),
        sa.Column("administrative_days", sa.Integer, nullable=False, server_default="90"),
        sa.Column("initial_measurement_months", sa.Integer, nullable=False, server_default="12"),
        sa.Column("hours_threshold", sa.Integer, nullable=False, server_default="130"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("effective_from", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "hr_aca_employee_hours",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("measurement_period", sa.String(64), nullable=False),
        sa.Column("total_hours", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("average_hours_per_week", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("is_full_time_eligible", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "hr_benefit_signatories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_type", sa.String(128), nullable=False),
        sa.Column("signatory_name", sa.String(200), nullable=True),
        sa.Column("signatory_department", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="signature_missing"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "hr_benefit_company_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("class_codes", sa.String(512), nullable=True),
        sa.Column("tax_std_not_taxed", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("tax_ltd_not_taxed", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("enrollment_hide_until_start", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("newly_eligible_window_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("part_time_offer_health", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("cost_show_monthly_in_app", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("cost_hide_company_contribution", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("ask_tobacco_question", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("qle_require_admin_approval", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("new_hire_preview_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("form_forwarding_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("carrier_connect_tier", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("benefit_admin_notification_user", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("hr_benefit_company_settings")
    op.drop_table("hr_benefit_signatories")
    op.drop_table("hr_aca_employee_hours")
    op.drop_table("hr_aca_lookback_policy")
    op.drop_index("ix_hr_aca_filings_year", table_name="hr_aca_filings")
    op.drop_table("hr_aca_filings")
