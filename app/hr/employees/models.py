from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class HrEmployeeCertification(Base):
    __tablename__ = "hr_employee_certifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(
        UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=False
    )
    kind = Column(String(32), nullable=False)
    number = Column(String(128), nullable=True)
    issued_at = Column(Date, nullable=True)
    expires_at = Column(Date, nullable=True)
    issuing_authority = Column(String(128), nullable=True)
    document_storage_key = Column(String(512), nullable=True)
    status = Column(String(16), nullable=False, default="active")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_hr_emp_cert_employee", "employee_id"),
        Index("ix_hr_emp_cert_expires", "expires_at"),
    )


class HrEmployeeDocument(Base):
    __tablename__ = "hr_employee_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(
        UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=False
    )
    kind = Column(String(32), nullable=False)
    storage_key = Column(String(512), nullable=False)
    signed_document_id = Column(
        UUID(as_uuid=True), ForeignKey("hr_signed_documents.id"), nullable=True
    )
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    expires_at = Column(Date, nullable=True)

    __table_args__ = (Index("ix_hr_emp_doc_employee_kind", "employee_id", "kind"),)


class HrFuelCard(Base):
    __tablename__ = "hr_fuel_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    card_number_masked = Column(String(32), nullable=False)
    vendor = Column(String(64), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrFuelCardAssignment(Base):
    __tablename__ = "hr_fuel_card_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(
        UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=False
    )
    card_id = Column(
        UUID(as_uuid=True), ForeignKey("hr_fuel_cards.id"), nullable=False
    )
    assigned_at = Column(DateTime, server_default=func.now(), nullable=False)
    unassigned_at = Column(DateTime, nullable=True)
    assigned_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    unassigned_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)

    __table_args__ = (
        Index("ix_hr_fuel_assign_employee_open", "employee_id", "unassigned_at"),
    )


class HrTruckAssignment(Base):
    __tablename__ = "hr_truck_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(
        UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=False
    )
    truck_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now(), nullable=False)
    unassigned_at = Column(DateTime, nullable=True)
    assigned_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    unassigned_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)

    __table_args__ = (
        Index("ix_hr_truck_assign_employee_open", "employee_id", "unassigned_at"),
    )


class HrAccessGrant(Base):
    __tablename__ = "hr_access_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(
        UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=False
    )
    system = Column(String(32), nullable=False)
    identifier = Column(String(256), nullable=True)
    granted_at = Column(DateTime, server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    granted_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    revoked_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)

    __table_args__ = (
        Index("ix_hr_access_employee_system", "employee_id", "system"),
    )


class HrOnboardingToken(Base):
    """Opaque token granting a new hire access to /onboarding/<token> and the
    companion public API. One-to-one with an onboarding workflow instance."""

    __tablename__ = "hr_onboarding_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    instance_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    token = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    viewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
