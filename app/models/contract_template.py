"""Contract Template model for reusable contract templates."""

from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ContractTemplate(Base):
    """Reusable contract templates."""

    __tablename__ = "contract_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Template identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    contract_type = Column(String(50), nullable=False)  # maintenance, service, annual, multi-year

    # Template content
    content = Column(Text, nullable=False)  # HTML or markdown template
    terms_and_conditions = Column(Text, nullable=True)

    # Default values
    default_duration_months = Column(Integer, default=12)
    default_billing_frequency = Column(String(20), default="monthly")
    default_payment_terms = Column(String(100), nullable=True)
    default_auto_renew = Column(Boolean, default=False)

    # Services (default services for this template type)
    default_services = Column(JSON, nullable=True)
    # Example: [
    #   {"service_code": "PUMP-1000", "name": "Annual Pumping", "frequency": "annual"},
    # ]

    # Pricing defaults
    base_price = Column(Float, nullable=True)
    pricing_notes = Column(Text, nullable=True)

    # Variables (placeholders in template)
    variables = Column(JSON, nullable=True)
    # Example: ["customer_name", "service_address", "tank_size", "start_date"]

    # Status
    is_active = Column(Boolean, default=True)
    version = Column(Integer, default=1)

    # Audit
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<ContractTemplate {self.code} - {self.name}>"
