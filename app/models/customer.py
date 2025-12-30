from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class CustomerType(str, enum.Enum):
    residential = "residential"
    commercial = "commercial"
    hoa = "hoa"
    municipal = "municipal"
    property_management = "property_management"


class ProspectStage(str, enum.Enum):
    new_lead = "new_lead"
    contacted = "contacted"
    qualified = "qualified"
    quoted = "quoted"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"


class LeadSource(str, enum.Enum):
    referral = "referral"
    website = "website"
    google = "google"
    facebook = "facebook"
    repeat_customer = "repeat_customer"
    door_to_door = "door_to_door"
    other = "other"


class Customer(Base):
    """Customer model."""

    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), index=True)
    phone = Column(String(20))
    # Match Flask column names
    address_line1 = Column(String(255))
    city = Column(String(100))
    state = Column(String(50))
    postal_code = Column(String(20))

    customer_type = Column(
        Enum(CustomerType),
        default=CustomerType.residential
    )
    prospect_stage = Column(
        Enum(ProspectStage),
        default=ProspectStage.new_lead
    )
    lead_source = Column(Enum(LeadSource))

    notes = Column(Text)
    is_active = Column(Boolean, default=True)

    # React-specific fields (new schema)
    preferred_contact_method = Column(String(20))
    company_name = Column(String(255))
    tags = Column(String(500))  # JSON array stored as string

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    work_orders = relationship("WorkOrder", back_populates="customer")
    messages = relationship("Message", back_populates="customer")

    def __repr__(self):
        return f"<Customer {self.first_name} {self.last_name}>"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
