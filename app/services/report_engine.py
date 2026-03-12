"""
Custom Report Engine

Dynamically builds SQLAlchemy queries based on report configuration.
Supports filtering, grouping, aggregation, sorting, and date ranges.
"""
import logging
from datetime import datetime, timedelta, date
from typing import Any
from uuid import uuid4

from sqlalchemy import select, func, desc, asc, cast, String, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.work_order import WorkOrder
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.customer import Customer
from app.models.technician import Technician
from app.models.quote import Quote
from app.models.contract import Contract
from app.models.custom_report import ReportSnapshot

logger = logging.getLogger(__name__)

# Model registry
SOURCE_MODELS = {
    "work_orders": WorkOrder,
    "invoices": Invoice,
    "payments": Payment,
    "customers": Customer,
    "technicians": Technician,
    "quotes": Quote,
    "contracts": Contract,
}

# Field metadata per data source
DATA_SOURCE_META = {
    "work_orders": {
        "label": "Work Orders",
        "fields": [
            {"name": "status", "type": "string", "label": "Status", "options": ["scheduled", "in_progress", "completed", "cancelled"]},
            {"name": "job_type", "type": "string", "label": "Job Type", "options": ["pumping", "inspection", "repair", "maintenance", "grease_trap", "aerobic", "emergency"]},
            {"name": "system_type", "type": "string", "label": "System Type", "options": ["conventional", "aerobic", "lift_station"]},
            {"name": "priority", "type": "string", "label": "Priority", "options": ["low", "medium", "high", "urgent"]},
            {"name": "scheduled_date", "type": "date", "label": "Scheduled Date"},
            {"name": "service_city", "type": "string", "label": "City"},
            {"name": "service_state", "type": "string", "label": "State"},
            {"name": "estimated_duration_hours", "type": "number", "label": "Est. Duration (hrs)"},
            {"name": "assigned_technician", "type": "string", "label": "Technician"},
            {"name": "is_recurring", "type": "boolean", "label": "Recurring"},
        ],
        "aggregations": ["count", "sum", "avg", "min", "max"],
        "default_date_field": "scheduled_date",
    },
    "invoices": {
        "label": "Invoices",
        "fields": [
            {"name": "status", "type": "string", "label": "Status", "options": ["draft", "sent", "paid", "overdue", "cancelled", "void"]},
            {"name": "amount", "type": "number", "label": "Amount"},
            {"name": "paid_amount", "type": "number", "label": "Paid Amount"},
            {"name": "issue_date", "type": "date", "label": "Issue Date"},
            {"name": "due_date", "type": "date", "label": "Due Date"},
            {"name": "paid_date", "type": "date", "label": "Paid Date"},
            {"name": "invoice_number", "type": "string", "label": "Invoice Number"},
        ],
        "aggregations": ["count", "sum", "avg", "min", "max"],
        "default_date_field": "issue_date",
    },
    "payments": {
        "label": "Payments",
        "fields": [
            {"name": "amount", "type": "number", "label": "Amount"},
            {"name": "payment_method", "type": "string", "label": "Payment Method", "options": ["card", "cash", "check", "ach"]},
            {"name": "status", "type": "string", "label": "Status", "options": ["pending", "completed", "failed", "refunded"]},
            {"name": "description", "type": "string", "label": "Description"},
            {"name": "created_at", "type": "date", "label": "Payment Date"},
        ],
        "aggregations": ["count", "sum", "avg", "min", "max"],
        "default_date_field": "created_at",
    },
    "customers": {
        "label": "Customers",
        "fields": [
            {"name": "first_name", "type": "string", "label": "First Name"},
            {"name": "last_name", "type": "string", "label": "Last Name"},
            {"name": "email", "type": "string", "label": "Email"},
            {"name": "phone", "type": "string", "label": "Phone"},
            {"name": "city", "type": "string", "label": "City"},
            {"name": "state", "type": "string", "label": "State"},
            {"name": "system_type", "type": "string", "label": "System Type"},
            {"name": "status", "type": "string", "label": "Status", "options": ["active", "inactive"]},
            {"name": "created_at", "type": "date", "label": "Created Date"},
        ],
        "aggregations": ["count"],
        "default_date_field": "created_at",
    },
    "technicians": {
        "label": "Technicians",
        "fields": [
            {"name": "name", "type": "string", "label": "Name"},
            {"name": "email", "type": "string", "label": "Email"},
            {"name": "phone", "type": "string", "label": "Phone"},
            {"name": "status", "type": "string", "label": "Status", "options": ["active", "inactive", "on_leave"]},
            {"name": "specializations", "type": "string", "label": "Specializations"},
            {"name": "hire_date", "type": "date", "label": "Hire Date"},
        ],
        "aggregations": ["count"],
        "default_date_field": "hire_date",
    },
    "quotes": {
        "label": "Quotes",
        "fields": [
            {"name": "status", "type": "string", "label": "Status", "options": ["draft", "sent", "accepted", "rejected", "expired"]},
            {"name": "total_amount", "type": "number", "label": "Total Amount"},
            {"name": "valid_until", "type": "date", "label": "Valid Until"},
            {"name": "created_at", "type": "date", "label": "Created Date"},
        ],
        "aggregations": ["count", "sum", "avg", "min", "max"],
        "default_date_field": "created_at",
    },
    "contracts": {
        "label": "Contracts",
        "fields": [
            {"name": "status", "type": "string", "label": "Status", "options": ["active", "expired", "cancelled", "pending"]},
            {"name": "contract_type", "type": "string", "label": "Type"},
            {"name": "monthly_amount", "type": "number", "label": "Monthly Amount"},
            {"name": "start_date", "type": "date", "label": "Start Date"},
            {"name": "end_date", "type": "date", "label": "End Date"},
        ],
        "aggregations": ["count", "sum", "avg", "min", "max"],
        "default_date_field": "start_date",
    },
}


