"""
User Activity Analytics endpoints — admin-only.

Provides:
- GET /admin/user-activity — paginated activity log with filters
- GET /admin/user-activity/stats — aggregated usage statistics
- GET /admin/user-activity/sessions — login session history
- DELETE /admin/user-activity/prune — clean up old records
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import DbSession, CurrentUser
from app.services.activity_tracker import log_activity, get_client_ip

router = APIRouter()
logger = logging.getLogger(__name__)


class TrackEvent(BaseModel):
    category: str
    action: str
    description: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/admin/user-activity/track")
async def track_frontend_event(
    event: TrackEvent,
    current_user: CurrentUser,
    request: Request,
):
    """Receive lightweight page-view / session events from the frontend."""
    asyncio.create_task(log_activity(
        category=event.category,
        action=event.action,
        description=event.description,
        user_id=current_user.id,
        user_email=current_user.email,
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or None,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:500],
        source="frontend",
        session_id=event.session_id,
    ))
    return {"ok": True}


@router.get("/admin/user-activity")
async def get_user_activity(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    category: Optional[str] = None,
    action: Optional[str] = None,
    user_email: Optional[str] = None,
    days: int = Query(7, ge=1, le=90),
):
    """Get paginated user activity log. Admin only."""
    if not current_user.is_superuser:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    conditions = ["created_at > NOW() - INTERVAL ':days days'"]
    params = {"days": days, "limit": page_size, "offset": (page - 1) * page_size}

    if category:
        conditions.append("category = :category")
        params["category"] = category
    if action:
        conditions.append("action = :action")
        params["action"] = action
    if user_email:
        conditions.append("user_email ILIKE :user_email")
        params["user_email"] = f"%{user_email}%"

    where = " AND ".join(conditions)

    # Use string interpolation ONLY for the days interval (integer, validated by Query)
    # All other params are parameterized
    base_where = f"created_at > NOW() - INTERVAL '{days} days'"
    extra_conditions = []
    if category:
        extra_conditions.append("category = :category")
    if action:
        extra_conditions.append("action = :action")
    if user_email:
        extra_conditions.append("user_email ILIKE :user_email")

    where_clause = base_where
    if extra_conditions:
        where_clause += " AND " + " AND ".join(extra_conditions)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM user_activity_log WHERE {where_clause}"),
        params,
    )
    total = count_result.scalar()

    rows = await db.execute(
        text(f"""
            SELECT id, user_id, user_email, user_name, category, action, description,
                   ip_address, source, resource_type, resource_id, endpoint, http_method,
                   status_code, response_time_ms, session_id, entity_id, created_at
            FROM user_activity_log
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )

    items = []
    for row in rows:
        items.append({
            "id": str(row.id),
            "user_id": row.user_id,
            "user_email": row.user_email,
            "user_name": row.user_name,
            "category": row.category,
            "action": row.action,
            "description": row.description,
            "ip_address": row.ip_address,
            "source": row.source,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "endpoint": row.endpoint,
            "http_method": row.http_method,
            "status_code": row.status_code,
            "response_time_ms": row.response_time_ms,
            "session_id": row.session_id,
            "entity_id": row.entity_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }


@router.get("/admin/user-activity/stats")
async def get_activity_stats(
    current_user: CurrentUser,
    db: DbSession,
    days: int = Query(7, ge=1, le=90),
):
    """Get aggregated usage statistics. Admin only."""
    if not current_user.is_superuser:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    interval = f"{days} days"

    # Active users (unique emails)
    active_users = await db.execute(text(f"""
        SELECT COUNT(DISTINCT user_email) FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}' AND user_email IS NOT NULL
    """))

    # Total events
    total_events = await db.execute(text(f"""
        SELECT COUNT(*) FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}'
    """))

    # Logins count
    logins = await db.execute(text(f"""
        SELECT COUNT(*) FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}' AND action = 'login'
    """))

    # Failed logins
    failed_logins = await db.execute(text(f"""
        SELECT COUNT(*) FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}' AND action = 'login_failed'
    """))

    # Events by category
    by_category = await db.execute(text(f"""
        SELECT category, COUNT(*) as count
        FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}'
        GROUP BY category ORDER BY count DESC
    """))

    # Events by action (top 15)
    by_action = await db.execute(text(f"""
        SELECT action, COUNT(*) as count
        FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}'
        GROUP BY action ORDER BY count DESC LIMIT 15
    """))

    # Most active users
    top_users = await db.execute(text(f"""
        SELECT user_email, COUNT(*) as count
        FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}' AND user_email IS NOT NULL
        GROUP BY user_email ORDER BY count DESC LIMIT 10
    """))

    # Most accessed resources
    top_resources = await db.execute(text(f"""
        SELECT resource_type, COUNT(*) as count
        FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}' AND resource_type IS NOT NULL
        GROUP BY resource_type ORDER BY count DESC LIMIT 10
    """))

    # Activity by hour of day (for heatmap)
    by_hour = await db.execute(text(f"""
        SELECT EXTRACT(HOUR FROM created_at) as hour, COUNT(*) as count
        FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}'
        GROUP BY hour ORDER BY hour
    """))

    # Activity by day
    by_day = await db.execute(text(f"""
        SELECT DATE(created_at) as day, COUNT(*) as count
        FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}'
        GROUP BY day ORDER BY day
    """))

    # Average response time for tracked requests
    avg_response = await db.execute(text(f"""
        SELECT AVG(response_time_ms), MAX(response_time_ms), PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms)
        FROM user_activity_log
        WHERE created_at > NOW() - INTERVAL '{interval}' AND response_time_ms IS NOT NULL
    """))
    resp_row = avg_response.fetchone()

    return {
        "period_days": days,
        "active_users": active_users.scalar() or 0,
        "total_events": total_events.scalar() or 0,
        "total_logins": logins.scalar() or 0,
        "failed_logins": failed_logins.scalar() or 0,
        "by_category": [{"category": r.category, "count": r.count} for r in by_category],
        "by_action": [{"action": r.action, "count": r.count} for r in by_action],
        "top_users": [{"email": r.user_email, "count": r.count} for r in top_users],
        "top_resources": [{"resource": r.resource_type, "count": r.count} for r in top_resources],
        "by_hour": [{"hour": int(r.hour), "count": r.count} for r in by_hour],
        "by_day": [{"day": r.day.isoformat() if r.day else None, "count": r.count} for r in by_day],
        "response_time": {
            "avg_ms": round(resp_row[0]) if resp_row and resp_row[0] else None,
            "max_ms": resp_row[1] if resp_row else None,
            "p95_ms": round(resp_row[2]) if resp_row and resp_row[2] else None,
        },
    }


@router.get("/admin/user-activity/sessions")
async def get_login_sessions(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user_email: Optional[str] = None,
    days: int = Query(30, ge=1, le=90),
):
    """Get login/logout session history. Admin only."""
    if not current_user.is_superuser:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    interval = f"{days} days"
    extra = ""
    params = {"limit": page_size, "offset": (page - 1) * page_size}

    if user_email:
        extra = " AND user_email ILIKE :user_email"
        params["user_email"] = f"%{user_email}%"

    rows = await db.execute(
        text(f"""
            SELECT id, user_id, user_email, user_name, action, description,
                   ip_address, user_agent, source, session_id, created_at
            FROM user_activity_log
            WHERE category = 'auth' AND created_at > NOW() - INTERVAL '{interval}'{extra}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )

    count_result = await db.execute(
        text(f"""
            SELECT COUNT(*) FROM user_activity_log
            WHERE category = 'auth' AND created_at > NOW() - INTERVAL '{interval}'{extra}
        """),
        params,
    )

    items = []
    for row in rows:
        items.append({
            "id": str(row.id),
            "user_id": row.user_id,
            "user_email": row.user_email,
            "user_name": row.user_name,
            "action": row.action,
            "description": row.description,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "source": row.source,
            "session_id": row.session_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    return {
        "items": items,
        "total": count_result.scalar() or 0,
        "page": page,
        "page_size": page_size,
    }


@router.delete("/admin/user-activity/prune")
async def prune_activity_log(
    current_user: CurrentUser,
    db: DbSession,
    days: int = Query(90, ge=30, le=365),
):
    """Delete activity records older than N days. Admin only."""
    if not current_user.is_superuser:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    result = await db.execute(
        text(f"DELETE FROM user_activity_log WHERE created_at < NOW() - INTERVAL '{days} days'")
    )
    await db.commit()
    return {"deleted": result.rowcount, "older_than_days": days}
