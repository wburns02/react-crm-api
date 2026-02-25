"""
Microsoft 365 Bookings Service

Manages Microsoft Bookings business, services, staff, and appointment sync.
Uses application-level permissions for reading appointments.
"""

import logging
from typing import Optional

from app.services.ms365_base import MS365BaseService
from app.config import settings

logger = logging.getLogger(__name__)


class MS365BookingsService(MS365BaseService):
    """Service for Microsoft Bookings integration."""

    @classmethod
    def is_configured(cls) -> bool:
        return cls.is_configured.__func__(cls) and bool(settings.MS365_BOOKING_BUSINESS_ID)

    @classmethod
    def _business_path(cls) -> str:
        return f"/solutions/bookingBusinesses/{settings.MS365_BOOKING_BUSINESS_ID}"

    # ── Read Operations (Application Permissions) ──

    @classmethod
    async def list_services(cls) -> list[dict]:
        """List all services defined in the Bookings business."""
        try:
            data = await cls.graph_get(f"{cls._business_path()}/services")
            return data.get("value", [])
        except Exception as e:
            logger.error("Failed to list Bookings services: %s", e)
            return []

    @classmethod
    async def list_staff(cls) -> list[dict]:
        """List all staff members in the Bookings business."""
        try:
            data = await cls.graph_get(f"{cls._business_path()}/staffMembers")
            return data.get("value", [])
        except Exception as e:
            logger.error("Failed to list Bookings staff: %s", e)
            return []

    @classmethod
    async def get_appointments(
        cls,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """Get appointments from Bookings.

        Args:
            start_date: ISO date string (e.g. "2026-02-25")
            end_date: ISO date string
        """
        try:
            path = f"{cls._business_path()}/appointments"
            params = []
            if start_date:
                params.append(f"start/dateTime ge '{start_date}T00:00:00Z'")
            if end_date:
                params.append(f"start/dateTime le '{end_date}T23:59:59Z'")
            if params:
                path += f"?$filter={' and '.join(params)}"
            data = await cls.graph_get(path)
            return data.get("value", [])
        except Exception as e:
            logger.error("Failed to get Bookings appointments: %s", e)
            return []

    @classmethod
    async def get_appointment(cls, appointment_id: str) -> Optional[dict]:
        """Get a single appointment by ID."""
        try:
            return await cls.graph_get(
                f"{cls._business_path()}/appointments/{appointment_id}"
            )
        except Exception as e:
            logger.error("Failed to get appointment %s: %s", appointment_id, e)
            return None

    @classmethod
    async def cancel_appointment(cls, appointment_id: str) -> bool:
        """Cancel an appointment in Bookings."""
        try:
            await cls.graph_post(
                f"{cls._business_path()}/appointments/{appointment_id}/cancel",
                json_data={"cancellationMessage": "Cancelled from CRM"},
            )
            return True
        except Exception as e:
            logger.error("Failed to cancel appointment %s: %s", appointment_id, e)
            return False

    # ── Business Setup (requires delegated permissions for full setup) ──

    @classmethod
    async def get_business(cls) -> Optional[dict]:
        """Get the configured Bookings business details."""
        try:
            return await cls.graph_get(cls._business_path())
        except Exception as e:
            logger.error("Failed to get Bookings business: %s", e)
            return None

    @classmethod
    async def get_booking_page_url(cls) -> Optional[str]:
        """Get the public booking page URL."""
        try:
            biz = await cls.get_business()
            if biz:
                return biz.get("publicUrl") or biz.get("webSiteUrl")
            return None
        except Exception:
            return None

    # ── Appointment Parsing Helpers ──

    @classmethod
    def parse_appointment_to_work_order_data(cls, appt: dict) -> dict:
        """Convert a Bookings appointment to work order creation data."""
        customers = appt.get("customers", [])
        customer_info = customers[0] if customers else {}

        start = appt.get("startDateTime", {})
        end = appt.get("endDateTime", {})
        start_dt = start.get("dateTime", "")
        end_dt = end.get("dateTime", "")

        # Parse date and time
        scheduled_date = start_dt[:10] if start_dt else None
        time_start = start_dt[11:16] if len(start_dt) > 16 else None
        time_end = end_dt[11:16] if len(end_dt) > 16 else None

        # Get service name for job type mapping
        service_name = appt.get("serviceName", "").lower()
        job_type = "pumping"  # default
        if "inspection" in service_name:
            job_type = "inspection"
        elif "repair" in service_name:
            job_type = "repair"
        elif "emergency" in service_name:
            job_type = "emergency"
        elif "grease" in service_name:
            job_type = "grease_trap"
        elif "maintenance" in service_name:
            job_type = "maintenance"

        return {
            "appointment_id": appt.get("id"),
            "customer_name": customer_info.get("name", ""),
            "customer_email": customer_info.get("emailAddress", ""),
            "customer_phone": customer_info.get("phone", ""),
            "service_address": appt.get("serviceLocation", {}).get("displayName", ""),
            "scheduled_date": scheduled_date,
            "time_start": time_start,
            "time_end": time_end,
            "job_type": job_type,
            "service_name": appt.get("serviceName", ""),
            "notes": appt.get("customerNotes", ""),
            "staff_member_ids": [s.get("staffId", "") for s in appt.get("staffMemberIds", [])],
            "duration_minutes": appt.get("duration"),
            "price": appt.get("price"),
            "status": appt.get("status", ""),  # booked, canceled, etc.
        }
