"""
Journey Orchestrator Service

Manages the execution of customer journeys, handling step progression,
condition evaluation, wait times, and action execution.
"""

from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_success import Journey, JourneyStep, JourneyEnrollment, JourneyStepExecution


class JourneyOrchestrator:
    """
    Orchestrates customer journey execution.

    Handles:
    - Step progression through journeys
    - Wait step timing
    - Condition evaluation and branching
    - Action execution (email, task creation, etc.)
    - Enrollment management
    """

    def __init__(self, db: AsyncSession):
        """Initialize orchestrator with database session."""
        self.db = db

    async def process_enrollments(self) -> dict:
        """
        Process all active enrollments that are ready for progression.

        This should be called periodically (e.g., every minute) to:
        - Execute due wait steps
        - Progress to next steps
        - Execute actions

        Returns:
            Summary of processed enrollments
        """
        processed = 0
        errors = []

        # Get enrollments ready for processing
        ready_enrollments = await self._get_ready_enrollments()

        for enrollment in ready_enrollments:
            try:
                await self._process_enrollment(enrollment)
                processed += 1
            except Exception as e:
                errors.append(
                    {
                        "enrollment_id": enrollment.id,
                        "error": str(e),
                    }
                )

        return {
            "processed": processed,
            "errors": errors,
            "total_ready": len(ready_enrollments),
        }

    async def advance_enrollment(self, enrollment_id: int) -> dict:
        """
        Manually advance an enrollment to the next step.

        Args:
            enrollment_id: The enrollment to advance

        Returns:
            Status of advancement
        """
        # Get enrollment
        result = await self.db.execute(select(JourneyEnrollment).where(JourneyEnrollment.id == enrollment_id))
        enrollment = result.scalar_one_or_none()

        if not enrollment:
            raise ValueError(f"Enrollment {enrollment_id} not found")

        if enrollment.status != "active":
            return {"status": "skipped", "reason": "Enrollment is not active"}

        return await self._process_enrollment(enrollment)

    async def execute_step(self, enrollment_id: int, step_id: int, force: bool = False) -> dict:
        """
        Execute a specific step for an enrollment.

        Args:
            enrollment_id: The enrollment
            step_id: The step to execute
            force: Skip conditions and waiting

        Returns:
            Execution result
        """
        # Get enrollment and step
        enrollment_result = await self.db.execute(
            select(JourneyEnrollment).where(JourneyEnrollment.id == enrollment_id)
        )
        enrollment = enrollment_result.scalar_one_or_none()

        step_result = await self.db.execute(select(JourneyStep).where(JourneyStep.id == step_id))
        step = step_result.scalar_one_or_none()

        if not enrollment or not step:
            raise ValueError("Enrollment or step not found")

        # Create step execution record
        execution = JourneyStepExecution(
            enrollment_id=enrollment_id,
            step_id=step_id,
            status="in_progress",
            started_at=datetime.utcnow(),
        )
        self.db.add(execution)
        await self.db.flush()

        try:
            result = await self._execute_step_action(enrollment, step, execution)
            execution.status = "completed"
            execution.completed_at = datetime.utcnow()
            execution.result = result
            await self.db.commit()
            return result
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            execution.attempts = (execution.attempts or 0) + 1
            await self.db.commit()
            raise

    async def _get_ready_enrollments(self) -> list[JourneyEnrollment]:
        """Get enrollments that are ready for step processing."""
        now = datetime.utcnow()

        # Get active enrollments
        result = await self.db.execute(
            select(JourneyEnrollment).where(
                JourneyEnrollment.status == "active",
            )
        )
        enrollments = result.scalars().all()

        ready = []
        for enrollment in enrollments:
            # Check if there's a pending execution with a wait
            pending = await self._get_pending_execution(enrollment.id)

            if pending:
                # Check if wait time has elapsed
                if pending.scheduled_at and pending.scheduled_at <= now:
                    ready.append(enrollment)
            else:
                # No pending execution, ready for next step
                ready.append(enrollment)

        return ready

    async def _process_enrollment(self, enrollment: JourneyEnrollment) -> dict:
        """Process a single enrollment."""
        # Get current step
        if not enrollment.current_step_id:
            # Get first step of journey
            journey_result = await self.db.execute(select(Journey).where(Journey.id == enrollment.journey_id))
            journey = journey_result.scalar_one_or_none()

            if not journey:
                return {"status": "error", "reason": "Journey not found"}

            steps_result = await self.db.execute(
                select(JourneyStep)
                .where(JourneyStep.journey_id == journey.id)
                .order_by(JourneyStep.step_order.asc())
                .limit(1)
            )
            first_step = steps_result.scalar_one_or_none()

            if not first_step:
                return {"status": "completed", "reason": "No steps in journey"}

            enrollment.current_step_id = first_step.id
            enrollment.current_step_order = first_step.step_order

        step_result = await self.db.execute(select(JourneyStep).where(JourneyStep.id == enrollment.current_step_id))
        step = step_result.scalar_one_or_none()

        if not step:
            return {"status": "error", "reason": "Current step not found"}

        # Execute current step
        execution_result = await self._execute_step_action(enrollment, step, None)

        # Determine next step
        next_step = await self._get_next_step(enrollment, step, execution_result)

        if next_step:
            # Progress to next step
            enrollment.current_step_id = next_step.id
            enrollment.current_step_order = next_step.step_order
            enrollment.steps_completed = (enrollment.steps_completed or 0) + 1
        else:
            # Journey complete
            enrollment.status = "completed"
            enrollment.completed_at = datetime.utcnow()
            enrollment.steps_completed = enrollment.steps_total

        await self.db.commit()

        return {
            "status": "success",
            "step_executed": step.name,
            "next_step": next_step.name if next_step else None,
            "journey_completed": enrollment.status == "completed",
        }

    async def _execute_step_action(
        self,
        enrollment: JourneyEnrollment,
        step: JourneyStep,
        execution: Optional[JourneyStepExecution],
    ) -> dict:
        """Execute the action for a step based on its type."""
        step_type = step.step_type
        config = step.action_config or {}

        if step_type == "wait":
            # Schedule wait
            wait_hours = step.wait_duration_hours or 24
            scheduled_at = datetime.utcnow() + timedelta(hours=wait_hours)

            if execution:
                execution.scheduled_at = scheduled_at
                execution.status = "pending"

            return {
                "action": "wait",
                "wait_hours": wait_hours,
                "scheduled_at": scheduled_at.isoformat(),
            }

        elif step_type == "condition":
            # Evaluate condition
            condition_result = await self._evaluate_condition(enrollment.customer_id, step.condition_rules)

            if execution:
                execution.condition_result = condition_result

            return {
                "action": "condition",
                "result": condition_result,
                "true_path": step.true_next_step_id,
                "false_path": step.false_next_step_id,
            }

        elif step_type == "email":
            # Queue email
            # In production, this would integrate with email service
            return {
                "action": "email",
                "template_id": config.get("template_id"),
                "subject": config.get("subject"),
                "status": "queued",
            }

        elif step_type == "task":
            # Create task
            # In production, this would create a CSTask
            return {
                "action": "task",
                "title": config.get("title"),
                "assignee_role": config.get("assignee_role"),
                "status": "created",
            }

        elif step_type == "webhook":
            # Call webhook
            # In production, this would make HTTP request
            return {
                "action": "webhook",
                "url": config.get("url"),
                "method": config.get("method", "POST"),
                "status": "sent",
            }

        elif step_type == "human_touchpoint":
            # Create task for human interaction
            return {
                "action": "human_touchpoint",
                "description": config.get("description"),
                "status": "pending_human_action",
            }

        elif step_type == "update_field":
            # Update customer/enrollment field
            return {
                "action": "update_field",
                "field": config.get("field"),
                "value": config.get("value"),
                "status": "updated",
            }

        elif step_type == "trigger_playbook":
            # Trigger another playbook
            return {
                "action": "trigger_playbook",
                "playbook_id": config.get("playbook_id"),
                "status": "triggered",
            }

        else:
            return {
                "action": step_type,
                "status": "completed",
            }

    async def _evaluate_condition(self, customer_id: int, condition_rules: Optional[dict]) -> bool:
        """Evaluate condition rules for a customer."""
        if not condition_rules:
            return True

        # Import segment evaluator for rule evaluation
        from app.services.customer_success.segment_evaluator import SegmentEvaluator

        evaluator = SegmentEvaluator(self.db)

        # Build a temporary rule set
        rule_set = {
            "logic": condition_rules.get("logic", "and"),
            "rules": condition_rules.get("rules", []),
        }

        # Evaluate for this specific customer
        return await evaluator._evaluate_rules_for_customer(customer_id, rule_set)

    async def _get_next_step(
        self,
        enrollment: JourneyEnrollment,
        current_step: JourneyStep,
        execution_result: dict,
    ) -> Optional[JourneyStep]:
        """Determine the next step based on current step and execution result."""
        # Handle condition branching
        if current_step.step_type == "condition":
            condition_result = execution_result.get("result", True)
            if condition_result:
                next_step_id = current_step.true_next_step_id
            else:
                next_step_id = current_step.false_next_step_id

            if next_step_id:
                result = await self.db.execute(select(JourneyStep).where(JourneyStep.id == next_step_id))
                return result.scalar_one_or_none()

        # Get next step by order
        result = await self.db.execute(
            select(JourneyStep)
            .where(
                JourneyStep.journey_id == enrollment.journey_id,
                JourneyStep.step_order > current_step.step_order,
                JourneyStep.is_active == True,
            )
            .order_by(JourneyStep.step_order.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_pending_execution(self, enrollment_id: int) -> Optional[JourneyStepExecution]:
        """Get pending execution for an enrollment."""
        result = await self.db.execute(
            select(JourneyStepExecution).where(
                JourneyStepExecution.enrollment_id == enrollment_id,
                JourneyStepExecution.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def check_exit_criteria(self, enrollment_id: int) -> tuple[bool, Optional[str]]:
        """
        Check if an enrollment should exit the journey.

        Args:
            enrollment_id: The enrollment to check

        Returns:
            Tuple of (should_exit, reason)
        """
        result = await self.db.execute(select(JourneyEnrollment).where(JourneyEnrollment.id == enrollment_id))
        enrollment = result.scalar_one_or_none()

        if not enrollment:
            return False, None

        journey_result = await self.db.execute(select(Journey).where(Journey.id == enrollment.journey_id))
        journey = journey_result.scalar_one_or_none()

        if not journey:
            return False, None

        # Check exit criteria
        if journey.exit_criteria:
            should_exit = await self._evaluate_condition(enrollment.customer_id, journey.exit_criteria)
            if should_exit:
                return True, "Exit criteria met"

        return False, None

    async def check_goal_achieved(self, enrollment_id: int) -> tuple[bool, Optional[str]]:
        """
        Check if the journey goal has been achieved.

        Args:
            enrollment_id: The enrollment to check

        Returns:
            Tuple of (goal_achieved, details)
        """
        result = await self.db.execute(select(JourneyEnrollment).where(JourneyEnrollment.id == enrollment_id))
        enrollment = result.scalar_one_or_none()

        if not enrollment:
            return False, None

        journey_result = await self.db.execute(select(Journey).where(Journey.id == enrollment.journey_id))
        journey = journey_result.scalar_one_or_none()

        if not journey or not journey.goal_criteria:
            return False, None

        # Check goal criteria
        goal_achieved = await self._evaluate_condition(enrollment.customer_id, journey.goal_criteria)

        if goal_achieved:
            enrollment.goal_achieved = True
            enrollment.goal_achieved_at = datetime.utcnow()
            await self.db.commit()
            return True, "Goal criteria met"

        return False, None
