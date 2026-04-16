from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.shared.models import HrAuditLog


async def write_audit(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: UUID,
    event: str,
    diff: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
    actor_ip: str | None = None,
    actor_user_agent: str | None = None,
    actor_location: str | None = None,
) -> HrAuditLog:
    """Append an immutable audit row.

    `actor_user_id` is an integer because `api_users.id` is an Integer PK —
    see app/hr/PLAN_CORRECTIONS.md.
    """
    row = HrAuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        event=event,
        diff=diff or {},
        actor_user_id=actor_user_id,
        actor_ip=actor_ip,
        actor_user_agent=actor_user_agent,
        actor_location=actor_location,
    )
    db.add(row)
    await db.flush()
    return row
