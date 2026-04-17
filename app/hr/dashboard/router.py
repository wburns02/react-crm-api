from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.hr.dashboard.overview import build_overview
from app.hr.dashboard.schemas import OverviewOut


overview_router = APIRouter(tags=["hr-dashboard"])


@overview_router.get("/overview", response_model=OverviewOut)
async def hr_overview(db: DbSession, user: CurrentUser) -> OverviewOut:
    data = await build_overview(db)
    return OverviewOut.model_validate(data)
