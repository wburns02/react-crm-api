from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, or_, text as sql_text
from typing import Optional, Literal
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.technician import Technician
from app.schemas.technician import (
    TechnicianCreate,
    TechnicianUpdate,
    TechnicianResponse,
    TechnicianListResponse,
    TechnicianPerformanceStats,
    TechnicianJobDetail,
    TechnicianJobsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/test-minimal")
async def test_minimal(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
):
    """Minimal test endpoint to diagnose Query parameter issues."""
    return {"message": "test ok", "page": page}


@router.get("/debug")
async def debug_technicians(
    db: DbSession,
    current_user: CurrentUser,
):
    """Debug endpoint to see raw technician data."""
    from sqlalchemy import text as sql_text

    sql = """
        SELECT id, first_name, last_name, email, phone, employee_id, is_active,
               skills, assigned_vehicle, vehicle_capacity_gallons,
               license_number, license_expiry, hourly_rate, notes,
               home_region, home_address, home_city, home_state, home_postal_code,
               home_latitude, home_longitude, created_at, updated_at
        FROM technicians
        LIMIT 3
    """
    result = await db.execute(sql_text(sql))
    rows = result.fetchall()

    debug_info = []
    for row in rows:
        debug_info.append({
            "id": {"value": row[0], "type": str(type(row[0]))},
            "first_name": {"value": row[1], "type": str(type(row[1]))},
            "last_name": {"value": row[2], "type": str(type(row[2]))},
            "email": {"value": row[3], "type": str(type(row[3]))},
            "phone": {"value": row[4], "type": str(type(row[4]))},
            "is_active": {"value": row[6], "type": str(type(row[6]))},
            "skills": {"value": str(row[7]), "type": str(type(row[7]))},
            "created_at": {"value": str(row[21]) if row[21] else None, "type": str(type(row[21]))},
            "updated_at": {"value": str(row[22]) if row[22] else None, "type": str(type(row[22]))},
        })

    return {"debug_info": debug_info}


@router.get("/list-raw")
async def list_technicians_raw(
    db: DbSession,
    current_user: CurrentUser,
):
    """List technicians without response model validation for debugging."""
    from sqlalchemy import text as sql_text

    sql = """
        SELECT id, first_name, last_name, email, phone, employee_id, is_active,
               skills, assigned_vehicle, vehicle_capacity_gallons,
               license_number, license_expiry, hourly_rate, notes,
               home_region, home_address, home_city, home_state, home_postal_code,
               home_latitude, home_longitude, created_at, updated_at
        FROM technicians
        ORDER BY first_name, last_name
        LIMIT 20
    """
    result = await db.execute(sql_text(sql))
    rows = result.fetchall()

    items = []
    for row in rows:
        first_name = row[1] or ""
        last_name = row[2] or ""

        # Handle skills - may be list, tuple, or comma-separated string
        # Note: Database has corrupted data where skills were stored as char arrays
        # e.g., ['p','u','m','p','i','n','g',',','m',...] instead of ['pumping','maintenance',...]
        skills_val = row[7]
        if skills_val is None:
            skills = []
        elif isinstance(skills_val, (list, tuple)):
            # Check if this is a corrupted char array (all items are single chars)
            if skills_val and all(isinstance(s, str) and len(s) <= 1 for s in skills_val):
                # Join chars back together and split by comma
                joined = "".join(skills_val)
                skills = [s.strip() for s in joined.split(",") if s.strip()]
            else:
                skills = list(skills_val)
        elif isinstance(skills_val, str):
            # Parse comma-separated string
            skills = [s.strip() for s in skills_val.split(",") if s.strip()]
        else:
            skills = []

        # Handle datetime fields
        created_at = None
        if row[21]:
            try:
                created_at = row[21].isoformat() if hasattr(row[21], 'isoformat') else str(row[21])
            except Exception:
                created_at = None

        updated_at = None
        if row[22]:
            try:
                updated_at = row[22].isoformat() if hasattr(row[22], 'isoformat') else str(row[22])
            except Exception:
                updated_at = None

        items.append({
            "id": str(row[0]),
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name} {last_name}".strip(),
            "email": row[3],
            "phone": row[4],
            "employee_id": row[5],
            "is_active": bool(row[6]) if row[6] is not None else True,
            "skills": skills,
            "assigned_vehicle": row[8],
            "vehicle_capacity_gallons": float(row[9]) if row[9] else None,
            "license_number": row[10],
            "license_expiry": str(row[11]) if row[11] else None,
            "hourly_rate": float(row[12]) if row[12] else None,
            "notes": row[13],
            "home_region": row[14],
            "home_address": row[15],
            "home_city": row[16],
            "home_state": row[17],
            "home_postal_code": row[18],
            "home_latitude": float(row[19]) if row[19] else None,
            "home_longitude": float(row[20]) if row[20] else None,
            "created_at": created_at,
            "updated_at": updated_at,
        })

    return {"items": items, "total": len(items), "page": 1, "page_size": 20}


