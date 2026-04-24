from fastapi import APIRouter

from app.hr.benefits.router import benefits_router
from app.hr.cobra.router import cobra_router
from app.hr.dashboard.router import overview_router
from app.hr.fsa.router import fsa_router
from app.hr.employees.router import employees_router
from app.hr.esign.router import esign_admin_router
from app.hr.onboarding.router import onboarding_admin_router
from app.hr.recruiting.applicant_router import applicants_router
from app.hr.recruiting.application_router import applications_router
from app.hr.recruiting.router import recruiting_router
from app.hr.recruiting.templates_admin_router import templates_admin_router
from app.hr.workflow.router import workflow_router


hr_router = APIRouter(prefix="/hr", tags=["hr"])
hr_router.include_router(overview_router)
hr_router.include_router(workflow_router)
hr_router.include_router(recruiting_router)
hr_router.include_router(templates_admin_router)
hr_router.include_router(applicants_router)
hr_router.include_router(applications_router)
hr_router.include_router(employees_router)
hr_router.include_router(onboarding_admin_router)
hr_router.include_router(esign_admin_router)
hr_router.include_router(benefits_router)
hr_router.include_router(fsa_router)
hr_router.include_router(cobra_router)


@hr_router.get("/health")
async def hr_health() -> dict[str, str]:
    return {"status": "ok", "module": "hr"}
