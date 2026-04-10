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

# Full SharePoint sharing URL for the workbook (from the browser URL)
# Used via Graph /shares/{encoded-url}/driveItem to resolve to drive item
WORKBOOK_SHARING_URL = (
    "https://macseptic.sharepoint.com/:x:/r/sites/Operations/_layouts/15/Doc.aspx"
    "?sourcedoc=%7BE1D76069-4BE7-4E58-AE62-6BB608929AA3%7D"
    "&file=Septic%20Inspection%20Form.xlsx"
)


def _encode_share_url(url: str) -> str:
    """Encode a URL for the Graph /shares/ endpoint.
    Format: u! + base64url(url) with padding removed.
    """
    import base64
    b64 = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
    return f"u!{b64}"

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
    _drive_id: str | None = None
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
    async def _get_drive_item_id(cls, site_id: str) -> tuple[str, str]:
        """Find the Excel workbook drive item ID.

        Tries multiple strategies:
        1. Search in the configured SharePoint drive (from settings)
        2. Search across all drives in the site
        3. Use the known source doc ID from the SharePoint URL directly
        4. Search the site via /search endpoint

        Returns: (drive_id, item_id)
        """
        if cls._drive_item_id and cls._drive_id:
            return (cls._drive_id, cls._drive_item_id)

        from app.config import settings

        # Strategy 1: Try the configured drive first
        configured_drive = getattr(settings, "MS365_SHAREPOINT_DRIVE_ID", None)
        if configured_drive:
            try:
                data = await cls.graph_get(
                    f"/drives/{configured_drive}/root:/{WORKBOOK_NAME}"
                )
                cls._drive_id = configured_drive
                cls._drive_item_id = data["id"]
                logger.info(
                    "Found workbook in configured drive: %s",
                    cls._drive_item_id,
                )
                return (cls._drive_id, cls._drive_item_id)
            except Exception as e:
                logger.info("Not in configured drive: %s", e)

        # Strategy 2: List all drives in the site and search each
        try:
            drives_data = await cls.graph_get(f"/sites/{site_id}/drives")
            drives = drives_data.get("value", [])
            logger.info("Site has %d drives", len(drives))
            for drive in drives:
                drive_id = drive["id"]
                drive_name = drive.get("name", "unknown")
                try:
                    data = await cls.graph_get(
                        f"/drives/{drive_id}/root:/{WORKBOOK_NAME}"
                    )
                    cls._drive_id = drive_id
                    cls._drive_item_id = data["id"]
                    logger.info(
                        "Found workbook in drive '%s': %s",
                        drive_name, cls._drive_item_id,
                    )
                    return (cls._drive_id, cls._drive_item_id)
                except Exception:
                    continue
        except Exception as e:
            logger.warning("Could not list site drives: %s", e)

        # Strategy 3: Use the known source doc GUID from the SharePoint URL
        # The URL contains sourcedoc={E1D76069-4BE7-4E58-AE62-6BB608929AA3}
        source_doc_id = "E1D76069-4BE7-4E58-AE62-6BB608929AA3"
        try:
            # Try to look up the file via site's items endpoint using the GUID
            data = await cls.graph_get(
                f"/sites/{site_id}/drive/items/{source_doc_id}"
            )
            cls._drive_id = data.get("parentReference", {}).get("driveId", "")
            cls._drive_item_id = data["id"]
            logger.info(
                "Found workbook via source doc GUID: drive=%s item=%s",
                cls._drive_id, cls._drive_item_id,
            )
            return (cls._drive_id, cls._drive_item_id)
        except Exception as e:
            logger.info("Source doc GUID lookup failed: %s", e)

        # Strategy 4: Search the site for the file by name
        try:
            import urllib.parse
            q = urllib.parse.quote("Septic Inspection Form")
            data = await cls.graph_get(
                f"/sites/{site_id}/drive/root/search(q='{q}')"
            )
            for item in data.get("value", []):
                if "Septic Inspection Form" in (item.get("name") or ""):
                    cls._drive_id = item.get("parentReference", {}).get("driveId", "")
                    cls._drive_item_id = item["id"]
                    logger.info(
                        "Found workbook via search: %s",
                        cls._drive_item_id,
                    )
                    return (cls._drive_id, cls._drive_item_id)
        except Exception as e:
            logger.warning("Site search failed: %s", e)

        # Strategy 5: Resolve via the /shares/{encoded-url}/driveItem endpoint
        # This works even without Sites.Read.All because the app just needs
        # permission to items shared with the sharing URL.
        try:
            encoded = _encode_share_url(WORKBOOK_SHARING_URL)
            data = await cls.graph_get(f"/shares/{encoded}/driveItem")
            parent_ref = data.get("parentReference", {})
            cls._drive_id = parent_ref.get("driveId", "")
            cls._drive_item_id = data["id"]
            logger.info(
                "Found workbook via /shares/ endpoint: drive=%s item=%s",
                cls._drive_id, cls._drive_item_id,
            )
            return (cls._drive_id, cls._drive_item_id)
        except Exception as e:
            logger.warning("Shares endpoint lookup failed: %s", e)

        raise RuntimeError(
            f"Could not find '{WORKBOOK_NAME}' in any drive of site {site_id}. "
            "Check Azure app permissions (Sites.Read.All or Files.Read.All)."
        )

    @classmethod
    async def _get_worksheet_name(cls, drive_id: str, item_id: str) -> str:
        """List worksheets and return the first one's name."""
        data = await cls.graph_get(
            f"/drives/{drive_id}/items/{item_id}/workbook/worksheets"
        )
        worksheets = data.get("value", [])
        if not worksheets:
            raise RuntimeError("No worksheets found in workbook")
        name = worksheets[0]["name"]
        logger.info("Using worksheet: %s", name)
        return name

    @classmethod
    async def _read_rows(cls, drive_id: str, item_id: str, sheet_name: str) -> list[list]:
        """Read all rows from the used range of the worksheet."""
        import urllib.parse
        encoded_sheet = urllib.parse.quote(sheet_name, safe="")
        data = await cls.graph_get(
            f"/drives/{drive_id}/items/{item_id}/workbook/worksheets/{encoded_sheet}/usedRange"
        )
        rows = data.get("values", [])
        # Skip header row (first row is column headers)
        if len(rows) > 1:
            return rows[1:]
        return []

    @classmethod
    async def _get_cached_rows(cls) -> list[list] | None:
        """Get form rows from the manual upload cache (if any)."""
        try:
            from app.services.cache_service import get_cache_service
            cache = get_cache_service()
            cached = await cache.get("inspection_forms:cached_rows")
            if cached:
                # Cache service auto-deserializes JSON
                rows = cached.get("rows", []) if isinstance(cached, dict) else []
                if rows:
                    logger.info(f"Using {len(rows)} cached form rows from manual upload")
                    return rows
        except Exception as e:
            logger.debug(f"No cached form rows: {e}")
        return None

    @classmethod
    async def find_inspection_by_address_or_name(
        cls,
        customer_name: str = "",
        address: str = "",
    ) -> dict | None:
        """Search form rows for a matching inspection by customer name OR address.

        Returns the inspection data dict for the best match, or None if no match found.
        Matching is case-insensitive and uses substring matching for flexibility.

        Tries cached rows (from manual upload) first, then falls back to Graph API.
        """
        try:
            # Try cached rows first (from manual upload workaround)
            rows = await cls._get_cached_rows()

            if not rows:
                if not cls.is_configured():
                    logger.warning("MS365 not configured and no cached rows")
                    return None
                site_id = await cls._get_site_id()
                drive_id, item_id = await cls._get_drive_item_id(site_id)
                sheet_name = await cls._get_worksheet_name(drive_id, item_id)
                rows = await cls._read_rows(drive_id, item_id, sheet_name)

            # Normalize search terms
            name_norm = (customer_name or "").lower().strip()
            addr_norm = (address or "").lower().strip()

            # Extract street number + street name from address for fuzzy matching
            # e.g. "7186 Brush Creek Road, Fairview, TN, 37062" -> "7186 brush creek"
            addr_short = ""
            if addr_norm:
                first_part = addr_norm.split(",")[0].strip()
                addr_short = first_part

            best_match = None
            best_score = 0

            for row in rows:
                row_name = _safe_get(row, COL["client_name"]).lower().strip()
                row_addr = _safe_get(row, COL["client_address"]).lower().strip()

                score = 0
                # Name match (full or partial)
                if name_norm and row_name:
                    if row_name == name_norm:
                        score += 10
                    elif name_norm in row_name or row_name in name_norm:
                        score += 5
                    else:
                        # Last name match
                        name_parts = name_norm.split()
                        row_parts = row_name.split()
                        if name_parts and row_parts:
                            if name_parts[-1] == row_parts[-1]:
                                score += 3

                # Address match (full, first segment, or street number)
                if addr_short and row_addr:
                    if addr_short in row_addr or row_addr.startswith(addr_short):
                        score += 10
                    else:
                        # Try matching just the street number
                        addr_num = addr_short.split()[0] if addr_short.split() else ""
                        row_addr_num = row_addr.split()[0] if row_addr.split() else ""
                        if addr_num and addr_num == row_addr_num:
                            score += 4

                if score > best_score:
                    best_score = score
                    best_match = row

            if best_match and best_score >= 3:
                logger.info(
                    "Found form match for name=%r addr=%r (score=%d)",
                    customer_name, address, best_score,
                )
                return _row_to_inspection_data(best_match)

            logger.info(
                "No form match found for name=%r addr=%r (best score=%d)",
                customer_name, address, best_score,
            )
            return None
        except Exception as e:
            logger.error("find_inspection_by_address_or_name failed: %s", e)
            return None

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
            drive_id, item_id = await cls._get_drive_item_id(site_id)
            sheet_name = await cls._get_worksheet_name(drive_id, item_id)
            rows = await cls._read_rows(drive_id, item_id, sheet_name)

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

                        # Build inspection data first (we'll use it either way)
                        inspection_data = _row_to_inspection_data(row)

                        existing = await db.execute(dup_query)
                        existing_wo = existing.scalar_one_or_none()
                        if existing_wo:
                            # Update the existing WO's checklist with the form data
                            # if it doesn't already have inspection data
                            existing_checklist = existing_wo.checklist if isinstance(existing_wo.checklist, dict) else {}
                            existing_inspection = existing_checklist.get("inspection") or {}
                            has_existing_data = bool(existing_inspection.get("steps")) or bool(existing_inspection.get("client"))

                            if not has_existing_data:
                                # Convert form data to checklist structure with steps
                                from app.services.inspection_letter_service import form_data_to_checklist
                                form_checklist = form_data_to_checklist(inspection_data)
                                # Preserve any existing ai_letter drafts
                                preserved_letter = existing_inspection.get("ai_letter")
                                form_checklist["source"] = "ms_forms"
                                if preserved_letter:
                                    form_checklist["ai_letter"] = preserved_letter
                                existing_checklist["inspection"] = form_checklist
                                existing_checklist["forms_import"] = True
                                existing_wo.checklist = existing_checklist
                                from sqlalchemy.orm.attributes import flag_modified
                                flag_modified(existing_wo, "checklist")
                                result["synced"] += 1
                                logger.info(
                                    "Forms sync: backfilled existing WO %s (%s) with form data",
                                    existing_wo.work_order_number, address,
                                )
                            else:
                                result["skipped"] += 1
                            continue

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
