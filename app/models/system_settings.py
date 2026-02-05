from sqlalchemy import Column, String, JSON, DateTime, Integer
from sqlalchemy.sql import func
from app.database import Base


class SystemSettingStore(Base):
    """Key-value settings store for admin configuration.

    Uses category + key composite for flexibility.
    Each row stores one settings category as a JSON blob.
    """

    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), unique=True, nullable=False, index=True)
    settings_data = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    updated_by = Column(Integer)  # user_id

    def __repr__(self):
        return f"<SystemSettingStore category={self.category}>"
