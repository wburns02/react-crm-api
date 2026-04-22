from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.types import UUIDStr


Status = Literal["draft", "open", "paused", "closed"]
EmploymentType = Literal["full_time", "part_time", "contract"]


class RequisitionIn(BaseModel):
    slug: str = Field(min_length=2, max_length=128, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str
    department: str | None = None
    location_city: str | None = None
    location_state: str | None = None
    employment_type: EmploymentType = "full_time"
    compensation_min: Decimal | None = None
    compensation_max: Decimal | None = None
    compensation_display: str | None = None
    description_md: str | None = None
    requirements_md: str | None = None
    benefits_md: str | None = None
    status: Status = "draft"
    hiring_manager_id: int | None = None
    onboarding_template_id: UUIDStr | None = None
    publish_to_indeed: bool = True


class RequisitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    slug: str
    title: str
    department: str | None
    location_city: str | None
    location_state: str | None
    employment_type: EmploymentType
    compensation_display: str | None
    description_md: str | None
    requirements_md: str | None
    benefits_md: str | None
    status: Status
    opened_at: datetime | None
    closed_at: datetime | None
    hiring_manager_id: int | None
    onboarding_template_id: UUIDStr | None
    publish_to_indeed: bool
    created_at: datetime


class RequisitionPatch(BaseModel):
    title: str | None = None
    department: str | None = None
    location_city: str | None = None
    location_state: str | None = None
    employment_type: EmploymentType | None = None
    compensation_display: str | None = None
    description_md: str | None = None
    requirements_md: str | None = None
    benefits_md: str | None = None
    status: Status | None = None
    hiring_manager_id: int | None = None
    onboarding_template_id: UUIDStr | None = None
    publish_to_indeed: bool | None = None


class RequisitionWithCountsOut(RequisitionOut):
    applicant_count: int = 0
