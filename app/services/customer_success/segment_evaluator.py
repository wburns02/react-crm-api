"""
Segment Evaluator Service

Evaluates dynamic segment rules against customer data to determine
segment membership. Supports complex rule trees with AND/OR logic.
"""

from typing import Any, Optional
from datetime import datetime
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_success import Segment, CustomerSegment, HealthScore


class SegmentEvaluator:
    """
    Evaluates customer segment membership based on dynamic rules.

    Supports operators:
    - eq, neq: Equal, not equal
    - gt, lt, gte, lte: Comparison operators
    - contains, not_contains: String containment
    - in, not_in: List membership
    - is_null, is_not_null: Null checks
    - between: Range check
    - starts_with, ends_with: String prefix/suffix

    Rule format:
    {
        "logic": "and" | "or",
        "rules": [
            {"field": "health_score", "operator": "lt", "value": 50},
            {"field": "customer_type", "operator": "eq", "value": "enterprise"},
            {
                "logic": "or",
                "rules": [
                    {"field": "arr", "operator": "gte", "value": 10000},
                    {"field": "is_vip", "operator": "eq", "value": true}
                ]
            }
        ]
    }
    """

    # Mapping of field names to model attributes
    FIELD_MAPPING = {
        # Customer fields
        "customer_type": (Customer, "customer_type"),
        "is_active": (Customer, "is_active"),
        "created_at": (Customer, "created_at"),
        "state": (Customer, "state"),
        "city": (Customer, "city"),
        "tags": (Customer, "tags"),
        "lead_source": (Customer, "lead_source"),
        "prospect_stage": (Customer, "prospect_stage"),
        # Health score fields
        "health_score": (HealthScore, "overall_score"),
        "health_status": (HealthScore, "health_status"),
        "adoption_score": (HealthScore, "product_adoption_score"),
        "engagement_score": (HealthScore, "engagement_score"),
        "relationship_score": (HealthScore, "relationship_score"),
        "financial_score": (HealthScore, "financial_score"),
        "support_score": (HealthScore, "support_score"),
        "churn_probability": (HealthScore, "churn_probability"),
        "expansion_probability": (HealthScore, "expansion_probability"),
        "score_trend": (HealthScore, "score_trend"),
    }

    def __init__(self, db: AsyncSession):
        """Initialize evaluator with database session."""
        self.db = db

    async def evaluate_segment(self, segment_id: int) -> list[int]:
        """
        Evaluate a segment and return matching customer IDs.

        Args:
            segment_id: The segment to evaluate

        Returns:
            List of customer IDs that match the segment rules
        """
        # Get segment
        result = await self.db.execute(select(Segment).where(Segment.id == segment_id))
        segment = result.scalar_one_or_none()

        if not segment:
            raise ValueError(f"Segment {segment_id} not found")

        if segment.segment_type == "static":
            # Static segments don't need evaluation
            return await self._get_static_segment_members(segment_id)

        if not segment.rules:
            return []

        # Build and execute query
        matching_ids = await self._evaluate_rules(segment.rules)
        return matching_ids

    async def evaluate_customer(self, customer_id: int, segment_id: int) -> bool:
        """
        Check if a specific customer matches a segment's rules.

        Args:
            customer_id: The customer to check
            segment_id: The segment to check against

        Returns:
            True if customer matches segment rules
        """
        # Get segment
        result = await self.db.execute(select(Segment).where(Segment.id == segment_id))
        segment = result.scalar_one_or_none()

        if not segment:
            raise ValueError(f"Segment {segment_id} not found")

        if segment.segment_type == "static":
            # Check static membership
            member_result = await self.db.execute(
                select(CustomerSegment).where(
                    CustomerSegment.segment_id == segment_id,
                    CustomerSegment.customer_id == customer_id,
                    CustomerSegment.is_active == True,
                )
            )
            return member_result.scalar_one_or_none() is not None

        if not segment.rules:
            return False

        # Evaluate rules for this specific customer
        return await self._evaluate_rules_for_customer(customer_id, segment.rules)

    async def update_segment_membership(self, segment_id: int) -> dict:
        """
        Update segment membership based on current rules.

        Args:
            segment_id: The segment to update

        Returns:
            Dictionary with added/removed counts
        """
        # Get segment
        result = await self.db.execute(select(Segment).where(Segment.id == segment_id))
        segment = result.scalar_one_or_none()

        if not segment:
            raise ValueError(f"Segment {segment_id} not found")

        if segment.segment_type == "static":
            return {"added": 0, "removed": 0, "message": "Static segment - no updates"}

        # Get current members
        current_members_result = await self.db.execute(
            select(CustomerSegment.customer_id).where(
                CustomerSegment.segment_id == segment_id,
                CustomerSegment.is_active == True,
            )
        )
        current_members = set(r[0] for r in current_members_result.all())

        # Get matching customers
        matching_ids = await self.evaluate_segment(segment_id)
        new_members = set(matching_ids)

        # Calculate additions and removals
        to_add = new_members - current_members
        to_remove = current_members - new_members

        # Process additions
        for customer_id in to_add:
            membership = CustomerSegment(
                customer_id=customer_id,
                segment_id=segment_id,
                entry_reason="Dynamic rule match",
                entered_at=datetime.utcnow(),
            )
            self.db.add(membership)

        # Process removals
        if to_remove:
            remove_result = await self.db.execute(
                select(CustomerSegment).where(
                    CustomerSegment.segment_id == segment_id,
                    CustomerSegment.customer_id.in_(to_remove),
                    CustomerSegment.is_active == True,
                )
            )
            for membership in remove_result.scalars():
                membership.is_active = False
                membership.exited_at = datetime.utcnow()
                membership.exit_reason = "No longer matches rules"

        # Update segment stats
        segment.customer_count = len(new_members)
        segment.last_evaluated_at = datetime.utcnow()

        await self.db.commit()

        return {
            "added": len(to_add),
            "removed": len(to_remove),
            "total": len(new_members),
        }

    async def preview_segment(self, rules: dict, limit: int = 100) -> dict:
        """
        Preview customers that would match given rules without saving.

        Args:
            rules: The rules to evaluate
            limit: Maximum number of customers to return

        Returns:
            Preview with total count and sample customers
        """
        matching_ids = await self._evaluate_rules(rules, limit=None)

        # Get customer details for preview
        if matching_ids:
            preview_result = await self.db.execute(
                select(Customer, HealthScore)
                .outerjoin(HealthScore, Customer.id == HealthScore.customer_id)
                .where(Customer.id.in_(matching_ids[:limit]))
            )
            sample_customers = []
            for customer, health in preview_result.all():
                sample_customers.append(
                    {
                        "id": customer.id,
                        "name": f"{customer.first_name} {customer.last_name}",
                        "email": customer.email,
                        "health_score": health.overall_score if health else None,
                        "customer_type": customer.customer_type,
                    }
                )
        else:
            sample_customers = []

        return {
            "total_matches": len(matching_ids),
            "sample_customers": sample_customers,
        }

    async def _evaluate_rules(self, rules: dict, limit: Optional[int] = None) -> list[int]:
        """Evaluate rules and return matching customer IDs."""
        # Build base query joining customer and health score
        query = select(Customer.id).outerjoin(HealthScore, Customer.id == HealthScore.customer_id)

        # Build filter conditions
        conditions = self._build_conditions(rules)
        if conditions is not None:
            query = query.where(conditions)

        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        return [r[0] for r in result.all()]

    async def _evaluate_rules_for_customer(self, customer_id: int, rules: dict) -> bool:
        """Evaluate rules for a specific customer."""
        query = (
            select(Customer.id)
            .outerjoin(HealthScore, Customer.id == HealthScore.customer_id)
            .where(Customer.id == customer_id)
        )

        conditions = self._build_conditions(rules)
        if conditions is not None:
            query = query.where(conditions)

        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    def _build_conditions(self, rule_set: dict) -> Any:
        """
        Recursively build SQLAlchemy conditions from rule set.

        Args:
            rule_set: Rule set with "logic" and "rules" keys

        Returns:
            SQLAlchemy condition expression
        """
        logic = rule_set.get("logic", "and")
        rules = rule_set.get("rules", [])

        if not rules:
            return None

        conditions = []
        for rule in rules:
            if "logic" in rule:
                # Nested rule set
                nested = self._build_conditions(rule)
                if nested is not None:
                    conditions.append(nested)
            else:
                # Single rule
                condition = self._build_single_condition(rule)
                if condition is not None:
                    conditions.append(condition)

        if not conditions:
            return None

        if logic == "or":
            return or_(*conditions)
        else:
            return and_(*conditions)

    def _build_single_condition(self, rule: dict) -> Any:
        """Build condition for a single rule."""
        field = rule.get("field")
        operator = rule.get("operator")
        value = rule.get("value")
        value2 = rule.get("value2")

        if field not in self.FIELD_MAPPING:
            return None

        model, attr_name = self.FIELD_MAPPING[field]
        column = getattr(model, attr_name)

        if operator == "eq":
            return column == value
        elif operator == "neq":
            return column != value
        elif operator == "gt":
            return column > value
        elif operator == "lt":
            return column < value
        elif operator == "gte":
            return column >= value
        elif operator == "lte":
            return column <= value
        elif operator == "contains":
            return column.ilike(f"%{value}%")
        elif operator == "not_contains":
            return ~column.ilike(f"%{value}%")
        elif operator == "in":
            return column.in_(value) if isinstance(value, list) else column == value
        elif operator == "not_in":
            return ~column.in_(value) if isinstance(value, list) else column != value
        elif operator == "is_null":
            return column.is_(None)
        elif operator == "is_not_null":
            return column.isnot(None)
        elif operator == "between":
            return and_(column >= value, column <= value2)
        elif operator == "starts_with":
            return column.ilike(f"{value}%")
        elif operator == "ends_with":
            return column.ilike(f"%{value}")
        else:
            return None

    async def _get_static_segment_members(self, segment_id: int) -> list[int]:
        """Get customer IDs for static segment."""
        result = await self.db.execute(
            select(CustomerSegment.customer_id).where(
                CustomerSegment.segment_id == segment_id,
                CustomerSegment.is_active == True,
            )
        )
        return [r[0] for r in result.all()]
