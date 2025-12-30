"""Call Log model for tracking phone calls via RingCentral."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Float, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class CallLog(Base):
    """Call log for RingCentral phone integration."""

    __tablename__ = "call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # RingCentral identifiers
    rc_call_id = Column(String(100), unique=True, nullable=True, index=True)
    rc_session_id = Column(String(100), nullable=True)

    # Call participants
    from_number = Column(String(20), nullable=False, index=True)
    to_number = Column(String(20), nullable=False, index=True)
    from_name = Column(String(255), nullable=True)
    to_name = Column(String(255), nullable=True)

    # CRM entity linking
    customer_id = Column(Integer, nullable=True, index=True)
    contact_name = Column(String(255), nullable=True)
    user_id = Column(String(36), nullable=True, index=True)  # CRM user who made/received call

    # Call details
    direction = Column(String(20), nullable=False)  # inbound, outbound
    call_type = Column(String(20), default="voice")  # voice, fax, sms
    status = Column(String(30), nullable=False, index=True)  # ringing, in_progress, completed, missed, voicemail

    # Timing
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    ring_duration_seconds = Column(Integer, nullable=True)

    # Recording
    recording_url = Column(String(500), nullable=True)
    recording_duration_seconds = Column(Integer, nullable=True)
    has_recording = Column(Boolean, default=False)

    # Transcription (via Whisper AI)
    transcription = Column(Text, nullable=True)
    transcription_status = Column(String(20), nullable=True)  # pending, completed, failed
    ai_summary = Column(Text, nullable=True)
    sentiment = Column(String(20), nullable=True)  # positive, negative, neutral
    sentiment_score = Column(Float, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)
    disposition = Column(String(50), nullable=True)  # sale, follow_up, no_answer, wrong_number, etc.

    # Activity link (auto-created activity)
    activity_id = Column(String(36), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<CallLog {self.direction} {self.from_number} -> {self.to_number}>"
