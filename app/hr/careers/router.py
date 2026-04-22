from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.api.deps import DbSession
from app.hr.employees.models import HrOnboardingToken
from app.hr.recruiting.careers_feed import build_indeed_xml
from app.hr.recruiting.services import get_requisition_by_slug, list_requisitions


_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


careers_router = APIRouter(prefix="/careers", tags=["careers-public"])


@careers_router.get("/jobs.xml", response_class=Response)
@careers_router.get("/indeed-feed.xml", response_class=Response)
async def jobs_feed(request: Request, db: DbSession) -> Response:
    reqs = await list_requisitions(db, status="open")
    # Respect per-requisition publish_to_indeed opt-out.  Older rows default
    # to true (see migration 105).
    reqs = [r for r in reqs if getattr(r, "publish_to_indeed", True)]
    base_url = str(request.base_url).rstrip("/")
    xml = build_indeed_xml(base_url, reqs)
    return Response(content=xml, media_type="application/xml")


@careers_router.get("", response_class=HTMLResponse)
@careers_router.get("/", response_class=HTMLResponse)
async def careers_index(request: Request, db: DbSession) -> HTMLResponse:
    reqs = await list_requisitions(db, status="open")
    return _TEMPLATES.TemplateResponse(
        request, "careers_index.html", {"reqs": reqs}
    )


@careers_router.get("/{slug}", response_class=HTMLResponse)
async def requisition_detail(
    request: Request, slug: str, db: DbSession
) -> HTMLResponse:
    req = await get_requisition_by_slug(db, slug)
    if req is None or req.status != "open":
        return HTMLResponse("Not found", status_code=404)
    return _TEMPLATES.TemplateResponse(
        request, "requisition_detail.html", {"req": req}
    )


@careers_router.get("/{slug}/apply", response_class=HTMLResponse)
async def apply(request: Request, slug: str, db: DbSession) -> HTMLResponse:
    req = await get_requisition_by_slug(db, slug)
    if req is None or req.status != "open":
        return HTMLResponse("Not found", status_code=404)
    return _TEMPLATES.TemplateResponse(
        request, "apply.html", {"req": req}
    )


# Plan 3: public MyOnboarding SSR shell.  Lives under the careers router so
# it shares the same Jinja2 templates dir and root mount (no /api/v2 prefix).
onboarding_ssr_router = APIRouter(tags=["hr-onboarding-public-ssr"])


@onboarding_ssr_router.get("/onboarding/{token}", response_class=HTMLResponse)
async def my_onboarding(
    request: Request, token: str, db: DbSession
) -> HTMLResponse:
    row = (
        await db.execute(
            select(HrOnboardingToken).where(HrOnboardingToken.token == token)
        )
    ).scalar_one_or_none()
    if row is None:
        return HTMLResponse(
            "<p>This link is invalid or expired.</p>", status_code=404
        )
    return _TEMPLATES.TemplateResponse(
        request, "my_onboarding.html", {"token": token}
    )
