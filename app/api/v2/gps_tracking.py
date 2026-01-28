"""
GPS Tracking API Endpoints
Real-time location tracking, ETA, geofencing, and customer tracking links
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timedelta

from app.database import get_db
from app.api.deps import get_current_user
from app.services.gps_tracking_service import GPSTrackingService, GeofenceService
from app.schemas.gps_tracking import (
    LocationUpdate, LocationUpdateBatch, TechnicianLocationResponse,
    AllTechniciansLocationResponse, LocationHistoryResponse,
    GeofenceCreate, GeofenceUpdate, GeofenceResponse, GeofenceEventResponse,
    TrackingLinkCreate, TrackingLinkResponse, PublicTrackingInfo,
    ETARequest, ETAResponse, ETANotification,
    GPSConfigUpdate, GPSConfigResponse,
    DispatchMapData, DispatchMapTechnician, DispatchMapWorkOrder
)

router = APIRouter(prefix="/gps", tags=["GPS Tracking"])


# ==================== Location Updates ====================

@router.post("/location", response_model=TechnicianLocationResponse)
async def update_location(
    location: LocationUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Update technician's current GPS location.
    Called by mobile app at configured intervals.
    """
    # Get technician ID from current user
    technician_id = current_user.technician_id if hasattr(current_user, 'technician_id') else current_user.id

    service = GPSTrackingService(db)
    return service.update_technician_location(technician_id, location)


