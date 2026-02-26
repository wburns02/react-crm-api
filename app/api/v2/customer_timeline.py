"""Unified customer timeline — aggregates all activity for a customer."""

from fastapi import APIRouter, Query
from sqlalchemy import select, union_all, literal, func, text, and_
from datetime import datetime
from typing import Optional
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.customer import Customer
from app.models.call_log import CallLog

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{customer_id}/timeline")
async def get_customer_timeline(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = Query(None, description="Filter: work_order, invoice, payment, call"),
):
    """Unified timeline of all events for a customer."""
    offset = (page - 1) * page_size
    events = []

    try:
        # Work Orders
        if not event_type or event_type == "work_order":
            wo_result = await db.execute(
                select(WorkOrder).where(WorkOrder.customer_id == customer_id)
                .order_by(WorkOrder.created_at.desc())
            )
            for wo in wo_result.scalars().all():
                events.append({
                    "id": str(wo.id),
                    "type": "work_order",
                    "title": f"Work Order #{wo.wo_number or wo.id}",
                    "description": wo.description or wo.service_type or "",
                    "status": wo.status,
                    "date": (wo.scheduled_date or wo.created_at).isoformat() if (wo.scheduled_date or wo.created_at) else None,
                    "created_at": wo.created_at.isoformat() if wo.created_at else None,
                    "amount": float(wo.total_cost) if wo.total_cost else None,
                })

        # Invoices
        if not event_type or event_type == "invoice":
            inv_result = await db.execute(
                select(Invoice).where(Invoice.customer_id == customer_id)
                .order_by(Invoice.created_at.desc())
            )
            for inv in inv_result.scalars().all():
                events.append({
                    "id": str(inv.id),
                    "type": "invoice",
                    "title": f"Invoice #{inv.invoice_number or inv.id}",
                    "description": f"Amount: ${float(inv.amount or 0):.2f}",
                    "status": inv.status,
                    "date": (inv.due_date or inv.created_at).isoformat() if (inv.due_date or inv.created_at) else None,
                    "created_at": inv.created_at.isoformat() if inv.created_at else None,
                    "amount": float(inv.amount) if inv.amount else None,
                })

        # Payments
        if not event_type or event_type == "payment":
            pay_result = await db.execute(
                select(Payment).where(Payment.customer_id == customer_id)
                .order_by(Payment.created_at.desc())
            )
            for pay in pay_result.scalars().all():
                events.append({
                    "id": str(pay.id),
                    "type": "payment",
                    "title": f"Payment ${float(pay.amount or 0):.2f}",
                    "description": pay.payment_method or "",
                    "status": pay.status or "completed",
                    "date": (pay.payment_date or pay.created_at).isoformat() if (pay.payment_date or pay.created_at) else None,
                    "created_at": pay.created_at.isoformat() if pay.created_at else None,
                    "amount": float(pay.amount) if pay.amount else None,
                })

        # Call Logs
        if not event_type or event_type == "call":
            try:
                call_result = await db.execute(
                    select(CallLog).where(CallLog.customer_id == customer_id)
                    .order_by(CallLog.created_at.desc())
                )
                for call in call_result.scalars().all():
                    events.append({
                        "id": str(call.id),
                        "type": "call",
                        "title": f"Call — {call.direction or 'unknown'}",
                        "description": call.notes or "",
                        "status": call.outcome or "completed",
                        "date": call.created_at.isoformat() if call.created_at else None,
                        "created_at": call.created_at.isoformat() if call.created_at else None,
                        "amount": None,
                    })
            except Exception:
                pass  # call_log table may not exist

        # Sort all events by date descending
        events.sort(key=lambda e: e.get("date") or "", reverse=True)

        total = len(events)
        paginated = events[offset : offset + page_size]

        return {
            "items": paginated,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error building customer timeline: {e}")
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
