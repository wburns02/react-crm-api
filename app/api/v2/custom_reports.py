"""
Custom Reports API

CRUD for custom reports + preview, execute, export, favorite, schedule.
"""
import csv
import io
from datetime import datetime
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, CurrentUser
from app.models.custom_report import CustomReport, ReportSnapshot
from app.services.report_engine import execute_report_query, save_snapshot, DATA_SOURCE_META

router = APIRouter()


# -- Schemas --

class ReportCreate(BaseModel):
    name: str = Field(max_length=200)
    description: Optional[str] = None
    report_type: str = "table"
    data_source: str
    columns: list[dict] = []
    filters: list[dict] = []
    group_by: list[str] = []
    sort_by: Optional[dict] = None
    date_range: Optional[dict] = None
    chart_config: Optional[dict] = None
    is_shared: bool = False


class ReportUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    report_type: Optional[str] = None
    data_source: Optional[str] = None
    columns: Optional[list[dict]] = None
    filters: Optional[list[dict]] = None
    group_by: Optional[list[str]] = None
    sort_by: Optional[dict] = None
    date_range: Optional[dict] = None
    chart_config: Optional[dict] = None
    is_shared: Optional[bool] = None


class PreviewRequest(BaseModel):
    data_source: str
    columns: list[dict] = []
    filters: list[dict] = []
    group_by: list[str] = []
    sort_by: Optional[dict] = None
    date_range: Optional[dict] = None


class ScheduleUpdate(BaseModel):
    frequency: Optional[str] = None  # daily, weekly, monthly
    day_of_week: Optional[int] = None
    time: Optional[str] = None
    recipients: list[str] = []
    enabled: bool = False


# -- Endpoints --