def _resolve_date_range(date_range: dict | None, default_date_field: str) -> tuple[date | None, date | None]:
    """Resolve date range config to start/end dates."""
    if not date_range:
        return None, None

    range_type = date_range.get("type", "all")
    today = date.today()

    if range_type == "last_7d":
        return today - timedelta(days=7), today
    elif range_type == "last_30d":
        return today - timedelta(days=30), today
    elif range_type == "last_90d":
        return today - timedelta(days=90), today
    elif range_type == "ytd":
        return date(today.year, 1, 1), today
    elif range_type == "custom":
        start = date_range.get("start")
        end = date_range.get("end")
        start_date = datetime.strptime(start, "%Y-%m-%d").date() if start else None
        end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else None
        return start_date, end_date
    return None, None


def _apply_filter(query, model, f: dict):
    """Apply a single filter to the query."""
    field_name = f.get("field", "")
    operator = f.get("operator", "equals")
    value = f.get("value", "")

    col = getattr(model, field_name, None)
    if col is None:
        return query

    if operator == "equals":
        query = query.where(col == value)
    elif operator == "not_equals":
        query = query.where(col != value)
    elif operator == "contains":
        query = query.where(cast(col, String).ilike(f"%{value}%"))
    elif operator == "greater_than":
        query = query.where(col > float(value))
    elif operator == "less_than":
        query = query.where(col < float(value))
    elif operator == "is_empty":
        query = query.where((col == None) | (col == ""))
    elif operator == "is_not_empty":
        query = query.where(col != None)

    return query


