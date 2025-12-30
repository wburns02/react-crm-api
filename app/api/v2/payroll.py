"""
Payroll API - Stub endpoints for payroll management.
Full implementation will be added in Phase 10.
"""
from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional
from datetime import datetime, date
from pydantic import BaseModel

from app.api.deps import DbSession, CurrentUser

router = APIRouter()


class PayrollPeriodResponse(BaseModel):
    """Payroll period response schema."""
    id: int
    start_date: date
    end_date: date
    status: str
    total_hours: float
    total_amount: float
    technician_count: int


class PayrollListResponse(BaseModel):
    """Paginated payroll list response."""
    items: list[PayrollPeriodResponse]
    total: int
    page: int
    page_size: int


class PayrollStats(BaseModel):
    """Payroll statistics."""
    current_period_hours: float
    current_period_amount: float
    ytd_total: float
    pending_approvals: int


@router.get("/", response_model=PayrollListResponse)
async def list_payroll_periods(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
):
    """List payroll periods. Stub implementation."""
    # Return empty list for now - will be implemented in Phase 10
    return PayrollListResponse(
        items=[],
        total=0,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=PayrollStats)
async def get_payroll_stats(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get payroll statistics. Stub implementation."""
    return PayrollStats(
        current_period_hours=0,
        current_period_amount=0,
        ytd_total=0,
        pending_approvals=0,
    )


@router.get("/current", response_model=PayrollPeriodResponse)
async def get_current_period(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get current payroll period. Stub implementation."""
    today = date.today()
    # Return a stub period
    return PayrollPeriodResponse(
        id=1,
        start_date=today.replace(day=1),
        end_date=today,
        status="open",
        total_hours=0,
        total_amount=0,
        technician_count=0,
    )


@router.get("/{period_id}")
async def get_payroll_period(
    period_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific payroll period. Stub implementation."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Payroll period not found. Feature coming soon.",
    )


@router.post("/{period_id}/approve")
async def approve_payroll_period(
    period_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Approve a payroll period. Stub implementation."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Payroll approval feature coming in Phase 10.",
    )


@router.post("/{period_id}/export")
async def export_payroll(
    period_id: int,
    format: str = Query("csv", pattern="^(csv|nacha|pdf)$"),
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """Export payroll data. Stub implementation."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Payroll export feature coming in Phase 10.",
    )
