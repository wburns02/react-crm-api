"""
GPS Tracking Service
Handles location updates, ETA calculations, geofencing, and customer tracking
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import math
import secrets

from app.models.gps_tracking import (
    TechnicianLocation, LocationHistory, Geofence, GeofenceEvent,
    CustomerTrackingLink, ETACalculation, GPSTrackingConfig,
    GeofenceType, GeofenceAction, TrackingLinkStatus
)
from app.schemas.gps_tracking import (
    LocationUpdate, TechnicianLocationResponse, LocationHistoryPoint,
    ETAResponse, PublicTrackingInfo, DispatchMapTechnician, DispatchMapWorkOrder
)


class GPSTrackingService:
    """Service for GPS tracking operations"""

    # Earth radius in miles for distance calculations
    EARTH_RADIUS_MILES = 3959

    # Default speeds for ETA estimation (mph)
    DEFAULT_CITY_SPEED = 25
    DEFAULT_HIGHWAY_SPEED = 55
    DEFAULT_RURAL_SPEED = 45

    # Stale location threshold (minutes)
    STALE_THRESHOLD_MINUTES = 5

    def __init__(self, db: Session):
        self.db = db

    # ==================== Location Updates ====================

    def update_technician_location(
        self,
        technician_id: int,
        location: LocationUpdate
    ) -> TechnicianLocationResponse:
        """
        Update a technician's current location and save to history
        """
        # Get or create current location record
        current = self.db.query(TechnicianLocation).filter(
            TechnicianLocation.technician_id == technician_id
        ).first()

        if current:
            # Calculate distance from previous location
            prev_lat, prev_lng = current.latitude, current.longitude
            distance = self._calculate_distance(
                prev_lat, prev_lng,
                location.latitude, location.longitude
            )

            # Update existing record
            current.latitude = location.latitude
            current.longitude = location.longitude
            current.accuracy = location.accuracy
            current.altitude = location.altitude
            current.speed = location.speed
            current.heading = location.heading
            current.battery_level = location.battery_level
            current.captured_at = location.captured_at
            current.received_at = datetime.utcnow()
            current.is_online = True
            current.current_status = location.current_status or "available"
            current.current_work_order_id = location.work_order_id
        else:
            # Create new location record
            distance = 0
            current = TechnicianLocation(
                technician_id=technician_id,
                latitude=location.latitude,
                longitude=location.longitude,
                accuracy=location.accuracy,
                altitude=location.altitude,
                speed=location.speed,
                heading=location.heading,
                battery_level=location.battery_level,
                captured_at=location.captured_at,
                received_at=datetime.utcnow(),
                is_online=True,
                current_status=location.current_status or "available",
                current_work_order_id=location.work_order_id
            )
            self.db.add(current)

        # Save to history
        self._save_location_history(technician_id, location, distance)

        # Check geofences
        geofence_events = self._check_geofences(technician_id, location)

        # Update ETA if on a job
        if location.work_order_id:
            self._update_eta_for_work_order(location.work_order_id, technician_id)

        self.db.commit()

        # Get technician name for response
        from app.models.technician import Technician
        tech = self.db.query(Technician).filter(Technician.id == technician_id).first()
        tech_name = f"{tech.first_name} {tech.last_name}" if tech else "Unknown"

        return TechnicianLocationResponse(
            technician_id=technician_id,
            technician_name=tech_name,
            latitude=current.latitude,
            longitude=current.longitude,
            accuracy=current.accuracy,
            speed=current.speed,
            heading=current.heading,
            is_online=current.is_online,
            battery_level=current.battery_level,
            current_status=current.current_status,
            current_work_order_id=current.current_work_order_id,
            captured_at=current.captured_at,
            received_at=current.received_at,
            minutes_since_update=0
        )

    def _save_location_history(
        self,
        technician_id: int,
        location: LocationUpdate,
        distance_from_prev: float
    ):
        """Save location to history table"""
        # Get cumulative distance for today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        last_history = self.db.query(LocationHistory).filter(
            and_(
                LocationHistory.technician_id == technician_id,
                LocationHistory.captured_at >= today_start
            )
        ).order_by(LocationHistory.captured_at.desc()).first()

        cumulative = (last_history.cumulative_distance or 0) + distance_from_prev if last_history else distance_from_prev

        history = LocationHistory(
            technician_id=technician_id,
            work_order_id=location.work_order_id,
            latitude=location.latitude,
            longitude=location.longitude,
            accuracy=location.accuracy,
            speed=location.speed,
            heading=location.heading,
            distance_from_previous=distance_from_prev,
            cumulative_distance=cumulative,
            captured_at=location.captured_at,
            status=location.current_status
        )
        self.db.add(history)

    def get_technician_location(
        self,
        technician_id: int
    ) -> Optional[TechnicianLocationResponse]:
        """Get current location for a technician"""
        location = self.db.query(TechnicianLocation).filter(
            TechnicianLocation.technician_id == technician_id
        ).first()

        if not location:
            return None

        from app.models.technician import Technician
        tech = self.db.query(Technician).filter(Technician.id == technician_id).first()
        tech_name = f"{tech.first_name} {tech.last_name}" if tech else "Unknown"

        minutes_since = int((datetime.utcnow() - location.captured_at).total_seconds() / 60)

        return TechnicianLocationResponse(
            technician_id=technician_id,
            technician_name=tech_name,
            latitude=location.latitude,
            longitude=location.longitude,
            accuracy=location.accuracy,
            speed=location.speed,
            heading=location.heading,
            is_online=location.is_online and minutes_since < self.STALE_THRESHOLD_MINUTES,
            battery_level=location.battery_level,
            current_status=location.current_status,
            current_work_order_id=location.current_work_order_id,
            captured_at=location.captured_at,
            received_at=location.received_at,
            minutes_since_update=minutes_since
        )

    def get_all_technician_locations(self) -> Dict:
        """Get all technician locations for dispatch map"""
        locations = self.db.query(TechnicianLocation).all()

        from app.models.technician import Technician
        technicians = []
        online_count = 0
        offline_count = 0

        for loc in locations:
            tech = self.db.query(Technician).filter(Technician.id == loc.technician_id).first()
            if not tech:
                continue

            minutes_since = int((datetime.utcnow() - loc.captured_at).total_seconds() / 60)
            is_online = loc.is_online and minutes_since < self.STALE_THRESHOLD_MINUTES

            if is_online:
                online_count += 1
            else:
                offline_count += 1

            technicians.append(TechnicianLocationResponse(
                technician_id=loc.technician_id,
                technician_name=f"{tech.first_name} {tech.last_name}",
                latitude=loc.latitude,
                longitude=loc.longitude,
                accuracy=loc.accuracy,
                speed=loc.speed,
                heading=loc.heading,
                is_online=is_online,
                battery_level=loc.battery_level,
                current_status=loc.current_status,
                current_work_order_id=loc.current_work_order_id,
                captured_at=loc.captured_at,
                received_at=loc.received_at,
                minutes_since_update=minutes_since
            ))

        return {
            "technicians": technicians,
            "total_online": online_count,
            "total_offline": offline_count,
            "last_refresh": datetime.utcnow()
        }

    # ==================== Location History ====================

    def get_location_history(
        self,
        technician_id: int,
        date: Optional[datetime] = None,
        work_order_id: Optional[int] = None
    ) -> Dict:
        """Get location history for a technician"""
        if date is None:
            date = datetime.utcnow()

        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        query = self.db.query(LocationHistory).filter(
            and_(
                LocationHistory.technician_id == technician_id,
                LocationHistory.captured_at >= start_of_day,
                LocationHistory.captured_at < end_of_day
            )
        )

        if work_order_id:
            query = query.filter(LocationHistory.work_order_id == work_order_id)

        history = query.order_by(LocationHistory.captured_at).all()

        if not history:
            return {
                "technician_id": technician_id,
                "technician_name": "",
                "date": date.strftime("%Y-%m-%d"),
                "points": [],
                "total_distance_miles": 0,
                "total_duration_minutes": 0,
                "average_speed_mph": None
            }

        from app.models.technician import Technician
        tech = self.db.query(Technician).filter(Technician.id == technician_id).first()
        tech_name = f"{tech.first_name} {tech.last_name}" if tech else "Unknown"

        points = [
            LocationHistoryPoint(
                latitude=h.latitude,
                longitude=h.longitude,
                accuracy=h.accuracy,
                speed=h.speed,
                heading=h.heading,
                captured_at=h.captured_at,
                status=h.status,
                distance_from_previous=h.distance_from_previous
            )
            for h in history
        ]

        total_distance = sum(p.distance_from_previous or 0 for p in points)
        total_duration = int((history[-1].captured_at - history[0].captured_at).total_seconds() / 60)
        avg_speed = sum(p.speed or 0 for p in points if p.speed) / len([p for p in points if p.speed]) if any(p.speed for p in points) else None

        return {
            "technician_id": technician_id,
            "technician_name": tech_name,
            "date": date.strftime("%Y-%m-%d"),
            "points": points,
            "total_distance_miles": round(total_distance, 2),
            "total_duration_minutes": total_duration,
            "average_speed_mph": round(avg_speed, 1) if avg_speed else None
        }

    # ==================== ETA Calculations ====================

    def calculate_eta(
        self,
        work_order_id: int,
        force_recalculate: bool = False
    ) -> Optional[ETAResponse]:
        """
        Calculate ETA for a work order based on technician's current location
        """
        from app.models.work_order import WorkOrder
        from app.models.technician import Technician
        from app.models.customer import Customer

        # Get work order with customer
        work_order = self.db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
        if not work_order or not work_order.technician_id:
            return None

        # Check for cached ETA
        if not force_recalculate:
            cached = self.db.query(ETACalculation).filter(
                ETACalculation.work_order_id == work_order_id
            ).first()
            if cached and (datetime.utcnow() - cached.calculated_at).total_seconds() < 60:
                # Return cached if less than 1 minute old
                tech = self.db.query(Technician).filter(Technician.id == cached.technician_id).first()
                return ETAResponse(
                    work_order_id=work_order_id,
                    technician_id=cached.technician_id,
                    technician_name=f"{tech.first_name} {tech.last_name}" if tech else "Unknown",
                    technician_latitude=cached.origin_latitude,
                    technician_longitude=cached.origin_longitude,
                    destination_latitude=cached.destination_latitude,
                    destination_longitude=cached.destination_longitude,
                    distance_miles=cached.distance_miles,
                    duration_minutes=cached.duration_minutes,
                    traffic_factor=cached.traffic_factor,
                    adjusted_duration_minutes=cached.adjusted_duration_minutes,
                    estimated_arrival=cached.estimated_arrival,
                    confidence=cached.confidence,
                    calculation_source=cached.calculation_source,
                    calculated_at=cached.calculated_at
                )

        # Get technician's current location
        tech_location = self.db.query(TechnicianLocation).filter(
            TechnicianLocation.technician_id == work_order.technician_id
        ).first()

        if not tech_location:
            return None

        # Get customer location
        customer = self.db.query(Customer).filter(Customer.id == work_order.customer_id).first()
        if not customer:
            return None

        # Use customer address for destination (geocoded)
        dest_lat = customer.latitude if hasattr(customer, 'latitude') and customer.latitude else 32.0
        dest_lng = customer.longitude if hasattr(customer, 'longitude') and customer.longitude else -96.0

        # Calculate distance
        distance_miles = self._calculate_distance(
            tech_location.latitude, tech_location.longitude,
            dest_lat, dest_lng
        )

        # Estimate duration based on distance and time of day
        base_duration = self._estimate_duration(distance_miles, tech_location.speed)
        traffic_factor = self._get_traffic_factor()
        adjusted_duration = int(base_duration * traffic_factor)

        # Calculate arrival time
        estimated_arrival = datetime.utcnow() + timedelta(minutes=adjusted_duration)

        # Get technician name
        tech = self.db.query(Technician).filter(Technician.id == work_order.technician_id).first()
        tech_name = f"{tech.first_name} {tech.last_name}" if tech else "Unknown"

        # Save/update ETA calculation
        existing = self.db.query(ETACalculation).filter(
            ETACalculation.work_order_id == work_order_id
        ).first()

        if existing:
            existing.origin_latitude = tech_location.latitude
            existing.origin_longitude = tech_location.longitude
            existing.destination_latitude = dest_lat
            existing.destination_longitude = dest_lng
            existing.distance_miles = distance_miles
            existing.duration_minutes = base_duration
            existing.traffic_factor = traffic_factor
            existing.adjusted_duration_minutes = adjusted_duration
            existing.estimated_arrival = estimated_arrival
            existing.calculated_at = datetime.utcnow()
        else:
            eta_calc = ETACalculation(
                work_order_id=work_order_id,
                technician_id=work_order.technician_id,
                origin_latitude=tech_location.latitude,
                origin_longitude=tech_location.longitude,
                destination_latitude=dest_lat,
                destination_longitude=dest_lng,
                distance_miles=distance_miles,
                duration_minutes=base_duration,
                traffic_factor=traffic_factor,
                adjusted_duration_minutes=adjusted_duration,
                estimated_arrival=estimated_arrival,
                confidence=0.85,
                calculation_source="internal"
            )
            self.db.add(eta_calc)

        self.db.commit()

        return ETAResponse(
            work_order_id=work_order_id,
            technician_id=work_order.technician_id,
            technician_name=tech_name,
            technician_latitude=tech_location.latitude,
            technician_longitude=tech_location.longitude,
            destination_latitude=dest_lat,
            destination_longitude=dest_lng,
            distance_miles=round(distance_miles, 2),
            duration_minutes=base_duration,
            traffic_factor=traffic_factor,
            adjusted_duration_minutes=adjusted_duration,
            estimated_arrival=estimated_arrival,
            confidence=0.85,
            calculation_source="internal",
            calculated_at=datetime.utcnow()
        )

    def _update_eta_for_work_order(self, work_order_id: int, technician_id: int):
        """Update ETA when technician location changes"""
        self.calculate_eta(work_order_id, force_recalculate=True)

    def _estimate_duration(self, distance_miles: float, current_speed: Optional[float]) -> int:
        """Estimate travel duration in minutes"""
        # Use current speed if available and reasonable
        if current_speed and 5 < current_speed < 80:
            estimated_speed = current_speed
        elif distance_miles < 5:
            estimated_speed = self.DEFAULT_CITY_SPEED
        elif distance_miles < 20:
            estimated_speed = self.DEFAULT_RURAL_SPEED
        else:
            estimated_speed = self.DEFAULT_HIGHWAY_SPEED

        duration_hours = distance_miles / estimated_speed
        return max(1, int(duration_hours * 60))

    def _get_traffic_factor(self) -> float:
        """
        Get traffic factor based on time of day
        1.0 = normal, 1.5 = 50% longer due to traffic
        """
        hour = datetime.utcnow().hour

        # Rush hour periods (adjusted for UTC - assuming Central Time)
        morning_rush = 13 <= hour <= 15  # 7-9 AM CT
        evening_rush = 22 <= hour <= 24 or 0 <= hour <= 1  # 4-7 PM CT

        if morning_rush or evening_rush:
            return 1.4
        elif 15 <= hour <= 22:  # Daytime
            return 1.1
        else:  # Night
            return 1.0

    # ==================== Geofencing ====================

    def _check_geofences(
        self,
        technician_id: int,
        location: LocationUpdate
    ) -> List[Dict]:
        """Check if technician has entered/exited any geofences"""
        events = []

        # Get active geofences
        geofences = self.db.query(Geofence).filter(Geofence.is_active == True).all()

        for geofence in geofences:
            is_inside = self._is_inside_geofence(
                location.latitude, location.longitude, geofence
            )

            # Get last event for this technician/geofence
            last_event = self.db.query(GeofenceEvent).filter(
                and_(
                    GeofenceEvent.geofence_id == geofence.id,
                    GeofenceEvent.technician_id == technician_id
                )
            ).order_by(GeofenceEvent.occurred_at.desc()).first()

            was_inside = last_event and last_event.event_type == "entry"

            # Detect entry
            if is_inside and not was_inside:
                event = self._create_geofence_event(
                    geofence, technician_id, location, "entry"
                )
                events.append(event)

            # Detect exit
            elif not is_inside and was_inside:
                event = self._create_geofence_event(
                    geofence, technician_id, location, "exit"
                )
                events.append(event)

        return events

    def _is_inside_geofence(
        self,
        lat: float,
        lng: float,
        geofence: Geofence
    ) -> bool:
        """Check if coordinates are inside a geofence"""
        if geofence.radius_meters:
            # Circle geofence
            distance_meters = self._calculate_distance(
                lat, lng,
                geofence.center_latitude, geofence.center_longitude
            ) * 1609.34  # Convert miles to meters

            return distance_meters <= geofence.radius_meters

        elif geofence.polygon_coordinates:
            # Polygon geofence (ray casting algorithm)
            return self._point_in_polygon(lat, lng, geofence.polygon_coordinates)

        return False

    def _point_in_polygon(
        self,
        lat: float,
        lng: float,
        polygon: List[List[float]]
    ) -> bool:
        """Ray casting algorithm to check if point is in polygon"""
        n = len(polygon)
        inside = False

        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]

            if ((yi > lng) != (yj > lng)) and (lat < (xj - xi) * (lng - yi) / (yj - yi) + xi):
                inside = not inside

            j = i

        return inside

    def _create_geofence_event(
        self,
        geofence: Geofence,
        technician_id: int,
        location: LocationUpdate,
        event_type: str
    ) -> Dict:
        """Create a geofence event and trigger actions"""
        action = geofence.entry_action if event_type == "entry" else geofence.exit_action
        action_result = "success"
        action_details = {}

        # Execute action
        if action == GeofenceAction.CLOCK_IN:
            action_details = self._auto_clock_in(technician_id, geofence)
        elif action == GeofenceAction.CLOCK_OUT:
            action_details = self._auto_clock_out(technician_id, geofence)
        elif action == GeofenceAction.NOTIFY_CUSTOMER:
            action_details = self._notify_customer_arrival(technician_id, geofence, location)
        elif action == GeofenceAction.START_JOB:
            action_details = self._auto_start_job(technician_id, geofence)

        # Create event record
        event = GeofenceEvent(
            geofence_id=geofence.id,
            technician_id=technician_id,
            work_order_id=location.work_order_id,
            event_type=event_type,
            latitude=location.latitude,
            longitude=location.longitude,
            action_triggered=action,
            action_result=action_result,
            action_details=action_details,
            occurred_at=datetime.utcnow()
        )
        self.db.add(event)

        return {
            "geofence_id": geofence.id,
            "geofence_name": geofence.name,
            "event_type": event_type,
            "action": action.value if action else None,
            "action_result": action_result
        }

    def _auto_clock_in(self, technician_id: int, geofence: Geofence) -> Dict:
        """Auto clock-in when entering office geofence"""
        # Implementation would integrate with time tracking system
        return {"action": "clock_in", "timestamp": datetime.utcnow().isoformat()}

    def _auto_clock_out(self, technician_id: int, geofence: Geofence) -> Dict:
        """Auto clock-out when leaving office geofence"""
        return {"action": "clock_out", "timestamp": datetime.utcnow().isoformat()}

    def _notify_customer_arrival(
        self,
        technician_id: int,
        geofence: Geofence,
        location: LocationUpdate
    ) -> Dict:
        """Notify customer that technician is arriving"""
        # Would integrate with notification system
        return {"notification_sent": True, "customer_id": geofence.customer_id}

    def _auto_start_job(self, technician_id: int, geofence: Geofence) -> Dict:
        """Auto-start job when entering customer geofence"""
        return {"job_started": True, "work_order_id": geofence.work_order_id}

    # ==================== Customer Tracking Links ====================

    def create_tracking_link(
        self,
        work_order_id: int,
        customer_id: int,
        technician_id: int,
        expires_hours: int = 24,
        show_technician_name: bool = True,
        show_technician_photo: bool = True,
        show_live_map: bool = True,
        show_eta: bool = True
    ) -> CustomerTrackingLink:
        """Create a customer tracking link for a work order"""
        # Deactivate any existing links for this work order
        self.db.query(CustomerTrackingLink).filter(
            and_(
                CustomerTrackingLink.work_order_id == work_order_id,
                CustomerTrackingLink.status == TrackingLinkStatus.ACTIVE
            )
        ).update({"status": TrackingLinkStatus.EXPIRED})

        token = CustomerTrackingLink.generate_token()
        expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

        link = CustomerTrackingLink(
            token=token,
            work_order_id=work_order_id,
            customer_id=customer_id,
            technician_id=technician_id,
            status=TrackingLinkStatus.ACTIVE,
            show_technician_name=show_technician_name,
            show_technician_photo=show_technician_photo,
            show_live_map=show_live_map,
            show_eta=show_eta,
            expires_at=expires_at
        )
        self.db.add(link)
        self.db.commit()

        return link

    def get_public_tracking_info(self, token: str) -> Optional[PublicTrackingInfo]:
        """Get tracking info for public tracking page"""
        link = self.db.query(CustomerTrackingLink).filter(
            CustomerTrackingLink.token == token
        ).first()

        if not link:
            return None

        # Check expiration
        if link.expires_at < datetime.utcnow():
            link.status = TrackingLinkStatus.EXPIRED
            self.db.commit()
            return None

        # Update view stats
        link.view_count += 1
        if not link.first_viewed_at:
            link.first_viewed_at = datetime.utcnow()
            link.status = TrackingLinkStatus.VIEWED
        link.last_viewed_at = datetime.utcnow()
        self.db.commit()

        # Get work order details
        from app.models.work_order import WorkOrder
        from app.models.technician import Technician
        from app.models.customer import Customer

        work_order = self.db.query(WorkOrder).filter(WorkOrder.id == link.work_order_id).first()
        technician = self.db.query(Technician).filter(Technician.id == link.technician_id).first()
        customer = self.db.query(Customer).filter(Customer.id == link.customer_id).first()

        if not work_order or not customer:
            return None

        # Get technician location if enabled
        tech_lat, tech_lng = None, None
        eta_minutes = None
        eta_arrival = None
        distance = None

        if link.show_live_map or link.show_eta:
            tech_location = self.db.query(TechnicianLocation).filter(
                TechnicianLocation.technician_id == link.technician_id
            ).first()

            if tech_location:
                if link.show_live_map:
                    tech_lat = tech_location.latitude
                    tech_lng = tech_location.longitude

                if link.show_eta:
                    eta = self.calculate_eta(link.work_order_id)
                    if eta:
                        eta_minutes = eta.adjusted_duration_minutes
                        eta_arrival = eta.estimated_arrival.strftime("%I:%M %p")
                        distance = eta.distance_miles

        # Determine status
        status, status_message = self._get_tracking_status(work_order, tech_location if link.show_live_map else None, eta_minutes)

        # Destination coordinates
        dest_lat = customer.latitude if hasattr(customer, 'latitude') and customer.latitude else 32.0
        dest_lng = customer.longitude if hasattr(customer, 'longitude') and customer.longitude else -96.0

        return PublicTrackingInfo(
            work_order_id=link.work_order_id,
            service_type=work_order.service_type or "Service",
            scheduled_date=work_order.scheduled_date.strftime("%B %d, %Y") if work_order.scheduled_date else "TBD",
            technician_name=f"{technician.first_name} {technician.last_name}" if link.show_technician_name and technician else None,
            technician_photo_url=technician.photo_url if link.show_technician_photo and technician and hasattr(technician, 'photo_url') else None,
            technician_latitude=tech_lat,
            technician_longitude=tech_lng,
            destination_latitude=dest_lat,
            destination_longitude=dest_lng,
            eta_minutes=eta_minutes,
            eta_arrival_time=eta_arrival,
            distance_miles=distance,
            status=status,
            status_message=status_message,
            last_updated=datetime.utcnow()
        )

    def _get_tracking_status(
        self,
        work_order,
        tech_location: Optional[TechnicianLocation],
        eta_minutes: Optional[int]
    ) -> Tuple[str, str]:
        """Determine tracking status and message"""
        wo_status = work_order.status if work_order else "scheduled"

        if wo_status == "completed":
            return "completed", "Service completed. Thank you!"
        elif wo_status == "in_progress":
            return "in_progress", "Your technician is currently working on your service."
        elif tech_location and tech_location.current_status == "en_route":
            if eta_minutes and eta_minutes <= 5:
                return "arriving_soon", f"Your technician is almost there! Arriving in about {eta_minutes} minutes."
            elif eta_minutes:
                return "en_route", f"Your technician is on the way. Estimated arrival in {eta_minutes} minutes."
            else:
                return "en_route", "Your technician is on the way."
        else:
            return "scheduled", "Your service is scheduled. We'll notify you when your technician is on the way."

    # ==================== Utility Methods ====================

    def _calculate_distance(
        self,
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float
    ) -> float:
        """
        Calculate distance between two coordinates using Haversine formula
        Returns distance in miles
        """
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)

        a = (
            math.sin(delta_lat / 2) ** 2 +
            math.cos(lat1_rad) * math.cos(lat2_rad) *
            math.sin(delta_lng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return self.EARTH_RADIUS_MILES * c


# ==================== Geofence CRUD Operations ====================

class GeofenceService:
    """Service for geofence management"""

    def __init__(self, db: Session):
        self.db = db

    def create_geofence(self, data: dict) -> Geofence:
        """Create a new geofence"""
        geofence = Geofence(**data)
        self.db.add(geofence)
        self.db.commit()
        self.db.refresh(geofence)
        return geofence

    def get_geofence(self, geofence_id: int) -> Optional[Geofence]:
        """Get a geofence by ID"""
        return self.db.query(Geofence).filter(Geofence.id == geofence_id).first()

    def get_all_geofences(
        self,
        geofence_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[Geofence]:
        """Get all geofences with optional filters"""
        query = self.db.query(Geofence)

        if geofence_type:
            query = query.filter(Geofence.geofence_type == geofence_type)
        if is_active is not None:
            query = query.filter(Geofence.is_active == is_active)

        return query.all()

    def update_geofence(self, geofence_id: int, data: dict) -> Optional[Geofence]:
        """Update a geofence"""
        geofence = self.get_geofence(geofence_id)
        if not geofence:
            return None

        for key, value in data.items():
            if value is not None:
                setattr(geofence, key, value)

        geofence.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(geofence)
        return geofence

    def delete_geofence(self, geofence_id: int) -> bool:
        """Delete a geofence"""
        geofence = self.get_geofence(geofence_id)
        if not geofence:
            return False

        self.db.delete(geofence)
        self.db.commit()
        return True

    def create_customer_geofence(
        self,
        customer_id: int,
        customer_name: str,
        latitude: float,
        longitude: float,
        radius_meters: float = 100
    ) -> Geofence:
        """Create a geofence for a customer site"""
        return self.create_geofence({
            "name": f"{customer_name} - Service Location",
            "geofence_type": GeofenceType.CUSTOMER_SITE,
            "center_latitude": latitude,
            "center_longitude": longitude,
            "radius_meters": radius_meters,
            "customer_id": customer_id,
            "entry_action": GeofenceAction.NOTIFY_CUSTOMER,
            "exit_action": GeofenceAction.LOG_ONLY,
            "notify_on_entry": True,
            "is_active": True
        })
