"""
GPS Tracking Schemas
Pydantic models for GPS tracking, geofencing, and customer tracking links
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class GeofenceTypeEnum(str, Enum):
    customer_site = "customer_site"
    office = "office"
    warehouse = "warehouse"
    service_area = "service_area"
    exclusion_zone = "exclusion_zone"


class GeofenceActionEnum(str, Enum):
    clock_in = "clock_in"
    clock_out = "clock_out"
    notify_dispatch = "notify_dispatch"
    notify_customer = "notify_customer"
    start_job = "start_job"
    complete_job = "complete_job"
    log_only = "log_only"


class TrackingLinkStatusEnum(str, Enum):
    active = "active"
    expired = "expired"
    viewed = "viewed"
    completed = "completed"


# ==================== Location Updates ====================


class LocationUpdate(BaseModel):
    """Incoming GPS location update from mobile app"""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(None, ge=0, description="GPS accuracy in meters")
    altitude: Optional[float] = None
    speed: Optional[float] = Field(None, ge=0, description="Speed in mph")
    heading: Optional[float] = Field(None, ge=0, le=360, description="Compass heading")
    battery_level: Optional[int] = Field(None, ge=0, le=100)
    captured_at: datetime
    current_status: Optional[str] = "available"
    work_order_id: Optional[str] = None


class LocationUpdateBatch(BaseModel):
    """Batch of location updates (for offline sync)"""

    locations: List[LocationUpdate]


class TechnicianLocationResponse(BaseModel):
    """Current technician location response"""

    technician_id: str
    technician_name: str
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    is_online: bool
    battery_level: Optional[int] = None
    current_status: str
    current_work_order_id: Optional[str] = None
    captured_at: datetime
    received_at: datetime
    minutes_since_update: int

    class Config:
        from_attributes = True


class AllTechniciansLocationResponse(BaseModel):
    """All technicians' locations for dispatch map"""

    technicians: List[TechnicianLocationResponse]
    total_online: int
    total_offline: int
    last_refresh: datetime


# ==================== Location History ====================


class LocationHistoryPoint(BaseModel):
    """Single point in location history"""

    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    captured_at: datetime
    status: Optional[str] = None
    distance_from_previous: Optional[float] = None

    class Config:
        from_attributes = True


class LocationHistoryResponse(BaseModel):
    """Location history for a technician"""

    technician_id: str
    technician_name: str
    date: str
    points: List[LocationHistoryPoint]
    total_distance_miles: float
    total_duration_minutes: int
    average_speed_mph: Optional[float] = None


class RouteVerification(BaseModel):
    """Route verification for a work order"""

    work_order_id: str
    technician_id: str
    expected_route_miles: float
    actual_route_miles: float
    deviation_percent: float
    suspicious: bool
    route_points: List[LocationHistoryPoint]


# ==================== Geofences ====================


class GeofenceCreate(BaseModel):
    """Create a new geofence"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    geofence_type: GeofenceTypeEnum

    # Circle definition
    center_latitude: Optional[float] = Field(None, ge=-90, le=90)
    center_longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_meters: Optional[float] = Field(None, ge=10, le=50000)

    # Polygon definition
    polygon_coordinates: Optional[List[List[float]]] = None

    # Associations
    customer_id: Optional[str] = None
    work_order_id: Optional[str] = None

    # Actions
    entry_action: GeofenceActionEnum = GeofenceActionEnum.log_only
    exit_action: GeofenceActionEnum = GeofenceActionEnum.log_only
    notify_on_entry: bool = False
    notify_on_exit: bool = False
    notification_recipients: Optional[List[str]] = None

    # Schedule
    active_start_time: Optional[str] = None
    active_end_time: Optional[str] = None
    active_days: Optional[List[int]] = None


class GeofenceUpdate(BaseModel):
    """Update an existing geofence"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    center_latitude: Optional[float] = None
    center_longitude: Optional[float] = None
    radius_meters: Optional[float] = None
    polygon_coordinates: Optional[List[List[float]]] = None
    entry_action: Optional[GeofenceActionEnum] = None
    exit_action: Optional[GeofenceActionEnum] = None
    notify_on_entry: Optional[bool] = None
    notify_on_exit: Optional[bool] = None
    notification_recipients: Optional[List[str]] = None
    active_start_time: Optional[str] = None
    active_end_time: Optional[str] = None
    active_days: Optional[List[int]] = None


class GeofenceResponse(BaseModel):
    """Geofence response"""

    id: int
    name: str
    description: Optional[str] = None
    geofence_type: str
    is_active: bool
    center_latitude: Optional[float] = None
    center_longitude: Optional[float] = None
    radius_meters: Optional[float] = None
    polygon_coordinates: Optional[List[List[float]]] = None
    customer_id: Optional[str] = None
    work_order_id: Optional[str] = None
    entry_action: str
    exit_action: str
    notify_on_entry: bool
    notify_on_exit: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GeofenceEventResponse(BaseModel):
    """Geofence event log entry"""

    id: int
    geofence_id: int
    geofence_name: str
    technician_id: str
    technician_name: str
    event_type: str
    latitude: float
    longitude: float
    action_triggered: Optional[str] = None
    action_result: Optional[str] = None
    occurred_at: datetime

    class Config:
        from_attributes = True


