"""Reference Docs API — serves static reference documents from disk."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app.api.deps import CurrentUser

try:
    from app.services.email_service import send_email
except ImportError:
    send_email = None

# Load manifest at module import time
MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "static" / "reference-docs-manifest.json"
with open(MANIFEST_PATH) as f:
    _manifest = json.load(f)

DOCS_DIR = Path(_manifest["docs_dir"])
DOCUMENTS = _manifest["documents"]
DOCS_BY_SLUG = {doc["slug"]: doc for doc in DOCUMENTS}

router = APIRouter()


class ReferenceDocItem(BaseModel):
    slug: str
    file: str
    title: str
    category: str
    description: str
    file_type: str


class SendDocRequest(BaseModel):
    to_email: str
    subject: Optional[str] = None
    message: Optional[str] = None


@router.get("/", response_model=list[ReferenceDocItem])
async def list_reference_docs(current_user: CurrentUser):
    """List all available reference documents."""
    return DOCUMENTS


@router.get("/{slug}/html", response_class=HTMLResponse)
async def get_reference_doc_html(slug: str, current_user: CurrentUser):
    """Serve a reference document as HTML."""
    doc = DOCS_BY_SLUG.get(slug)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{slug}' not found")

    file_path = DOCS_DIR / doc["file"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found on disk: {doc['file']}")

    content = file_path.read_text(encoding="utf-8")

    if doc["file_type"] == "text":
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{doc['title']}</title>
    <style>
        body {{ font-family: monospace; padding: 2rem; background: #f9fafb; }}
        pre {{ white-space: pre-wrap; word-wrap: break-word; }}
    </style>
</head>
<body>
<pre>{content}</pre>
</body>
</html>"""
        return HTMLResponse(content=html)

    return HTMLResponse(content=content)


@router.get("/{slug}/download")
async def download_reference_doc(slug: str, current_user: CurrentUser):
    """Download a reference document as a file attachment."""
    doc = DOCS_BY_SLUG.get(slug)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{slug}' not found")

    file_path = DOCS_DIR / doc["file"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found on disk: {doc['file']}")

    media_type = "text/html" if doc["file_type"] == "html" else "text/plain"
    return FileResponse(
        path=str(file_path),
        filename=doc["file"],
        media_type=media_type,
    )


@router.post("/{slug}/send")
async def send_reference_doc(slug: str, body: SendDocRequest, current_user: CurrentUser):
    """Email a reference document to a customer."""
    if send_email is None:
        raise HTTPException(status_code=501, detail="Email service not configured")

    doc = DOCS_BY_SLUG.get(slug)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{slug}' not found")

    file_path = DOCS_DIR / doc["file"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found on disk: {doc['file']}")

    content = file_path.read_text(encoding="utf-8")

    subject = body.subject or f"{doc['title']} — MAC Septic"

    if doc["file_type"] == "text":
        html_body = f"<pre>{content}</pre>"
    else:
        html_body = content

    if body.message:
        html_body = f"<p>{body.message}</p><hr/>{html_body}"

    await send_email(to=body.to_email, subject=subject, html_body=html_body)

    return {"status": "sent", "to": body.to_email, "document": doc["title"]}
