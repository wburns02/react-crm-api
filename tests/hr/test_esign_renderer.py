import hashlib
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from app.hr.esign.renderer import fill_and_stamp


def _make_blank_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.drawString(100, 700, "Original content")
    c.showPage()
    c.save()


@pytest.fixture
def blank_pdf(tmp_path) -> Path:
    p = tmp_path / "blank.pdf"
    _make_blank_pdf(p)
    return p


@pytest.fixture
def signature_png(tmp_path) -> Path:
    p = tmp_path / "sig.png"
    Image.new("RGBA", (200, 80), (0, 0, 0, 0)).save(p)
    return p


def test_fill_and_stamp_produces_pdf(blank_pdf, signature_png):
    output = fill_and_stamp(
        source_pdf_path=blank_pdf,
        field_values={"full_name": "John Doe"},
        fields=[
            {"name": "full_name", "page": 0, "x": 100, "y": 650, "w": 200, "h": 20, "field_type": "text"}
        ],
        signature_image_path=signature_png,
        signature_field={"name": "signature", "page": 0, "x": 100, "y": 500, "w": 200, "h": 50, "field_type": "signature"},
        signer_name="John Doe",
        signer_ip="192.0.2.1",
    )
    assert output.startswith(b"%PDF")
    assert len(output) > 100


def test_fill_and_stamp_hashes_deterministically(blank_pdf, signature_png):
    fields = [
        {"name": "full_name", "page": 0, "x": 100, "y": 650, "w": 200, "h": 20, "field_type": "text"}
    ]
    kwargs = dict(
        source_pdf_path=blank_pdf,
        field_values={"full_name": "Same Name"},
        fields=fields,
        signature_image_path=signature_png,
        signature_field={"name": "signature", "page": 0, "x": 100, "y": 500, "w": 200, "h": 50, "field_type": "signature"},
        signer_name="Same",
        signer_ip="192.0.2.1",
        timestamp_override="2026-04-15T10:00:00Z",
    )
    h1 = hashlib.sha256(fill_and_stamp(**kwargs)).hexdigest()
    h2 = hashlib.sha256(fill_and_stamp(**kwargs)).hexdigest()
    assert h1 == h2
