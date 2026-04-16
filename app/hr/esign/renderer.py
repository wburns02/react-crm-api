"""PDF fill-and-stamp renderer.

Takes an existing PDF template, overlays typed field values + a signature
image + a metadata stamp, and returns the merged bytes.  Deterministic when
`timestamp_override` is supplied so callers can compute a stable content hash
(used for audit logging).
"""
import io
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


def _overlay_page(
    page_size: tuple[float, float],
    field_values: dict,
    fields: Iterable[dict],
    signature_image_path: Path | None,
    signature_field: dict | None,
    signer_name: str,
    signer_ip: str,
    timestamp_override: str | None,
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)

    for f in fields:
        if f.get("field_type") == "text":
            value = str(field_values.get(f["name"], ""))
            c.setFont("Helvetica", 11)
            c.drawString(f["x"], f["y"], value)

    if signature_image_path and signature_field:
        c.drawImage(
            str(signature_image_path),
            signature_field["x"],
            signature_field["y"],
            width=signature_field["w"],
            height=signature_field["h"],
            mask="auto",
        )
        stamp = f"Signed by {signer_name} on {timestamp_override or ''} from IP {signer_ip}"
        c.setFont("Helvetica", 7)
        c.drawString(signature_field["x"], signature_field["y"] - 10, stamp)

    c.save()
    return buf.getvalue()


def fill_and_stamp(
    *,
    source_pdf_path: Path,
    field_values: dict,
    fields: list[dict],
    signature_image_path: Path,
    signature_field: dict,
    signer_name: str,
    signer_ip: str,
    timestamp_override: str | None = None,
) -> bytes:
    reader = PdfReader(str(source_pdf_path))
    writer = PdfWriter()

    for page_idx, page in enumerate(reader.pages):
        page_fields = [f for f in fields if f["page"] == page_idx]
        sig_field = signature_field if signature_field["page"] == page_idx else None
        if page_fields or sig_field:
            overlay_bytes = _overlay_page(
                page_size=(float(page.mediabox.width), float(page.mediabox.height)),
                field_values=field_values,
                fields=page_fields,
                signature_image_path=signature_image_path if sig_field else None,
                signature_field=sig_field,
                signer_name=signer_name,
                signer_ip=signer_ip,
                timestamp_override=timestamp_override,
            )
            overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
            page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
