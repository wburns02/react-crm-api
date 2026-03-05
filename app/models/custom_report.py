from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from uuid import uuid4
from app.database import Base


class CustomReport(Base):
    __tablename__ = "custom_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("company_entities.id"), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    report_type = Column(String(30), default="table")
    data_source = Column(String(50), nullable=False)
    columns = Column(JSON, default=list)
    filters = Column(JSON, default=list)
    group_by = Column(JSON, default=list)
    sort_by = Column(JSON, nullable=True)
    date_range = Column(JSON, nullable=True)
    chart_config = Column(JSON, nullable=True)
    layout = Column(JSON, nullable=True)
    is_favorite = Column(Boolean, default=False)
    is_shared = Column(Boolean, default=False)
    schedule = Column(JSON, nullable=True)
    last_generated_at = Column(DateTime, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    report_id = Column(UUID(as_uuid=True), ForeignKey("custom_reports.id", ondelete="CASCADE"), nullable=False)
    data = Column(JSON, default=list)
    row_count = Column(Integer, default=0)
    generated_at = Column(DateTime, server_default=func.now())
