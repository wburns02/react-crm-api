"""hr employee extension tables (certs, docs, fuel cards, truck/fuel-card/access assignments, onboarding tokens)

Revision ID: 103
Revises: 102
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "103"
down_revision = "102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_employee_certifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("number", sa.String(128), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("issuing_authority", sa.String(128), nullable=True),
        sa.Column("document_storage_key", sa.String(512), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_hr_emp_cert_employee", "hr_employee_certifications", ["employee_id"])
    op.create_index("ix_hr_emp_cert_expires", "hr_employee_certifications", ["expires_at"])

    op.create_table(
        "hr_employee_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("signed_document_id", UUID(as_uuid=True), sa.ForeignKey("hr_signed_documents.id"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
    )
    op.create_index("ix_hr_emp_doc_employee_kind", "hr_employee_documents", ["employee_id", "kind"])

    op.create_table(
        "hr_fuel_cards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("card_number_masked", sa.String(32), nullable=False),
        sa.Column("vendor", sa.String(64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "hr_fuel_card_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=False),
        sa.Column("card_id", UUID(as_uuid=True), sa.ForeignKey("hr_fuel_cards.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("unassigned_at", sa.DateTime(), nullable=True),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("unassigned_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
    )
    op.create_index("ix_hr_fuel_assign_employee_open", "hr_fuel_card_assignments", ["employee_id", "unassigned_at"])

    op.create_table(
        "hr_truck_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=False),
        sa.Column("truck_id", UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("unassigned_at", sa.DateTime(), nullable=True),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("unassigned_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
    )
    op.create_index("ix_hr_truck_assign_employee_open", "hr_truck_assignments", ["employee_id", "unassigned_at"])

    op.create_table(
        "hr_access_grants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("technicians.id"), nullable=False),
        sa.Column("system", sa.String(32), nullable=False),
        sa.Column("identifier", sa.String(256), nullable=True),
        sa.Column("granted_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("granted_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("revoked_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
    )
    op.create_index("ix_hr_access_employee_system", "hr_access_grants", ["employee_id", "system"])

    op.create_table(
        "hr_onboarding_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "instance_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_instances.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("viewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hr_onboarding_tokens")
    op.drop_index("ix_hr_access_employee_system", table_name="hr_access_grants")
    op.drop_table("hr_access_grants")
    op.drop_index("ix_hr_truck_assign_employee_open", table_name="hr_truck_assignments")
    op.drop_table("hr_truck_assignments")
    op.drop_index("ix_hr_fuel_assign_employee_open", table_name="hr_fuel_card_assignments")
    op.drop_table("hr_fuel_card_assignments")
    op.drop_table("hr_fuel_cards")
    op.drop_index("ix_hr_emp_doc_employee_kind", table_name="hr_employee_documents")
    op.drop_table("hr_employee_documents")
    op.drop_index("ix_hr_emp_cert_expires", table_name="hr_employee_certifications")
    op.drop_index("ix_hr_emp_cert_employee", table_name="hr_employee_certifications")
    op.drop_table("hr_employee_certifications")
