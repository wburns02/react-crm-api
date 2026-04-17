from pydantic import BaseModel


class PendingTaskOut(BaseModel):
    id: str
    name: str
    instance_id: str
    due_at: str | None
    status: str


class OverviewOut(BaseModel):
    open_requisitions: int
    applicants_last_7d: int
    active_onboardings: int
    active_offboardings: int
    expiring_certs_30d: int
    active_applications_by_stage: dict[str, int]
    pending_hr_tasks: list[PendingTaskOut]
