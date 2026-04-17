"""seed lifecycle workflow templates (onboarding 23 tasks, offboarding 14 tasks)

Revision ID: 104
Revises: 103
"""
import json
import uuid

from alembic import op
from sqlalchemy import text


revision = "104"
down_revision = "103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.hr.onboarding.seed import LIFECYCLE_TEMPLATES

    bind = op.get_bind()

    for template in LIFECYCLE_TEMPLATES:
        existing = bind.execute(
            text(
                "SELECT id FROM hr_workflow_templates WHERE name = :n"
            ),
            {"n": template["name"]},
        ).scalar_one_or_none()
        if existing is not None:
            continue

        template_id = uuid.uuid4()
        bind.execute(
            text(
                "INSERT INTO hr_workflow_templates "
                "(id, name, category, version, is_active) "
                "VALUES (CAST(:id AS uuid), :name, :category, 1, true)"
            ),
            {
                "id": str(template_id),
                "name": template["name"],
                "category": template["category"],
            },
        )

        position_to_task_id: dict[int, str] = {}
        for task in template["tasks"]:
            task_id = uuid.uuid4()
            position_to_task_id[task["position"]] = str(task_id)
            bind.execute(
                text(
                    "INSERT INTO hr_workflow_template_tasks "
                    "(id, template_id, position, stage, name, kind, assignee_role, "
                    " due_offset_days, required, config) "
                    "VALUES (CAST(:id AS uuid), CAST(:tid AS uuid), :pos, :stage, "
                    "        :name, :kind, :role, :due, :req, CAST(:cfg AS json))"
                ),
                {
                    "id": str(task_id),
                    "tid": str(template_id),
                    "pos": task["position"],
                    "stage": task.get("stage"),
                    "name": task["name"],
                    "kind": task["kind"],
                    "role": task["assignee_role"],
                    "due": task.get("due_offset_days", 0),
                    "req": task.get("required", True),
                    "cfg": json.dumps(task.get("config", {})),
                },
            )

        for task in template["tasks"]:
            for dep_pos in task.get("depends_on", []):
                bind.execute(
                    text(
                        "INSERT INTO hr_workflow_template_dependencies "
                        "(task_id, depends_on_task_id) "
                        "VALUES (CAST(:t AS uuid), CAST(:d AS uuid))"
                    ),
                    {
                        "t": position_to_task_id[task["position"]],
                        "d": position_to_task_id[dep_pos],
                    },
                )


def downgrade() -> None:
    # Load template names to find + delete.
    op.execute(
        "DELETE FROM hr_workflow_template_dependencies "
        "WHERE task_id IN (SELECT id FROM hr_workflow_template_tasks "
        "                  WHERE template_id IN (SELECT id FROM hr_workflow_templates "
        "                                        WHERE name IN ('New Field Tech Onboarding','Tech Separation')))"
    )
    op.execute(
        "DELETE FROM hr_workflow_template_tasks "
        "WHERE template_id IN (SELECT id FROM hr_workflow_templates "
        "                      WHERE name IN ('New Field Tech Onboarding','Tech Separation'))"
    )
    op.execute(
        "DELETE FROM hr_workflow_templates "
        "WHERE name IN ('New Field Tech Onboarding','Tech Separation')"
    )
