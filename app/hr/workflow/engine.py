from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.hr.shared.audit import write_audit
from app.hr.shared.role_resolver import SUBJECT_ROLES, resolve_role
from app.hr.workflow.models import (
    HrWorkflowInstance,
    HrWorkflowTask,
    HrWorkflowTaskDependency,
    HrWorkflowTemplate,
    HrWorkflowTemplateDependency,
    HrWorkflowTemplateTask,
)
from app.hr.workflow.schemas import TemplateIn


async def create_template(
    db: AsyncSession,
    payload: TemplateIn,
    *,
    created_by: int | None = None,
) -> HrWorkflowTemplate:
    template = HrWorkflowTemplate(
        name=payload.name,
        category=payload.category,
        version=1,
        created_by=created_by,
    )
    db.add(template)
    await db.flush()

    position_to_task: dict[int, HrWorkflowTemplateTask] = {}
    for t in payload.tasks:
        tt = HrWorkflowTemplateTask(
            template_id=template.id,
            position=t.position,
            stage=t.stage,
            name=t.name,
            description=t.description,
            kind=t.kind,
            assignee_role=t.assignee_role,
            due_offset_days=t.due_offset_days,
            required=t.required,
            config=t.config,
        )
        db.add(tt)
        await db.flush()
        position_to_task[t.position] = tt

    for t in payload.tasks:
        for dep_pos in t.depends_on_positions:
            if dep_pos not in position_to_task:
                raise ValueError(
                    f"task position {t.position} depends on missing position {dep_pos}"
                )
            db.add(
                HrWorkflowTemplateDependency(
                    task_id=position_to_task[t.position].id,
                    depends_on_task_id=position_to_task[dep_pos].id,
                )
            )
    await db.flush()
    return template


async def spawn_instance(
    db: AsyncSession,
    *,
    template_id: UUID,
    subject_type: str,
    subject_id: UUID,
    started_by: int | None = None,
    start_date: datetime | None = None,
) -> HrWorkflowInstance:
    start = start_date or datetime.now(timezone.utc)

    template = (
        await db.execute(
            select(HrWorkflowTemplate)
            .options(selectinload(HrWorkflowTemplate.tasks))
            .where(
                HrWorkflowTemplate.id == template_id,
                HrWorkflowTemplate.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if template is None:
        raise ValueError(f"template {template_id} not found or inactive")

    template_task_ids = [t.id for t in template.tasks]
    deps_rows = (
        await db.execute(
            select(HrWorkflowTemplateDependency).where(
                HrWorkflowTemplateDependency.task_id.in_(template_task_ids)
            )
        )
    ).scalars().all()
    template_deps_by_task: dict[UUID, list[UUID]] = {}
    for d in deps_rows:
        template_deps_by_task.setdefault(d.task_id, []).append(d.depends_on_task_id)

    instance = HrWorkflowInstance(
        template_id=template.id,
        template_version=template.version,
        subject_type=subject_type,
        subject_id=subject_id,
        started_by=started_by,
    )
    db.add(instance)
    await db.flush()

    template_task_to_instance_task: dict[UUID, HrWorkflowTask] = {}
    for tt in template.tasks:
        resolved = await resolve_role(db, role=tt.assignee_role, subject_id=subject_id)
        # Subject-based roles return a UUID that belongs in assignee_subject_id,
        # not assignee_user_id (which is Integer FK api_users.id).
        if tt.assignee_role in SUBJECT_ROLES:
            assignee_user_id = None
            assignee_subject_id = resolved if isinstance(resolved, UUID) else subject_id
        else:
            assignee_user_id = resolved if isinstance(resolved, int) else None
            assignee_subject_id = None

        task = HrWorkflowTask(
            instance_id=instance.id,
            template_task_id=tt.id,
            position=tt.position,
            stage=tt.stage,
            name=tt.name,
            kind=tt.kind,
            assignee_user_id=assignee_user_id,
            assignee_subject_id=assignee_subject_id,
            assignee_role=tt.assignee_role,
            status="blocked" if tt.id in template_deps_by_task else "ready",
            due_at=start + timedelta(days=tt.due_offset_days),
            config=tt.config or {},
            result={},
        )
        db.add(task)
        await db.flush()
        template_task_to_instance_task[tt.id] = task

    for tt_id, dep_tt_ids in template_deps_by_task.items():
        task = template_task_to_instance_task[tt_id]
        for dep_tt_id in dep_tt_ids:
            dep_task = template_task_to_instance_task[dep_tt_id]
            db.add(
                HrWorkflowTaskDependency(
                    task_id=task.id, depends_on_task_id=dep_task.id
                )
            )

    await db.flush()
    await write_audit(
        db,
        entity_type="workflow_instance",
        entity_id=instance.id,
        event="spawned",
        diff={"template_id": [None, str(template.id)]},
        actor_user_id=started_by,
    )
    return instance
