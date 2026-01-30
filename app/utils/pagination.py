"""Pagination utilities for SQLAlchemy queries.

Provides helper functions for implementing cursor-based pagination
on SQLAlchemy async queries.
"""

from typing import TypeVar, Optional, Tuple, List, Any
from datetime import datetime
from sqlalchemy import and_, or_
from sqlalchemy.sql import Select

from app.schemas.pagination import encode_cursor, decode_cursor, CursorPaginatedResponse

T = TypeVar("T")


def apply_cursor_pagination(
    query: Select,
    model: Any,
    cursor: Optional[str],
    page_size: int,
    order_by_field: str = "created_at",
    descending: bool = True,
) -> Tuple[Select, int]:
    """Apply cursor-based pagination to a SQLAlchemy query.

    Args:
        query: The SQLAlchemy Select query
        model: The SQLAlchemy model class
        cursor: Base64 encoded cursor (or None for first page)
        page_size: Number of items to fetch
        order_by_field: Field to order by (default: created_at)
        descending: Whether to order descending (default: True)

    Returns:
        Tuple of (modified query, fetch_limit)
        fetch_limit is page_size + 1 to detect if there are more results
    """
    order_field = getattr(model, order_by_field)
    id_field = model.id

    # Apply cursor filter if provided
    if cursor:
        cursor_id, cursor_ts = decode_cursor(cursor)

        if descending:
            # For descending: get items BEFORE the cursor
            # (created_at < cursor_ts) OR (created_at == cursor_ts AND id < cursor_id)
            if cursor_ts:
                cursor_filter = or_(
                    order_field < cursor_ts,
                    and_(order_field == cursor_ts, id_field < cursor_id),
                )
            else:
                cursor_filter = id_field < cursor_id
        else:
            # For ascending: get items AFTER the cursor
            if cursor_ts:
                cursor_filter = or_(
                    order_field > cursor_ts,
                    and_(order_field == cursor_ts, id_field > cursor_id),
                )
            else:
                cursor_filter = id_field > cursor_id

        query = query.where(cursor_filter)

    # Apply ordering
    if descending:
        query = query.order_by(order_field.desc(), id_field.desc())
    else:
        query = query.order_by(order_field.asc(), id_field.asc())

    # Limit to page_size + 1 to check if there are more results
    fetch_limit = page_size + 1
    query = query.limit(fetch_limit)

    return query, fetch_limit


def build_cursor_response(
    items: List[T],
    page_size: int,
    order_by_field: str = "created_at",
    total: Optional[int] = None,
) -> CursorPaginatedResponse[T]:
    """Build a cursor-paginated response from query results.

    Args:
        items: List of items (may include one extra to detect has_more)
        page_size: Requested page size
        order_by_field: Field used for ordering (to build next cursor)
        total: Optional total count

    Returns:
        CursorPaginatedResponse with items, next_cursor, and has_more
    """
    has_more = len(items) > page_size
    result_items = items[:page_size]  # Trim to actual page size

    next_cursor = None
    if has_more and result_items:
        last_item = result_items[-1]
        last_id = getattr(last_item, "id")
        last_ts = getattr(last_item, order_by_field, None)
        next_cursor = encode_cursor(last_id, last_ts)

    return CursorPaginatedResponse(
        items=result_items,
        next_cursor=next_cursor,
        has_more=has_more,
        total=total,
    )
