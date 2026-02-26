"""
Smart Dispatch API — recommends technicians for work orders
based on proximity, skills, availability, and workload.

Also provides the Command Center endpoints for quick phone-to-dispatch workflow:
- GET /customer-lookup?phone=... — find customer by phone
- POST /quick-create — atomic create work order + SMS tech
- POST /notify — send SMS to assigned tech for existing work order
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date
import logging
import uuid as _uuid

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser
from app.services.dispatch_service import recommend_technicians
from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.models.technician import Technician

logger = logging.getLogger(__name__)
router = APIRouter()


class TechRecommendation(BaseModel):
    technician_id: str
    name: str
    phone: Optional[str] = None
    distance_miles: Optional[float] = None
    estimated_travel_minutes: Optional[float] = None
    location_source: Optional[str] = None
    skills_match: list[str] = []
    skills_missing: list[str] = []
    availability: str = "available"
    job_load: dict = {}
    score: float = 0


class DispatchRecommendation(BaseModel):
    work_order_id: str
    job_type: Optional[str] = None
    job_location: Optional[dict] = None
    priority: Optional[str] = None
    recommended_technicians: list[TechRecommendation] = []
    total_active_technicians: int = 0
    message: Optional[str] = None
    error: Optional[str] = None


class AssignRequest(BaseModel):
    technician_id: str


@router.get("/recommend/{work_order_id}", response_model=DispatchRecommendation)
async def get_dispatch_recommendation(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
    max_results: int = 5,
):
    """Get smart technician recommendations for a work order."""
    result = await recommend_technicians(db, work_order_id, max_results)

    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.post("/assign/{work_order_id}")
async def dispatch_assign(
    work_order_id: str,
    req: AssignRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Assign a technician to a work order via smart dispatch."""
    from sqlalchemy import text

    # Verify work order exists
    wo_result = await db.execute(
        text("SELECT id, status FROM work_orders WHERE id = :id"),
        {"id": work_order_id},
    )
    wo = wo_result.fetchone()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    # Verify technician exists
    tech_result = await db.execute(
        text("SELECT id, first_name, last_name FROM technicians WHERE id = :id"),
        {"id": req.technician_id},
    )
    tech = tech_result.fetchone()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    tech_name = f"{tech[1] or ''} {tech[2] or ''}".strip()

    # Assign technician
    await db.execute(
        text("""
            UPDATE work_orders
            SET technician_id = :tech_id,
                assigned_technician = :tech_name,
                updated_at = NOW()
            WHERE id = :wo_id
        """),
        {
            "tech_id": req.technician_id,
            "tech_name": tech_name,
            "wo_id": work_order_id,
        },
    )
    await db.commit()

    return {
        "success": True,
        "work_order_id": work_order_id,
        "technician_id": req.technician_id,
        "technician_name": tech_name,
        "message": f"Assigned {tech_name} to work order",
    }


# =====================================================
# Command Center — Quick Dispatch Endpoints
# =====================================================


class NewCustomerData(BaseModel):
    first_name: str
    last_name: str
    phone: str
    address_line1: str
    city: str = ""
    state: str = "TX"
    postal_code: str = ""


class QuickCreateRequest(BaseModel):
    customer_id: Optional[str] = None
    new_customer: Optional[NewCustomerData] = None
    job_type: str = "pumping"
    scheduled_date: date
    technician_id: str
    notes: Optional[str] = None
    notify_tech: bool = True


class NotifyRequest(BaseModel):
    work_order_id: str


