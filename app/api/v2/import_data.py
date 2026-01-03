"""Data Import API - CSV import and template generation.

Features:
- CSV template downloads for each entity type
- CSV validation before import
- Bulk data import with error handling
"""
from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
import logging
import io

from app.api.deps import DbSession, CurrentUser
from app.services.csv_importer import (
    ImportType,
    ImportResult,
    generate_csv_template,
    generate_template_with_examples,
    validate_csv_file,
    process_import,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================
# Schemas
# ========================

class ImportRequest(BaseModel):
    skip_errors: bool = False  # Continue importing even if some rows fail


# ========================
# Template Endpoints
# ========================

@router.get("/templates/{import_type}")
async def download_template(
    import_type: str,
    current_user: CurrentUser,
    include_examples: bool = Query(False, description="Include example data row"),
):
    """Download a CSV template for the specified import type."""
    try:
        enum_type = ImportType(import_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid import type. Must be one of: {', '.join([t.value for t in ImportType])}"
        )

    if include_examples:
        content = generate_template_with_examples(enum_type)
    else:
        content = generate_csv_template(enum_type)

    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={import_type}_template.csv"
        }
    )


@router.get("/templates")
async def list_available_templates(
    current_user: CurrentUser,
):
    """List all available import templates."""
    return {
        "templates": [
            {
                "type": t.value,
                "description": f"Import template for {t.value.replace('_', ' ')}",
                "download_url": f"/api/v2/import/templates/{t.value}",
            }
            for t in ImportType
        ]
    }


# ========================
# Validation Endpoints
# ========================

@router.post("/validate/{import_type}", response_model=ImportResult)
async def validate_import_file(
    import_type: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
):
    """Validate a CSV file without importing. Returns validation errors."""
    try:
        enum_type = ImportType(import_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid import type. Must be one of: {', '.join([t.value for t in ImportType])}"
        )

    # Read file content
    content = await file.read()
    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content_str = content.decode("latin-1")
        except:
            raise HTTPException(
                status_code=400,
                detail="Could not decode file. Please ensure it's a valid CSV file with UTF-8 encoding."
            )

    # Validate
    result = await validate_csv_file(content_str, enum_type)
    return result


# ========================
# Import Endpoints
# ========================

@router.post("/upload/{import_type}", response_model=ImportResult)
async def import_csv_file(
    import_type: str,
    file: UploadFile = File(...),
    db: DbSession = None,
    current_user: CurrentUser = None,
    skip_errors: bool = Query(False, description="Skip rows with errors and continue importing"),
):
    """Import data from a CSV file."""
    try:
        enum_type = ImportType(import_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid import type. Must be one of: {', '.join([t.value for t in ImportType])}"
        )

    # Read file content
    content = await file.read()
    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content_str = content.decode("latin-1")
        except:
            raise HTTPException(
                status_code=400,
                detail="Could not decode file. Please ensure it's a valid CSV file with UTF-8 encoding."
            )

    # Process import
    try:
        result = await process_import(
            content_str,
            enum_type,
            db,
            current_user.email,
            skip_errors=skip_errors,
        )
        return result
    except Exception as e:
        logger.error(f"Import error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}"
        )


# ========================
# Utility Endpoints
# ========================

@router.get("/status")
async def get_import_status(
    current_user: CurrentUser,
):
    """Get import service status and available types."""
    return {
        "status": "ready",
        "available_import_types": [t.value for t in ImportType],
        "max_file_size_mb": 10,
        "supported_encodings": ["utf-8", "latin-1"],
    }