# ==================== Customer Tracking Links ====================


class TrackingLinkCreate(BaseModel):
    """Create a customer tracking link"""

    work_order_id: str
    show_technician_name: bool = True
    show_technician_photo: bool = True
    show_live_map: bool = True
    show_eta: bool = True
    expires_hours: int = Field(default=24, ge=1, le=72)


class TrackingLinkResponse(BaseModel):
    """Tracking link response (for internal use)"""

    id: int
    token: str
    tracking_url: str
    work_order_id: str
    customer_id: str
    technician_id: str
    status: str
    expires_at: datetime
    view_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class PublicTrackingInfo(BaseModel):
    """Public tracking information for customers"""

    work_order_id: str
    service_type: str
    scheduled_date: str

    # Technician info (if enabled)
    technician_name: Optional[str] = None
    technician_photo_url: Optional[str] = None

    # Location and ETA (if enabled)
    technician_latitude: Optional[float] = None
    technician_longitude: Optional[float] = None
    destination_latitude: float
    destination_longitude: float

    # ETA details
    eta_minutes: Optional[int] = None
    eta_arrival_time: Optional[str] = None
    distance_miles: Optional[float] = None

    # Status
    status: str  # scheduled, en_route, arriving_soon, arrived, in_progress, completed
    status_message: str
    last_updated: datetime


# ==================== ETA Calculations ====================


class ETARequest(BaseModel):
    """Request ETA calculation"""

    work_order_id: str
    recalculate: bool = False


class ETAResponse(BaseModel):
    """ETA calculation response"""

    work_order_id: str
    technician_id: str
    technician_name: str

    # Current positions
    technician_latitude: float
    technician_longitude: float
    destination_latitude: float
    destination_longitude: float

    # Estimates
    distance_miles: float
    duration_minutes: int
    traffic_factor: float
    adjusted_duration_minutes: int
    estimated_arrival: datetime

    # Confidence
    confidence: float
    calculation_source: str
    calculated_at: datetime

    class Config:
        from_attributes = True


class ETANotification(BaseModel):
    """ETA notification to send to customer"""

    work_order_id: str
    customer_id: str
    customer_phone: str
    customer_email: Optional[str] = None
    technician_name: str
    eta_minutes: int
    tracking_url: str
    message_template: str = "standard"


# ==================== GPS Config ====================


class GPSConfigUpdate(BaseModel):
    """Update GPS tracking configuration"""

    active_interval: Optional[int] = Field(None, ge=10, le=300)
    idle_interval: Optional[int] = Field(None, ge=60, le=3600)
    background_interval: Optional[int] = Field(None, ge=60, le=7200)
    tracking_enabled: Optional[bool] = None
    geofencing_enabled: Optional[bool] = None
    auto_clockin_enabled: Optional[bool] = None
    customer_tracking_enabled: Optional[bool] = None
    high_accuracy_mode: Optional[bool] = None
    battery_saver_threshold: Optional[int] = Field(None, ge=5, le=50)
    track_during_breaks: Optional[bool] = None
    track_after_hours: Optional[bool] = None
    work_hours_start: Optional[str] = None
    work_hours_end: Optional[str] = None
    history_retention_days: Optional[int] = Field(None, ge=7, le=365)


class GPSConfigResponse(BaseModel):
    """GPS configuration response"""

    id: int
    technician_id: Optional[str] = None
    active_interval: int
    idle_interval: int
    background_interval: int
    tracking_enabled: bool
    geofencing_enabled: bool
    auto_clockin_enabled: bool
    customer_tracking_enabled: bool
    high_accuracy_mode: bool
    battery_saver_threshold: int
    track_during_breaks: bool
    track_after_hours: bool
    work_hours_start: str
    work_hours_end: str
    history_retention_days: int
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Dispatch Map ====================


class DispatchMapTechnician(BaseModel):
    """Technician info for dispatch map"""

    id: str
    name: str
    latitude: float
    longitude: float
    status: str
    current_work_order_id: Optional[str] = None
    current_job_address: Optional[str] = None
    battery_level: Optional[int] = None
    speed: Optional[float] = None
    last_updated: datetime
    is_stale: bool  # True if location is > 5 min old


class DispatchMapWorkOrder(BaseModel):
    """Work order info for dispatch map"""

    id: str
    customer_name: str
    address: str
    latitude: float
    longitude: float
    status: str
    scheduled_time: Optional[datetime] = None
    assigned_technician_id: Optional[str] = None
    assigned_technician_name: Optional[str] = None
    service_type: str
    priority: str


class DispatchMapData(BaseModel):
    """Complete dispatch map data"""

    technicians: List[DispatchMapTechnician]
    work_orders: List[DispatchMapWorkOrder]
    geofences: List[GeofenceResponse]
    center_latitude: float
    center_longitude: float
    zoom_level: int
    last_refresh: datetime
