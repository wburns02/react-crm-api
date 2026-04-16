import io

import pytest
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from app.hr.esign.models import HrDocumentTemplate
from app.hr.esign.schemas import SignatureRequestCreateIn
from app.hr.esign.services import create_signature_request
from app.hr.shared import storage


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("HR_STORAGE_ROOT", str(tmp_path))
    yield


def _pdf_key() -> str:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(100, 700, "Doc")
    c.showPage()
    c.save()
    return storage.save_bytes(buf.getvalue(), ".pdf")


@pytest.mark.asyncio
async def test_view_signature_page_public(client, db):
    tmpl = HrDocumentTemplate(
        kind="handbook",
        pdf_storage_key=_pdf_key(),
        fields=[
            {"name": "signature", "page": 0, "x": 100, "y": 500, "w": 200, "h": 50, "field_type": "signature"}
        ],
        active=True,
    )
    db.add(tmpl)
    await db.commit()

    req = await create_signature_request(
        db,
        SignatureRequestCreateIn(
            document_template_kind="handbook",
            signer_email="a@b.com",
            signer_name="A B",
        ),
        actor_user_id=None,
    )
    await db.commit()

    r = await client.get(f"/api/v2/public/sign/{req.token}")
    assert r.status_code == 200, r.text
    assert r.json()["token"] == req.token


@pytest.mark.asyncio
async def test_invalid_token_404(client):
    r = await client.get("/api/v2/public/sign/does-not-exist")
    assert r.status_code == 404
