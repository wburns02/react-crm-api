"""Assets API - Company asset management (trucks, pumps, tools, PPE)."""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, case, or_
from typing import Optional
from datetime import date, datetime
import logging
import uuid

from app.api.deps import DbSession, CurrentUser
from app.models.asset import Asset, AssetMaintenanceLog, AssetAssignment
from app.schemas.asset import (
    AssetCreate,
    AssetUpdate,
    AssetResponse,
    AssetListResponse,
    MaintenanceLogCreate,
    MaintenanceLogResponse,
    AssetCheckout,
    AssetCheckin,
    AssignmentResponse,
    AssetDashboardResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def parse_date_field(value: Optional[str]) -> Optional[date]:
    """Parse YYYY-MM-DD string to date object."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def format_date(d) -> Optional[str]:
    """Format date to ISO string."""
    if d is None:
        return None
    if isinstance(d, (date, datetime)):
        return d.isoformat()
    return str(d)


def asset_to_response(asset: Asset) -> dict:
    """Convert Asset model to response dict."""
    # Calculate depreciated value
    depreciated = None
    if asset.purchase_price and asset.purchase_date:
        years_owned = (date.today() - asset.purchase_date).days / 365.25
        useful_life = asset.useful_life_years or 10
        salvage = asset.salvage_value or 0
        if useful_life > 0:
            annual_dep = (asset.purchase_price - salvage) / useful_life
            depreciated = max(
                asset.purchase_price - (annual_dep * min(years_owned, useful_life)),
                salvage,
            )

    return {
        "id": str(asset.id),
        "name": asset.name,
        "asset_tag": asset.asset_tag,
        "asset_type": asset.asset_type,
        "category": asset.category,
        "description": asset.description,
        "make": asset.make,
        "model": asset.model,
        "serial_number": asset.serial_number,
        "year": asset.year,
        "purchase_date": format_date(asset.purchase_date),
        "purchase_price": asset.purchase_price,
        "current_value": asset.current_value,
        "depreciated_value": round(depreciated, 2) if depreciated is not None else None,
        "salvage_value": asset.salvage_value,
        "useful_life_years": asset.useful_life_years,
        "depreciation_method": asset.depreciation_method,
        "status": asset.status or "available",
        "condition": asset.condition,
        "assigned_technician_id": str(asset.assigned_technician_id) if asset.assigned_technician_id else None,
        "assigned_technician_name": asset.assigned_technician_name,
        "assigned_work_order_id": str(asset.assigned_work_order_id) if asset.assigned_work_order_id else None,
        "location_description": asset.location_description,
        "latitude": asset.latitude,
        "longitude": asset.longitude,
        "samsara_vehicle_id": asset.samsara_vehicle_id,
        "last_maintenance_date": format_date(asset.last_maintenance_date),
        "next_maintenance_date": format_date(asset.next_maintenance_date),
        "maintenance_interval_days": asset.maintenance_interval_days,
        "total_hours": asset.total_hours,
        "odometer_miles": asset.odometer_miles,
        "photo_url": asset.photo_url,
        "qr_code": asset.qr_code,
        "warranty_expiry": format_date(asset.warranty_expiry),
        "insurance_policy": asset.insurance_policy,
        "insurance_expiry": format_date(asset.insurance_expiry),
        "notes": asset.notes,
        "is_active": asset.is_active if asset.is_active is not None else True,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
    }


def maintenance_to_response(log: AssetMaintenanceLog) -> dict:
    """Convert MaintenanceLog model to response dict."""
    return {
        "id": str(log.id),
        "asset_id": str(log.asset_id),
        "maintenance_type": log.maintenance_type,
        "title": log.title,
        "description": log.description,
        "performed_by_id": str(log.performed_by_id) if log.performed_by_id else None,
        "performed_by_name": log.performed_by_name,
        "performed_at": log.performed_at.isoformat() if log.performed_at else None,
        "cost": log.cost,
        "parts_used": log.parts_used,
        "hours_at_service": log.hours_at_service,
        "odometer_at_service": log.odometer_at_service,
        "next_due_date": format_date(log.next_due_date),
        "next_due_hours": log.next_due_hours,
        "next_due_miles": log.next_due_miles,
        "condition_before": log.condition_before,
        "condition_after": log.condition_after,
        "photos": log.photos,
        "notes": log.notes,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def assignment_to_response(a: AssetAssignment) -> dict:
    """Convert AssetAssignment model to response dict."""
    return {
        "id": str(a.id),
        "asset_id": str(a.asset_id),
        "assigned_to_type": a.assigned_to_type,
        "assigned_to_id": str(a.assigned_to_id),
        "assigned_to_name": a.assigned_to_name,
        "checked_out_at": a.checked_out_at.isoformat() if a.checked_out_at else None,
        "checked_in_at": a.checked_in_at.isoformat() if a.checked_in_at else None,
        "checked_out_by_id": str(a.checked_out_by_id) if a.checked_out_by_id else None,
        "checked_out_by_name": a.checked_out_by_name,
        "condition_at_checkout": a.condition_at_checkout,
        "condition_at_checkin": a.condition_at_checkin,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ==================== Dashboard ====================


@router.get("/dashboard")
async def get_asset_dashboard(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get asset dashboard summary with stats and recent activity."""
    try:
        today = date.today()

        # Total assets
        total_q = select(func.count()).where(Asset.is_active == True)
        total = (await db.execute(total_q)).scalar() or 0

        # Total value
        value_q = select(func.coalesce(func.sum(Asset.purchase_price), 0)).where(Asset.is_active == True)
        total_value = (await db.execute(value_q)).scalar() or 0

        # By status
        status_q = (
            select(Asset.status, func.count())
            .where(Asset.is_active == True)
            .group_by(Asset.status)
        )
        status_result = await db.execute(status_q)
        by_status = {row[0] or "available": row[1] for row in status_result.fetchall()}

        # By type
        type_q = (
            select(Asset.asset_type, func.count())
            .where(Asset.is_active == True)
            .group_by(Asset.asset_type)
        )
        type_result = await db.execute(type_q)
        by_type = {row[0]: row[1] for row in type_result.fetchall()}

        # By condition
        cond_q = (
            select(Asset.condition, func.count())
            .where(Asset.is_active == True)
            .group_by(Asset.condition)
        )
        cond_result = await db.execute(cond_q)
        by_condition = {row[0] or "good": row[1] for row in cond_result.fetchall()}

        # Maintenance due (within next 7 days)
        due_q = select(func.count()).where(
            Asset.is_active == True,
            Asset.next_maintenance_date.isnot(None),
            Asset.next_maintenance_date <= today,
        )
        maintenance_overdue = (await db.execute(due_q)).scalar() or 0

        from datetime import timedelta
        due_soon_q = select(func.count()).where(
            Asset.is_active == True,
            Asset.next_maintenance_date.isnot(None),
            Asset.next_maintenance_date > today,
            Asset.next_maintenance_date <= today + timedelta(days=7),
        )
        maintenance_due = (await db.execute(due_soon_q)).scalar() or 0

        # Recently added (last 5)
        recent_q = (
            select(Asset)
            .where(Asset.is_active == True)
            .order_by(Asset.created_at.desc())
            .limit(5)
        )
        recent_result = await db.execute(recent_q)
        recently_added = [asset_to_response(a) for a in recent_result.scalars().all()]

        # Recent maintenance (last 5)
        maint_q = (
            select(AssetMaintenanceLog)
            .order_by(AssetMaintenanceLog.created_at.desc())
            .limit(5)
        )
        maint_result = await db.execute(maint_q)
        recent_maintenance = [maintenance_to_response(m) for m in maint_result.scalars().all()]

        # Low condition assets
        low_q = (
            select(Asset)
            .where(Asset.is_active == True, Asset.condition.in_(["poor", "fair"]))
            .order_by(Asset.condition)
            .limit(10)
        )
        low_result = await db.execute(low_q)
        low_condition = [asset_to_response(a) for a in low_result.scalars().all()]

        return {
            "total_assets": total,
            "total_value": float(total_value),
            "by_status": by_status,
            "by_type": by_type,
            "by_condition": by_condition,
            "maintenance_due": maintenance_due,
            "maintenance_overdue": maintenance_overdue,
            "recently_added": recently_added,
            "recent_maintenance": recent_maintenance,
            "low_condition_assets": low_condition,
        }
    except Exception as e:
        import traceback
        logger.error(f"Error in asset dashboard: {traceback.format_exc()}")
        return {
            "total_assets": 0,
            "total_value": 0,
            "by_status": {},
            "by_type": {},
            "by_condition": {},
            "maintenance_due": 0,
            "maintenance_overdue": 0,
            "recently_added": [],
            "recent_maintenance": [],
            "low_condition_assets": [],
        }


# ==================== Asset CRUD ====================


@router.get("")
async def list_assets(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    asset_type: Optional[str] = None,
    status: Optional[str] = None,
    condition: Optional[str] = None,
    assigned_to: Optional[str] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List assets with pagination and filtering."""
    try:
        query = select(Asset)

        # Filters
        if asset_type:
            query = query.where(Asset.asset_type == asset_type)
        if status:
            query = query.where(Asset.status == status)
        if condition:
            query = query.where(Asset.condition == condition)
        if assigned_to:
            query = query.where(
                or_(
                    Asset.assigned_technician_id == assigned_to,
                    Asset.assigned_technician_name.ilike(f"%{assigned_to}%"),
                )
            )
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    Asset.name.ilike(pattern),
                    Asset.asset_tag.ilike(pattern),
                    Asset.serial_number.ilike(pattern),
                    Asset.make.ilike(pattern),
                    Asset.model.ilike(pattern),
                )
            )
        if is_active is not None:
            query = query.where(Asset.is_active == is_active)
        else:
            # Default to active only
            query = query.where(Asset.is_active == True)

        # Count
        count_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Asset.name)

        result = await db.execute(query)
        assets = result.scalars().all()

        return {
            "items": [asset_to_response(a) for a in assets],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        import traceback
        logger.error(f"Error in list_assets: {traceback.format_exc()}")
        return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/types")
async def get_asset_types(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get distinct asset types."""
    query = select(Asset.asset_type).where(Asset.asset_type.isnot(None)).distinct()
    result = await db.execute(query)
    types = [row[0] for row in result.fetchall() if row[0]]
    # Include default types even if no assets exist yet
    default_types = ["vehicle", "pump", "tool", "ppe", "trailer", "part", "other"]
    all_types = sorted(set(types + default_types))
    return {"types": all_types}


@router.get("/{asset_id}")
async def get_asset(
    asset_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single asset by ID."""
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset_to_response(asset)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_asset(
    data: AssetCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new asset."""
    asset_data = data.model_dump(exclude_unset=True)

    # Parse date fields
    for field in ["purchase_date", "last_maintenance_date", "next_maintenance_date", "warranty_expiry", "insurance_expiry"]:
        if field in asset_data and asset_data[field]:
            asset_data[field] = parse_date_field(asset_data[field])

    # Generate QR code if not provided
    if "qr_code" not in asset_data or not asset_data.get("qr_code"):
        asset_data["qr_code"] = f"AST-{uuid.uuid4().hex[:8].upper()}"

    # Auto-generate asset_tag if not provided
    if not asset_data.get("asset_tag"):
        prefix_map = {
            "vehicle": "VEH",
            "pump": "PMP",
            "tool": "TL",
            "ppe": "PPE",
            "trailer": "TRL",
            "part": "PRT",
        }
        prefix = prefix_map.get(asset_data.get("asset_type", ""), "AST")
        # Count existing assets of this type
        count_q = select(func.count()).where(Asset.asset_type == asset_data.get("asset_type"))
        count = (await db.execute(count_q)).scalar() or 0
        asset_data["asset_tag"] = f"{prefix}-{count + 1:03d}"

    # Convert technician_id string to UUID if present
    if asset_data.get("assigned_technician_id"):
        try:
            asset_data["assigned_technician_id"] = uuid.UUID(asset_data["assigned_technician_id"])
        except (ValueError, TypeError):
            asset_data["assigned_technician_id"] = None

    if asset_data.get("assigned_work_order_id"):
        try:
            asset_data["assigned_work_order_id"] = uuid.UUID(asset_data["assigned_work_order_id"])
        except (ValueError, TypeError):
            asset_data["assigned_work_order_id"] = None

    asset = Asset(**asset_data)
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset_to_response(asset)


@router.patch("/{asset_id}")
async def update_asset(
    asset_id: str,
    data: AssetUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an asset."""
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    update_data = data.model_dump(exclude_unset=True)

    # Parse date fields
    for field in ["purchase_date", "last_maintenance_date", "next_maintenance_date", "warranty_expiry", "insurance_expiry"]:
        if field in update_data and update_data[field]:
            update_data[field] = parse_date_field(update_data[field])

    # Convert UUID fields
    if "assigned_technician_id" in update_data:
        val = update_data["assigned_technician_id"]
        if val:
            try:
                update_data["assigned_technician_id"] = uuid.UUID(val)
            except (ValueError, TypeError):
                update_data["assigned_technician_id"] = None
        else:
            update_data["assigned_technician_id"] = None

    if "assigned_work_order_id" in update_data:
        val = update_data["assigned_work_order_id"]
        if val:
            try:
                update_data["assigned_work_order_id"] = uuid.UUID(val)
            except (ValueError, TypeError):
                update_data["assigned_work_order_id"] = None
        else:
            update_data["assigned_work_order_id"] = None

    for field, value in update_data.items():
        setattr(asset, field, value)

    await db.commit()
    await db.refresh(asset)
    return asset_to_response(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an asset (soft delete by setting is_active=False)."""
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset.is_active = False
    asset.status = "retired"
    await db.commit()


# ==================== Maintenance Logs ====================


@router.get("/{asset_id}/maintenance")
async def list_maintenance_logs(
    asset_id: str,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    """List maintenance logs for an asset."""
    # Verify asset exists
    asset_result = await db.execute(select(Asset).where(Asset.id == asset_id))
    if not asset_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Asset not found")

    count_q = select(func.count()).where(AssetMaintenanceLog.asset_id == asset_id)
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    query = (
        select(AssetMaintenanceLog)
        .where(AssetMaintenanceLog.asset_id == asset_id)
        .order_by(AssetMaintenanceLog.performed_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "items": [maintenance_to_response(log) for log in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{asset_id}/maintenance", status_code=status.HTTP_201_CREATED)
async def create_maintenance_log(
    asset_id: str,
    data: MaintenanceLogCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Log a maintenance activity for an asset."""
    # Verify asset exists
    asset_result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    log_data = data.model_dump(exclude_unset=True)
    log_data["asset_id"] = uuid.UUID(asset_id)

    # Parse date fields
    if log_data.get("next_due_date"):
        log_data["next_due_date"] = parse_date_field(log_data["next_due_date"])
    if log_data.get("performed_at"):
        try:
            log_data["performed_at"] = datetime.fromisoformat(log_data["performed_at"])
        except (ValueError, TypeError):
            log_data.pop("performed_at", None)

    # Convert UUID fields
    if log_data.get("performed_by_id"):
        try:
            log_data["performed_by_id"] = uuid.UUID(log_data["performed_by_id"])
        except (ValueError, TypeError):
            log_data["performed_by_id"] = None

    # Auto-set performed_by from current user if not specified
    if not log_data.get("performed_by_name"):
        log_data["performed_by_name"] = getattr(current_user, "email", "Unknown")

    log = AssetMaintenanceLog(**log_data)
    db.add(log)

    # Update asset's maintenance dates
    asset.last_maintenance_date = date.today()
    if log_data.get("next_due_date"):
        asset.next_maintenance_date = log_data["next_due_date"]
    elif asset.maintenance_interval_days:
        from datetime import timedelta
        asset.next_maintenance_date = date.today() + timedelta(days=asset.maintenance_interval_days)

    # Update asset condition if provided
    if log_data.get("condition_after"):
        asset.condition = log_data["condition_after"]

    # Update usage metrics
    if log_data.get("hours_at_service"):
        asset.total_hours = log_data["hours_at_service"]
    if log_data.get("odometer_at_service"):
        asset.odometer_miles = log_data["odometer_at_service"]

    await db.commit()
    await db.refresh(log)
    return maintenance_to_response(log)


# ==================== Asset Assignments (Check-out/in) ====================


@router.get("/{asset_id}/assignments")
async def list_assignments(
    asset_id: str,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    """List assignment history for an asset."""
    count_q = select(func.count()).where(AssetAssignment.asset_id == asset_id)
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    query = (
        select(AssetAssignment)
        .where(AssetAssignment.asset_id == asset_id)
        .order_by(AssetAssignment.checked_out_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    assignments = result.scalars().all()

    return {
        "items": [assignment_to_response(a) for a in assignments],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/checkout", status_code=status.HTTP_201_CREATED)
async def checkout_asset(
    data: AssetCheckout,
    db: DbSession,
    current_user: CurrentUser,
):
    """Check out an asset to a technician or work order."""
    # Verify asset exists and is available
    result = await db.execute(select(Asset).where(Asset.id == data.asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.status == "maintenance":
        raise HTTPException(status_code=400, detail="Asset is currently in maintenance")
    if asset.status == "retired":
        raise HTTPException(status_code=400, detail="Asset is retired")

    # Create assignment record
    assignment = AssetAssignment(
        asset_id=uuid.UUID(data.asset_id),
        assigned_to_type=data.assigned_to_type,
        assigned_to_id=uuid.UUID(data.assigned_to_id),
        assigned_to_name=data.assigned_to_name,
        checked_out_by_id=uuid.UUID(str(current_user.id)) if current_user.id else None,
        checked_out_by_name=getattr(current_user, "email", "Unknown"),
        condition_at_checkout=data.condition_at_checkout or asset.condition,
        notes=data.notes,
    )
    db.add(assignment)

    # Update asset status
    asset.status = "in_use"
    if data.assigned_to_type == "technician":
        try:
            asset.assigned_technician_id = uuid.UUID(data.assigned_to_id)
        except (ValueError, TypeError):
            pass
        asset.assigned_technician_name = data.assigned_to_name

    await db.commit()
    await db.refresh(assignment)
    return assignment_to_response(assignment)


@router.post("/checkin/{assignment_id}")
async def checkin_asset(
    assignment_id: str,
    data: AssetCheckin,
    db: DbSession,
    current_user: CurrentUser,
):
    """Check in an asset (return from assignment)."""
    result = await db.execute(select(AssetAssignment).where(AssetAssignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.checked_in_at:
        raise HTTPException(status_code=400, detail="Asset already checked in")

    # Update assignment
    assignment.checked_in_at = datetime.utcnow()
    assignment.condition_at_checkin = data.condition_at_checkin
    if data.notes:
        assignment.notes = (assignment.notes or "") + "\n" + data.notes

    # Update asset
    asset_result = await db.execute(select(Asset).where(Asset.id == assignment.asset_id))
    asset = asset_result.scalar_one_or_none()
    if asset:
        asset.status = "available"
        asset.assigned_technician_id = None
        asset.assigned_technician_name = None
        asset.assigned_work_order_id = None
        if data.condition_at_checkin:
            asset.condition = data.condition_at_checkin

    await db.commit()
    await db.refresh(assignment)
    return assignment_to_response(assignment)
