"""
Microsoft 365 Forms Sync Service

Reads Microsoft Forms inspection responses from a SharePoint Excel workbook
and creates real_estate_inspection work orders in the CRM.
"""

import logging
import uuid
from datetime import datetime, date as date_type

from sqlalchemy import select, and_

from app.services.ms365_base import MS365BaseService
from app.database import async_session_maker
from app.models.work_order import WorkOrder

logger = logging.getLogger(__name__)

# SharePoint site hostname and path
SP_SITE_HOST = "macseptic.sharepoint.com"
SP_SITE_PATH = "/sites/Operations"
WORKBOOK_NAME = "Septic Inspection Form.xlsx"

# Column mapping — zero-indexed positions for each field in the Excel row
COL = {
    "location": 0,
    "technician": 1,
    "who_present": 2,
    "date": 3,
    "time": 4,
    "weather": 5,
    "last_precipitation": 6,
    "client_name": 7,
    "client_address": 8,
    "client_phone": 9,
    "client_email": 10,
    "last_service": 11,
    "tank_location": 12,
    "tank_depth": 13,
    "system_type": 14,
    "system_size": 15,
    "system_age": 16,
    "flow_type": 17,
    "tank_good_condition": 18,
    "tank_visible_damage": 19,
    "drain_field_leaching": 20,
    "drain_field_super_saturation": 21,
    "system_functioning": 22,
    "additional_info": 23,
}


def _safe_get(row: list, index: int) -> str:
    """Safely get a value from a row by index, returning empty string if missing."""
    if index < len(row):
        val = row[index]
        if val is None:
            return ""
        return str(val).strip()
    return ""


def _parse_date(date_str: str) -> date_type | None:
    """Try parsing a date string from Forms (various formats)."""
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    # Try Excel serial date number
    try:
        serial = float(date_str)
        if 40000 < serial < 60000:
            from datetime import timedelta
            return (datetime(1899, 12, 30) + timedelta(days=int(serial))).date()
    except (ValueError, TypeError):
        pass
    return None


def _row_to_inspection_data(row: list) -> dict:
    """Map a spreadsheet row to our inspection checklist structure."""
    g = lambda key: _safe_get(row, COL[key])

    return {
        "location": g("location"),
        "technician": g("technician"),
        "who_present": g("who_present"),
        "date_of_inspection": g("date"),
        "time_of_inspection": g("time"),
        "weather": {
            "conditions": g("weather"),
            "last_precipitation": g("last_precipitation"),
        },
        "client": {
            "name": g("client_name"),
            "address": g("client_address"),
            "phone": g("client_phone"),
            "email": g("client_email"),
        },
        "service_history": {
            "last_cleaning": g("last_service"),
        },
        "system": {
            "tank_location": g("tank_location"),
            "tank_depth": g("tank_depth"),
            "system_type": g("system_type"),
            "system_size": g("system_size"),
            "system_age": g("system_age"),
            "flow_type": g("flow_type"),
        },
        "findings": {
            "tank_good_condition": g("tank_good_condition"),
            "tank_visible_damage": g("tank_visible_damage"),
            "drain_field_leaching": g("drain_field_leaching"),
            "drain_field_super_saturation": g("drain_field_super_saturation"),
            "system_functioning": g("system_functioning"),
        },
        "additional_info": g("additional_info"),
    }


async def _generate_wo_number(db) -> str:
    """Generate next work order number."""
    from sqlalchemy import func as sa_func
    result = await db.execute(
        select(sa_func.max(WorkOrder.work_order_number))
    )
    last_number = result.scalar()
    if last_number and last_number.startswith("WO-"):
        try:
            num = int(last_number.replace("WO-", "")) + 1
        except ValueError:
            num = 1
    else:
        num = 1
    return f"WO-{num:06d}"


