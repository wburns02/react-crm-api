from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
from typing import Optional, Union
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
    """Schema for sending email.

    Accepts both new field names (to, body) and legacy field names (email, message)
    for backwards compatibility with deployed frontends.
    """
    customer_id: Optional[int] = None
    to: Optional[str] = Field(None, description="Email address")
    email: Optional[str] = Field(None, description="Email address (legacy)")
    subject: str = Field(..., min_length=1)
    body: Optional[str] = Field(None, min_length=1)
    message: Optional[str] = Field(None, description="Message content (legacy)")
    source: str = "react"

    @field_validator('customer_id', mode='before')
    @classmethod
    def parse_customer_id(cls, v):
        """Handle empty string as None for customer_id."""
        if v == '' or v is None:
            return None
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return None
        return v

    @model_validator(mode='after')
    def normalize_fields(self):
        """Normalize legacy field names to new ones."""
        # Use 'email' if 'to' is not provided
        if not self.to and self.email:
            self.to = self.email
        # Use 'message' if 'body' is not provided
        if not self.body and self.message:
            self.body = self.message
        # Validate required fields
        if not self.to:
            raise ValueError("Either 'to' or 'email' field is required")
        if not self.body:
            raise ValueError("Either 'body' or 'message' field is required")
        return self


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
