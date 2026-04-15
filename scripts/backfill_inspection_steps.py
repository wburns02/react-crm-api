"""One-shot: convert raw MS Forms inspection data into the steps checklist
structure so the Inspection Letters queue recognizes these WOs as having data.

Run with: railway run python scripts/backfill_inspection_steps.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, cast, String
from sqlalchemy.orm.attributes import flag_modified

from app.database import async_session_maker
from app.models.work_order import WorkOrder
from app.services.inspection_letter_service import form_data_to_checklist

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("backfill")


async def main() -> None:
    updated = 0
    skipped = 0
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                select(WorkOrder).where(
                    cast(WorkOrder.job_type, String) == "real_estate_inspection"
                )
            )
        ).scalars().all()

        for wo in rows:
            checklist = wo.checklist if isinstance(wo.checklist, dict) else {}
            inspection = checklist.get("inspection") or {}

            if not isinstance(inspection, dict):
                skipped += 1
                continue
            if inspection.get("steps"):
                skipped += 1
                continue
            if not (inspection.get("client") or inspection.get("findings")):
                skipped += 1
                continue

            preserved_letter = inspection.get("ai_letter")
            new_inspection = form_data_to_checklist(inspection)
            new_inspection["source"] = inspection.get("source") or "ms_forms"
            if preserved_letter:
                new_inspection["ai_letter"] = preserved_letter

            checklist["inspection"] = new_inspection
            checklist["forms_import"] = True
            wo.checklist = checklist
            flag_modified(wo, "checklist")
            updated += 1

        await db.commit()

    log.info("Backfill complete: updated=%d skipped=%d", updated, skipped)


if __name__ == "__main__":
    asyncio.run(main())
