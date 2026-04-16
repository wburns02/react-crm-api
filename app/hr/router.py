from fastapi import APIRouter

hr_router = APIRouter(prefix="/hr", tags=["hr"])


@hr_router.get("/health")
async def hr_health() -> dict[str, str]:
    return {"status": "ok", "module": "hr"}