class MS365FormsSyncService(MS365BaseService):
    """Sync inspection form responses from SharePoint Excel workbook."""

    _site_id: str | None = None
    _drive_item_id: str | None = None

    @classmethod
    async def _get_site_id(cls) -> str:
        """Look up the Operations SharePoint site ID."""
        if cls._site_id:
            return cls._site_id
        data = await cls.graph_get(f"/sites/{SP_SITE_HOST}:{SP_SITE_PATH}")
        cls._site_id = data["id"]
        logger.info("Resolved SharePoint site ID: %s", cls._site_id)
        return cls._site_id

    @classmethod
    async def _get_drive_item_id(cls, site_id: str) -> str:
        """Find the Excel workbook drive item ID."""
        if cls._drive_item_id:
            return cls._drive_item_id
        data = await cls.graph_get(
            f"/sites/{site_id}/drive/root:/{WORKBOOK_NAME}"
        )
        cls._drive_item_id = data["id"]
        logger.info("Resolved workbook item ID: %s", cls._drive_item_id)
        return cls._drive_item_id

    @classmethod
    async def _get_worksheet_name(cls, site_id: str, item_id: str) -> str:
        """List worksheets and return the first one's name."""
        data = await cls.graph_get(
            f"/sites/{site_id}/drive/items/{item_id}/workbook/worksheets"
        )
        worksheets = data.get("value", [])
        if not worksheets:
            raise RuntimeError("No worksheets found in workbook")
        name = worksheets[0]["name"]
        logger.info("Using worksheet: %s", name)
        return name

    @classmethod
    async def _read_rows(cls, site_id: str, item_id: str, sheet_name: str) -> list[list]:
        """Read all rows from the used range of the worksheet."""
        import urllib.parse
        encoded_sheet = urllib.parse.quote(sheet_name, safe="")
        data = await cls.graph_get(
            f"/sites/{site_id}/drive/items/{item_id}/workbook/worksheets/{encoded_sheet}/usedRange"
        )
        rows = data.get("values", [])
        # Skip header row (first row is column headers)
        if len(rows) > 1:
            return rows[1:]
        return []

    @classmethod
    async def sync_inspection_forms(cls) -> dict:
        """
        Pull inspection form responses from SharePoint and create work orders.

        Returns: {"synced": N, "skipped": N, "errors": []}
        """
        if not cls.is_configured():
            return {"synced": 0, "skipped": 0, "errors": ["MS365 not configured"]}

        result = {"synced": 0, "skipped": 0, "errors": []}

        try:
            site_id = await cls._get_site_id()
            item_id = await cls._get_drive_item_id(site_id)
            sheet_name = await cls._get_worksheet_name(site_id, item_id)
            rows = await cls._read_rows(site_id, item_id, sheet_name)

            if not rows:
                logger.info("Forms sync: no data rows found")
                return result

            logger.info("Forms sync: processing %d rows", len(rows))

            async with async_session_maker() as db:
                for i, row in enumerate(rows):
                    try:
                        address = _safe_get(row, COL["client_address"])
                        date_str = _safe_get(row, COL["date"])
                        scheduled_date = _parse_date(date_str)

                        if not address:
                            result["skipped"] += 1
                            continue

                        # Check for duplicate — same address + date + job type
                        dup_query = select(WorkOrder.id).where(
                            and_(
                                WorkOrder.service_address_line1 == address,
                                WorkOrder.job_type == "real_estate_inspection",
                            )
                        )
                        if scheduled_date:
                            dup_query = dup_query.where(
                                WorkOrder.scheduled_date == scheduled_date
                            )

                        existing = await db.execute(dup_query)
                        if existing.scalar_one_or_none():
                            result["skipped"] += 1
                            continue

                        # Build inspection data
                        inspection_data = _row_to_inspection_data(row)

                        # Parse client name into first/last
                        client_name = _safe_get(row, COL["client_name"])
                        name_parts = client_name.split(None, 1)
                        client_first = name_parts[0] if name_parts else ""
                        client_last = name_parts[1] if len(name_parts) > 1 else ""

                        # Determine system type
                        system_type_raw = _safe_get(row, COL["system_type"]).lower()
                        system_type = "aerobic" if "aerobic" in system_type_raw else "conventional"

                        # Determine technician name
                        technician_name = _safe_get(row, COL["technician"])

                        wo_number = await _generate_wo_number(db)

                        wo = WorkOrder(
                            id=uuid.uuid4(),
                            work_order_number=wo_number,
                            job_type="real_estate_inspection",
                            status="completed",
                            system_type=system_type,
                            scheduled_date=scheduled_date,
                            service_address_line1=address,
                            assigned_technician=technician_name,
                            notes="Imported from MS Forms inspection form",
                            source="import",
                            checklist={
                                "inspection": inspection_data,
                                "forms_import": True,
                            },
                        )
                        db.add(wo)
                        await db.flush()  # Ensure WO number doesn't collide
                        result["synced"] += 1
                        logger.info(
                            "Forms sync: created WO %s for %s on %s",
                            wo_number, address, scheduled_date,
                        )

                    except Exception as e:
                        msg = f"Row {i + 2}: {e}"
                        logger.error("Forms sync row error: %s", msg)
                        result["errors"].append(msg)

                await db.commit()

        except Exception as e:
            msg = f"Forms sync error: {e}"
            logger.error(msg)
            result["errors"].append(msg)

        logger.info(
            "Forms sync complete: synced=%d, skipped=%d, errors=%d",
            result["synced"], result["skipped"], len(result["errors"]),
        )
        return result
