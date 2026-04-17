from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.types import UUIDStr


Stage = Literal["screen", "ride_along", "offer", "hired", "rejected"]
Channel = Literal["sms", "email"]


class MessageTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    stage: str
    channel: Channel
    body: str
    active: bool
    updated_at: datetime | None
    created_at: datetime


class MessageTemplatePatch(BaseModel):
    body: str | None = None
    active: bool | None = None
