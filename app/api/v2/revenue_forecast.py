"""Revenue forecasting — 30/60/90 day projections."""

from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_, extract
from datetime import date, timedelta
from typing import Optional
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.invoice import Invoice
from app.models.work_order import WorkOrder
from app.models.contract import Contract

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/forecast")
async def revenue_forecast(
    db: DbSession,
    current_user: CurrentUser,
    days: int = Query(90, ge=30, le=365),
):
    """30/60/90 day revenue forecast based on historical data and scheduled work."""
    today = date.today()

    try:
        # Historical: average monthly revenue over last 6 months
        six_months_ago = today - timedelta(days=180)
        hist = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                and_(Invoice.status == "paid", Invoice.paid_date >= six_months_ago)
            )
        )
        total_6mo = float(hist.scalar() or 0)
        avg_monthly = total_6mo / 6 if total_6mo > 0 else 0
        avg_daily = avg_monthly / 30

        # Scheduled work orders (confirmed revenue pipeline)
        sched = await db.execute(
            select(func.coalesce(func.sum(WorkOrder.total_cost), 0)).where(
                and_(
                    WorkOrder.status.in_(["scheduled", "pending", "confirmed"]),
                    func.date(WorkOrder.scheduled_date) >= today,
                    func.date(WorkOrder.scheduled_date) <= today + timedelta(days=days),
                )
            )
        )
        scheduled_revenue = float(sched.scalar() or 0)

        # Active contracts recurring revenue
        contract_monthly = 0
        try:
            cr = await db.execute(
                select(func.coalesce(func.sum(Contract.monthly_amount), 0)).where(
                    Contract.status == "active"
                )
            )
            contract_monthly = float(cr.scalar() or 0)
        except Exception:
            pass

        # Outstanding invoices likely to be paid
        outstanding = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.status.in_(["sent", "draft"])
            )
        )
        outstanding_amt = float(outstanding.scalar() or 0)

        # Build 30/60/90 breakdowns
        forecasts = []
        for period in [30, 60, 90]:
            if period > days:
                break
            projected_historical = avg_daily * period
            projected_contracts = contract_monthly * (period / 30)
            # Scheduled WOs within this period
            sw = await db.execute(
                select(func.coalesce(func.sum(WorkOrder.total_cost), 0)).where(
                    and_(
                        WorkOrder.status.in_(["scheduled", "pending", "confirmed"]),
                        func.date(WorkOrder.scheduled_date) >= today,
                        func.date(WorkOrder.scheduled_date) <= today + timedelta(days=period),
                    )
                )
            )
            period_scheduled = float(sw.scalar() or 0)

            forecasts.append({
                "period_days": period,
                "projected_total": round(projected_historical + projected_contracts + period_scheduled, 2),
                "from_scheduled_work": round(period_scheduled, 2),
                "from_contracts": round(projected_contracts, 2),
                "from_historical_trend": round(projected_historical, 2),
            })

        return {
            "generated_at": today.isoformat(),
            "avg_monthly_revenue": round(avg_monthly, 2),
            "scheduled_pipeline": round(scheduled_revenue, 2),
            "contract_mrr": round(contract_monthly, 2),
            "outstanding_invoices": round(outstanding_amt, 2),
            "forecasts": forecasts,
        }
    except Exception as e:
        logger.error(f"Error generating revenue forecast: {e}")
        return {
            "generated_at": today.isoformat(),
            "avg_monthly_revenue": 0,
            "scheduled_pipeline": 0,
            "contract_mrr": 0,
            "outstanding_invoices": 0,
            "forecasts": [],
        }
