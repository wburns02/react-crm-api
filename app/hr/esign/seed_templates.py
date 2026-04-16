"""Seed the five Plan 1 document templates.

Field coordinates were measured directly from the AcroForm widget /Rect
annotations where the PDFs expose them (w-4, i-9, adp_info).  For the
scanned-static PDFs (employment_agreement, benefits_election) the
coordinates are estimates relative to US Letter (612 x 792) and should be
adjusted after the first real end-to-end sign-and-render test.  See
app/hr/esign/PDF_FIELD_MAPPING.md for the raw widget dump.

PDF coordinate system: origin is bottom-left, units are points (72 pt = 1 in).
"""
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.esign.models import HrDocumentTemplate
from app.hr.shared import storage


_PDF_DIR = Path(__file__).parent / "pdfs"


TEMPLATES: list[dict] = [
    {
        # Static PDF, 7 pages, no AcroForm widgets — coords are estimates.
        "kind": "employment_agreement_2026",
        "version": "1",
        "filename": "employment_agreement_2026.pdf",
        "fields": [
            {"name": "employee_name", "page": 0, "x": 120, "y": 650, "w": 300, "h": 14, "field_type": "text"},
            {"name": "start_date", "page": 0, "x": 120, "y": 620, "w": 200, "h": 14, "field_type": "text"},
            # Signature block on the last page (page 6).
            {"name": "signature", "page": 6, "x": 100, "y": 120, "w": 220, "h": 50, "field_type": "signature"},
        ],
    },
    {
        # IRS 2026 W-4, AcroForm on page 0.  No native signature widget; the
        # signer's signature block is the "Employee's signature" line under
        # Step 5, approximately (72, 140) from the 2023/2024 revisions.
        "kind": "w4_2026",
        "version": "2026",
        "filename": "w4_2026.pdf",
        "fields": [
            {"name": "first_name", "page": 0, "x": 95, "y": 684, "w": 178, "h": 14, "field_type": "text"},
            {"name": "last_name", "page": 0, "x": 275, "y": 684, "w": 200, "h": 14, "field_type": "text"},
            {"name": "address", "page": 0, "x": 95, "y": 660, "w": 380, "h": 14, "field_type": "text"},
            {"name": "city_state_zip", "page": 0, "x": 95, "y": 636, "w": 380, "h": 14, "field_type": "text"},
            {"name": "ssn", "page": 0, "x": 476, "y": 684, "w": 100, "h": 14, "field_type": "text"},
            {"name": "signature", "page": 0, "x": 80, "y": 130, "w": 220, "h": 40, "field_type": "signature"},
        ],
    },
    {
        # USCIS I-9 (2025), AcroForm on page 0.  Real signature widget:
        # "Signature of Employee" at (42, 421, w=323, h=13).
        "kind": "i9",
        "version": "2025",
        "filename": "i9.pdf",
        "fields": [
            {"name": "last_name", "page": 0, "x": 43, "y": 605, "w": 156, "h": 15, "field_type": "text"},
            {"name": "first_name", "page": 0, "x": 204, "y": 605, "w": 138, "h": 15, "field_type": "text"},
            {"name": "middle_initial", "page": 0, "x": 348, "y": 605, "w": 65, "h": 15, "field_type": "text"},
            {"name": "address", "page": 0, "x": 42, "y": 580, "w": 186, "h": 14, "field_type": "text"},
            {"name": "city", "page": 0, "x": 306, "y": 580, "w": 149, "h": 14, "field_type": "text"},
            {"name": "zip", "page": 0, "x": 510, "y": 580, "w": 65, "h": 14, "field_type": "text"},
            {"name": "dob", "page": 0, "x": 42, "y": 554, "w": 99, "h": 14, "field_type": "text"},
            {"name": "ssn", "page": 0, "x": 150, "y": 553, "w": 105, "h": 14, "field_type": "text"},
            {"name": "email", "page": 0, "x": 264, "y": 554, "w": 186, "h": 14, "field_type": "text"},
            {"name": "phone", "page": 0, "x": 456, "y": 553, "w": 119, "h": 14, "field_type": "text"},
            {"name": "signature", "page": 0, "x": 42, "y": 421, "w": 323, "h": 13, "field_type": "signature"},
        ],
    },
    {
        # ADP blank employee info, AcroForm on page 0.  No signature widget —
        # coords estimated at the bottom of the page.
        "kind": "adp_info",
        "version": "1",
        "filename": "adp_info.pdf",
        "fields": [
            {"name": "first_name", "page": 0, "x": 36, "y": 599, "w": 222, "h": 16, "field_type": "text"},
            {"name": "middle_initial", "page": 0, "x": 273, "y": 599, "w": 15, "h": 16, "field_type": "text"},
            {"name": "last_name", "page": 0, "x": 303, "y": 599, "w": 272, "h": 16, "field_type": "text"},
            {"name": "phone", "page": 0, "x": 35, "y": 497, "w": 227, "h": 17, "field_type": "text"},
            {"name": "mobile", "page": 0, "x": 301, "y": 498, "w": 275, "h": 16, "field_type": "text"},
            {"name": "signature", "page": 0, "x": 72, "y": 100, "w": 220, "h": 40, "field_type": "signature"},
        ],
    },
    {
        # MAC Septic benefits election — static PDF (no AcroForm) with 2 pages.
        # Estimated coords; refine after first real sign.
        "kind": "benefits_election",
        "version": "2026",
        "filename": "benefits_election.pdf",
        "fields": [
            {"name": "employee_name", "page": 0, "x": 120, "y": 680, "w": 300, "h": 14, "field_type": "text"},
            {"name": "plan_selected", "page": 0, "x": 120, "y": 640, "w": 300, "h": 14, "field_type": "text"},
            {"name": "signature", "page": 1, "x": 80, "y": 120, "w": 220, "h": 40, "field_type": "signature"},
        ],
    },
]


async def seed_document_templates(db: AsyncSession) -> None:
    """Idempotent upsert-by-kind. Each PDF is copied into storage on first run."""
    for t in TEMPLATES:
        existing = (
            await db.execute(
                select(HrDocumentTemplate).where(HrDocumentTemplate.kind == t["kind"])
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        pdf_bytes = (_PDF_DIR / t["filename"]).read_bytes()
        key = storage.save_bytes(pdf_bytes, ".pdf")
        db.add(
            HrDocumentTemplate(
                kind=t["kind"],
                version=t["version"],
                pdf_storage_key=key,
                fields=t["fields"],
                active=True,
            )
        )
    await db.flush()
