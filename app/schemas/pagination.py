"""Cursor-based pagination schemas and utilities.

Cursor pagination is more efficient than offset pagination for large datasets
because it doesn't require counting all rows or skipping rows.
"""

from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional, List
from datetime import datetime
import base64
import json

T = TypeVar("T")


class CursorPaginationParams(BaseModel):
    """Parameters for cursor-based pagination requests."""

    cursor: Optional[str] = Field(
        default=None,
        description="Base64 encoded cursor for fetching next page",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page (max 100)",
    )


class CursorPaginatedResponse(BaseModel, Generic[T]):
    """Generic response for cursor-paginated endpoints."""

    items: List[T]
    next_cursor: Optional[str] = Field(
        default=None,
        description="Cursor for fetching the next page (null if no more pages)",
    )
    has_more: bool = Field(
        description="Whether there are more items after this page",
    )
    total: Optional[int] = Field(
        default=None,
        description="Total count (optional, may be omitted for performance)",
    )

    class Config:
        from_attributes = True


def encode_cursor(id: int, created_at: datetime) -> str:
    """Encode pagination cursor from ID and timestamp.

    Uses both ID and created_at to ensure stable pagination even when
    multiple records have the same timestamp.
    """
    data = {
        "id": id,
        "ts": created_at.isoformat() if created_at else None,
    }
    json_str = json.dumps(data, separators=(",", ":"))
    return base64.urlsafe_b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> tuple[int, Optional[datetime]]:
    """Decode pagination cursor to ID and timestamp.

    Returns:
        Tuple of (id, created_at datetime or None)

    Raises:
        ValueError: If cursor is invalid or malformed
    """
    try:
        json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(json_str)
        cursor_id = int(data["id"])
        cursor_ts = None
        if data.get("ts"):
            cursor_ts = datetime.fromisoformat(data["ts"])
        return cursor_id, cursor_ts
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        raise ValueError(f"Invalid cursor format: {e}")