@router.get("")
async def list_reports(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    data_source: Optional[str] = None,
    is_favorite: Optional[bool] = None,
    search: Optional[str] = None,
):
    query = select(CustomReport).order_by(desc(CustomReport.created_at))
    count_query = select(func.count(CustomReport.id))

    if data_source:
        query = query.where(CustomReport.data_source == data_source)
        count_query = count_query.where(CustomReport.data_source == data_source)
    if is_favorite is not None:
        query = query.where(CustomReport.is_favorite == is_favorite)
        count_query = count_query.where(CustomReport.is_favorite == is_favorite)
    if search:
        query = query.where(CustomReport.name.ilike(f"%{search}%"))
        count_query = count_query.where(CustomReport.name.ilike(f"%{search}%"))

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    reports = result.scalars().all()

    return {
        "items": [_serialize_report(r) for r in reports],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/data-sources")
async def get_data_sources(user: CurrentUser):
    return DATA_SOURCE_META


@router.post("")
async def create_report(data: ReportCreate, db: DbSession, user: CurrentUser):
    report = CustomReport(
        id=uuid4(),
        name=data.name,
        description=data.description,
        report_type=data.report_type,
        data_source=data.data_source,
        columns=data.columns,
        filters=data.filters,
        group_by=data.group_by,
        sort_by=data.sort_by,
        date_range=data.date_range,
        chart_config=data.chart_config,
        is_shared=data.is_shared,
        created_by=user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return _serialize_report(report)


@router.post("/preview")
async def preview_report(data: PreviewRequest, db: DbSession, user: CurrentUser):
    result = await execute_report_query(
        db=db,
        data_source=data.data_source,
        columns=data.columns,
        filters=data.filters,
        group_by=data.group_by,
        sort_by=data.sort_by,
        date_range=data.date_range,
        limit=100,
    )
    return result


@router.get("/{report_id}")
async def get_report(report_id: str, db: DbSession, user: CurrentUser):
    report = await _get_report_or_404(db, report_id)
    result = _serialize_report(report)

    # Get latest snapshot
    snap_result = await db.execute(
        select(ReportSnapshot)
        .where(ReportSnapshot.report_id == report.id)
        .order_by(desc(ReportSnapshot.generated_at))
        .limit(1)
    )
    snapshot = snap_result.scalars().first()
    if snapshot:
        result["latest_snapshot"] = {
            "id": str(snapshot.id),
            "data": snapshot.data,
            "row_count": snapshot.row_count,
            "generated_at": snapshot.generated_at.isoformat() if snapshot.generated_at else None,
        }

    # Get snapshot history
    hist_result = await db.execute(
        select(ReportSnapshot.id, ReportSnapshot.row_count, ReportSnapshot.generated_at)
        .where(ReportSnapshot.report_id == report.id)
        .order_by(desc(ReportSnapshot.generated_at))
        .limit(10)
    )
    result["snapshot_history"] = [
        {"id": str(row.id), "row_count": row.row_count, "generated_at": row.generated_at.isoformat() if row.generated_at else None}
        for row in hist_result.all()
    ]

    return result


@router.patch("/{report_id}")
async def update_report(report_id: str, data: ReportUpdate, db: DbSession, user: CurrentUser):
    report = await _get_report_or_404(db, report_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(report, key, value)
    report.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(report)
    return _serialize_report(report)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: str, db: DbSession, user: CurrentUser):
    report = await _get_report_or_404(db, report_id)
    await db.delete(report)
    await db.commit()


@router.post("/{report_id}/execute")
async def execute_report(report_id: str, db: DbSession, user: CurrentUser):
    report = await _get_report_or_404(db, report_id)
    result = await execute_report_query(
        db=db,
        data_source=report.data_source,
        columns=report.columns or [],
        filters=report.filters or [],
        group_by=report.group_by or [],
        sort_by=report.sort_by,
        date_range=report.date_range,
        limit=10000,
    )

    # Save snapshot
    await save_snapshot(db, report.id, result["rows"], result["row_count"])
    report.last_generated_at = datetime.utcnow()
    await db.commit()

    return result


@router.post("/{report_id}/export")
async def export_report(report_id: str, db: DbSession, user: CurrentUser):
    report = await _get_report_or_404(db, report_id)
    result = await execute_report_query(
        db=db,
        data_source=report.data_source,
        columns=report.columns or [],
        filters=report.filters or [],
        group_by=report.group_by or [],
        sort_by=report.sort_by,
        date_range=report.date_range,
        limit=10000,
    )

    rows = result.get("rows", [])
    if not rows:
        raise HTTPException(status_code=404, detail="No data to export")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={report.name.replace(' ', '_')}.csv"},
    )


@router.patch("/{report_id}/favorite")
async def toggle_favorite(report_id: str, db: DbSession, user: CurrentUser):
    report = await _get_report_or_404(db, report_id)
    report.is_favorite = not report.is_favorite
    await db.commit()
    await db.refresh(report)
    return _serialize_report(report)


@router.patch("/{report_id}/schedule")
async def update_schedule(report_id: str, data: ScheduleUpdate, db: DbSession, user: CurrentUser):
    report = await _get_report_or_404(db, report_id)
    if data.enabled:
        report.schedule = {
            "frequency": data.frequency,
            "day_of_week": data.day_of_week,
            "time": data.time,
            "recipients": data.recipients,
            "enabled": True,
        }
    else:
        report.schedule = None
    await db.commit()
    await db.refresh(report)
    return _serialize_report(report)


# -- Helpers --

async def _get_report_or_404(db: AsyncSession, report_id: str) -> CustomReport:
    result = await db.execute(select(CustomReport).where(CustomReport.id == report_id))
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _serialize_report(r: CustomReport) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "description": r.description,
        "report_type": r.report_type,
        "data_source": r.data_source,
        "columns": r.columns or [],
        "filters": r.filters or [],
        "group_by": r.group_by or [],
        "sort_by": r.sort_by,
        "date_range": r.date_range,
        "chart_config": r.chart_config,
        "layout": r.layout,
        "is_favorite": r.is_favorite or False,
        "is_shared": r.is_shared or False,
        "schedule": r.schedule,
        "last_generated_at": r.last_generated_at.isoformat() if r.last_generated_at else None,
        "created_by": str(r.created_by) if r.created_by else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }
