"""
GPS Tracking Models
Real-time technician location tracking, geofencing, and customer tracking links
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON, Index, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum
from datetime import datetime
import secrets


class GeofenceType(str, enum.Enum):
    """Types of geofences"""

    CUSTOMER_SITE = "customer_site"
    OFFICE = "office"
    WAREHOUSE = "warehouse"
    SERVICE_AREA = "service_area"
    EXCLUSION_ZONE = "exclusion_zone"


class GeofenceAction(str, enum.Enum):
    """Actions to trigger on geofence entry/exit"""

    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"
    NOTIFY_DISPATCH = "notify_dispatch"
    NOTIFY_CUSTOMER = "notify_customer"
    START_JOB = "start_job"
    COMPLETE_JOB = "complete_job"
    LOG_ONLY = "log_only"


class TrackingLinkStatus(str, enum.Enum):
    """Status of customer tracking links"""

    ACTIVE = "active"
    EXPIRED = "expired"
    VIEWED = "viewed"
    COMPLETED = "completed"


class TechnicianLocation(Base):
    """
    Real-time GPS location for technicians
    Updated frequently from mobile app
    """

    __tablename__ = "technician_locations"

    id = Column(Integer, primary_key=True, index=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False, unique=True)

    # GPS coordinates
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=True)  # GPS accuracy in meters
    altitude = Column(Float, nullable=True)

    # Movement data
    speed = Column(Float, nullable=True)  # Speed in mph
    heading = Column(Float, nullable=True)  # Compass heading 0-360

    # Status
    is_online = Column(Boolean, default=True)
    battery_level = Column(Integer, nullable=True)  # Battery percentage

    # Timestamps
    captured_at = Column(DateTime, nullable=False)  # When the GPS was captured on device
    received_at = Column(DateTime, default=func.now())  # When server received it

    # Current context
    current_work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)
    current_status = Column(String(50), default="available")  # available, en_route, on_site, break

    # Relationships
    technician = relationship("Technician", backref="current_location")

    __table_args__ = (
        Index("idx_tech_location_tech_id", "technician_id"),
        Index("idx_tech_location_coords", "latitude", "longitude"),
    )


class LocationHistory(Base):
    """
    Historical GPS locations for route verification and analytics
    Stored at configurable intervals (e.g., every 30 seconds)
    """

    __tablename__ = "location_history"

    id = Column(Integer, primary_key=True, index=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)

    # GPS coordinates
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=True)

    # Movement data
    speed = Column(Float, nullable=True)
    heading = Column(Float, nullable=True)

    # Distance tracking
    distance_from_previous = Column(Float, nullable=True)  # Miles from last point
    cumulative_distance = Column(Float, nullable=True)  # Total trip distance

    # Metadata
    captured_at = Column(DateTime, nullable=False)
    status = Column(String(50), nullable=True)

    # Relationships
    technician = relationship("Technician")

    __table_args__ = (
        Index("idx_loc_history_tech_date", "technician_id", "captured_at"),
        Index("idx_loc_history_work_order", "work_order_id"),
    )


class Geofence(Base):
    """
    Geographic boundaries for automatic actions
    Supports circles (center + radius) and polygons
    """

    __tablename__ = "geofences"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Type and configuration
    geofence_type = Column(SQLEnum(GeofenceType), nullable=False)
    is_active = Column(Boolean, default=True)

    # Circle geofence (simple)
    center_latitude = Column(Float, nullable=True)
    center_longitude = Column(Float, nullable=True)
    radius_meters = Column(Float, nullable=True)  # Radius in meters

    # Polygon geofence (complex shapes)
    polygon_coordinates = Column(JSON, nullable=True)  # Array of [lat, lng] pairs

    # Associated entities
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)

    # Actions
    entry_action = Column(SQLEnum(GeofenceAction), default=GeofenceAction.LOG_ONLY)
    exit_action = Column(SQLEnum(GeofenceAction), default=GeofenceAction.LOG_ONLY)

    # Notification settings
    notify_on_entry = Column(Boolean, default=False)
    notify_on_exit = Column(Boolean, default=False)
    notification_recipients = Column(JSON, nullable=True)  # List of user IDs or emails

    # Timing
    active_start_time = Column(String(5), nullable=True)  # HH:MM format
    active_end_time = Column(String(5), nullable=True)
    active_days = Column(JSON, nullable=True)  # [0,1,2,3,4,5,6] for Sun-Sat

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", backref="geofences")
    events = relationship("GeofenceEvent", back_populates="geofence")

    __table_args__ = (
        Index("idx_geofence_coords", "center_latitude", "center_longitude"),
        Index("idx_geofence_customer", "customer_id"),
    )


class GeofenceEvent(Base):
    """
    Log of geofence entry/exit events
    """

    __tablename__ = "geofence_events"

    id = Column(Integer, primary_key=True, index=True)
    geofence_id = Column(Integer, ForeignKey("geofences.id"), nullable=False)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)

    # Event details
    event_type = Column(String(20), nullable=False)  # entry or exit
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # Action taken
    action_triggered = Column(SQLEnum(GeofenceAction), nullable=True)
    action_result = Column(String(50), nullable=True)  # success, failed, skipped
    action_details = Column(JSON, nullable=True)

    # Timestamp
    occurred_at = Column(DateTime, default=func.now())

    # Relationships
    geofence = relationship("Geofence", back_populates="events")
    technician = relationship("Technician")

    __table_args__ = (Index("idx_geofence_event_tech", "technician_id", "occurred_at"),)


class CustomerTrackingLink(Base):
    """
    Public tracking links for customers to track technician ETA
    Similar to Uber/DoorDash tracking experience
    """

    __tablename__ = "customer_tracking_links"

    id = Column(Integer, primary_key=True, index=True)

    # Unique token for public URL
    token = Column(String(64), unique=True, nullable=False, index=True)

    # Associated entities
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)

    # Status
    status = Column(SQLEnum(TrackingLinkStatus), default=TrackingLinkStatus.ACTIVE)

    # Display settings
    show_technician_name = Column(Boolean, default=True)
    show_technician_photo = Column(Boolean, default=True)
    show_live_map = Column(Boolean, default=True)
    show_eta = Column(Boolean, default=True)

    # Expiration
    expires_at = Column(DateTime, nullable=False)

    # Analytics
    view_count = Column(Integer, default=0)
    first_viewed_at = Column(DateTime, nullable=True)
    last_viewed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())

    # Relationships
    work_order = relationship("WorkOrder", backref="tracking_links")
    customer = relationship("Customer")
    technician = relationship("Technician")

    @classmethod
    def generate_token(cls) -> str:
        """Generate a secure random token for tracking URLs"""
        return secrets.token_urlsafe(32)

    __table_args__ = (
        Index("idx_tracking_link_work_order", "work_order_id"),
        Index("idx_tracking_link_expires", "expires_at"),
    )


class ETACalculation(Base):
    """
    Cached ETA calculations for work orders
    Updated as technician moves
    """

    __tablename__ = "eta_calculations"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False, unique=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)

    # Origin (technician location)
    origin_latitude = Column(Float, nullable=False)
    origin_longitude = Column(Float, nullable=False)

    # Destination (customer location)
    destination_latitude = Column(Float, nullable=False)
    destination_longitude = Column(Float, nullable=False)

    # Distance and time estimates
    distance_miles = Column(Float, nullable=False)
    duration_minutes = Column(Integer, nullable=False)

    # Traffic adjustment
    traffic_factor = Column(Float, default=1.0)  # 1.0 = normal, 1.5 = 50% longer
    adjusted_duration_minutes = Column(Integer, nullable=False)

    # Calculated ETA
    estimated_arrival = Column(DateTime, nullable=False)

    # Confidence and source
    confidence = Column(Float, default=0.9)  # 0-1 confidence score
    calculation_source = Column(String(50), default="internal")  # internal, google_maps, etc

    # Timestamps
    calculated_at = Column(DateTime, default=func.now())

    # Relationships
    work_order = relationship("WorkOrder", backref="eta_calculation")
    technician = relationship("Technician")

    __table_args__ = (Index("idx_eta_work_order", "work_order_id"),)


class GPSTrackingConfig(Base):
    """
    Configuration for GPS tracking per technician or global
    """

    __tablename__ = "gps_tracking_config"

    id = Column(Integer, primary_key=True, index=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True, unique=True)  # NULL = global config

    # Tracking intervals (in seconds)
    active_interval = Column(Integer, default=30)  # When en route or on job
    idle_interval = Column(Integer, default=300)  # When idle/available
    background_interval = Column(Integer, default=600)  # Background tracking

    # Features
    tracking_enabled = Column(Boolean, default=True)
    geofencing_enabled = Column(Boolean, default=True)
    auto_clockin_enabled = Column(Boolean, default=True)
    customer_tracking_enabled = Column(Boolean, default=True)

    # Battery optimization
    high_accuracy_mode = Column(Boolean, default=True)
    battery_saver_threshold = Column(Integer, default=20)  # Switch to low power below this %

    # Privacy
    track_during_breaks = Column(Boolean, default=False)
    track_after_hours = Column(Boolean, default=False)
    work_hours_start = Column(String(5), default="07:00")
    work_hours_end = Column(String(5), default="18:00")

    # Data retention
    history_retention_days = Column(Integer, default=90)

    # Timestamps
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    technician = relationship("Technician", backref="gps_config")
