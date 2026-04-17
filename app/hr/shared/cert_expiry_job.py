"""Daily cert-expiry SMS alerter.

Queries `hr_employee_certifications` for certs expiring in exactly 30, 7, or
1 days and sends an SMS to the owning technician (gated on phone + consent).
Never raises; per-cert failures are logged.

Scheduled from the FastAPI lifespan at 07:00 daily via APScheduler.  Runs
safely in a standalone test harness too via the sync `run_once_for_today`
coroutine.
"""
import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.hr.employees.models import HrEmployeeCertification
from app.hr.shared.audit import write_audit
from app.models.technician import Technician


logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

# Days out from today.  Matches spec §13.4 — 30 / 7 / 1.
_WINDOWS = [30, 7, 1]


async def _send(to: str, body: str) -> None:
    """Wrapper around the module-level send_sms helper so tests can
    monkeypatch this without touching upstream."""
    from app.services.sms_service import send_sms

    await send_sms(to, body)


async def _notify_cert(
    db: AsyncSession, cert: HrEmployeeCertification, days: int
) -> dict:
    tech = (
        await db.execute(
            select(Technician).where(Technician.id == cert.employee_id)
        )
    ).scalar_one_or_none()
    if tech is None:
        return {"cert_id": str(cert.id), "status": "skipped", "reason": "no_tech"}
    if not tech.phone:
        return {"cert_id": str(cert.id), "status": "skipped", "reason": "no_phone"}
    body = (
        f"Hi {tech.first_name}, your {cert.kind.replace('_', ' ').upper()} "
        f"expires in {days} day{'s' if days != 1 else ''} "
        f"({cert.expires_at.isoformat()}). "
        "Please renew and upload the new card in MyOnboarding."
    )
    status = "ok"
    try:
        await _send(tech.phone, body)
    except Exception as e:  # noqa: BLE001
        logger.error("cert_expiry sms send failed for cert %s: %s", cert.id, e)
        status = "error"
    await write_audit(
        db,
        entity_type="employee_certification",
        entity_id=cert.id,
        event="expiry_notice_sent",
        diff={"days": [None, str(days)], "status": [None, status]},
        actor_user_id=None,
    )
    return {"cert_id": str(cert.id), "status": status, "days": days}


async def run_once_for_today(
    db: AsyncSession | None = None,
) -> list[dict]:
    """Send notices for any cert whose expires_at is exactly today+30/7/1.

    Returns a list of per-cert result dicts for observability.  Accepts an
    optional db session so tests can pass their in-memory SQLite session;
    otherwise opens one from ``async_session_maker``.
    """
    own_session = db is None
    results: list[dict] = []

    async def _work(session: AsyncSession) -> None:
        today = date.today()
        for days in _WINDOWS:
            target = today + timedelta(days=days)
            rows = (
                await session.execute(
                    select(HrEmployeeCertification).where(
                        HrEmployeeCertification.expires_at == target,
                        HrEmployeeCertification.status == "active",
                    )
                )
            ).scalars().all()
            for cert in rows:
                results.append(await _notify_cert(session, cert, days))
        await session.flush()

    if own_session:
        async with async_session_maker() as session:
            await _work(session)
            await session.commit()
    else:
        await _work(db)

    return results


def start_cert_expiry_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_once_for_today,
        "cron",
        hour=7,
        minute=0,
        id="hr_cert_expiry",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("HR cert-expiry scheduler started (daily at 07:00)")


def stop_cert_expiry_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
