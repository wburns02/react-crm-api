"""
Workflow Automations API

CRUD for workflow automations + test execution + execution history.
"""
from datetime import datetime
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, CurrentUser
from app.models.workflow_automation import WorkflowAutomation, WorkflowExecution
from app.services.workflow_engine import execute_workflow, WORKFLOW_TEMPLATES

router = APIRouter()


# -- Pydantic schemas --

class WorkflowNodeSchema(BaseModel):
    id: str
    type: str
    category: str  # trigger, condition, action, delay
    config: dict = {}
    position_x: float = 300
    position_y: float = 0


class WorkflowEdgeSchema(BaseModel):
    source_id: str
    target_id: str
    condition_branch: Optional[str] = None  # "yes" | "no" | None


class WorkflowCreate(BaseModel):
    name: str = Field(max_length=200)
    description: Optional[str] = None
    trigger_type: str
    trigger_config: dict = {}
    nodes: list[dict] = []
    edges: list[dict] = []
    status: str = "draft"


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None
    nodes: Optional[list[dict]] = None
    edges: Optional[list[dict]] = None
    status: Optional[str] = None


# -- Endpoints --

@router.get("")
async def list_workflows(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    query = select(WorkflowAutomation).order_by(desc(WorkflowAutomation.created_at))
    count_query = select(func.count(WorkflowAutomation.id))

    if status_filter:
        query = query.where(WorkflowAutomation.status == status_filter)
        count_query = count_query.where(WorkflowAutomation.status == status_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    workflows = result.scalars().all()

    return {
        "items": [_serialize_workflow(w) for w in workflows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workflow(
    data: WorkflowCreate,
    db: DbSession,
    user: CurrentUser,
):
    workflow = WorkflowAutomation(
        id=uuid4(),
        name=data.name,
        description=data.description,
        trigger_type=data.trigger_type,
        trigger_config=data.trigger_config,
        nodes=data.nodes,
        edges=data.edges,
        status=data.status,
        created_by=user.id,
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return _serialize_workflow(workflow)


@router.get("/templates")
async def get_templates(user: CurrentUser):
    return {"templates": WORKFLOW_TEMPLATES}


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    db: DbSession,
    user: CurrentUser,
):
    workflow = await _get_workflow_or_404(db, workflow_id)

    # Include recent executions
    exec_result = await db.execute(
        select(WorkflowExecution)
        .where(WorkflowExecution.workflow_id == workflow.id)
        .order_by(desc(WorkflowExecution.started_at))
        .limit(10)
    )
    executions = exec_result.scalars().all()

    result = _serialize_workflow(workflow)
    result["recent_executions"] = [_serialize_execution(e) for e in executions]
    return result


@router.patch("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    data: WorkflowUpdate,
    db: DbSession,
    user: CurrentUser,
):
    workflow = await _get_workflow_or_404(db, workflow_id)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(workflow, key, value)

    workflow.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(workflow)
    return _serialize_workflow(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: str,
    db: DbSession,
    user: CurrentUser,
):
    workflow = await _get_workflow_or_404(db, workflow_id)
    await db.delete(workflow)
    await db.commit()


@router.post("/{workflow_id}/test")
async def test_workflow(
    workflow_id: str,
    db: DbSession,
    user: CurrentUser,
):
    workflow = await _get_workflow_or_404(db, workflow_id)

    sample_data = {
        "customer_name": "John Smith",
        "customer_phone": "+15125551234",
        "customer_email": "john@example.com",
        "work_order_id": "WO-12345",
        "invoice_id": "INV-67890",
        "amount": "450.00",
        "service_type": "aerobic",
        "status": "completed",
        "customer_tags": ["vip", "annual_contract"],
    }

    result = await execute_workflow(workflow, sample_data, db=None, dry_run=True)
    return result


@router.post("/{workflow_id}/toggle")
async def toggle_workflow(
    workflow_id: str,
    db: DbSession,
    user: CurrentUser,
):
    workflow = await _get_workflow_or_404(db, workflow_id)

    if workflow.status == "active":
        workflow.status = "paused"
    elif workflow.status in ("paused", "draft"):
        workflow.status = "active"

    workflow.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(workflow)
    return _serialize_workflow(workflow)


@router.get("/{workflow_id}/executions")
async def list_executions(
    workflow_id: str,
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    await _get_workflow_or_404(db, workflow_id)

    count_result = await db.execute(
        select(func.count(WorkflowExecution.id))
        .where(WorkflowExecution.workflow_id == workflow_id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(WorkflowExecution)
        .where(WorkflowExecution.workflow_id == workflow_id)
        .order_by(desc(WorkflowExecution.started_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    executions = result.scalars().all()

    return {
        "items": [_serialize_execution(e) for e in executions],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# -- Helpers --

async def _get_workflow_or_404(db: AsyncSession, workflow_id: str) -> WorkflowAutomation:
    result = await db.execute(
        select(WorkflowAutomation).where(WorkflowAutomation.id == workflow_id)
    )
    workflow = result.scalars().first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


def _serialize_workflow(w: WorkflowAutomation) -> dict:
    return {
        "id": str(w.id),
        "name": w.name,
        "description": w.description,
        "trigger_type": w.trigger_type,
        "trigger_config": w.trigger_config or {},
        "nodes": w.nodes or [],
        "edges": w.edges or [],
        "status": w.status or "draft",
        "run_count": w.run_count or 0,
        "last_run_at": w.last_run_at.isoformat() if w.last_run_at else None,
        "created_by": str(w.created_by) if w.created_by else None,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }


def _serialize_execution(e: WorkflowExecution) -> dict:
    return {
        "id": str(e.id),
        "workflow_id": str(e.workflow_id),
        "trigger_event": e.trigger_event,
        "steps_executed": e.steps_executed or [],
        "status": e.status or "unknown",
        "error_message": e.error_message,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
    }
