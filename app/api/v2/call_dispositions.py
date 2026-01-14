"""Call Dispositions API - Analytics for call dispositions."""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from typing import Optional
from datetime import datetime, timedelta, date
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.call_log import CallLog

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/analytics")
async def get_disposition_analytics(
    db: DbSession,
    current_user: CurrentUser,
    date_from: Optional[date] = Query(None, description="Analytics from this date"),
    date_to: Optional[date] = Query(None, description="Analytics to this date"),
):
    """Get call disposition analytics."""
    try:
        # Default to last 30 days if no date range specified
        if not date_from:
            date_from = date.today() - timedelta(days=30)
        if not date_to:
            date_to = date.today()

        # Get all calls with dispositions in date range
        result = await db.execute(
            select(CallLog).where(
                CallLog.call_date >= date_from,
                CallLog.call_date <= date_to,
                CallLog.call_disposition.isnot(None)
            )
        )
        calls = result.scalars().all()

        # Count calls by disposition
        disposition_counts = {}
        total_calls = len(calls)

        for call in calls:
            disp = call.call_disposition or "unknown"
            disposition_counts[disp] = disposition_counts.get(disp, 0) + 1

        # Calculate percentages and format response
        disposition_stats = []
        for disposition, count in disposition_counts.items():
            percentage = (count / total_calls) * 100 if total_calls > 0 else 0
            disposition_stats.append({
                "disposition": disposition,
                "count": count,
                "percentage": round(percentage, 1),
                "color": "#6B7280"  # Default color, could be customized
            })

        # Sort by count descending
        disposition_stats.sort(key=lambda x: x["count"], reverse=True)

        return {
            "stats": disposition_stats,
            "total_calls": total_calls,
            "date_range": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat()
            },
            "top_disposition": disposition_stats[0]["disposition"] if disposition_stats else None,
            "updated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting disposition analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))