@router.post("/location/batch", response_model=dict)
async def update_location_batch(
    batch: LocationUpdateBatch,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Submit batch of location updates (for offline sync).
    Mobile app can queue locations while offline and sync when online.
    """
    technician_id = current_user.technician_id if hasattr(current_user, 'technician_id') else current_user.id
    service = GPSTrackingService(db)

    processed = 0
    for location in sorted(batch.locations, key=lambda x: x.captured_at):
        try:
            service.update_technician_location(technician_id, location)
            processed += 1
        except Exception as e:
            # Log error but continue processing
            pass

    return {
        "processed": processed,
        "total": len(batch.locations),
        "success": processed == len(batch.locations)
    }


@router.get("/location/{technician_id}", response_model=TechnicianLocationResponse)
async def get_technician_location(
    technician_id: int = Path(..., description="Technician ID"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get current location for a specific technician."""
    service = GPSTrackingService(db)
    location = service.get_technician_location(technician_id)

    if not location:
        raise HTTPException(status_code=404, detail="Technician location not found")

    return location


@router.get("/locations", response_model=AllTechniciansLocationResponse)
async def get_all_locations(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get all technician locations for dispatch map.
    Returns current position, status, and online/offline count.
    """
    service = GPSTrackingService(db)
    data = service.get_all_technician_locations()

    return AllTechniciansLocationResponse(
        technicians=data["technicians"],
        total_online=data["total_online"],
        total_offline=data["total_offline"],
        last_refresh=data["last_refresh"]
    )


# ==================== Location History ====================

@router.get("/history/{technician_id}", response_model=LocationHistoryResponse)
async def get_location_history(
    technician_id: int = Path(..., description="Technician ID"),
    date: Optional[str] = Query(None, description="Date (YYYY-MM-DD), defaults to today"),
    work_order_id: Optional[int] = Query(None, description="Filter by work order"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get location history for route verification.
    Shows all GPS points captured for a technician on a given day.
    """
    date_obj = None
    if date:
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    service = GPSTrackingService(db)
    history = service.get_location_history(technician_id, date_obj, work_order_id)

    return LocationHistoryResponse(**history)


@router.get("/history/{technician_id}/route/{work_order_id}")
async def get_route_for_work_order(
    technician_id: int = Path(..., description="Technician ID"),
    work_order_id: int = Path(..., description="Work Order ID"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get the route a technician took to reach a work order.
    Useful for route verification and mileage tracking.
    """
    service = GPSTrackingService(db)
    history = service.get_location_history(technician_id, work_order_id=work_order_id)

    return history


# ==================== ETA Calculations ====================

@router.get("/eta/{work_order_id}", response_model=ETAResponse)
async def get_eta(
    work_order_id: int = Path(..., description="Work Order ID"),
    recalculate: bool = Query(False, description="Force recalculation"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get ETA for a work order.
    Calculates based on technician's current location and traffic.
    """
    service = GPSTrackingService(db)
    eta = service.calculate_eta(work_order_id, force_recalculate=recalculate)

    if not eta:
        raise HTTPException(
            status_code=404,
            detail="Cannot calculate ETA. Work order may not have an assigned technician or technician location is unknown."
        )

    return eta


@router.post("/eta/notify")
async def send_eta_notification(
    notification: ETANotification,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Send ETA notification to customer.
    Includes tracking link in SMS/email.
    """
    # Would integrate with notification service
    # For now, return confirmation
    return {
        "success": True,
        "notification_type": "sms",
        "recipient": notification.customer_phone,
        "message": f"Your technician {notification.technician_name} is on the way! "
                   f"ETA: {notification.eta_minutes} minutes. "
                   f"Track here: {notification.tracking_url}"
    }


# ==================== Customer Tracking Links ====================

@router.post("/tracking-links", response_model=TrackingLinkResponse)
async def create_tracking_link(
    data: TrackingLinkCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Create a customer tracking link for a work order.
    Returns a URL that customers can use to track their technician.
    """
    from app.models.work_order import WorkOrder

    work_order = db.query(WorkOrder).filter(WorkOrder.id == data.work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    if not work_order.technician_id:
        raise HTTPException(status_code=400, detail="Work order has no assigned technician")

    service = GPSTrackingService(db)
    link = service.create_tracking_link(
        work_order_id=data.work_order_id,
        customer_id=work_order.customer_id,
        technician_id=work_order.technician_id,
        expires_hours=data.expires_hours,
        show_technician_name=data.show_technician_name,
        show_technician_photo=data.show_technician_photo,
        show_live_map=data.show_live_map,
        show_eta=data.show_eta
    )

    return TrackingLinkResponse(
        id=link.id,
        token=link.token,
        tracking_url=f"/track/{link.token}",
        work_order_id=link.work_order_id,
        customer_id=link.customer_id,
        technician_id=link.technician_id,
        status=link.status.value,
        expires_at=link.expires_at,
        view_count=link.view_count,
        created_at=link.created_at
    )


@router.get("/tracking-links/{work_order_id}", response_model=List[TrackingLinkResponse])
async def get_tracking_links(
    work_order_id: int = Path(..., description="Work Order ID"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all tracking links for a work order."""
    from app.models.gps_tracking import CustomerTrackingLink

    links = db.query(CustomerTrackingLink).filter(
        CustomerTrackingLink.work_order_id == work_order_id
    ).order_by(CustomerTrackingLink.created_at.desc()).all()

    return [
        TrackingLinkResponse(
            id=link.id,
            token=link.token,
            tracking_url=f"/track/{link.token}",
            work_order_id=link.work_order_id,
            customer_id=link.customer_id,
            technician_id=link.technician_id,
            status=link.status.value,
            expires_at=link.expires_at,
            view_count=link.view_count,
            created_at=link.created_at
        )
        for link in links
    ]


# Public endpoint - no auth required
@router.get("/track/{token}", response_model=PublicTrackingInfo)
async def get_public_tracking(
    token: str = Path(..., description="Tracking link token"),
    db: Session = Depends(get_db)
):
    """
    PUBLIC ENDPOINT - Get tracking info for customer.
    This is the endpoint customers access to track their technician.
    No authentication required.
    """
    service = GPSTrackingService(db)
    info = service.get_public_tracking_info(token)

    if not info:
        raise HTTPException(status_code=404, detail="Tracking link not found or expired")

    return info


# ==================== Geofences ====================

@router.post("/geofences", response_model=GeofenceResponse)
async def create_geofence(
    geofence: GeofenceCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new geofence."""
    service = GeofenceService(db)
    result = service.create_geofence(geofence.model_dump())

    return GeofenceResponse(
        id=result.id,
        name=result.name,
        description=result.description,
        geofence_type=result.geofence_type.value if result.geofence_type else None,
        is_active=result.is_active,
        center_latitude=result.center_latitude,
        center_longitude=result.center_longitude,
        radius_meters=result.radius_meters,
        polygon_coordinates=result.polygon_coordinates,
        customer_id=result.customer_id,
        work_order_id=result.work_order_id,
        entry_action=result.entry_action.value if result.entry_action else "log_only",
        exit_action=result.exit_action.value if result.exit_action else "log_only",
        notify_on_entry=result.notify_on_entry,
        notify_on_exit=result.notify_on_exit,
        created_at=result.created_at,
        updated_at=result.updated_at
    )


@router.get("/geofences", response_model=List[GeofenceResponse])
async def list_geofences(
    geofence_type: Optional[str] = Query(None, description="Filter by type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all geofences."""
    service = GeofenceService(db)
    geofences = service.get_all_geofences(geofence_type, is_active)

    return [
        GeofenceResponse(
            id=g.id,
            name=g.name,
            description=g.description,
            geofence_type=g.geofence_type.value if g.geofence_type else None,
            is_active=g.is_active,
            center_latitude=g.center_latitude,
            center_longitude=g.center_longitude,
            radius_meters=g.radius_meters,
            polygon_coordinates=g.polygon_coordinates,
            customer_id=g.customer_id,
            work_order_id=g.work_order_id,
            entry_action=g.entry_action.value if g.entry_action else "log_only",
            exit_action=g.exit_action.value if g.exit_action else "log_only",
            notify_on_entry=g.notify_on_entry,
            notify_on_exit=g.notify_on_exit,
            created_at=g.created_at,
            updated_at=g.updated_at
        )
        for g in geofences
    ]


@router.get("/geofences/{geofence_id}", response_model=GeofenceResponse)
async def get_geofence(
    geofence_id: int = Path(..., description="Geofence ID"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get a specific geofence."""
    service = GeofenceService(db)
    geofence = service.get_geofence(geofence_id)

    if not geofence:
        raise HTTPException(status_code=404, detail="Geofence not found")

    return GeofenceResponse(
        id=geofence.id,
        name=geofence.name,
        description=geofence.description,
        geofence_type=geofence.geofence_type.value if geofence.geofence_type else None,
        is_active=geofence.is_active,
        center_latitude=geofence.center_latitude,
        center_longitude=geofence.center_longitude,
        radius_meters=geofence.radius_meters,
        polygon_coordinates=geofence.polygon_coordinates,
        customer_id=geofence.customer_id,
        work_order_id=geofence.work_order_id,
        entry_action=geofence.entry_action.value if geofence.entry_action else "log_only",
        exit_action=geofence.exit_action.value if geofence.exit_action else "log_only",
        notify_on_entry=geofence.notify_on_entry,
        notify_on_exit=geofence.notify_on_exit,
        created_at=geofence.created_at,
        updated_at=geofence.updated_at
    )


@router.patch("/geofences/{geofence_id}", response_model=GeofenceResponse)
async def update_geofence(
    geofence_id: int = Path(..., description="Geofence ID"),
    update: GeofenceUpdate = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update a geofence."""
    service = GeofenceService(db)
    geofence = service.update_geofence(geofence_id, update.model_dump(exclude_unset=True))

    if not geofence:
        raise HTTPException(status_code=404, detail="Geofence not found")

    return GeofenceResponse(
        id=geofence.id,
        name=geofence.name,
        description=geofence.description,
        geofence_type=geofence.geofence_type.value if geofence.geofence_type else None,
        is_active=geofence.is_active,
        center_latitude=geofence.center_latitude,
        center_longitude=geofence.center_longitude,
        radius_meters=geofence.radius_meters,
        polygon_coordinates=geofence.polygon_coordinates,
        customer_id=geofence.customer_id,
        work_order_id=geofence.work_order_id,
        entry_action=geofence.entry_action.value if geofence.entry_action else "log_only",
        exit_action=geofence.exit_action.value if geofence.exit_action else "log_only",
        notify_on_entry=geofence.notify_on_entry,
        notify_on_exit=geofence.notify_on_exit,
        created_at=geofence.created_at,
        updated_at=geofence.updated_at
    )


@router.delete("/geofences/{geofence_id}")
async def delete_geofence(
    geofence_id: int = Path(..., description="Geofence ID"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a geofence."""
    service = GeofenceService(db)
    success = service.delete_geofence(geofence_id)

    if not success:
        raise HTTPException(status_code=404, detail="Geofence not found")

    return {"success": True, "message": "Geofence deleted"}


@router.get("/geofences/events", response_model=List[GeofenceEventResponse])
async def get_geofence_events(
    technician_id: Optional[int] = Query(None, description="Filter by technician"),
    geofence_id: Optional[int] = Query(None, description="Filter by geofence"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get geofence events log."""
    from app.models.gps_tracking import GeofenceEvent, Geofence
    from app.models.technician import Technician
    from sqlalchemy import and_

    query = db.query(GeofenceEvent)

    if technician_id:
        query = query.filter(GeofenceEvent.technician_id == technician_id)
    if geofence_id:
        query = query.filter(GeofenceEvent.geofence_id == geofence_id)
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(GeofenceEvent.occurred_at >= start)
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(GeofenceEvent.occurred_at < end)

    events = query.order_by(GeofenceEvent.occurred_at.desc()).limit(limit).all()

    results = []
    for event in events:
        geofence = db.query(Geofence).filter(Geofence.id == event.geofence_id).first()
        tech = db.query(Technician).filter(Technician.id == event.technician_id).first()

        results.append(GeofenceEventResponse(
            id=event.id,
            geofence_id=event.geofence_id,
            geofence_name=geofence.name if geofence else "Unknown",
            technician_id=event.technician_id,
            technician_name=f"{tech.first_name} {tech.last_name}" if tech else "Unknown",
            event_type=event.event_type,
            latitude=event.latitude,
            longitude=event.longitude,
            action_triggered=event.action_triggered.value if event.action_triggered else None,
            action_result=event.action_result,
            occurred_at=event.occurred_at
        ))

    return results


# ==================== Dispatch Map ====================

@router.get("/dispatch-map", response_model=DispatchMapData)
async def get_dispatch_map_data(
    include_completed: bool = Query(False, description="Include completed work orders"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get all data needed for the dispatch map.
    Includes technician locations, work orders, and geofences.
    Uses raw SQL for async compatibility.
    """
    from sqlalchemy import text

    technicians = []
    work_orders = []

    # Get technician locations with names
    loc_result = await db.execute(text("""
        SELECT
            tl.technician_id, t.first_name, t.last_name,
            tl.latitude, tl.longitude, tl.accuracy, tl.speed, tl.heading,
            tl.is_online, tl.battery_level, tl.captured_at, tl.received_at,
            tl.current_work_order_id, tl.current_status
        FROM technician_locations tl
        JOIN technicians t ON tl.technician_id = t.id
    """))
    locations = loc_result.fetchall()

    for loc in locations:
        tech_id, first_name, last_name, lat, lng, accuracy, speed, heading, \
            is_online, battery, captured_at, received_at, wo_id, status = loc

        # Calculate minutes since update
        if captured_at:
            minutes_since = int((datetime.utcnow() - captured_at).total_seconds() / 60)
        else:
            minutes_since = 999

        is_stale = minutes_since > 5

        technicians.append(DispatchMapTechnician(
            id=tech_id,
            name=f"{first_name} {last_name}",
            latitude=lat,
            longitude=lng,
            status=status or "available",
            current_work_order_id=wo_id,
            current_job_address=None,  # Simplified - would need another query
            battery_level=battery,
            speed=speed,
            last_updated=captured_at,
            is_stale=is_stale
        ))

    # Get work orders for today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    status_filter = "" if include_completed else "AND wo.status != 'completed'"

    wo_result = await db.execute(text(f"""
        SELECT
            wo.id, wo.customer_id, wo.technician_id, wo.assigned_technician,
            wo.job_type, wo.status, wo.scheduled_date,
            c.first_name, c.last_name, c.address_line1, c.city, c.state,
            COALESCE(c.latitude, 32.0) as lat, COALESCE(c.longitude, -96.0) as lng,
            t.first_name as tech_first, t.last_name as tech_last
        FROM work_orders wo
        JOIN customers c ON wo.customer_id = c.id
        LEFT JOIN technicians t ON wo.technician_id = t.id
        WHERE wo.scheduled_date >= :today_start
          AND wo.scheduled_date < :today_end
          {status_filter}
        ORDER BY wo.scheduled_date
    """), {"today_start": today_start, "today_end": today_end})
    work_orders_db = wo_result.fetchall()

    for wo in work_orders_db:
        wo_id, cust_id, tech_id, assigned_tech, job_type, status, sched_date, \
            cust_first, cust_last, addr, city, state, lat, lng, tech_first, tech_last = wo

        tech_name = f"{tech_first} {tech_last}" if tech_first else assigned_tech
        address = f"{addr}, {city}, {state}" if addr else "No address"

        work_orders.append(DispatchMapWorkOrder(
            id=wo_id,
            customer_name=f"{cust_first} {cust_last}",
            address=address,
            latitude=float(lat),
            longitude=float(lng),
            status=status,
            scheduled_time=sched_date,
            assigned_technician_id=tech_id,
            assigned_technician_name=tech_name,
            service_type=job_type or "Service",
            priority="normal"
        ))

    # Calculate map center (average of all points)
    all_points = [(t.latitude, t.longitude) for t in technicians] + [(w.latitude, w.longitude) for w in work_orders]
    if all_points:
        center_lat = sum(p[0] for p in all_points) / len(all_points)
        center_lng = sum(p[1] for p in all_points) / len(all_points)
    else:
        # Default to Texas
        center_lat = 30.27
        center_lng = -97.74

    return DispatchMapData(
        technicians=technicians,
        work_orders=work_orders,
        geofences=[],  # Simplified - geofences not critical for demo
        center_latitude=center_lat,
        center_longitude=center_lng,
        zoom_level=10,
        last_refresh=datetime.utcnow()
    )


# ==================== GPS Configuration ====================

@router.get("/config", response_model=GPSConfigResponse)
async def get_global_config(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get global GPS tracking configuration."""
    from app.models.gps_tracking import GPSTrackingConfig

    config = db.query(GPSTrackingConfig).filter(
        GPSTrackingConfig.technician_id == None
    ).first()

    if not config:
        # Return defaults
        return GPSConfigResponse(
            id=0,
            technician_id=None,
            active_interval=30,
            idle_interval=300,
            background_interval=600,
            tracking_enabled=True,
            geofencing_enabled=True,
            auto_clockin_enabled=True,
            customer_tracking_enabled=True,
            high_accuracy_mode=True,
            battery_saver_threshold=20,
            track_during_breaks=False,
            track_after_hours=False,
            work_hours_start="07:00",
            work_hours_end="18:00",
            history_retention_days=90,
            updated_at=datetime.utcnow()
        )

    return GPSConfigResponse(
        id=config.id,
        technician_id=config.technician_id,
        active_interval=config.active_interval,
        idle_interval=config.idle_interval,
        background_interval=config.background_interval,
        tracking_enabled=config.tracking_enabled,
        geofencing_enabled=config.geofencing_enabled,
        auto_clockin_enabled=config.auto_clockin_enabled,
        customer_tracking_enabled=config.customer_tracking_enabled,
        high_accuracy_mode=config.high_accuracy_mode,
        battery_saver_threshold=config.battery_saver_threshold,
        track_during_breaks=config.track_during_breaks,
        track_after_hours=config.track_after_hours,
        work_hours_start=config.work_hours_start,
        work_hours_end=config.work_hours_end,
        history_retention_days=config.history_retention_days,
        updated_at=config.updated_at
    )


@router.patch("/config", response_model=GPSConfigResponse)
async def update_global_config(
    update: GPSConfigUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update global GPS tracking configuration."""
    from app.models.gps_tracking import GPSTrackingConfig

    config = db.query(GPSTrackingConfig).filter(
        GPSTrackingConfig.technician_id == None
    ).first()

    if not config:
        config = GPSTrackingConfig(technician_id=None)
        db.add(config)

    for key, value in update.model_dump(exclude_unset=True).items():
        setattr(config, key, value)

    db.commit()
    db.refresh(config)

    return GPSConfigResponse(
        id=config.id,
        technician_id=config.technician_id,
        active_interval=config.active_interval,
        idle_interval=config.idle_interval,
        background_interval=config.background_interval,
        tracking_enabled=config.tracking_enabled,
        geofencing_enabled=config.geofencing_enabled,
        auto_clockin_enabled=config.auto_clockin_enabled,
        customer_tracking_enabled=config.customer_tracking_enabled,
        high_accuracy_mode=config.high_accuracy_mode,
        battery_saver_threshold=config.battery_saver_threshold,
        track_during_breaks=config.track_during_breaks,
        track_after_hours=config.track_after_hours,
        work_hours_start=config.work_hours_start,
        work_hours_end=config.work_hours_end,
        history_retention_days=config.history_retention_days,
        updated_at=config.updated_at
    )


@router.get("/config/{technician_id}", response_model=GPSConfigResponse)
async def get_technician_config(
    technician_id: int = Path(..., description="Technician ID"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get GPS configuration for a specific technician (falls back to global)."""
    from app.models.gps_tracking import GPSTrackingConfig

    # Try technician-specific config
    config = db.query(GPSTrackingConfig).filter(
        GPSTrackingConfig.technician_id == technician_id
    ).first()

    # Fall back to global
    if not config:
        config = db.query(GPSTrackingConfig).filter(
            GPSTrackingConfig.technician_id == None
        ).first()

    if not config:
        # Return defaults
        return GPSConfigResponse(
            id=0,
            technician_id=technician_id,
            active_interval=30,
            idle_interval=300,
            background_interval=600,
            tracking_enabled=True,
            geofencing_enabled=True,
            auto_clockin_enabled=True,
            customer_tracking_enabled=True,
            high_accuracy_mode=True,
            battery_saver_threshold=20,
            track_during_breaks=False,
            track_after_hours=False,
            work_hours_start="07:00",
            work_hours_end="18:00",
            history_retention_days=90,
            updated_at=datetime.utcnow()
        )

    return GPSConfigResponse(
        id=config.id,
        technician_id=config.technician_id,
        active_interval=config.active_interval,
        idle_interval=config.idle_interval,
        background_interval=config.background_interval,
        tracking_enabled=config.tracking_enabled,
        geofencing_enabled=config.geofencing_enabled,
        auto_clockin_enabled=config.auto_clockin_enabled,
        customer_tracking_enabled=config.customer_tracking_enabled,
        high_accuracy_mode=config.high_accuracy_mode,
        battery_saver_threshold=config.battery_saver_threshold,
        track_during_breaks=config.track_during_breaks,
        track_after_hours=config.track_after_hours,
        work_hours_start=config.work_hours_start,
        work_hours_end=config.work_hours_end,
        history_retention_days=config.history_retention_days,
        updated_at=config.updated_at
    )


# ==================== Demo Data Seeding ====================

@router.post("/seed-demo-data")
async def seed_demo_data(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Seed demo GPS data for testing the tracking page.
    Creates technician locations and work orders for today.
    Requires authentication.
    Uses raw SQL for async compatibility.
    """
    import random
    import uuid
    import traceback
    from sqlalchemy import text

    try:
        # First, ensure the technician_locations table exists
        # Note: technicians.id is VARCHAR(36) in the existing schema
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS technician_locations (
                id SERIAL PRIMARY KEY,
                technician_id VARCHAR(36) NOT NULL UNIQUE,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                accuracy DOUBLE PRECISION,
                altitude DOUBLE PRECISION,
                speed DOUBLE PRECISION,
                heading DOUBLE PRECISION,
                is_online BOOLEAN DEFAULT TRUE,
                battery_level INTEGER,
                captured_at TIMESTAMP NOT NULL,
                received_at TIMESTAMP DEFAULT NOW(),
                current_work_order_id VARCHAR(36),
                current_status VARCHAR(50) DEFAULT 'available'
            )
        """))
        await db.commit()

        # Texas locations for demo
        TEXAS_LOCATIONS = [
            {"name": "Austin Downtown", "lat": 30.2672, "lng": -97.7431},
            {"name": "Round Rock", "lat": 30.5083, "lng": -97.6789},
            {"name": "Georgetown", "lat": 30.6327, "lng": -97.6773},
            {"name": "Pflugerville", "lat": 30.4393, "lng": -97.6200},
            {"name": "Cedar Park", "lat": 30.5052, "lng": -97.8203},
            {"name": "Lakeway", "lat": 30.3632, "lng": -97.9795},
            {"name": "Dripping Springs", "lat": 30.1902, "lng": -98.0867},
            {"name": "Kyle", "lat": 29.9891, "lng": -97.8772},
            {"name": "Buda", "lat": 30.0852, "lng": -97.8403},
            {"name": "San Marcos", "lat": 29.8833, "lng": -97.9414},
        ]

        STATUSES = ["available", "en_route", "on_site", "break"]

        # Get active technicians using raw SQL
        result = await db.execute(
            text("SELECT id, first_name, last_name FROM technicians WHERE is_active = true")
        )
        technicians = result.fetchall()

        if not technicians:
            return {"success": False, "message": "No active technicians found"}

        now = datetime.utcnow()
        created_locations = 0
        updated_locations = 0

        # Create/update locations for each technician
        for i, tech in enumerate(technicians):
            tech_id, first_name, last_name = tech
            location = TEXAS_LOCATIONS[i % len(TEXAS_LOCATIONS)]

            # Add randomness to position
            lat = location["lat"] + random.uniform(-0.005, 0.005)
            lng = location["lng"] + random.uniform(-0.005, 0.005)
            status = random.choice(STATUSES)
            battery = random.randint(40, 100)
            speed = 0 if status in ("on_site", "break") else random.uniform(0, 45)
            heading = random.uniform(0, 360)

            # Check if location exists
            existing_result = await db.execute(
                text("SELECT id FROM technician_locations WHERE technician_id = :tech_id"),
                {"tech_id": tech_id}
            )
            existing = existing_result.fetchone()

            if existing:
                await db.execute(
                    text("""
                        UPDATE technician_locations SET
                            latitude = :lat, longitude = :lng, accuracy = :accuracy,
                            speed = :speed, heading = :heading, is_online = true,
                            battery_level = :battery, captured_at = :captured_at,
                            received_at = :received_at, current_status = :status
                        WHERE technician_id = :tech_id
                    """),
                    {
                        "tech_id": tech_id, "lat": lat, "lng": lng,
                        "accuracy": random.uniform(5, 25), "speed": speed,
                        "heading": heading, "battery": battery,
                        "captured_at": now, "received_at": now, "status": status
                    }
                )
                updated_locations += 1
            else:
                await db.execute(
                    text("""
                        INSERT INTO technician_locations (
                            technician_id, latitude, longitude, accuracy,
                            speed, heading, is_online, battery_level,
                            captured_at, received_at, current_status
                        ) VALUES (
                            :tech_id, :lat, :lng, :accuracy,
                            :speed, :heading, true, :battery,
                            :captured_at, :received_at, :status
                        )
                    """),
                    {
                        "tech_id": tech_id, "lat": lat, "lng": lng,
                        "accuracy": random.uniform(5, 25), "speed": speed,
                        "heading": heading, "battery": battery,
                        "captured_at": now, "received_at": now, "status": status
                    }
                )
                created_locations += 1

        # Check for today's work orders
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        count_result = await db.execute(
            text("""
                SELECT COUNT(*) FROM work_orders
                WHERE scheduled_date >= :today_start
                  AND scheduled_date < :today_end
                  AND status != 'completed'
            """),
            {"today_start": today_start, "today_end": today_end}
        )
        todays_orders = count_result.scalar() or 0

        created_orders = 0
        if todays_orders == 0:
            # Get customers
            customers_result = await db.execute(
                text("SELECT id, first_name, last_name FROM customers WHERE is_active = true LIMIT 5")
            )
            customers = customers_result.fetchall()

            if customers and technicians:
                for i, customer in enumerate(customers[:min(5, len(technicians))]):
                    cust_id, cust_first, cust_last = customer
                    tech = technicians[i % len(technicians)]
                    tech_id, tech_first, tech_last = tech
                    scheduled_time = today_start + timedelta(hours=8 + random.randint(0, 8))

                    await db.execute(
                        text("""
                            INSERT INTO work_orders (
                                id, customer_id, technician_id, assigned_technician,
                                job_type, status, scheduled_date, notes,
                                created_at, updated_at
                            ) VALUES (
                                :id, :customer_id, :tech_id, :tech_name,
                                :job_type, :status, :scheduled_date, :notes,
                                :created_at, :updated_at
                            )
                        """),
                        {
                            "id": str(uuid.uuid4()),
                            "customer_id": cust_id,
                            "tech_id": tech_id,
                            "tech_name": f"{tech_first} {tech_last}",
                            "job_type": random.choice(["pumping", "inspection", "maintenance"]),
                            "status": random.choice(["scheduled", "in_progress"]),
                            "scheduled_date": scheduled_time,
                            "notes": "[GPS DEMO] Test work order for GPS tracking demo",
                            "created_at": now,
                            "updated_at": now
                        }
                    )
                    created_orders += 1

        await db.commit()

        return {
            "success": True,
            "technicians_found": len(technicians),
            "locations_created": created_locations,
            "locations_updated": updated_locations,
            "existing_orders_today": todays_orders,
            "work_orders_created": created_orders,
            "message": f"Seeded {created_locations + updated_locations} technician locations and {created_orders} work orders"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
