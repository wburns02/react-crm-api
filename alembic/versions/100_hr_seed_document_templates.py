"""seed hr document templates

Revision ID: 100
Revises: 099
"""
import hashlib
import json
import uuid
from pathlib import Path

from alembic import op
from sqlalchemy import text


revision = "100"
down_revision = "099"
branch_labels = None
depends_on = None


# Mirror of app/hr/esign/seed_templates.TEMPLATES kept local so this migration
# does not import app code (app imports may fail during alembic startup).
_TEMPLATES: list[dict] = [
    {
        "kind": "employment_agreement_2026",
        "version": "1",
        "filename": "employment_agreement_2026.pdf",
        "fields": [
            {"name": "employee_name", "page": 0, "x": 120, "y": 650, "w": 300, "h": 14, "field_type": "text"},
            {"name": "start_date", "page": 0, "x": 120, "y": 620, "w": 200, "h": 14, "field_type": "text"},
            {"name": "signature", "page": 6, "x": 100, "y": 120, "w": 220, "h": 50, "field_type": "signature"},
        ],
    },
    {
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


def _pdf_key_for(kind: str, pdf_bytes: bytes) -> str:
    """Deterministic storage key so the migration is replay-safe.

    Using a content hash means re-running the migration against a database
    whose rows were manually wiped won't orphan the on-disk files.
    """
    digest = hashlib.sha256(pdf_bytes).hexdigest()[:32]
    return f"seed-{kind}-{digest}.pdf"


def upgrade() -> None:
    bind = op.get_bind()

    # Skip any kinds already present — replay-safe.
    existing = {
        row[0]
        for row in bind.execute(text("SELECT kind FROM hr_document_templates")).fetchall()
    }

    pdf_dir = Path(__file__).resolve().parents[2] / "app" / "hr" / "esign" / "pdfs"

    rows_to_insert = []
    for t in _TEMPLATES:
        if t["kind"] in existing:
            continue
        pdf_bytes = (pdf_dir / t["filename"]).read_bytes()
        storage_key = _pdf_key_for(t["kind"], pdf_bytes)

        # Write to HR_STORAGE_ROOT if available; the storage.read_bytes()
        # fallback in app/hr/shared/storage.py also reads straight from the
        # bundled PDFs dir, so a failure here is not fatal.
        try:
            import os
            root = Path(os.getenv("HR_STORAGE_ROOT", "/var/tmp/hr-storage-dev"))
            root.mkdir(parents=True, exist_ok=True)
            (root / storage_key).write_bytes(pdf_bytes)
        except Exception:
            pass  # storage fallback in app code handles this

        rows_to_insert.append(
            {
                "id": uuid.uuid4(),
                "kind": t["kind"],
                "version": t["version"],
                "pdf_storage_key": storage_key,
                "fields": json.dumps(t["fields"]),
                "active": True,
            }
        )

    insert_stmt = text(
        "INSERT INTO hr_document_templates "
        "(id, kind, version, pdf_storage_key, fields, active) "
        "VALUES (CAST(:id AS uuid), :kind, :version, :pdf_storage_key, "
        "        CAST(:fields AS json), :active)"
    )
    for row in rows_to_insert:
        bind.execute(
            insert_stmt,
            {
                "id": str(row["id"]),
                "kind": row["kind"],
                "version": row["version"],
                "pdf_storage_key": row["pdf_storage_key"],
                "fields": row["fields"],
                "active": row["active"],
            },
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM hr_document_templates WHERE kind IN ("
        "'employment_agreement_2026','w4_2026','i9','adp_info','benefits_election'"
        ")"
    )