async def execute_report_query(
    db: AsyncSession,
    data_source: str,
    columns: list[dict],
    filters: list[dict],
    group_by: list[str],
    sort_by: dict | None,
    date_range: dict | None,
    limit: int = 500,
) -> dict:
    """Execute a report query and return rows + summary."""
    model = SOURCE_MODELS.get(data_source)
    if not model:
        return {"rows": [], "summary": {}, "row_count": 0, "error": f"Unknown data source: {data_source}"}

    meta = DATA_SOURCE_META.get(data_source, {})
    default_date_field = meta.get("default_date_field", "created_at")

    try:
        # Determine which columns to select
        col_names = [c.get("field", "") for c in columns if c.get("field")]
        if not col_names:
            col_names = [f["name"] for f in meta.get("fields", [])[:8]]

        # Build aggregation query if group_by is set
        if group_by:
            select_cols = []
            for gb in group_by:
                gb_col = getattr(model, gb, None)
                if gb_col is not None:
                    select_cols.append(gb_col.label(gb))

            for c in columns:
                agg = c.get("aggregation")
                field = c.get("field", "")
                col = getattr(model, field, None)
                if agg and col is not None:
                    if agg == "count":
                        select_cols.append(func.count(col).label(f"{field}_count"))
                    elif agg == "sum":
                        select_cols.append(func.sum(col).label(f"{field}_sum"))
                    elif agg == "avg":
                        select_cols.append(func.avg(col).label(f"{field}_avg"))
                    elif agg == "min":
                        select_cols.append(func.min(col).label(f"{field}_min"))
                    elif agg == "max":
                        select_cols.append(func.max(col).label(f"{field}_max"))

            if not select_cols:
                select_cols = [func.count(model.id).label("count")]

            query = select(*select_cols)

            # Apply group by
            for gb in group_by:
                gb_col = getattr(model, gb, None)
                if gb_col is not None:
                    query = query.group_by(gb_col)
        else:
            # Simple select
            select_cols = []
            for cn in col_names:
                col = getattr(model, cn, None)
                if col is not None:
                    select_cols.append(col.label(cn))

            if not select_cols:
                query = select(model)
            else:
                query = select(*select_cols)

        # Apply filters
        for f in (filters or []):
            query = _apply_filter(query, model, f)

        # Apply date range
        start_date, end_date = _resolve_date_range(date_range, default_date_field)
        date_col = getattr(model, default_date_field, None)
        if date_col is not None:
            if start_date:
                query = query.where(date_col >= start_date)
            if end_date:
                query = query.where(date_col <= end_date)

        # Apply sort
        if sort_by and sort_by.get("field"):
            sort_col = getattr(model, sort_by["field"], None)
            if sort_col is not None:
                query = query.order_by(desc(sort_col) if sort_by.get("direction") == "desc" else asc(sort_col))

        query = query.limit(limit)
        result = await db.execute(query)
        raw_rows = result.all()

        # Convert to dicts
        rows = []
        for row in raw_rows:
            if hasattr(row, "_mapping"):
                rows.append({k: _serialize_val(v) for k, v in row._mapping.items()})
            elif hasattr(row, "__dict__"):
                d = {k: _serialize_val(v) for k, v in row.__dict__.items() if not k.startswith("_")}
                rows.append(d)
            else:
                rows.append({"value": str(row)})

        # Build summary
        summary = {"row_count": len(rows)}
        for c in columns:
            field = c.get("field", "")
            if c.get("aggregation") or any(isinstance(v.get(field), (int, float)) for v in rows[:1] if isinstance(v, dict)):
                values = [r.get(field) for r in rows if isinstance(r.get(field), (int, float))]
                if values:
                    summary[f"{field}_total"] = sum(values)
                    summary[f"{field}_avg"] = sum(values) / len(values)

        return {"rows": rows, "summary": summary, "row_count": len(rows)}

    except Exception as e:
        logger.error(f"Report query failed: {e}")
        return {"rows": [], "summary": {}, "row_count": 0, "error": str(e)}


async def save_snapshot(db: AsyncSession, report_id, data: list[dict], row_count: int) -> None:
    """Save an execution snapshot."""
    snapshot = ReportSnapshot(
        id=uuid4(),
        report_id=report_id,
        data=data,
        row_count=row_count,
    )
    db.add(snapshot)
    await db.commit()


def _serialize_val(v: Any) -> Any:
    """Serialize a value for JSON response."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if hasattr(v, "__str__") and not isinstance(v, (str, int, float, bool, type(None), list, dict)):
        return str(v)
    return v
