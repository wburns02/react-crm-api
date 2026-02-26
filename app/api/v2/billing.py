"""Real billing endpoints — replaces stubs."""

from fastapi import APIRouter
from sqlalchemy import select, func, and_
from datetime import date
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.invoice import Invoice

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stats")
async def billing_stats(db: DbSession, current_user: CurrentUser):
    """Real billing statistics from invoice data."""
    today = date.today()
    month_start = today.replace(day=1)

    try:
        # MTD revenue: paid invoices this month
        rev = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                and_(Invoice.status == "paid", Invoice.paid_date >= month_start)
            )
        )
        total_revenue = float(rev.scalar() or 0)

        # Outstanding: draft + sent invoices
        out = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.status.in_(["draft", "sent"])
            )
        )
        outstanding = float(out.scalar() or 0)

        # Overdue invoices
        ov = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.status == "overdue"
            )
        )
        overdue = float(ov.scalar() or 0)

        # Pending estimates count
        pending_estimates = 0
        try:
            from app.models.estimate import Estimate
            pe = await db.execute(select(func.count()).select_from(Estimate).where(Estimate.status == "pending"))
            pending_estimates = pe.scalar() or 0
        except Exception:
            pass

        # Active payment plans count
        active_payment_plans = 0
        try:
            from app.models.payment_plan import PaymentPlan
            pp = await db.execute(select(func.count()).select_from(PaymentPlan).where(PaymentPlan.status == "active"))
            active_payment_plans = pp.scalar() or 0
        except Exception:
            pass

        return {
            "total_revenue": total_revenue,
            "outstanding": outstanding,
            "overdue": overdue,
            "outstanding_invoices": outstanding,
            "pending_estimates": pending_estimates,
            "active_payment_plans": active_payment_plans,
        }
    except Exception as e:
        logger.error(f"Error fetching billing stats: {e}")
        return {
            "total_revenue": 0, "outstanding": 0, "overdue": 0,
            "outstanding_invoices": 0, "pending_estimates": 0,
            "active_payment_plans": 0,
        }
