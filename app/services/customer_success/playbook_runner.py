"""
Playbook Runner Service

Manages playbook execution, creating tasks for CSMs based on playbook steps,
tracking progress, and evaluating success criteria.
"""

from typing import Optional
from datetime import datetime, timedelta, date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_success import (
    Playbook, PlaybookStep, PlaybookExecution, CSTask, HealthScore
)


class PlaybookRunner:
    """
    Manages playbook execution for customers.

    Handles:
    - Triggering playbooks based on conditions
    - Creating tasks from playbook steps
    - Tracking execution progress
    - Evaluating success criteria
    """

    def __init__(self, db: AsyncSession):
        """Initialize runner with database session."""
        self.db = db

    async def trigger_playbook(
        self,
        playbook_id: int,
        customer_id: int,
        triggered_by: str,
        reason: Optional[str] = None,
        assigned_to_user_id: Optional[int] = None,
    ) -> PlaybookExecution:
        """
        Trigger a playbook for a customer.

        Args:
            playbook_id: The playbook to trigger
            customer_id: The customer to run it for
            triggered_by: Who/what triggered it (e.g., "user:123", "system:health_threshold")
            reason: Optional reason for triggering
            assigned_to_user_id: Optional user to assign all tasks to

        Returns:
            The created PlaybookExecution
        """
        # Get playbook with steps
        result = await self.db.execute(
            select(Playbook).where(Playbook.id == playbook_id)
        )
        playbook = result.scalar_one_or_none()

        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        if not playbook.is_active:
            raise ValueError(f"Playbook {playbook_id} is not active")

        # Check cooldown
        if playbook.cooldown_days:
            recent = await self._check_recent_execution(
                playbook_id, customer_id, playbook.cooldown_days
            )
            if recent:
                raise ValueError(
                    f"Playbook cooldown not elapsed. Last run: {recent.started_at}"
                )

        # Check max active executions
        if not playbook.allow_parallel_execution:
            active_count = await self._count_active_executions(playbook_id, customer_id)
            if active_count >= (playbook.max_active_per_customer or 1):
                raise ValueError("Max active executions reached")

        # Get steps
        steps_result = await self.db.execute(
            select(PlaybookStep)
            .where(
                PlaybookStep.playbook_id == playbook_id,
                PlaybookStep.is_active == True,
            )
            .order_by(PlaybookStep.step_order.asc())
        )
        steps = steps_result.scalars().all()

        # Get customer's current health score
        health_result = await self.db.execute(
            select(HealthScore).where(HealthScore.customer_id == customer_id)
        )
        health = health_result.scalar_one_or_none()

        # Create execution
        execution = PlaybookExecution(
            playbook_id=playbook_id,
            customer_id=customer_id,
            status="active",
            triggered_by=triggered_by,
            trigger_reason=reason,
            assigned_to_user_id=assigned_to_user_id,
            steps_total=len(steps),
            started_at=datetime.utcnow(),
            health_score_at_start=health.overall_score if health else None,
            target_completion_date=(
                datetime.utcnow() + timedelta(days=playbook.target_completion_days)
                if playbook.target_completion_days else None
            ),
        )
        self.db.add(execution)
        await self.db.flush()

        # Create tasks for steps
        for step in steps:
            task = await self._create_task_for_step(
                execution, step, customer_id, assigned_to_user_id
            )
            self.db.add(task)

        # Update playbook metrics
        playbook.times_triggered = (playbook.times_triggered or 0) + 1

        await self.db.commit()
        await self.db.refresh(execution)
        return execution

    async def process_executions(self) -> dict:
        """
        Process all active playbook executions.

        Checks:
        - Step completion status
        - Success criteria
        - Overdue tasks

        Returns:
            Processing summary
        """
        processed = 0
        completed = 0
        errors = []

        # Get active executions
        result = await self.db.execute(
            select(PlaybookExecution).where(PlaybookExecution.status == "active")
        )
        executions = result.scalars().all()

        for execution in executions:
            try:
                # Check completion
                is_complete = await self._check_execution_complete(execution)
                if is_complete:
                    await self._complete_execution(execution)
                    completed += 1
                processed += 1
            except Exception as e:
                errors.append({
                    "execution_id": execution.id,
                    "error": str(e),
                })

        await self.db.commit()

        return {
            "processed": processed,
            "completed": completed,
            "errors": errors,
        }

    async def update_execution_progress(self, execution_id: int) -> dict:
        """
        Update execution progress based on task status.

        Args:
            execution_id: The execution to update

        Returns:
            Updated progress info
        """
        result = await self.db.execute(
            select(PlaybookExecution).where(PlaybookExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        # Count completed tasks
        completed_result = await self.db.execute(
            select(func.count(CSTask.id)).where(
                CSTask.playbook_execution_id == execution_id,
                CSTask.status == "completed",
            )
        )
        completed_count = completed_result.scalar()

        # Get current step
        in_progress_result = await self.db.execute(
            select(CSTask)
            .where(
                CSTask.playbook_execution_id == execution_id,
                CSTask.status.in_(["pending", "in_progress"]),
            )
            .order_by(CSTask.due_date.asc().nullslast())
            .limit(1)
        )
        current_task = in_progress_result.scalar_one_or_none()

        # Update execution
        execution.steps_completed = completed_count
        if current_task and current_task.playbook_step_id:
            step_result = await self.db.execute(
                select(PlaybookStep).where(PlaybookStep.id == current_task.playbook_step_id)
            )
            step = step_result.scalar_one_or_none()
            if step:
                execution.current_step_order = step.step_order

        await self.db.commit()

        return {
            "execution_id": execution_id,
            "steps_completed": completed_count,
            "steps_total": execution.steps_total,
            "current_step": execution.current_step_order,
        }

    async def evaluate_triggers(self) -> dict:
        """
        Evaluate playbook triggers and create executions as needed.

        Checks:
        - Health threshold triggers
        - Days to renewal triggers
        - Event-based triggers

        Returns:
            Summary of triggered playbooks
        """
        triggered = []

        # Get active playbooks with automatic triggers
        result = await self.db.execute(
            select(Playbook).where(
                Playbook.is_active == True,
                Playbook.trigger_type != "manual",
            )
        )
        playbooks = result.scalars().all()

        for playbook in playbooks:
            customers_to_trigger = await self._find_customers_for_trigger(playbook)

            for customer_id in customers_to_trigger:
                try:
                    execution = await self.trigger_playbook(
                        playbook.id,
                        customer_id,
                        f"system:{playbook.trigger_type}",
                        f"Automatic trigger: {playbook.trigger_type}",
                    )
                    triggered.append({
                        "playbook_id": playbook.id,
                        "playbook_name": playbook.name,
                        "customer_id": customer_id,
                        "execution_id": execution.id,
                    })
                except ValueError:
                    # Cooldown or max executions reached
                    pass

        return {
            "evaluated_playbooks": len(playbooks),
            "triggered": triggered,
            "total_triggered": len(triggered),
        }

    async def _create_task_for_step(
        self,
        execution: PlaybookExecution,
        step: PlaybookStep,
        customer_id: int,
        assigned_to_user_id: Optional[int] = None,
    ) -> CSTask:
        """Create a task from a playbook step."""
        # Calculate due date
        due_date = None
        if step.due_days:
            start_date = execution.started_at or datetime.utcnow()
            days_offset = (step.days_from_start or 0) + step.due_days
            due_date = (start_date + timedelta(days=days_offset)).date()

        return CSTask(
            customer_id=customer_id,
            playbook_execution_id=execution.id,
            playbook_step_id=step.id,
            title=step.name,
            description=step.description,
            task_type=step.step_type if step.step_type in [
                "call", "email", "meeting", "review", "escalation",
                "training", "product_demo", "custom"
            ] else "custom",
            priority=execution.playbook.priority if execution.playbook else "medium",
            status="pending",
            assigned_to_user_id=assigned_to_user_id,
            assigned_to_role=step.default_assignee_role,
            due_date=due_date,
            instructions=step.instructions,
            talk_track=step.talk_track,
            required_artifacts=step.required_artifacts,
            source="playbook",
        )

    async def _check_recent_execution(
        self, playbook_id: int, customer_id: int, cooldown_days: int
    ) -> Optional[PlaybookExecution]:
        """Check for recent executions within cooldown period."""
        cooldown_start = datetime.utcnow() - timedelta(days=cooldown_days)
        result = await self.db.execute(
            select(PlaybookExecution).where(
                PlaybookExecution.playbook_id == playbook_id,
                PlaybookExecution.customer_id == customer_id,
                PlaybookExecution.started_at >= cooldown_start,
            )
        )
        return result.scalar_one_or_none()

    async def _count_active_executions(
        self, playbook_id: int, customer_id: int
    ) -> int:
        """Count active executions for a playbook/customer."""
        result = await self.db.execute(
            select(func.count(PlaybookExecution.id)).where(
                PlaybookExecution.playbook_id == playbook_id,
                PlaybookExecution.customer_id == customer_id,
                PlaybookExecution.status == "active",
            )
        )
        return result.scalar()

    async def _check_execution_complete(self, execution: PlaybookExecution) -> bool:
        """Check if all tasks for an execution are complete."""
        # Count incomplete tasks
        incomplete_result = await self.db.execute(
            select(func.count(CSTask.id)).where(
                CSTask.playbook_execution_id == execution.id,
                CSTask.status.in_(["pending", "in_progress", "blocked"]),
            )
        )
        incomplete_count = incomplete_result.scalar()

        return incomplete_count == 0

    async def _complete_execution(self, execution: PlaybookExecution) -> None:
        """Mark an execution as complete and evaluate success."""
        execution.status = "completed"
        execution.completed_at = datetime.utcnow()
        execution.steps_completed = execution.steps_total

        # Get current health score
        health_result = await self.db.execute(
            select(HealthScore).where(HealthScore.customer_id == execution.customer_id)
        )
        health = health_result.scalar_one_or_none()

        if health:
            execution.health_score_at_end = health.overall_score

        # Calculate total time spent
        time_result = await self.db.execute(
            select(func.sum(CSTask.time_spent_minutes)).where(
                CSTask.playbook_execution_id == execution.id
            )
        )
        execution.total_time_spent_minutes = time_result.scalar() or 0

        # Evaluate success criteria
        playbook_result = await self.db.execute(
            select(Playbook).where(Playbook.id == execution.playbook_id)
        )
        playbook = playbook_result.scalar_one_or_none()

        if playbook:
            success = await self._evaluate_success_criteria(execution, playbook)
            execution.outcome = "successful" if success else "unsuccessful"
            execution.success_criteria_met = success

            # Update playbook metrics
            playbook.times_completed = (playbook.times_completed or 0) + 1
            if success:
                playbook.times_successful = (playbook.times_successful or 0) + 1

            # Update success rate
            if playbook.times_completed > 0:
                playbook.success_rate = (
                    playbook.times_successful / playbook.times_completed * 100
                )

            # Update average completion days
            if execution.started_at:
                days = (datetime.utcnow() - execution.started_at).days
                if playbook.avg_completion_days:
                    playbook.avg_completion_days = (
                        playbook.avg_completion_days * 0.9 + days * 0.1
                    )
                else:
                    playbook.avg_completion_days = float(days)

    async def _evaluate_success_criteria(
        self, execution: PlaybookExecution, playbook: Playbook
    ) -> bool:
        """Evaluate if playbook success criteria were met."""
        criteria = playbook.success_criteria
        if not criteria:
            return True  # No criteria = success

        result = {}

        # Health score improvement
        if "health_score_increase" in criteria:
            required = criteria["health_score_increase"]
            start_score = execution.health_score_at_start or 0
            end_score = execution.health_score_at_end or 0
            result["health_score_increase"] = (end_score - start_score) >= required

        # Meeting held
        if "meeting_held" in criteria:
            meeting_result = await self.db.execute(
                select(func.count(CSTask.id)).where(
                    CSTask.playbook_execution_id == execution.id,
                    CSTask.task_type == "meeting",
                    CSTask.outcome == "successful",
                )
            )
            result["meeting_held"] = meeting_result.scalar() > 0

        # All tasks successful
        if "all_tasks_successful" in criteria:
            unsuccessful_result = await self.db.execute(
                select(func.count(CSTask.id)).where(
                    CSTask.playbook_execution_id == execution.id,
                    CSTask.outcome == "unsuccessful",
                )
            )
            result["all_tasks_successful"] = unsuccessful_result.scalar() == 0

        execution.success_criteria_met = result

        # Success if all criteria met
        return all(result.values()) if result else True

    async def _find_customers_for_trigger(
        self, playbook: Playbook
    ) -> list[int]:
        """Find customers that should have a playbook triggered."""
        customer_ids = []

        if playbook.trigger_type == "health_threshold":
            threshold = playbook.trigger_health_threshold
            direction = playbook.trigger_health_direction

            if threshold and direction:
                query = select(HealthScore.customer_id)
                if direction == "below":
                    query = query.where(HealthScore.overall_score < threshold)
                else:
                    query = query.where(HealthScore.overall_score > threshold)

                result = await self.db.execute(query)
                customer_ids = [r[0] for r in result.all()]

        elif playbook.trigger_type == "segment_entry":
            if playbook.trigger_segment_id:
                from app.models.customer_success import CustomerSegment
                result = await self.db.execute(
                    select(CustomerSegment.customer_id).where(
                        CustomerSegment.segment_id == playbook.trigger_segment_id,
                        CustomerSegment.is_active == True,
                    )
                )
                customer_ids = [r[0] for r in result.all()]

        # Filter out customers with recent executions
        filtered = []
        for cid in customer_ids:
            if playbook.cooldown_days:
                recent = await self._check_recent_execution(
                    playbook.id, cid, playbook.cooldown_days
                )
                if not recent:
                    filtered.append(cid)
            else:
                filtered.append(cid)

        return filtered
