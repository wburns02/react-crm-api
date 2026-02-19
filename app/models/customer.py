from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, Date, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from app.database import Base
import uuid
import uuid as uuid_module


class Customer(Base):
    """Customer model - matches Flask database schema."""

    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(255), index=True)
    phone = Column(String(20))

    # Address
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(50))
    postal_code = Column(String(20))

    # Status
    is_active = Column(Boolean, default=True)

    # Lead/Sales tracking (stored as varchar in Flask DB)
    lead_source = Column(String(50), default="unknown")
    lead_notes = Column(Text)
    prospect_stage = Column(String(50), default="new_lead")
    assigned_sales_rep = Column(String(100))
    estimated_value = Column(Float)
    customer_type = Column(String(50))

    # Septic system info
    tank_size_gallons = Column(Integer)
    number_of_tanks = Column(Integer)
    system_type = Column(String(100))
    manufacturer = Column(String(100))
    installer_name = Column(String(100))
    subdivision = Column(String(100))
    system_issued_date = Column(Date)

    # Tags
    tags = Column(String(500))

    # Timestamps
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    # Marketing attribution
    utm_source = Column(String(255))
    utm_medium = Column(String(255))
    utm_campaign = Column(String(255))
    utm_term = Column(String(255))
    utm_content = Column(String(255))
    gclid = Column(String(255))
    landing_page = Column(String(500))
    first_touch_ts = Column(DateTime)
    last_touch_ts = Column(DateTime)

    # Geolocation
    latitude = Column(Numeric)
    longitude = Column(Numeric)

    # Integrations
    default_payment_terms = Column(String(50))
    quickbooks_customer_id = Column(String(100))
    hubspot_contact_id = Column(String(100))
    servicenow_ticket_ref = Column(String(100))

    # Follow-up
    next_follow_up_date = Column(Date)

    # Multi-entity (LLC) support
    entity_id = Column(UUID(as_uuid=True), ForeignKey("company_entities.id"), nullable=True, index=True)

    # Relationships
    work_orders = relationship("WorkOrder", back_populates="customer")
    messages = relationship("Message", back_populates="customer")
    bookings = relationship("Booking", back_populates="customer", foreign_keys="Booking.customer_id")

    def __repr__(self):
        return f"<Customer {self.first_name} {self.last_name}>"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
