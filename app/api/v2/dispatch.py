"""
Smart Dispatch API — recommends technicians for work orders
based on proximity, skills, availability, and workload.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.api.deps import DbSession, CurrentUser
from app.services.dispatch_service import recommend_technicians

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
