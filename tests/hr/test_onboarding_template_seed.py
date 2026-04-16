"""Verify the two seeded workflow templates are wired correctly.

Seeds via the async session (same code path migration 104 exercises on real
Postgres) and asserts 23 + 14 tasks + dependencies.
"""
import json
import uuid

import pytest
from sqlalchemy import text


async def _seed_template(db, template: dict) -> uuid.UUID:
    template_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO hr_workflow_templates (id, name, category, version, is_active) "
            "VALUES (:id, :n, :c, 1, 1)"
        ),
        {"id": str(template_id), "n": template["name"], "c": template["category"]},
    )
    position_to_task_id = {}
    for task in template["tasks"]:
        tid = uuid.uuid4()
        position_to_task_id[task["position"]] = str(tid)
        await db.execute(
            text(
                "INSERT INTO hr_workflow_template_tasks "
                "(id, template_id, position, stage, name, kind, assignee_role, "
                " due_offset_days, required, config) "
                "VALUES (:id, :tid, :pos, :stage, :name, :kind, :role, :due, :req, :cfg)"
            ),
            {
                "id": str(tid),
                "tid": str(template_id),
                "pos": task["position"],
                "stage": task.get("stage"),
                "name": task["name"],
                "kind": task["kind"],
                "role": task["assignee_role"],
                "due": task.get("due_offset_days", 0),
                "req": int(task.get("required", True)),
                "cfg": json.dumps(task.get("config", {})),
            },
        )
    for task in template["tasks"]:
        for dep_pos in task.get("depends_on", []):
            await db.execute(
                text(
                    "INSERT INTO hr_workflow_template_dependencies "
                    "(task_id, depends_on_task_id) VALUES (:t, :d)"
                ),
                {
                    "t": position_to_task_id[task["position"]],
                    "d": position_to_task_id[dep_pos],
                },
            )
    await db.commit()
    return template_id


@pytest.mark.asyncio
async def test_onboarding_template_has_23_tasks(db):
    from app.hr.onboarding.seed import ONBOARDING_TEMPLATE
    tid = await _seed_template(db, ONBOARDING_TEMPLATE)

    r = await db.execute(
        text(
            "SELECT count(*) FROM hr_workflow_template_tasks WHERE template_id = :t"
        ),
        {"t": str(tid)},
    )
    assert r.scalar_one() == 23


@pytest.mark.asyncio
async def test_offboarding_template_has_14_tasks(db):
    from app.hr.onboarding.seed import OFFBOARDING_TEMPLATE
    tid = await _seed_template(db, OFFBOARDING_TEMPLATE)

    r = await db.execute(
        text(
            "SELECT count(*) FROM hr_workflow_template_tasks WHERE template_id = :t"
        ),
        {"t": str(tid)},
    )
    assert r.scalar_one() == 14


@pytest.mark.asyncio
async def test_onboarding_dependencies_wired(db):
    """Task 10 (Verify I-9 Section 2) depends on positions 2 and 7.
    Task 23 (Confirm all certs logged) depends on 8 and 9."""
    from app.hr.onboarding.seed import ONBOARDING_TEMPLATE
    tid = await _seed_template(db, ONBOARDING_TEMPLATE)

    # count deps for task at position 10
    r = await db.execute(
        text(
            "SELECT count(*) FROM hr_workflow_template_dependencies d "
            "JOIN hr_workflow_template_tasks t ON d.task_id = t.id "
            "WHERE t.template_id = :tid AND t.position = 10"
        ),
        {"tid": str(tid)},
    )
    assert r.scalar_one() == 2

    r = await db.execute(
        text(
            "SELECT count(*) FROM hr_workflow_template_dependencies d "
            "JOIN hr_workflow_template_tasks t ON d.task_id = t.id "
            "WHERE t.template_id = :tid AND t.position = 23"
        ),
        {"tid": str(tid)},
    )
    assert r.scalar_one() == 2


@pytest.mark.asyncio
async def test_offboarding_dependencies_wired(db):
    """Task 6 (inventory audit) depends on task 3 (return truck)."""
    from app.hr.onboarding.seed import OFFBOARDING_TEMPLATE
    tid = await _seed_template(db, OFFBOARDING_TEMPLATE)

    r = await db.execute(
        text(
            "SELECT count(*) FROM hr_workflow_template_dependencies d "
            "JOIN hr_workflow_template_tasks t ON d.task_id = t.id "
            "WHERE t.template_id = :tid AND t.position = 6"
        ),
        {"tid": str(tid)},
    )
    assert r.scalar_one() == 1
