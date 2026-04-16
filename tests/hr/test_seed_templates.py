import pytest
from sqlalchemy import select

from app.hr.esign.models import HrDocumentTemplate
from app.hr.esign.seed_templates import seed_document_templates


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("HR_STORAGE_ROOT", str(tmp_path))
    yield


@pytest.mark.asyncio
async def test_seed_creates_five_templates(db):
    await seed_document_templates(db)
    await db.commit()

    rows = (await db.execute(select(HrDocumentTemplate))).scalars().all()
    kinds = {r.kind for r in rows}
    assert kinds >= {
        "employment_agreement_2026",
        "w4_2026",
        "i9",
        "adp_info",
        "benefits_election",
    }


@pytest.mark.asyncio
async def test_seed_is_idempotent(db):
    await seed_document_templates(db)
    await db.commit()
    # Second call must not insert duplicates.
    await seed_document_templates(db)
    await db.commit()

    rows = (await db.execute(select(HrDocumentTemplate))).scalars().all()
    assert len(rows) == 5


@pytest.mark.asyncio
async def test_every_template_has_signature_field(db):
    await seed_document_templates(db)
    await db.commit()

    rows = (await db.execute(select(HrDocumentTemplate))).scalars().all()
    for r in rows:
        sig_fields = [f for f in r.fields if f.get("field_type") == "signature"]
        assert len(sig_fields) == 1, f"{r.kind} missing signature field"
