"""Company Entity model for multi-LLC support.

Each entity represents a separate legal business (LLC) with its own
bank account, Clover merchant, QBO company, invoice numbering, and branding.
"""

import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base


class CompanyEntity(Base):
    __tablename__ = "company_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(100), nullable=False)
    short_code = Column(String(10), unique=True, index=True)
    tax_id = Column(String(20))
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(50))
    postal_code = Column(String(20))
    phone = Column(String(20))
    email = Column(String(255))
    logo_url = Column(String(500))
    invoice_prefix = Column(String(10))
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<CompanyEntity {self.short_code}: {self.name}>"
