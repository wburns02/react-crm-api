"""
SMS Inbox Endpoints

Real implementation of SMS conversation listing for the SMS Inbox UI.
Replaces the prior stub that returned an empty list.

The frontend (src/features/communications/pages/SMSInbox.tsx) calls
GET /api/v2/sms/conversations and expects items shaped like:
    {
      id: string,                 # phone number used as stable thread key
      customer_name: str | None,
      phone_number: str,
      last_message: str,
      last_message_time: ISO-8601 datetime,
      unread_count: int,
      direction: 'inbound' | 'outbound',
    }

We group SMS messages by the "other party" phone number — for inbound
messages that's `from_number`, for outbound that's `to_number`. We then
aggregate per phone for last message, unread count, and total count.
"""

from __future__ import annotations

import logging
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import DbSession, CurrentUser
from app.schemas.types import UUIDStr

logger = logging.getLogger(__name__)

router = APIRouter()


class ConversationItem(BaseModel):
    """A single SMS thread aggregated by other-party phone number."""

    id: str  # phone number used as stable id (frontend routes /sms/{id})
    customer_id: Optional[UUIDStr] = None
    customer_name: Optional[str] = None
    phone_number: str
    last_message: str
    last_message_time: Optional[str] = None
    last_direction: str
    direction: str  # alias of last_direction for frontend compatibility
    unread_count: int = 0
    total_count: int = 0


class ConversationListResponse(BaseModel):
    items: List[ConversationItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Static routes BEFORE catch-all /{id} routes (none exist here yet, but
# follow the rule).
# ---------------------------------------------------------------------------


@router.get("/conversations", response_model=ConversationListResponse)
async def list_sms_conversations(
    db: DbSession,
    current_user: CurrentUser,
    search: Optional[str] = Query(None, description="Search phone or customer name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    List SMS conversation threads grouped by the "other party" phone number.

    For inbound messages the other party is `from_number`; for outbound
    messages it's `to_number`. We use a single SQL aggregation grouped by that
    derived phone, joined to the most recent message via DISTINCT ON, and
    finally joined to customers (when linked) for the display name.
    """
    offset = (page - 1) * page_size

    # SQL: derive the other-party phone, then aggregate per phone, then
    # pick the latest message per phone via DISTINCT ON.
    #
    # We do this in one CTE pipeline:
    #   1. base: messages WHERE type='sms' with other_phone derived
    #   2. agg: GROUP BY other_phone -> total_count, unread_count, last_at
    #   3. last_msg: DISTINCT ON (other_phone) latest message details
    #   4. join with customers (best-effort: by customer_id, else by phone)
    sql = text(
        """
        WITH base AS (
            SELECT
                m.id,
                m.customer_id,
                m.direction::text AS direction,
                m.content,
                m.read_at,
                m.created_at,
                CASE
                    WHEN m.direction::text = 'inbound' THEN m.from_number
                    ELSE m.to_number
                END AS other_phone
            FROM messages m
            WHERE m.type = 'sms'
              AND (
                (m.direction::text = 'inbound'  AND m.from_number IS NOT NULL AND m.from_number <> '')
                OR
                (m.direction::text = 'outbound' AND m.to_number   IS NOT NULL AND m.to_number   <> '')
              )
        ),
        agg AS (
            SELECT
                other_phone,
                COUNT(*) AS total_count,
                SUM(CASE WHEN direction = 'inbound' AND read_at IS NULL THEN 1 ELSE 0 END) AS unread_count,
                MAX(created_at) AS last_message_at
            FROM base
            GROUP BY other_phone
        ),
        last_msg AS (
            SELECT DISTINCT ON (other_phone)
                other_phone,
                content       AS last_content,
                direction     AS last_direction,
                created_at    AS last_at,
                customer_id   AS last_customer_id
            FROM base
            ORDER BY other_phone, created_at DESC
        )
        SELECT
            a.other_phone                                   AS phone_number,
            a.total_count                                   AS total_count,
            COALESCE(a.unread_count, 0)                     AS unread_count,
            a.last_message_at                               AS last_message_at,
            lm.last_content                                 AS last_content,
            lm.last_direction                               AS last_direction,
            COALESCE(c_by_id.id, c_by_phone.id)             AS customer_id,
            COALESCE(c_by_id.first_name, c_by_phone.first_name) AS first_name,
            COALESCE(c_by_id.last_name,  c_by_phone.last_name)  AS last_name
        FROM agg a
        JOIN last_msg lm ON lm.other_phone = a.other_phone
        LEFT JOIN customers c_by_id    ON c_by_id.id = lm.last_customer_id
        LEFT JOIN customers c_by_phone ON c_by_id.id IS NULL
                                       AND c_by_phone.phone = a.other_phone
        WHERE
            (CAST(:search AS TEXT) IS NULL)
            OR a.other_phone ILIKE '%' || CAST(:search AS TEXT) || '%'
            OR COALESCE(c_by_id.first_name, c_by_phone.first_name, '') ILIKE '%' || CAST(:search AS TEXT) || '%'
            OR COALESCE(c_by_id.last_name,  c_by_phone.last_name,  '') ILIKE '%' || CAST(:search AS TEXT) || '%'
            OR lm.last_content ILIKE '%' || CAST(:search AS TEXT) || '%'
        ORDER BY a.last_message_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
        """
    )

    count_sql = text(
        """
        WITH base AS (
            SELECT
                CASE
                    WHEN m.direction::text = 'inbound' THEN m.from_number
                    ELSE m.to_number
                END AS other_phone
            FROM messages m
            WHERE m.type = 'sms'
              AND (
                (m.direction::text = 'inbound'  AND m.from_number IS NOT NULL AND m.from_number <> '')
                OR
                (m.direction::text = 'outbound' AND m.to_number   IS NOT NULL AND m.to_number   <> '')
              )
        )
        SELECT COUNT(DISTINCT other_phone) FROM base
        """
    )

    try:
        total_result = await db.execute(count_sql)
        total = int(total_result.scalar() or 0)

        rows = (
            await db.execute(
                sql,
                {
                    "search": search,
                    "limit": page_size,
                    "offset": offset,
                },
            )
        ).mappings().all()
    except Exception as e:
        logger.error("SMS conversations query failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load SMS conversations",
        )

    items: List[ConversationItem] = []
    for r in rows:
        first = (r.get("first_name") or "").strip()
        last = (r.get("last_name") or "").strip()
        full_name = (first + " " + last).strip() or None

        last_content = r.get("last_content") or ""
        preview = last_content[:200] if last_content else ""

        last_direction = r.get("last_direction") or "inbound"
        last_at = r.get("last_message_at")
        phone = r.get("phone_number") or ""

        items.append(
            ConversationItem(
                id=phone,
                customer_id=str(r["customer_id"]) if r.get("customer_id") else None,
                customer_name=full_name,
                phone_number=phone,
                last_message=preview,
                last_message_time=last_at.isoformat() if last_at else None,
                last_direction=last_direction,
                direction=last_direction,
                unread_count=int(r.get("unread_count") or 0),
                total_count=int(r.get("total_count") or 0),
            )
        )

    return ConversationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
