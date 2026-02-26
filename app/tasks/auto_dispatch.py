"""Overnight auto-dispatch and unassigned job alerts."""

from datetime import datetime, date, timedelta
import logging

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models.work_order import WorkOrder
from app.models.technician import Technician

logger = logging.getLogger(__name__)


async def get_available_technicians(db: AsyncSession, target_date: date) -> list:
    """Get technicians sorted by fewest assignments on target_date."""
    result = await db.execute(
        select(
            Technician,
            func.count(WorkOrder.id).label("job_count"),
        )
        .outerjoin(
            WorkOrder,
            and_(
                WorkOrder.assigned_technician_id == Technician.id,
                func.date(WorkOrder.scheduled_date) == target_date,
            ),
        )
        .where(Technician.is_active == True)
        .group_by(Technician.id)
        .order_by(func.count(WorkOrder.id).asc())
    )
    return result.all()


async def auto_dispatch_unassigned():
    """Assign unassigned jobs for tomorrow using round-robin by workload."""
    async with async_session_maker() as db:
        tomorrow = date.today() + timedelta(days=1)

        # Find unassigned WOs scheduled for tomorrow
        unassigned = await db.execute(
            select(WorkOrder).where(
                and_(
                    WorkOrder.assigned_technician_id.is_(None),
                    func.date(WorkOrder.scheduled_date) == tomorrow,
                    WorkOrder.status.in_(["pending", "scheduled"]),
                )
            )
        )
        jobs = unassigned.scalars().all()

        if not jobs:
            logger.info("No unassigned jobs for tomorrow")
            return {"assigned": 0, "unassigned": 0}

        techs = await get_available_technicians(db, tomorrow)
        if not techs:
            logger.warning(f"{len(jobs)} unassigned jobs but no available technicians")
            await _send_unassigned_alert(len(jobs), tomorrow)
            return {"assigned": 0, "unassigned": len(jobs)}

        assigned_count = 0
        for i, job in enumerate(jobs):
            tech, _ = techs[i % len(techs)]
            job.assigned_technician_id = tech.id
            job.assigned_technician = f"{tech.first_name} {tech.last_name}"
            job.status = "scheduled"
            assigned_count += 1
            logger.info(f"Auto-dispatched WO {job.id} to {tech.first_name} {tech.last_name}")

        await db.commit()
        logger.info(f"Auto-dispatch complete: {assigned_count} assigned for {tomorrow}")
        return {"assigned": assigned_count, "unassigned": 0}


async def _send_unassigned_alert(count: int, target_date: date):
    """Send SMS alert about unassigned jobs."""
    try:
        from app.services.twilio_service import send_sms
        from app.core.config import settings
        admin_phone = getattr(settings, "ADMIN_PHONE", None)
        if admin_phone:
            await send_sms(
                admin_phone,
                f"⚠️ {count} unassigned job(s) for {target_date.strftime('%m/%d/%Y')}. "
                f"Please assign technicians ASAP.",
            )
    except Exception as e:
        logger.error(f"Failed to send unassigned job alert: {e}")


async def check_unassigned_alerts():
    """Check for unassigned jobs in the next 48 hours and alert."""
    async with async_session_maker() as db:
        cutoff = date.today() + timedelta(days=2)
        result = await db.execute(
            select(func.count()).select_from(WorkOrder).where(
                and_(
                    WorkOrder.assigned_technician_id.is_(None),
                    func.date(WorkOrder.scheduled_date) <= cutoff,
                    func.date(WorkOrder.scheduled_date) >= date.today(),
                    WorkOrder.status.in_(["pending", "scheduled"]),
                )
            )
        )
        count = result.scalar() or 0
        if count > 0:
            await _send_unassigned_alert(count, date.today())
            logger.warning(f"{count} unassigned jobs in next 48 hours")
        return {"unassigned_count": count}
