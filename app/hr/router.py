from fastapi import APIRouter

from app.hr.esign.router import esign_admin_router
from app.hr.recruiting.applicant_router import applicants_router
from app.hr.recruiting.router import recruiting_router
from app.hr.workflow.router import workflow_router


hr_router = APIRouter(prefix="/hr", tags=["hr"])
hr_router.include_router(workflow_router)
hr_router.include_router(recruiting_router)
hr_router.include_router(applicants_router)
hr_router.include_router(esign_admin_router)


@hr_router.get("/health")
async def hr_health() -> dict[str, str]:
    return {"status": "ok", "module": "hr"}
