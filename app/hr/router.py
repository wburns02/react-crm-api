from fastapi import APIRouter

from app.hr.workflow.router import workflow_router


hr_router = APIRouter(prefix="/hr", tags=["hr"])
hr_router.include_router(workflow_router)


@hr_router.get("/health")
async def hr_health() -> dict[str, str]:
    return {"status": "ok", "module": "hr"}
