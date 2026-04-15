"""One-shot: re-read MS Forms spreadsheet and rebuild every matching WO's
inspection checklist using the current (richer) form_data_to_checklist.

Preserves any ai_letter drafts already on the WO.

Run: DATABASE_URL=... MS365_* ... python scripts/refresh_inspection_data.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, cast, String, and_
from sqlalchemy.orm.attributes import flag_modified

from app.database import async_session_maker
from app.models.work_order import WorkOrder
from app.services.ms365_forms_sync_service import (
    MS365FormsSyncService,
    COL,
    _safe_get,
    _row_to_inspection_data,
)
from app.services.inspection_letter_service import form_data_to_checklist

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("refresh")


async def main() -> None:
    drive_id = os.environ["MS365_SHAREPOINT_DRIVE_ID"]
    # Resolve via drive+path (Strategy 1) which consistently works
    path_data = await MS365FormsSyncService.graph_get(
        f"/drives/{drive_id}/root:/Septic Inspection Form.xlsx"
    )
    item_id = path_data["id"]
    MS365FormsSyncService._drive_id = drive_id
    MS365FormsSyncService._drive_item_id = item_id
    sheet = await MS365FormsSyncService._get_worksheet_name(drive_id, item_id)
    rows = await MS365FormsSyncService._read_rows(drive_id, item_id, sheet)
    log.info("loaded %d form rows", len(rows))

    updated = 0
    skipped_no_match = 0
    skipped_no_address = 0

    async with async_session_maker() as db:
        for i, row in enumerate(rows):
            address = _safe_get(row, COL["client_address"])
            if not address:
                skipped_no_address += 1
                continue

            form_data = _row_to_inspection_data(row)

            result = await db.execute(
                select(WorkOrder).where(
                    and_(
                        WorkOrder.service_address_line1 == address,
                        cast(WorkOrder.job_type, String) == "real_estate_inspection",
                    )
                ).limit(1)
            )
            wo = result.scalars().first()
            if not wo:
                skipped_no_match += 1
                continue

            checklist = wo.checklist if isinstance(wo.checklist, dict) else {}
            existing_inspection = checklist.get("inspection") or {}
            preserved_letter = existing_inspection.get("ai_letter") if isinstance(existing_inspection, dict) else None

            new_inspection = form_data_to_checklist(form_data)
            new_inspection["source"] = "ms_forms"
            if preserved_letter:
                new_inspection["ai_letter"] = preserved_letter

            checklist["inspection"] = new_inspection
            checklist["forms_import"] = True
            wo.checklist = checklist
            flag_modified(wo, "checklist")
            updated += 1

        await db.commit()

    log.info(
        "refresh complete: updated=%d no_match=%d no_address=%d",
        updated, skipped_no_match, skipped_no_address,
    )


if __name__ == "__main__":
    asyncio.run(main())
