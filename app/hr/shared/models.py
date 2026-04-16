from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.sql import func
from uuid import uuid4

from app.database import Base


_INET = INET().with_variant(String(45), "sqlite")


class HrAuditLog(Base):
    __tablename__ = "hr_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    event = Column(String(64), nullable=False)
    diff = Column(JSON, default=dict)
    actor_user_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    actor_ip = Column(_INET, nullable=True)
    actor_user_agent = Column(Text, nullable=True)
    actor_location = Column(String(128), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_hr_audit_log_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_hr_audit_log_actor", "actor_user_id", "created_at"),
    )


class HrRoleAssignment(Base):
    __tablename__ = "hr_role_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    role = Column(String(32), nullable=False)
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_hr_role_assignments_active", "role", "active", "priority"),
    )
