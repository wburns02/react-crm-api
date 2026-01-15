"""Call Log model for tracking phone calls via RingCentral.

NOTE: This model matches the EXISTING production database schema.
The column names here must match the actual call_logs table.
"""
from sqlalchemy import Column, String, DateTime, Text, Integer, Date, Time, JSON, Float
from sqlalchemy.sql import func


from app.database import Base


class CallLog(Base):
    """Call log for RingCentral phone integration.

    Maps to the existing call_logs table in production.
    """

    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # RingCentral identifiers (match actual DB columns)
    ringcentral_call_id = Column(String(100), nullable=True, index=True)
    ringcentral_session_id = Column(String(100), nullable=True)

    # Call participants (using actual DB column names)
    caller_number = Column(String(50), nullable=True, index=True)
    called_number = Column(String(50), nullable=True, index=True)

    # CRM entity linking
    customer_id = Column(Integer, nullable=True, index=True)
    answered_by = Column(String(255), nullable=True)
    assigned_to = Column(String(255), nullable=True)

    # Call details
    direction = Column(String(20), nullable=True)  # inbound, outbound
    call_type = Column(String(50), nullable=True)  # voice, fax, sms
    call_disposition = Column(String(100), nullable=True)  # outcome/result

    # Timing (using actual DB column names)
    call_date = Column(Date, nullable=True)
    call_time = Column(Time, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    ring_duration = Column(Integer, nullable=True)

    # Recording
    recording_url = Column(String(500), nullable=True)

    # Notes and tags
    notes = Column(Text, nullable=True)
    # Using JSON instead of ARRAY for SQLite test compatibility
    tags = Column(JSON, nullable=True)

    # External system reference
    external_system = Column(String(100), nullable=True)

    # AI Analysis fields (added via direct SQL 2026-01-15)
    transcription = Column(Text, nullable=True)  # Full call transcript
    transcription_status = Column(String(20), nullable=True)  # pending/completed/failed
    ai_summary = Column(Text, nullable=True)  # AI-generated summary
    sentiment = Column(String(20), nullable=True)  # positive/negative/neutral
    sentiment_score = Column(Float, nullable=True)  # -100 to 100
    quality_score = Column(Float, nullable=True)  # 0-100 overall quality
    csat_prediction = Column(Float, nullable=True)  # 1-5 predicted CSAT
    escalation_risk = Column(String(20), nullable=True)  # low/medium/high/critical
    professionalism_score = Column(Float, nullable=True)  # 0-100
    empathy_score = Column(Float, nullable=True)  # 0-100
    clarity_score = Column(Float, nullable=True)  # 0-100
    resolution_score = Column(Float, nullable=True)  # 0-100
    topics = Column(JSON, nullable=True)  # List of topic strings
    analyzed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Aliases for API compatibility (properties that map to actual columns)
    @property
    def rc_call_id(self):
        return self.ringcentral_call_id

    @property
    def rc_session_id(self):
        return self.ringcentral_session_id

    @property
    def from_number(self):
        return self.caller_number

    @property
    def to_number(self):
        return self.called_number

    @property
    def start_time(self):
        """Combine call_date and call_time into a datetime."""
        from datetime import datetime
        if self.call_date and self.call_time:
            return datetime.combine(self.call_date, self.call_time)
        elif self.call_date:
            return datetime.combine(self.call_date, datetime.min.time())
        return self.created_at

    @property
    def status(self):
        return self.call_disposition or "unknown"

    @property
    def disposition(self):
        return self.call_disposition

    @property
    def contact_name(self):
        return self.answered_by

    @property
    def has_recording(self):
        return bool(self.recording_url)

    def __repr__(self):
        return f"<CallLog {self.direction} {self.caller_number} -> {self.called_number}>"