def technician_to_response(tech: Technician) -> dict:
    """Convert Technician model to response dict with string ID."""
    return {
        "id": str(tech.id),
        "first_name": tech.first_name,
        "last_name": tech.last_name,
        "full_name": f"{tech.first_name} {tech.last_name}",
        "email": tech.email,
        "phone": tech.phone,
        "employee_id": tech.employee_id,
        "is_active": tech.is_active,
        "home_region": tech.home_region,
        "home_address": tech.home_address,
        "home_city": tech.home_city,
        "home_state": tech.home_state,
        "home_postal_code": tech.home_postal_code,
        "home_latitude": tech.home_latitude,
        "home_longitude": tech.home_longitude,
        "skills": tech.skills or [],
        "assigned_vehicle": tech.assigned_vehicle,
        "vehicle_capacity_gallons": tech.vehicle_capacity_gallons,
        "license_number": tech.license_number,
        "license_expiry": str(tech.license_expiry) if tech.license_expiry else None,
        "hourly_rate": tech.hourly_rate,
        "notes": tech.notes,
        "created_at": tech.created_at.isoformat() if tech.created_at else None,
        "updated_at": tech.updated_at.isoformat() if tech.updated_at else None,
    }


@router.get("")
async def list_technicians(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    active_only: Optional[bool] = None,
):
    """List technicians with pagination and filtering."""
    try:
        from sqlalchemy import text as sql_text

        # Build WHERE clause based on filters
        where_clauses = []
        params = {"limit": page_size, "offset": (page - 1) * page_size}

        if active_only:
            where_clauses.append("is_active = true")

        if search:
            where_clauses.append("(first_name ILIKE :search OR last_name ILIKE :search OR email ILIKE :search OR employee_id ILIKE :search)")
            params["search"] = f"%{search}%"

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Use raw SQL to avoid ORM issues
        sql = f"""
            SELECT id, first_name, last_name, email, phone, employee_id, is_active,
                   skills, assigned_vehicle, vehicle_capacity_gallons,
                   license_number, license_expiry, hourly_rate, notes,
                   home_region, home_address, home_city, home_state, home_postal_code,
                   home_latitude, home_longitude, created_at, updated_at
            FROM technicians
            {where_sql}
            ORDER BY first_name, last_name
            LIMIT :limit OFFSET :offset
        """
        result = await db.execute(sql_text(sql), params)
        rows = result.fetchall()

        # Count total with same filter
        count_sql = f"SELECT COUNT(*) FROM technicians {where_sql}"
        count_result = await db.execute(sql_text(count_sql), params)
        total = count_result.scalar()

        # Convert rows to response dicts
        items = []
        for row in rows:
            first_name = row[1] or ""
            last_name = row[2] or ""

            # Handle skills - may be list, tuple, or comma-separated string
            # Note: Database has corrupted data where skills were stored as char arrays
            skills_val = row[7]
            if skills_val is None:
                skills = []
            elif isinstance(skills_val, (list, tuple)):
                # Check if this is a corrupted char array (all items are single chars)
                if skills_val and all(isinstance(s, str) and len(s) <= 1 for s in skills_val):
                    joined = "".join(skills_val)
                    skills = [s.strip() for s in joined.split(",") if s.strip()]
                else:
                    skills = list(skills_val)
            elif isinstance(skills_val, str):
                skills = [s.strip() for s in skills_val.split(",") if s.strip()]
            else:
                skills = []

            # Handle datetime fields - convert to ISO string for serialization
            created_at = None
            if row[21]:
                try:
                    created_at = row[21].isoformat() if hasattr(row[21], 'isoformat') else str(row[21])
                except Exception:
                    created_at = None

            updated_at = None
            if row[22]:
                try:
                    updated_at = row[22].isoformat() if hasattr(row[22], 'isoformat') else str(row[22])
                except Exception:
                    updated_at = None

            items.append({
                "id": str(row[0]),
                "first_name": first_name,
                "last_name": last_name,
                "full_name": f"{first_name} {last_name}".strip(),
                "email": row[3],
                "phone": row[4],
                "employee_id": row[5],
                "is_active": bool(row[6]) if row[6] is not None else True,
                "skills": skills,
                "assigned_vehicle": row[8],
                "vehicle_capacity_gallons": float(row[9]) if row[9] else None,
                "license_number": row[10],
                "license_expiry": str(row[11]) if row[11] else None,
                "hourly_rate": float(row[12]) if row[12] else None,
                "notes": row[13],
                "home_region": row[14],
                "home_address": row[15],
                "home_city": row[16],
                "home_state": row[17],
                "home_postal_code": row[18],
                "home_latitude": float(row[19]) if row[19] else None,
                "home_longitude": float(row[20]) if row[20] else None,
                "created_at": created_at,
                "updated_at": updated_at,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        import traceback
        logger.error(f"Error in list_technicians: {traceback.format_exc()}")
        return {"error": str(e), "type": type(e).__name__, "traceback": traceback.format_exc()}


@router.get("/{technician_id}", response_model=TechnicianResponse)
async def get_technician(
    technician_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single technician by ID."""
    result = await db.execute(select(Technician).where(Technician.id == technician_id))
    technician = result.scalar_one_or_none()

    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    return technician_to_response(technician)


@router.post("", response_model=TechnicianResponse, status_code=status.HTTP_201_CREATED)
async def create_technician(
    technician_data: TechnicianCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new technician."""
    import uuid
    from datetime import datetime
    import traceback

    try:
        # Generate UUID for the technician ID
        tech_data = technician_data.model_dump()
        tech_data["id"] = str(uuid.uuid4())
        tech_data["created_at"] = datetime.utcnow()
        tech_data["updated_at"] = datetime.utcnow()

        # Remove None employee_id to avoid unique constraint issues with empty strings
        if tech_data.get("employee_id") is None or tech_data.get("employee_id") == "":
            tech_data.pop("employee_id", None)

        # Convert vehicle_capacity_gallons to int if present (model expects Integer)
        if tech_data.get("vehicle_capacity_gallons") is not None:
            tech_data["vehicle_capacity_gallons"] = int(tech_data["vehicle_capacity_gallons"])

        technician = Technician(**tech_data)
        db.add(technician)
        await db.commit()
        await db.refresh(technician)
        return technician_to_response(technician)
    except Exception as e:
        logger.error(f"Error creating technician: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create technician: {str(e)}"
        )


@router.patch("/{technician_id}", response_model=TechnicianResponse)
async def update_technician(
    technician_id: str,
    technician_data: TechnicianUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a technician."""
    result = await db.execute(select(Technician).where(Technician.id == technician_id))
    technician = result.scalar_one_or_none()

    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    # Update only provided fields
    update_data = technician_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(technician, field, value)

    await db.commit()
    await db.refresh(technician)
    return technician_to_response(technician)


@router.delete("/{technician_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_technician(
    technician_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a technician (soft delete - sets is_active=false)."""
    result = await db.execute(select(Technician).where(Technician.id == technician_id))
    technician = result.scalar_one_or_none()

    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    # Soft delete - set is_active to False
    technician.is_active = False
    await db.commit()


# =====================================================
# Performance Stats Endpoints
# =====================================================

@router.get("/{technician_id}/performance", response_model=TechnicianPerformanceStats)
async def get_technician_performance(
    technician_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get aggregated performance statistics for a technician.

    Returns:
    - Total jobs completed
    - Total revenue generated
    - Returns/revisits count (jobs at same customer within 30 days)
    - Breakdown by job type (pump outs, repairs, other)
    """
    import traceback

    try:
        # First verify technician exists
        tech_result = await db.execute(
            select(Technician).where(Technician.id == technician_id)
        )
        if not tech_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Technician not found",
            )

        # Get performance stats using raw SQL for efficiency
        stats_sql = """
            WITH completed_jobs AS (
                SELECT
                    id, customer_id, job_type,
                    COALESCE(total_amount, 0) as total_amount,
                    scheduled_date
                FROM work_orders
                WHERE technician_id = :tech_id
                  AND status = 'completed'
            ),
            returns_calc AS (
                SELECT COUNT(DISTINCT c1.id) as return_count
                FROM completed_jobs c1
                WHERE EXISTS (
                    SELECT 1 FROM completed_jobs c2
                    WHERE c1.customer_id = c2.customer_id
                      AND c1.id != c2.id
                      AND c1.scheduled_date > c2.scheduled_date
                      AND c1.scheduled_date - c2.scheduled_date <= 30
                )
            )
            SELECT
                COUNT(*) as total_jobs,
                COALESCE(SUM(total_amount), 0) as total_revenue,
                COUNT(*) FILTER (WHERE job_type IN ('pumping', 'grease_trap')) as pump_out_jobs,
                COALESCE(SUM(total_amount) FILTER (WHERE job_type IN ('pumping', 'grease_trap')), 0) as pump_out_revenue,
                COUNT(*) FILTER (WHERE job_type IN ('repair', 'maintenance')) as repair_jobs,
                COALESCE(SUM(total_amount) FILTER (WHERE job_type IN ('repair', 'maintenance')), 0) as repair_revenue,
                COUNT(*) FILTER (WHERE job_type NOT IN ('pumping', 'grease_trap', 'repair', 'maintenance')) as other_jobs,
                COALESCE(SUM(total_amount) FILTER (WHERE job_type NOT IN ('pumping', 'grease_trap', 'repair', 'maintenance')), 0) as other_revenue,
                COALESCE((SELECT return_count FROM returns_calc), 0) as returns_count
            FROM completed_jobs
        """

        result = await db.execute(sql_text(stats_sql), {"tech_id": technician_id})
        row = result.fetchone()

        if row:
            return TechnicianPerformanceStats(
                technician_id=technician_id,
                total_jobs_completed=int(row[0] or 0),
                total_revenue=float(row[1] or 0),
                pump_out_jobs=int(row[2] or 0),
                pump_out_revenue=float(row[3] or 0),
                repair_jobs=int(row[4] or 0),
                repair_revenue=float(row[5] or 0),
                other_jobs=int(row[6] or 0),
                other_revenue=float(row[7] or 0),
                returns_count=int(row[8] or 0),
            )
        else:
            # Return zeros if no data
            return TechnicianPerformanceStats(technician_id=technician_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting technician performance: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get performance stats: {str(e)}"
        )


@router.get("/{technician_id}/jobs", response_model=TechnicianJobsResponse)
async def get_technician_jobs(
    technician_id: str,
    db: DbSession,
    current_user: CurrentUser,
    job_category: Literal["pump_outs", "repairs", "all"] = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get detailed list of jobs for a technician.

    Args:
        job_category: Filter by job category
            - pump_outs: pumping and grease_trap jobs
            - repairs: repair and maintenance jobs
            - all: all completed jobs
        page: Page number
        page_size: Items per page
    """
    import traceback
    import re

    try:
        # First verify technician exists
        tech_result = await db.execute(
            select(Technician).where(Technician.id == technician_id)
        )
        if not tech_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Technician not found",
            )

        # Build job type filter
        if job_category == "pump_outs":
            job_type_filter = "AND wo.job_type IN ('pumping', 'grease_trap')"
        elif job_category == "repairs":
            job_type_filter = "AND wo.job_type IN ('repair', 'maintenance')"
        else:
            job_type_filter = ""

        offset = (page - 1) * page_size

        # Get jobs with customer info and cost breakdown
        jobs_sql = f"""
            SELECT
                wo.id,
                wo.scheduled_date::text,
                wo.actual_end_time::text as completed_date,
                wo.customer_id,
                COALESCE(c.first_name || ' ' || c.last_name, 'Customer #' || wo.customer_id::text) as customer_name,
                wo.service_location,
                wo.job_type,
                wo.status,
                COALESCE(wo.total_amount, 0) as total_amount,
                wo.total_labor_minutes as duration_minutes,
                wo.notes,
                -- Get labor hours from job_costs
                (SELECT COALESCE(SUM(quantity), 0) FROM job_costs
                 WHERE work_order_id = wo.id AND cost_type = 'labor' AND unit = 'hour') as labor_hours,
                -- Get parts cost from job_costs
                (SELECT COALESCE(SUM(total_cost), 0) FROM job_costs
                 WHERE work_order_id = wo.id AND cost_type = 'materials') as parts_cost
            FROM work_orders wo
            LEFT JOIN customers c ON wo.customer_id = c.id
            WHERE wo.technician_id = :tech_id
              AND wo.status = 'completed'
              {job_type_filter}
            ORDER BY wo.scheduled_date DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """

        result = await db.execute(
            sql_text(jobs_sql),
            {"tech_id": technician_id, "limit": page_size, "offset": offset}
        )
        rows = result.fetchall()

        # Get total count
        count_sql = f"""
            SELECT COUNT(*)
            FROM work_orders wo
            WHERE wo.technician_id = :tech_id
              AND wo.status = 'completed'
              {job_type_filter}
        """
        count_result = await db.execute(sql_text(count_sql), {"tech_id": technician_id})
        total = count_result.scalar() or 0

        # Build response items
        items = []
        for row in rows:
            # Try to extract gallons from notes (e.g., "Pumped 1200 gallons")
            gallons_pumped = None
            tank_size = None
            notes = row[10] or ""

            if row[6] in ('pumping', 'grease_trap'):
                # Look for gallon amounts in notes
                gallon_match = re.search(r'(\d+)\s*(?:gallons?|gal)', notes, re.IGNORECASE)
                if gallon_match:
                    gallons_pumped = int(gallon_match.group(1))
                # Look for tank size
                tank_match = re.search(r'(\d+)\s*(?:gallon)?\s*tank', notes, re.IGNORECASE)
                if tank_match:
                    tank_size = f"{tank_match.group(1)} gallon"

            items.append(TechnicianJobDetail(
                id=str(row[0]),
                scheduled_date=row[1],
                completed_date=row[2],
                customer_id=row[3],
                customer_name=row[4],
                service_location=row[5],
                job_type=row[6],
                status=row[7],
                total_amount=float(row[8] or 0),
                duration_minutes=int(row[9]) if row[9] else None,
                notes=notes if notes else None,
                gallons_pumped=gallons_pumped,
                tank_size=tank_size,
                labor_hours=float(row[11]) if row[11] else None,
                parts_cost=float(row[12]) if row[12] else None,
            ))

        return TechnicianJobsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            job_category=job_category,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting technician jobs: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get jobs: {str(e)}"
        )
