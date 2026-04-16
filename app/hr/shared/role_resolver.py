from typing import Union
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.shared.models import HrRoleAssignment


SUBJECT_ROLES = {"hire", "employee"}


async def resolve_role(
    db: AsyncSession,
    *,
    role: str,
    subject_id: UUID | None = None,
) -> Union[int, UUID, None]:
    """Resolve an `assignee_role` string to a concrete identity.

    Returns:
      * `subject_id` (UUID) when the role is a subject role (`hire`, `employee`).
        The engine MUST NOT persist this into `HrWorkflowTask.assignee_user_id`
        (which is an Integer FK to api_users.id). Leave that column NULL and let
        the UI derive the subject from `(assignee_role, instance.subject_id)`.
      * `user_id` (int) from the highest-priority active assignment for the role.
      * `None` if no active assignment exists.
    """
    if role in SUBJECT_ROLES:
        return subject_id

    stmt = (
        select(HrRoleAssignment.user_id)
        .where(HrRoleAssignment.role == role, HrRoleAssignment.active.is_(True))
        .order_by(HrRoleAssignment.priority.desc(), HrRoleAssignment.created_at.asc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
