"""
User Activity Log — tracks login/logout, page views, API actions, security events.

Designed for minimal performance impact:
- Async inserts (fire-and-forget background tasks)
- Partitioned by created_at for fast pruning
- Indexed on user_id + created_at for per-user queries
- Auto-prune records older than 90 days
"""
from sqlalchemy import Column, String, DateTime, Text, Integer, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import uuid


class UserActivityLog(Base):
    __tablename__ = "user_activity_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Who
    user_id = Column(Integer, nullable=True, index=True)  # api_users.id (Integer PK)
    user_email = Column(String(100), nullable=True)
    user_name = Column(String(200), nullable=True)

    # What happened
    category = Column(String(30), nullable=False, index=True)
    # Categories: auth, navigation, action, security, system
    action = Column(String(50), nullable=False, index=True)
    # Actions: login, logout, login_failed, mfa_verified, mfa_failed,
    #          page_view, api_call, create, update, delete,
    #          password_changed, mfa_enabled, mfa_disabled, role_switched
    description = Column(Text, nullable=True)

    # Where (request context)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    source = Column(String(50), nullable=True)  # crm, employee_portal, customer_portal, api, mobile

    # What resource was accessed
    resource_type = Column(String(50), nullable=True)  # work_order, customer, invoice, etc.
    resource_id = Column(String(100), nullable=True)
    endpoint = Column(String(200), nullable=True)  # API path
    http_method = Column(String(10), nullable=True)
    status_code = Column(Integer, nullable=True)

    # Performance
    response_time_ms = Column(Integer, nullable=True)

    # Session tracking
    session_id = Column(String(50), nullable=True)  # Correlation ID = session

    # Entity (multi-LLC)
    entity_id = Column(String(100), nullable=True)

    # When
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        # Composite indexes for common queries
        Index("ix_user_activity_user_created", "user_id", "created_at"),
        Index("ix_user_activity_category_created", "category", "created_at"),
        Index("ix_user_activity_action_created", "action", "created_at"),
    )

    def __repr__(self):
        return f"<UserActivityLog {self.category}:{self.action} by {self.user_email}>"
