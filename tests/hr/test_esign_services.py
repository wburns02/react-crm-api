import base64
import io
import os

import pytest
from PIL import Image
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from app.hr.esign.models import HrDocumentTemplate
from app.hr.esign.schemas import SignatureRequestCreateIn
from app.hr.esign.services import (
    SignatureError,
    create_signature_request,
    submit_signature,
)
from app.hr.shared import storage


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("HR_STORAGE_ROOT", str(tmp_path))
    yield


def _make_pdf_and_store() -> str:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(100, 700, "Test doc")
    c.showPage()
    c.save()
    return storage.save_bytes(buf.getvalue(), ".pdf")


def _png_base64() -> str:
    img = Image.new("RGBA", (100, 40), (0, 0, 0, 255))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


@pytest.mark.asyncio
async def test_create_and_submit_signature(db):
    template_key = _make_pdf_and_store()
    tmpl = HrDocumentTemplate(
        kind="test_doc",
        version="1",
        pdf_storage_key=template_key,
        fields=[
            {"name": "full_name", "page": 0, "x": 100, "y": 650, "w": 200, "h": 20, "field_type": "text"},
            {"name": "signature", "page": 0, "x": 100, "y": 500, "w": 200, "h": 50, "field_type": "signature"},
        ],
        active=True,
    )
    db.add(tmpl)
    await db.commit()

    req = await create_signature_request(
        db,
        SignatureRequestCreateIn(
            document_template_kind="test_doc",
            signer_email="hire@example.com",
            signer_name="John Hire",
            field_values={"full_name": "John Hire"},
            ttl_days=7,
        ),
        actor_user_id=None,
    )
    await db.commit()
    assert req.token
    assert req.status == "sent"

    signed = await submit_signature(
        db,
        token=req.token,
        signature_image_base64=_png_base64(),
        consent_confirmed=True,
        ip="192.0.2.1",
        user_agent="pytest",
    )
    await db.commit()
    assert signed.hash_sha256
    assert signed.storage_key


@pytest.mark.asyncio
async def test_submit_requires_consent(db):
    tmpl = HrDocumentTemplate(
        kind="consent_doc",
        pdf_storage_key=_make_pdf_and_store(),
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
            document_template_kind="consent_doc",
            signer_email="a@b.com",
            signer_name="A B",
        ),
        actor_user_id=None,
    )
    await db.commit()
    with pytest.raises(SignatureError, match="consent"):
        await submit_signature(
            db,
            token=req.token,
            signature_image_base64=_png_base64(),
            consent_confirmed=False,
            ip="192.0.2.1",
            user_agent="pytest",
        )
