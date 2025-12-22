from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.message import MessageType, MessageDirection, MessageStatus


class MessageBase(BaseModel):
    """Base message schema."""
    customer_id: Optional[int] = None
    type: MessageType
    direction: MessageDirection
    to_address: str
    from_address: Optional[str] = None
    subject: Optional[str] = None
    content: str


class MessageCreate(MessageBase):
    """Schema for creating a message."""
    source: str = "react"


class SendSMSRequest(BaseModel):
    """Schema for sending SMS."""
    customer_id: Optional[int] = None
    to: str = Field(..., description="Phone number to send to")
    body: str = Field(..., min_length=1, description="Message content")
    source: str = "react"


class SendEmailRequest(BaseModel):
    """Schema for sending email."""
    customer_id: Optional[int] = None
    to: str = Field(..., description="Email address")
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    source: str = "react"


class MessageResponse(BaseModel):
    """Schema for message response."""
    id: int
    customer_id: Optional[int] = None
    type: MessageType
    direction: MessageDirection
    status: MessageStatus
    to_address: str
    from_address: Optional[str] = None
    subject: Optional[str] = None
    content: str
    twilio_sid: Optional[str] = None
    source: str
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Paginated message list response."""
    items: list[MessageResponse]
    total: int
    page: int
    page_size: int


class TwilioWebhookPayload(BaseModel):
    """Schema for Twilio webhook payload."""
    MessageSid: str
    AccountSid: str
    From: str
    To: str
    Body: Optional[str] = None
    MessageStatus: Optional[str] = None
    ErrorCode: Optional[str] = None
    ErrorMessage: Optional[str] = None
