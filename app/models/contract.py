"""Contract model for customer service agreements."""

from sqlalchemy import Column, String, DateTime, Text, Integer, Date, Boolean, Float, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Contract(Base):
    """Service contract/agreement with customers."""

    __tablename__ = "contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Contract identification
    contract_number = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    contract_type = Column(String(50), nullable=False)  # maintenance, service, annual, multi-year

    # Customer
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    customer_name = Column(String(255), nullable=True)

    # Template reference
    template_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Contract terms
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False, index=True)
    auto_renew = Column(Boolean, default=False)
    renewal_terms = Column(Text, nullable=True)

    # Pricing
    total_value = Column(Float, nullable=True)
    billing_frequency = Column(String(20), default="monthly")  # monthly, quarterly, annual, one-time
    payment_terms = Column(String(100), nullable=True)  # net30, net60, due-on-receipt

    # Services covered (JSON array)
    services_included = Column(JSON, nullable=True)
    # Example: [
    #   {"service_code": "PUMP-1000", "frequency": "annual", "quantity": 1},
    #   {"service_code": "MAINT-100", "frequency": "quarterly", "quantity": 4}
    # ]

    # Coverage
    covered_properties = Column(JSON, nullable=True)  # List of property addresses/IDs
    coverage_details = Column(Text, nullable=True)

    # Status
    status = Column(String(20), default="draft")  # draft, pending, active, expired, cancelled, renewed

    # Signature tracking
    requires_signature = Column(Boolean, default=True)
    customer_signed = Column(Boolean, default=False)
    customer_signed_date = Column(DateTime(timezone=True), nullable=True)
    company_signed = Column(Boolean, default=False)
    company_signed_date = Column(DateTime(timezone=True), nullable=True)
    signature_request_id = Column(String(36), nullable=True)  # Link to e-signature request

    # Document
    document_url = Column(String(500), nullable=True)
    signed_document_url = Column(String(500), nullable=True)

    # Terms and conditions
    terms_and_conditions = Column(Text, nullable=True)
    special_terms = Column(Text, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)

    # Audit
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Contract {self.contract_number} - {self.customer_name}>"

    @property
    def is_active(self):
        from datetime import date

        today = date.today()
        return self.status == "active" and self.start_date <= today <= self.end_date

    @property
    def days_until_expiry(self):
        from datetime import date

        if not self.end_date:
            return None
        return (self.end_date - date.today()).days

    @property
    def is_expired(self):
        from datetime import date

        return self.end_date < date.today()

    @property
    def is_fully_signed(self):
        return self.customer_signed and self.company_signed