@router.get("/customer-lookup")
async def customer_lookup(
    phone: str = Query(..., min_length=3),
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """Look up customer by phone number for Command Center screen pop."""
    # Normalize: strip non-digits, remove leading 1
    normalized = "".join(c for c in phone if c.isdigit())
    if len(normalized) == 11 and normalized.startswith("1"):
        normalized = normalized[1:]

    if len(normalized) < 7:
        return {"found": False, "customer": None, "last_work_order": None}

    # Find customer
    result = await db.execute(
        select(Customer).where(Customer.phone.contains(normalized[-10:])).limit(1)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        return {"found": False, "customer": None, "last_work_order": None}

    # Get last work order for this customer
    wo_result = await db.execute(
        select(WorkOrder)
        .where(WorkOrder.customer_id == customer.id)
        .order_by(WorkOrder.scheduled_date.desc())
        .limit(1)
    )
    last_wo = wo_result.scalar_one_or_none()

    return {
        "found": True,
        "customer": {
            "id": str(customer.id),
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "phone": customer.phone,
            "email": customer.email,
            "address_line1": customer.address_line1,
            "city": customer.city,
            "state": customer.state,
            "postal_code": customer.postal_code,
            "system_type": customer.system_type,
            "manufacturer": customer.manufacturer,
        },
        "last_work_order": {
            "id": str(last_wo.id),
            "job_type": last_wo.job_type,
            "status": last_wo.status,
            "scheduled_date": str(last_wo.scheduled_date) if last_wo.scheduled_date else None,
        } if last_wo else None,
    }


@router.post("/quick-create")
async def quick_create(
    req: QuickCreateRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Atomic create work order (+ optional new customer) and SMS the tech."""
    customer_id = req.customer_id

    # Create customer if new_customer provided
    if req.new_customer and not customer_id:
        nc = req.new_customer
        new_id = _uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO customers (id, first_name, last_name, phone, address_line1, city, state, postal_code, is_active, created_at, updated_at)
                VALUES (:id, :fn, :ln, :phone, :addr, :city, :state, :zip, true, NOW(), NOW())
            """),
            {
                "id": str(new_id), "fn": nc.first_name, "ln": nc.last_name,
                "phone": nc.phone, "addr": nc.address_line1,
                "city": nc.city, "state": nc.state, "zip": nc.postal_code,
            },
        )
        customer_id = str(new_id)

    if not customer_id:
        raise HTTPException(status_code=400, detail="Must provide customer_id or new_customer")

    # Look up technician
    tech_result = await db.execute(
        select(Technician).where(Technician.id == req.technician_id)
    )
    tech = tech_result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    tech_name = f"{tech.first_name or ''} {tech.last_name or ''}".strip()

    # Look up customer name + address for SMS
    cust_result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    cust_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
    cust_addr = customer.address_line1 or "No address"

    # Create work order
    wo_id = _uuid.uuid4()
    wo_number = f"WO-{_uuid.uuid4().hex[:6].upper()}"
    await db.execute(
        text("""
            INSERT INTO work_orders (
                id, work_order_number, customer_id, technician_id,
                assigned_technician, job_type, status, priority,
                scheduled_date, notes,
                service_address_line1, service_city, service_state, service_postal_code,
                system_type, created_at, updated_at
            ) VALUES (
                :id, :wo_num, :cust_id, :tech_id,
                :tech_name, :job_type, 'scheduled', 'normal',
                :sched_date, :notes,
                :addr, :city, :state, :zip,
                :sys_type, NOW(), NOW()
            )
        """),
        {
            "id": str(wo_id), "wo_num": wo_number,
            "cust_id": customer_id, "tech_id": req.technician_id,
            "tech_name": tech_name, "job_type": req.job_type,
            "sched_date": req.scheduled_date.isoformat(), "notes": req.notes or "",
            "addr": customer.address_line1 or "", "city": customer.city or "",
            "state": customer.state or "", "zip": customer.postal_code or "",
            "sys_type": customer.system_type or "conventional",
        },
    )
    await db.commit()

    # Send SMS to technician if requested
    sms_sent = False
    if req.notify_tech and tech.phone:
        try:
            from app.services.twilio_service import twilio_service
            sms_body = (
                f"New job! {cust_name} at {cust_addr}. "
                f"{req.job_type.title()} on {req.scheduled_date.strftime('%m/%d/%Y')}."
            )
            if req.notes:
                sms_body += f" Notes: {req.notes}"
            sms_body += " — Mac Septic CRM"
            await twilio_service.send_sms(tech.phone, sms_body)
            sms_sent = True
        except Exception as e:
            logger.warning(f"Failed to send dispatch SMS to {tech_name}: {e}")

    return {
        "success": True,
        "work_order_id": str(wo_id),
        "work_order_number": wo_number,
        "customer_id": customer_id,
        "customer_name": cust_name,
        "technician_name": tech_name,
        "sms_sent": sms_sent,
    }


@router.post("/notify")
async def notify_tech(
    req: NotifyRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Send SMS to the assigned technician for an existing work order."""
    # Fetch work order with customer
    wo_result = await db.execute(
        select(WorkOrder).where(WorkOrder.id == req.work_order_id)
    )
    wo = wo_result.scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    if not wo.technician_id:
        raise HTTPException(status_code=400, detail="No technician assigned to this work order")

    # Get technician
    tech_result = await db.execute(
        select(Technician).where(Technician.id == wo.technician_id)
    )
    tech = tech_result.scalar_one_or_none()
    if not tech or not tech.phone:
        raise HTTPException(status_code=400, detail="Technician has no phone number")

    # Get customer
    cust_result = await db.execute(
        select(Customer).where(Customer.id == wo.customer_id)
    )
    customer = cust_result.scalar_one_or_none()

    tech_name = f"{tech.first_name or ''} {tech.last_name or ''}".strip()
    cust_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() if customer else "Unknown"
    cust_addr = (customer.address_line1 if customer else wo.service_address_line1) or "No address"

    try:
        from app.services.twilio_service import twilio_service
        sms_body = (
            f"Job reminder: {cust_name} at {cust_addr}. "
            f"{(wo.job_type or 'Service').title()}"
        )
        if wo.scheduled_date:
            sms_body += f" on {wo.scheduled_date.strftime('%m/%d/%Y')}"
        if wo.notes:
            sms_body += f". Notes: {wo.notes}"
        sms_body += " — Mac Septic CRM"
        await twilio_service.send_sms(tech.phone, sms_body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SMS failed: {str(e)}")

    return {
        "success": True,
        "technician_name": tech_name,
        "message": f"SMS sent to {tech_name}",
    }
