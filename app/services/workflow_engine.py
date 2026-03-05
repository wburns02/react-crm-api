"""
Workflow Automation Engine

Evaluates triggers, walks through workflow nodes/edges,
executes actions, and logs execution steps.
"""
import logging
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_automation import WorkflowAutomation, WorkflowExecution

logger = logging.getLogger(__name__)


# -- Template variable resolution --

def resolve_template(template: str, context: dict[str, Any]) -> str:
    result = template
    for key, value in context.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


# -- Condition evaluators --

def _check_field_value(config: dict, context: dict) -> bool:
    field = config.get("field", "")
    operator = config.get("operator", "equals")
    expected = config.get("value", "")
    actual = str(context.get(field, ""))

    if operator == "equals":
        return actual == str(expected)
    elif operator == "contains":
        return str(expected) in actual
    elif operator == "greater_than":
        try:
            return float(actual) > float(expected)
        except (ValueError, TypeError):
            return False
    elif operator == "less_than":
        try:
            return float(actual) < float(expected)
        except (ValueError, TypeError):
            return False
    elif operator == "is_empty":
        return not actual or actual == "None"
    return False


def _check_customer_tag(config: dict, context: dict) -> bool:
    tag = config.get("tag", "")
    has_tag = config.get("has_tag", True)
    customer_tags = context.get("customer_tags", [])
    found = tag in customer_tags
    return found if has_tag else not found


def _check_service_type(config: dict, context: dict) -> bool:
    return context.get("service_type", "") == config.get("service_type", "")


def _check_amount(config: dict, context: dict) -> bool:
    operator = config.get("operator", "greater_than")
    threshold = float(config.get("amount", 0))
    actual = float(context.get("amount", 0))
    if operator == "greater_than":
        return actual > threshold
    elif operator == "less_than":
        return actual < threshold
    elif operator == "equals":
        return actual == threshold
    return False


def _check_time_window(config: dict, _context: dict) -> bool:
    now = datetime.now()
    start_hour = config.get("start_hour", 8)
    end_hour = config.get("end_hour", 17)
    days = config.get("days_of_week", [0, 1, 2, 3, 4])  # Mon-Fri
    return now.weekday() in days and start_hour <= now.hour < end_hour


CONDITION_EVALUATORS = {
    "check_field_value": _check_field_value,
    "check_customer_tag": _check_customer_tag,
    "check_service_type": _check_service_type,
    "check_amount": _check_amount,
    "time_window": _check_time_window,
}


# -- Action handlers (simulated for now) --

async def _send_sms(config: dict, context: dict) -> dict:
    message = resolve_template(config.get("message", ""), context)
    return {"action": "send_sms", "to": context.get("customer_phone", "N/A"), "message": message, "simulated": True}


async def _send_email(config: dict, context: dict) -> dict:
    subject = resolve_template(config.get("subject", ""), context)
    body = resolve_template(config.get("body", ""), context)
    return {"action": "send_email", "to": context.get("customer_email", "N/A"), "subject": subject, "simulated": True}


async def _create_work_order(config: dict, context: dict) -> dict:
    desc = resolve_template(config.get("description", ""), context)
    return {"action": "create_work_order", "service_type": config.get("service_type", ""), "description": desc, "simulated": True}


async def _generate_invoice(config: dict, context: dict) -> dict:
    return {"action": "generate_invoice", "include_tax": config.get("include_tax", True), "simulated": True}


async def _update_field(config: dict, context: dict) -> dict:
    return {"action": "update_field", "entity": config.get("entity", ""), "field": config.get("field", ""), "value": config.get("value", ""), "simulated": True}


async def _create_task(config: dict, context: dict) -> dict:
    title = resolve_template(config.get("title", ""), context)
    return {"action": "create_task", "title": title, "assign_to": config.get("assign_to", ""), "priority": config.get("priority", "medium"), "simulated": True}


async def _add_note(config: dict, context: dict) -> dict:
    text = resolve_template(config.get("text", ""), context)
    return {"action": "add_note", "text": text, "simulated": True}


async def _call_webhook(config: dict, context: dict) -> dict:
    return {"action": "webhook", "url": config.get("url", ""), "simulated": True}


ACTION_HANDLERS = {
    "send_sms": _send_sms,
    "send_email": _send_email,
    "create_work_order": _create_work_order,
    "generate_invoice": _generate_invoice,
    "update_field": _update_field,
    "create_task": _create_task,
    "add_note": _add_note,
    "webhook": _call_webhook,
}


# -- Engine --

def _build_adjacency(nodes: list[dict], edges: list[dict]) -> dict[str, list[dict]]:
    """Build node_id -> list of {target_id, condition_branch} adjacency map."""
    adj: dict[str, list[dict]] = {}
    for edge in edges:
        src = edge.get("source_id", "")
        if src not in adj:
            adj[src] = []
        adj[src].append({"target_id": edge.get("target_id", ""), "branch": edge.get("condition_branch")})
    return adj


def _nodes_by_id(nodes: list[dict]) -> dict[str, dict]:
    return {n["id"]: n for n in nodes}


async def execute_workflow(
    workflow: WorkflowAutomation,
    trigger_data: dict,
    db: AsyncSession | None = None,
    dry_run: bool = False,
) -> dict:
    """Execute a workflow's nodes, returning the execution result."""
    nodes = workflow.nodes or []
    edges = workflow.edges or []

    if not nodes:
        return {"status": "skipped", "steps": [], "error": "No nodes in workflow"}

    adj = _build_adjacency(nodes, edges)
    node_map = _nodes_by_id(nodes)
    context = {**trigger_data}
    steps = []
    current_ids = [nodes[0]["id"]]  # Start with first node (trigger)

    # Record trigger step
    trigger_node = node_map.get(nodes[0]["id"], {})
    steps.append({
        "node_id": nodes[0]["id"],
        "type": trigger_node.get("type", "trigger"),
        "action": f"Trigger: {trigger_node.get('type', 'unknown')}",
        "result": "fired",
        "timestamp": datetime.utcnow().isoformat(),
    })

    visited = set()
    max_iterations = 50

    while current_ids and max_iterations > 0:
        max_iterations -= 1
        next_ids = []

        for node_id in current_ids:
            if node_id in visited:
                continue
            visited.add(node_id)

            node = node_map.get(node_id)
            if not node:
                continue

            category = node.get("category", "")
            node_type = node.get("type", "")
            config = node.get("config", {})

            # Process conditions
            if category == "condition":
                evaluator = CONDITION_EVALUATORS.get(node_type)
                if evaluator:
                    result = evaluator(config, context)
                    steps.append({
                        "node_id": node_id,
                        "type": node_type,
                        "action": f"Condition: {node_type}",
                        "result": "yes" if result else "no",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    # Follow the correct branch
                    for edge in adj.get(node_id, []):
                        if edge.get("branch") == ("yes" if result else "no") or edge.get("branch") is None:
                            next_ids.append(edge["target_id"])
                    continue

            # Process actions
            if category == "action":
                handler = ACTION_HANDLERS.get(node_type)
                if handler:
                    try:
                        result = await handler(config, context)
                        steps.append({
                            "node_id": node_id,
                            "type": node_type,
                            "action": f"Action: {node_type}",
                            "result": result,
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                    except Exception as e:
                        steps.append({
                            "node_id": node_id,
                            "type": node_type,
                            "action": f"Action: {node_type}",
                            "result": {"error": str(e)},
                            "timestamp": datetime.utcnow().isoformat(),
                        })

            # Process delays (simulated)
            if category == "delay":
                amount = config.get("amount", 1)
                unit = config.get("unit", "hours")
                steps.append({
                    "node_id": node_id,
                    "type": node_type,
                    "action": f"Delay: {amount} {unit}",
                    "result": "simulated" if dry_run else "queued",
                    "timestamp": datetime.utcnow().isoformat(),
                })

            # Follow edges to next nodes
            for edge in adj.get(node_id, []):
                next_ids.append(edge["target_id"])

        current_ids = next_ids

    execution_result = {
        "status": "completed",
        "steps": steps,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
    }

    # Persist execution record if not dry run
    if db and not dry_run:
        execution = WorkflowExecution(
            id=uuid4(),
            workflow_id=workflow.id,
            trigger_event=trigger_data,
            steps_executed=steps,
            status="completed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db.add(execution)

        await db.execute(
            update(WorkflowAutomation)
            .where(WorkflowAutomation.id == workflow.id)
            .values(run_count=WorkflowAutomation.run_count + 1, last_run_at=datetime.utcnow())
        )
        await db.commit()

    return execution_result


# -- Pre-built templates --

WORKFLOW_TEMPLATES = [
    {
        "id": "tpl-job-complete-invoice-sms",
        "name": "Job Complete → Invoice & SMS",
        "description": "Automatically generate an invoice and send customer an SMS when a job is completed.",
        "trigger_type": "work_order_status_changed",
        "trigger_config": {"status": "completed"},
        "nodes": [
            {"id": "n1", "type": "work_order_status_changed", "category": "trigger", "config": {"status": "completed"}, "position_x": 300, "position_y": 50},
            {"id": "n2", "type": "generate_invoice", "category": "action", "config": {"include_tax": True}, "position_x": 300, "position_y": 200},
            {"id": "n3", "type": "send_sms", "category": "action", "config": {"message": "Hi {{customer_name}}, your service is complete! Invoice #{{invoice_id}} for ${{amount}} has been sent."}, "position_x": 300, "position_y": 350},
        ],
        "edges": [
            {"source_id": "n1", "target_id": "n2"},
            {"source_id": "n2", "target_id": "n3"},
        ],
    },
    {
        "id": "tpl-overdue-payment-reminder",
        "name": "Overdue Payment Reminder",
        "description": "Send escalating reminders for overdue invoices: SMS after 1 day, email after 8 days, task after 15 days.",
        "trigger_type": "invoice_overdue",
        "trigger_config": {"days_overdue": 7},
        "nodes": [
            {"id": "n1", "type": "invoice_overdue", "category": "trigger", "config": {"days_overdue": 7}, "position_x": 300, "position_y": 50},
            {"id": "n2", "type": "wait_duration", "category": "delay", "config": {"amount": 1, "unit": "days"}, "position_x": 300, "position_y": 200},
            {"id": "n3", "type": "send_sms", "category": "action", "config": {"message": "Hi {{customer_name}}, you have an outstanding invoice of ${{amount}}. Please remit payment at your earliest convenience."}, "position_x": 300, "position_y": 350},
            {"id": "n4", "type": "wait_duration", "category": "delay", "config": {"amount": 7, "unit": "days"}, "position_x": 300, "position_y": 500},
            {"id": "n5", "type": "send_email", "category": "action", "config": {"subject": "Payment Reminder - Invoice #{{invoice_id}}", "body": "Dear {{customer_name}},\n\nThis is a reminder that invoice #{{invoice_id}} for ${{amount}} is overdue. Please contact us if you have questions."}, "position_x": 300, "position_y": 650},
            {"id": "n6", "type": "create_task", "category": "action", "config": {"title": "Follow up on overdue invoice for {{customer_name}}", "assign_to": "admin", "priority": "high"}, "position_x": 300, "position_y": 800},
        ],
        "edges": [
            {"source_id": "n1", "target_id": "n2"},
            {"source_id": "n2", "target_id": "n3"},
            {"source_id": "n3", "target_id": "n4"},
            {"source_id": "n4", "target_id": "n5"},
            {"source_id": "n5", "target_id": "n6"},
        ],
    },
    {
        "id": "tpl-new-customer-welcome",
        "name": "New Customer Welcome",
        "description": "Send a welcome email and schedule a follow-up task when a new customer is created.",
        "trigger_type": "new_customer_created",
        "trigger_config": {},
        "nodes": [
            {"id": "n1", "type": "new_customer_created", "category": "trigger", "config": {}, "position_x": 300, "position_y": 50},
            {"id": "n2", "type": "send_email", "category": "action", "config": {"subject": "Welcome to Mac Service Platform!", "body": "Hi {{customer_name}},\n\nWelcome! We're excited to serve you. Our team will reach out shortly to schedule your initial site evaluation."}, "position_x": 300, "position_y": 200},
            {"id": "n3", "type": "wait_duration", "category": "delay", "config": {"amount": 3, "unit": "days"}, "position_x": 300, "position_y": 350},
            {"id": "n4", "type": "create_task", "category": "action", "config": {"title": "Schedule initial site evaluation for {{customer_name}}", "assign_to": "admin", "priority": "medium"}, "position_x": 300, "position_y": 500},
        ],
        "edges": [
            {"source_id": "n1", "target_id": "n2"},
            {"source_id": "n2", "target_id": "n3"},
            {"source_id": "n3", "target_id": "n4"},
        ],
    },
    {
        "id": "tpl-contract-renewal-alert",
        "name": "Contract Renewal Alert",
        "description": "Notify team when contracts are expiring and create follow-up tasks.",
        "trigger_type": "contract_expiring",
        "trigger_config": {"days_before": 30},
        "nodes": [
            {"id": "n1", "type": "contract_expiring", "category": "trigger", "config": {"days_before": 30}, "position_x": 300, "position_y": 50},
            {"id": "n2", "type": "send_email", "category": "action", "config": {"subject": "Contract Renewal Reminder", "body": "Hi {{customer_name}}, your service contract expires soon. Contact us to discuss renewal options."}, "position_x": 300, "position_y": 200},
            {"id": "n3", "type": "wait_duration", "category": "delay", "config": {"amount": 14, "unit": "days"}, "position_x": 300, "position_y": 350},
            {"id": "n4", "type": "create_task", "category": "action", "config": {"title": "Call {{customer_name}} about contract renewal", "assign_to": "admin", "priority": "high"}, "position_x": 300, "position_y": 500},
        ],
        "edges": [
            {"source_id": "n1", "target_id": "n2"},
            {"source_id": "n2", "target_id": "n3"},
            {"source_id": "n3", "target_id": "n4"},
        ],
    },
    {
        "id": "tpl-service-follow-up",
        "name": "Service Follow-Up",
        "description": "Schedule a follow-up maintenance check 30 days after an aerobic service is completed.",
        "trigger_type": "work_order_status_changed",
        "trigger_config": {"status": "completed"},
        "nodes": [
            {"id": "n1", "type": "work_order_status_changed", "category": "trigger", "config": {"status": "completed"}, "position_x": 300, "position_y": 50},
            {"id": "n2", "type": "check_service_type", "category": "condition", "config": {"service_type": "aerobic"}, "position_x": 300, "position_y": 200},
            {"id": "n3", "type": "wait_duration", "category": "delay", "config": {"amount": 30, "unit": "days"}, "position_x": 300, "position_y": 350},
            {"id": "n4", "type": "create_work_order", "category": "action", "config": {"service_type": "maintenance_check", "description": "30-day post-service check for {{customer_name}}"}, "position_x": 300, "position_y": 500},
        ],
        "edges": [
            {"source_id": "n1", "target_id": "n2"},
            {"source_id": "n2", "target_id": "n3", "condition_branch": "yes"},
            {"source_id": "n3", "target_id": "n4"},
        ],
    },
]
