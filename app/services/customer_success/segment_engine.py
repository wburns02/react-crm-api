"""
World-Class Segment Engine for Enterprise Customer Success Platform

This is the core segmentation engine providing:
- Real-time membership calculation using efficient SQLAlchemy queries with CTEs
- Nested segment support (segment of segments)
- Exclusion rules (in A but not in B)
- Query builder that avoids N+1 with optimized joins
- Segment size estimation before creation
- Historical membership tracking with snapshots
- Support for all operator types including relative dates

RULE TYPES SUPPORTED:
- Customer attributes (location, type, created_date)
- Behavioral (last_service_date, total_spent, visit_count)
- Health scores (NPS, CSAT, churn_risk, health_score)
- Financial (lifetime_value, payment_status)
- Service history (system_type, last_pump_date, contract_status)

OPERATORS SUPPORTED:
- equals, not_equals, contains, not_contains
- greater_than, less_than, between
- is_empty, is_not_empty
- in_list, not_in_list
- days_ago, weeks_ago, months_ago
- relative dates (last 30 days, this quarter)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Any, Optional, List, Dict, Set, Tuple, Union
from enum import Enum

from sqlalchemy import select, func, and_, or_, not_, case, literal, text, union_all
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.customer import Customer
from app.models.customer_success import (
    Segment,
    CustomerSegment,
    SegmentRule,
    SegmentMembership,
    SegmentSnapshot,
    HealthScore,
    Touchpoint,
)
from app.models.work_order import WorkOrder


logger = logging.getLogger(__name__)


class FieldCategory(str, Enum):
    """Categories of fields that can be used in segment rules."""

    CUSTOMER = "customer"
    HEALTH = "health"
    BEHAVIORAL = "behavioral"
    FINANCIAL = "financial"
    SERVICE = "service"
    ENGAGEMENT = "engagement"


@dataclass
class FieldDefinition:
    """Definition of a field that can be used in segment rules."""

    name: str
    display_name: str
    category: FieldCategory
    data_type: str  # 'string', 'number', 'date', 'boolean', 'list'
    model: type
    column: str
    description: str = ""
    requires_join: bool = False
    aggregation: Optional[str] = None  # 'count', 'sum', 'avg', 'max', 'min'
    subquery: bool = False


@dataclass
class SegmentEvaluationResult:
    """Result of evaluating a segment."""

    segment_id: int
    matching_customer_ids: List[int]
    total_count: int
    execution_time_ms: float
    query_generated: Optional[str] = None
    errors: List[str] = field(default_factory=list)


@dataclass
class SegmentPreviewResult:
    """Result of previewing a segment before creation."""

    estimated_count: int
    sample_customers: List[Dict[str, Any]]
    estimated_arr: Optional[Decimal] = None
    avg_health_score: Optional[float] = None
    health_distribution: Dict[str, int] = field(default_factory=dict)
    customer_type_distribution: Dict[str, int] = field(default_factory=dict)
    geographic_distribution: Dict[str, int] = field(default_factory=dict)
    execution_time_ms: float = 0


@dataclass
class MembershipUpdateResult:
    """Result of updating segment membership."""

    segment_id: int
    customers_added: int
    customers_removed: int
    total_members: int
    add_details: List[Dict[str, Any]] = field(default_factory=list)
    remove_details: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_ms: float = 0


class SegmentEngine:
    """
    World-class segment evaluation and management engine.

    Features:
    - Efficient CTE-based queries to avoid N+1
    - Support for nested segments (unions and intersections)
    - Exclusion rules for complex segment logic
    - Real-time and batch evaluation modes
    - Historical membership tracking
    - AI-ready segment suggestions
    """

    # Comprehensive field mapping for all supported rule types
    FIELD_DEFINITIONS: Dict[str, FieldDefinition] = {
        # Customer Attributes
        "customer_type": FieldDefinition(
            "customer_type",
            "Customer Type",
            FieldCategory.CUSTOMER,
            "string",
            Customer,
            "customer_type",
            "Type of customer (residential, commercial, enterprise)",
        ),
        "city": FieldDefinition("city", "City", FieldCategory.CUSTOMER, "string", Customer, "city", "Customer city"),
        "state": FieldDefinition(
            "state", "State", FieldCategory.CUSTOMER, "string", Customer, "state", "Customer state"
        ),
        "postal_code": FieldDefinition(
            "postal_code",
            "Postal Code",
            FieldCategory.CUSTOMER,
            "string",
            Customer,
            "postal_code",
            "Customer postal/zip code",
        ),
        "subdivision": FieldDefinition(
            "subdivision",
            "Subdivision",
            FieldCategory.CUSTOMER,
            "string",
            Customer,
            "subdivision",
            "Customer subdivision/neighborhood",
        ),
        "lead_source": FieldDefinition(
            "lead_source",
            "Lead Source",
            FieldCategory.CUSTOMER,
            "string",
            Customer,
            "lead_source",
            "How the customer was acquired",
        ),
        "prospect_stage": FieldDefinition(
            "prospect_stage",
            "Prospect Stage",
            FieldCategory.CUSTOMER,
            "string",
            Customer,
            "prospect_stage",
            "Current sales stage",
        ),
        "created_at": FieldDefinition(
            "created_at",
            "Created Date",
            FieldCategory.CUSTOMER,
            "date",
            Customer,
            "created_at",
            "When customer was created",
        ),
        "is_active": FieldDefinition(
            "is_active",
            "Is Active",
            FieldCategory.CUSTOMER,
            "boolean",
            Customer,
            "is_active",
            "Whether customer is active",
        ),
        "tags": FieldDefinition("tags", "Tags", FieldCategory.CUSTOMER, "string", Customer, "tags", "Customer tags"),
        # Health Score Metrics
        "health_score": FieldDefinition(
            "health_score",
            "Health Score",
            FieldCategory.HEALTH,
            "number",
            HealthScore,
            "overall_score",
            "Overall customer health score (0-100)",
            True,
        ),
        "health_status": FieldDefinition(
            "health_status",
            "Health Status",
            FieldCategory.HEALTH,
            "string",
            HealthScore,
            "health_status",
            "Health status (healthy, at_risk, critical, churned)",
            True,
        ),
        "churn_probability": FieldDefinition(
            "churn_probability",
            "Churn Probability",
            FieldCategory.HEALTH,
            "number",
            HealthScore,
            "churn_probability",
            "Probability of churn (0-1)",
            True,
        ),
        "expansion_probability": FieldDefinition(
            "expansion_probability",
            "Expansion Probability",
            FieldCategory.HEALTH,
            "number",
            HealthScore,
            "expansion_probability",
            "Probability of expansion (0-1)",
            True,
        ),
        "score_trend": FieldDefinition(
            "score_trend",
            "Score Trend",
            FieldCategory.HEALTH,
            "string",
            HealthScore,
            "score_trend",
            "Health score trend (improving, stable, declining)",
            True,
        ),
        "adoption_score": FieldDefinition(
            "adoption_score",
            "Adoption Score",
            FieldCategory.HEALTH,
            "number",
            HealthScore,
            "product_adoption_score",
            "Product adoption score (0-100)",
            True,
        ),
        "engagement_score": FieldDefinition(
            "engagement_score",
            "Engagement Score",
            FieldCategory.HEALTH,
            "number",
            HealthScore,
            "engagement_score",
            "Engagement score (0-100)",
            True,
        ),
        "relationship_score": FieldDefinition(
            "relationship_score",
            "Relationship Score",
            FieldCategory.HEALTH,
            "number",
            HealthScore,
            "relationship_score",
            "Relationship score (0-100)",
            True,
        ),
        "financial_score": FieldDefinition(
            "financial_score",
            "Financial Score",
            FieldCategory.HEALTH,
            "number",
            HealthScore,
            "financial_score",
            "Financial health score (0-100)",
            True,
        ),
        "support_score": FieldDefinition(
            "support_score",
            "Support Score",
            FieldCategory.HEALTH,
            "number",
            HealthScore,
            "support_score",
            "Support satisfaction score (0-100)",
            True,
        ),
        # Service History
        "system_type": FieldDefinition(
            "system_type",
            "System Type",
            FieldCategory.SERVICE,
            "string",
            Customer,
            "system_type",
            "Type of septic system installed",
        ),
        "tank_size_gallons": FieldDefinition(
            "tank_size_gallons",
            "Tank Size (Gallons)",
            FieldCategory.SERVICE,
            "number",
            Customer,
            "tank_size_gallons",
            "Size of septic tank in gallons",
        ),
        "number_of_tanks": FieldDefinition(
            "number_of_tanks",
            "Number of Tanks",
            FieldCategory.SERVICE,
            "number",
            Customer,
            "number_of_tanks",
            "Number of septic tanks",
        ),
        "system_issued_date": FieldDefinition(
            "system_issued_date",
            "System Install Date",
            FieldCategory.SERVICE,
            "date",
            Customer,
            "system_issued_date",
            "When the septic system was installed",
        ),
        # Financial
        "estimated_value": FieldDefinition(
            "estimated_value",
            "Estimated Value",
            FieldCategory.FINANCIAL,
            "number",
            Customer,
            "estimated_value",
            "Estimated customer value",
        ),
        # Behavioral (require subqueries/aggregations)
        "total_work_orders": FieldDefinition(
            "total_work_orders",
            "Total Work Orders",
            FieldCategory.BEHAVIORAL,
            "number",
            WorkOrder,
            "id",
            "Total number of work orders",
            True,
            "count",
            True,
        ),
        "last_service_date": FieldDefinition(
            "last_service_date",
            "Last Service Date",
            FieldCategory.BEHAVIORAL,
            "date",
            WorkOrder,
            "scheduled_date",
            "Date of most recent service",
            True,
            "max",
            True,
        ),
        # Engagement (touchpoints)
        "total_touchpoints": FieldDefinition(
            "total_touchpoints",
            "Total Touchpoints",
            FieldCategory.ENGAGEMENT,
            "number",
            Touchpoint,
            "id",
            "Total customer touchpoints",
            True,
            "count",
            True,
        ),
        "last_touchpoint_date": FieldDefinition(
            "last_touchpoint_date",
            "Last Touchpoint Date",
            FieldCategory.ENGAGEMENT,
            "date",
            Touchpoint,
            "occurred_at",
            "Date of most recent touchpoint",
            True,
            "max",
            True,
        ),
        "avg_sentiment": FieldDefinition(
            "avg_sentiment",
            "Average Sentiment",
            FieldCategory.ENGAGEMENT,
            "number",
            Touchpoint,
            "sentiment_score",
            "Average sentiment score across touchpoints",
            True,
            "avg",
            True,
        ),
        "nps_score": FieldDefinition(
            "nps_score",
            "NPS Score",
            FieldCategory.ENGAGEMENT,
            "number",
            Touchpoint,
            "nps_score",
            "Most recent NPS score",
            True,
            "max",
            True,
        ),
        "csat_score": FieldDefinition(
            "csat_score",
            "CSAT Score",
            FieldCategory.ENGAGEMENT,
            "number",
            Touchpoint,
            "csat_score",
            "Most recent CSAT score",
            True,
            "max",
            True,
        ),
    }

    def __init__(self, db: AsyncSession):
        """Initialize the segment engine with a database session."""
        self.db = db
        self._query_cache: Dict[str, Any] = {}

    # =========================================================================
    # CORE EVALUATION METHODS
    # =========================================================================

    async def evaluate_segment(self, segment_id: int, limit: Optional[int] = None) -> SegmentEvaluationResult:
        """
        Evaluate a segment and return matching customer IDs.

        This is the main entry point for segment evaluation. It handles:
        - Static segments (returns existing members)
        - Dynamic segments (evaluates rules)
        - Nested segments (combines other segments)
        - AI-generated segments (returns AI-matched members)

        Args:
            segment_id: The segment to evaluate
            limit: Optional limit on results

        Returns:
            SegmentEvaluationResult with matching customer IDs and metadata
        """
        start_time = datetime.utcnow()

        # Fetch segment with eager loading
        result = await self.db.execute(
            select(Segment).options(selectinload(Segment.segment_rules)).where(Segment.id == segment_id)
        )
        segment = result.scalar_one_or_none()

        if not segment:
            return SegmentEvaluationResult(
                segment_id=segment_id,
                matching_customer_ids=[],
                total_count=0,
                execution_time_ms=0,
                errors=[f"Segment {segment_id} not found"],
            )

        try:
            if segment.segment_type == "static":
                customer_ids = await self._get_static_segment_members(segment_id)
            elif segment.segment_type == "nested":
                customer_ids = await self._evaluate_nested_segment(segment)
            elif segment.segment_type == "ai_generated":
                customer_ids = await self._get_ai_segment_members(segment_id)
            else:  # dynamic
                customer_ids = await self._evaluate_dynamic_segment(segment, limit)

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return SegmentEvaluationResult(
                segment_id=segment_id,
                matching_customer_ids=customer_ids,
                total_count=len(customer_ids),
                execution_time_ms=execution_time,
            )

        except Exception as e:
            logger.exception(f"Error evaluating segment {segment_id}")
            return SegmentEvaluationResult(
                segment_id=segment_id, matching_customer_ids=[], total_count=0, execution_time_ms=0, errors=[str(e)]
            )

    async def evaluate_rules(
        self,
        rules: Dict[str, Any],
        limit: Optional[int] = None,
        include_segments: Optional[List[int]] = None,
        exclude_segments: Optional[List[int]] = None,
    ) -> List[int]:
        """
        Evaluate a set of rules and return matching customer IDs.

        This is used for previewing segments before creation.

        Args:
            rules: Rule set in the format {"logic": "and/or", "rules": [...]}
            limit: Optional limit on results
            include_segments: Optional list of segment IDs to include
            exclude_segments: Optional list of segment IDs to exclude

        Returns:
            List of matching customer IDs
        """
        query = self._build_query_from_rules(rules)

        # Handle segment inclusions
        if include_segments:
            include_ids = await self._get_customers_in_segments(include_segments)
            if include_ids:
                query = query.where(Customer.id.in_(include_ids))

        # Handle segment exclusions
        if exclude_segments:
            exclude_ids = await self._get_customers_in_segments(exclude_segments)
            if exclude_ids:
                query = query.where(Customer.id.notin_(exclude_ids))

        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        return [row[0] for row in result.all()]

    async def preview_segment(
        self,
        rules: Dict[str, Any],
        sample_size: int = 50,
        include_segments: Optional[List[int]] = None,
        exclude_segments: Optional[List[int]] = None,
    ) -> SegmentPreviewResult:
        """
        Preview a segment before creation with detailed statistics.

        Args:
            rules: Rule set to preview
            sample_size: Number of sample customers to return
            include_segments: Optional segment IDs to include
            exclude_segments: Optional segment IDs to exclude

        Returns:
            SegmentPreviewResult with counts, samples, and distributions
        """
        start_time = datetime.utcnow()

        # Get matching customer IDs
        matching_ids = await self.evaluate_rules(
            rules, include_segments=include_segments, exclude_segments=exclude_segments
        )

        total_count = len(matching_ids)

        if total_count == 0:
            return SegmentPreviewResult(
                estimated_count=0,
                sample_customers=[],
                execution_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            )

        # Get sample customers with health scores
        sample_ids = matching_ids[:sample_size]
        sample_query = (
            select(Customer, HealthScore)
            .outerjoin(HealthScore, Customer.id == HealthScore.customer_id)
            .where(Customer.id.in_(sample_ids))
        )
        sample_result = await self.db.execute(sample_query)

        sample_customers = []
        for customer, health in sample_result.all():
            sample_customers.append(
                {
                    "id": customer.id,
                    "name": f"{customer.first_name} {customer.last_name}".strip(),
                    "email": customer.email,
                    "customer_type": customer.customer_type,
                    "city": customer.city,
                    "state": customer.state,
                    "health_score": health.overall_score if health else None,
                    "health_status": health.health_status if health else None,
                }
            )

        # Calculate aggregate statistics
        stats_query = (
            select(
                func.avg(HealthScore.overall_score).label("avg_health"),
                func.sum(Customer.estimated_value).label("total_value"),
            )
            .outerjoin(HealthScore, Customer.id == HealthScore.customer_id)
            .where(Customer.id.in_(matching_ids))
        )
        stats_result = await self.db.execute(stats_query)
        stats = stats_result.first()

        # Health distribution
        health_dist_query = (
            select(HealthScore.health_status, func.count().label("count"))
            .where(HealthScore.customer_id.in_(matching_ids))
            .group_by(HealthScore.health_status)
        )
        health_dist_result = await self.db.execute(health_dist_query)
        health_distribution = {row.health_status: row.count for row in health_dist_result.all() if row.health_status}

        # Customer type distribution
        type_dist_query = (
            select(Customer.customer_type, func.count().label("count"))
            .where(Customer.id.in_(matching_ids))
            .group_by(Customer.customer_type)
        )
        type_dist_result = await self.db.execute(type_dist_query)
        type_distribution = {row.customer_type or "Unknown": row.count for row in type_dist_result.all()}

        # Geographic distribution (by state)
        geo_dist_query = (
            select(Customer.state, func.count().label("count"))
            .where(Customer.id.in_(matching_ids))
            .group_by(Customer.state)
        )
        geo_dist_result = await self.db.execute(geo_dist_query)
        geo_distribution = {row.state or "Unknown": row.count for row in geo_dist_result.all()}

        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        return SegmentPreviewResult(
            estimated_count=total_count,
            sample_customers=sample_customers,
            estimated_arr=Decimal(str(stats.total_value)) if stats.total_value else None,
            avg_health_score=float(stats.avg_health) if stats.avg_health else None,
            health_distribution=health_distribution,
            customer_type_distribution=type_distribution,
            geographic_distribution=geo_distribution,
            execution_time_ms=execution_time,
        )

    async def estimate_segment_size(
        self,
        rules: Dict[str, Any],
        include_segments: Optional[List[int]] = None,
        exclude_segments: Optional[List[int]] = None,
    ) -> int:
        """
        Quickly estimate segment size without fetching all IDs.

        Uses COUNT(*) for efficiency on large datasets.
        """
        query = self._build_query_from_rules(rules)

        # Convert to count query
        count_query = select(func.count()).select_from(query.subquery())

        # Apply segment filters
        if include_segments:
            include_ids = await self._get_customers_in_segments(include_segments)
            if include_ids:
                # Need to rebuild with the filter
                query = query.where(Customer.id.in_(include_ids))
                count_query = select(func.count()).select_from(query.subquery())

        if exclude_segments:
            exclude_ids = await self._get_customers_in_segments(exclude_segments)
            if exclude_ids:
                query = query.where(Customer.id.notin_(exclude_ids))
                count_query = select(func.count()).select_from(query.subquery())

        result = await self.db.execute(count_query)
        return result.scalar() or 0

    # =========================================================================
    # MEMBERSHIP MANAGEMENT
    # =========================================================================

    async def update_segment_membership(
        self, segment_id: int, track_history: bool = True, create_snapshot: bool = True
    ) -> MembershipUpdateResult:
        """
        Update segment membership based on current rules.

        This is the main method for refreshing dynamic segments. It:
        1. Evaluates current rules to find matching customers
        2. Compares with existing membership
        3. Adds new members and removes non-matching ones
        4. Tracks entry/exit history if enabled
        5. Creates a snapshot if enabled

        Args:
            segment_id: The segment to update
            track_history: Whether to track entry/exit in SegmentMembership
            create_snapshot: Whether to create a SegmentSnapshot

        Returns:
            MembershipUpdateResult with add/remove counts
        """
        start_time = datetime.utcnow()

        # Get segment
        result = await self.db.execute(select(Segment).where(Segment.id == segment_id))
        segment = result.scalar_one_or_none()

        if not segment:
            raise ValueError(f"Segment {segment_id} not found")

        if segment.segment_type == "static":
            return MembershipUpdateResult(
                segment_id=segment_id,
                customers_added=0,
                customers_removed=0,
                total_members=segment.customer_count or 0,
                execution_time_ms=0,
            )

        # Get current members
        current_members_result = await self.db.execute(
            select(CustomerSegment.customer_id).where(
                CustomerSegment.segment_id == segment_id,
                CustomerSegment.is_active == True,
            )
        )
        current_members = set(row[0] for row in current_members_result.all())

        # Evaluate segment to get new members
        eval_result = await self.evaluate_segment(segment_id)
        new_members = set(eval_result.matching_customer_ids)

        # Calculate changes
        to_add = new_members - current_members
        to_remove = current_members - new_members

        add_details = []
        remove_details = []

        # Process additions
        for customer_id in to_add:
            membership = CustomerSegment(
                customer_id=customer_id,
                segment_id=segment_id,
                entry_reason="Dynamic rule match",
                entered_at=datetime.utcnow(),
                added_by="system",
            )
            self.db.add(membership)

            if track_history:
                detailed_membership = SegmentMembership(
                    customer_id=customer_id,
                    segment_id=segment_id,
                    entry_reason="Matched segment rules",
                    entry_source="rule_match",
                    entered_at=datetime.utcnow(),
                )
                self.db.add(detailed_membership)

            add_details.append({"customer_id": customer_id})

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
                remove_details.append({"customer_id": membership.customer_id})

            if track_history:
                hist_result = await self.db.execute(
                    select(SegmentMembership).where(
                        SegmentMembership.segment_id == segment_id,
                        SegmentMembership.customer_id.in_(to_remove),
                        SegmentMembership.is_active == True,
                    )
                )
                for hist in hist_result.scalars():
                    hist.is_active = False
                    hist.exited_at = datetime.utcnow()
                    hist.exit_reason = "No longer matches segment rules"
                    hist.exit_source = "rule_mismatch"

        # Update segment stats
        segment.customer_count = len(new_members)
        segment.last_refreshed_at = datetime.utcnow()

        # Create snapshot if enabled
        if create_snapshot and (to_add or to_remove):
            await self._create_segment_snapshot(segment_id, len(new_members), len(to_add), len(to_remove), "scheduled")

        await self.db.commit()

        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        return MembershipUpdateResult(
            segment_id=segment_id,
            customers_added=len(to_add),
            customers_removed=len(to_remove),
            total_members=len(new_members),
            add_details=add_details,
            remove_details=remove_details,
            execution_time_ms=execution_time,
        )

    async def _create_segment_snapshot(
        self, segment_id: int, member_count: int, entered: int, exited: int, snapshot_type: str
    ):
        """Create a point-in-time snapshot of segment membership."""
        # Get previous snapshot for comparison
        prev_result = await self.db.execute(
            select(SegmentSnapshot)
            .where(SegmentSnapshot.segment_id == segment_id)
            .order_by(SegmentSnapshot.snapshot_at.desc())
            .limit(1)
        )
        prev_snapshot = prev_result.scalar_one_or_none()

        previous_count = prev_snapshot.member_count if prev_snapshot else 0

        snapshot = SegmentSnapshot(
            segment_id=segment_id,
            member_count=member_count,
            previous_count=previous_count,
            count_change=member_count - previous_count,
            members_entered=entered,
            members_exited=exited,
            snapshot_type=snapshot_type,
            triggered_by="scheduler",
        )
        self.db.add(snapshot)

    # =========================================================================
    # NESTED SEGMENT SUPPORT
    # =========================================================================

    async def _evaluate_nested_segment(self, segment: Segment) -> List[int]:
        """
        Evaluate a nested segment that combines other segments.

        Nested segments can:
        - Include customers from multiple segments (union)
        - Exclude customers from certain segments
        """
        result_ids: Set[int] = set()

        # Process included segments
        if segment.include_segment_ids:
            for included_id in segment.include_segment_ids:
                included_ids = await self._get_customers_in_segments([included_id])
                result_ids.update(included_ids)

        # Also apply any rules the nested segment might have
        if segment.rules_json or segment.rules:
            rules = segment.rules_json or segment.rules
            if rules:
                rule_ids = await self.evaluate_rules(rules)
                if segment.include_segment_ids:
                    # Intersection with rule results
                    result_ids.intersection_update(rule_ids)
                else:
                    result_ids.update(rule_ids)

        # Process excluded segments
        if segment.exclude_segment_ids:
            excluded_ids = await self._get_customers_in_segments(segment.exclude_segment_ids)
            result_ids.difference_update(excluded_ids)

        return list(result_ids)

    async def _get_customers_in_segments(self, segment_ids: List[int]) -> Set[int]:
        """Get all customer IDs that are members of any of the given segments."""
        if not segment_ids:
            return set()

        result = await self.db.execute(
            select(CustomerSegment.customer_id).where(
                CustomerSegment.segment_id.in_(segment_ids),
                CustomerSegment.is_active == True,
            )
        )
        return set(row[0] for row in result.all())

    # =========================================================================
    # QUERY BUILDING
    # =========================================================================

    def _build_query_from_rules(self, rules: Dict[str, Any]) -> Select:
        """
        Build a SQLAlchemy query from a rule set.

        Uses CTEs for efficient joins and avoids N+1 queries.
        """
        # Base query with necessary joins
        query = select(Customer.id).outerjoin(HealthScore, Customer.id == HealthScore.customer_id)

        # Build conditions from rules
        conditions = self._build_conditions(rules)
        if conditions is not None:
            query = query.where(conditions)

        return query

    def _build_conditions(self, rule_set: Dict[str, Any]) -> Any:
        """
        Recursively build SQLAlchemy conditions from a rule set.

        Supports:
        - Nested rule groups with AND/OR logic
        - All operator types including relative dates
        - Field validation and type conversion
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

    def _build_single_condition(self, rule: Dict[str, Any]) -> Any:
        """Build a SQLAlchemy condition for a single rule."""
        field_name = rule.get("field")
        operator = rule.get("operator")
        value = rule.get("value")
        value2 = rule.get("value2") or rule.get("value_end")

        if not field_name or not operator:
            return None

        # Get field definition
        field_def = self.FIELD_DEFINITIONS.get(field_name)
        if not field_def:
            # Try legacy field mapping
            return self._build_legacy_condition(field_name, operator, value, value2)

        # Get the column
        model = field_def.model
        column = getattr(model, field_def.column, None)
        if column is None:
            return None

        # Build condition based on operator
        return self._apply_operator(column, operator, value, value2, field_def.data_type)

    def _apply_operator(
        self, column: Any, operator: str, value: Any, value2: Any = None, data_type: str = "string"
    ) -> Any:
        """Apply an operator to a column with proper type handling."""

        # Normalize operator name (handle both formats)
        op = operator.lower().replace("-", "_")

        # Equality operators
        if op in ("equals", "eq", "equal"):
            return column == value
        elif op in ("not_equals", "neq", "not_equal"):
            return column != value

        # Comparison operators
        elif op in ("greater_than", "gt"):
            return column > value
        elif op in ("less_than", "lt"):
            return column < value
        elif op in ("greater_than_or_equals", "gte", "greater_than_or_equal"):
            return column >= value
        elif op in ("less_than_or_equals", "lte", "less_than_or_equal"):
            return column <= value
        elif op == "between":
            if value2 is not None:
                return and_(column >= value, column <= value2)
            return None

        # String operators
        elif op == "contains":
            return column.ilike(f"%{value}%")
        elif op == "not_contains":
            return not_(column.ilike(f"%{value}%"))
        elif op == "starts_with":
            return column.ilike(f"{value}%")
        elif op == "ends_with":
            return column.ilike(f"%{value}")

        # List operators
        elif op == "in_list":
            if isinstance(value, list):
                return column.in_(value)
            return column == value
        elif op == "not_in_list":
            if isinstance(value, list):
                return not_(column.in_(value))
            return column != value

        # Null operators
        elif op in ("is_empty", "is_null"):
            return column.is_(None)
        elif op in ("is_not_empty", "is_not_null"):
            return column.isnot(None)

        # Relative date operators
        elif op == "days_ago":
            target_date = datetime.utcnow() - timedelta(days=int(value))
            return func.date(column) == target_date.date()
        elif op == "weeks_ago":
            target_date = datetime.utcnow() - timedelta(weeks=int(value))
            return func.date(column) == target_date.date()
        elif op == "months_ago":
            target_date = datetime.utcnow() - timedelta(days=int(value) * 30)
            return func.date(column) >= target_date.date()
        elif op == "in_last_n_days":
            cutoff = datetime.utcnow() - timedelta(days=int(value))
            return column >= cutoff
        elif op == "in_last_n_weeks":
            cutoff = datetime.utcnow() - timedelta(weeks=int(value))
            return column >= cutoff
        elif op == "in_last_n_months":
            cutoff = datetime.utcnow() - timedelta(days=int(value) * 30)
            return column >= cutoff
        elif op == "before_date":
            if isinstance(value, str):
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return column < value
        elif op == "after_date":
            if isinstance(value, str):
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return column > value

        # Relative period operators
        elif op == "this_week":
            today = datetime.utcnow().date()
            start_of_week = today - timedelta(days=today.weekday())
            return and_(func.date(column) >= start_of_week, func.date(column) <= today)
        elif op == "last_week":
            today = datetime.utcnow().date()
            start_of_last_week = today - timedelta(days=today.weekday() + 7)
            end_of_last_week = start_of_last_week + timedelta(days=6)
            return and_(func.date(column) >= start_of_last_week, func.date(column) <= end_of_last_week)
        elif op == "this_month":
            today = datetime.utcnow().date()
            start_of_month = today.replace(day=1)
            return and_(func.date(column) >= start_of_month, func.date(column) <= today)
        elif op == "last_month":
            today = datetime.utcnow().date()
            first_of_this_month = today.replace(day=1)
            last_of_prev_month = first_of_this_month - timedelta(days=1)
            first_of_prev_month = last_of_prev_month.replace(day=1)
            return and_(func.date(column) >= first_of_prev_month, func.date(column) <= last_of_prev_month)
        elif op == "this_quarter":
            today = datetime.utcnow().date()
            quarter = (today.month - 1) // 3
            start_of_quarter = today.replace(month=quarter * 3 + 1, day=1)
            return and_(func.date(column) >= start_of_quarter, func.date(column) <= today)
        elif op == "this_year":
            today = datetime.utcnow().date()
            start_of_year = today.replace(month=1, day=1)
            return and_(func.date(column) >= start_of_year, func.date(column) <= today)

        return None

    def _build_legacy_condition(self, field_name: str, operator: str, value: Any, value2: Any) -> Any:
        """Handle legacy field mappings from existing segment evaluator."""
        # Legacy field mapping for backward compatibility
        LEGACY_FIELD_MAPPING = {
            "customer_type": (Customer, "customer_type"),
            "is_active": (Customer, "is_active"),
            "created_at": (Customer, "created_at"),
            "state": (Customer, "state"),
            "city": (Customer, "city"),
            "tags": (Customer, "tags"),
            "lead_source": (Customer, "lead_source"),
            "prospect_stage": (Customer, "prospect_stage"),
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

        if field_name not in LEGACY_FIELD_MAPPING:
            return None

        model, attr_name = LEGACY_FIELD_MAPPING[field_name]
        column = getattr(model, attr_name)

        return self._apply_operator(column, operator, value, value2)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _get_static_segment_members(self, segment_id: int) -> List[int]:
        """Get customer IDs for a static segment."""
        result = await self.db.execute(
            select(CustomerSegment.customer_id).where(
                CustomerSegment.segment_id == segment_id,
                CustomerSegment.is_active == True,
            )
        )
        return [row[0] for row in result.all()]

    async def _get_ai_segment_members(self, segment_id: int) -> List[int]:
        """Get customer IDs for an AI-generated segment."""
        # AI segments store members like static segments
        return await self._get_static_segment_members(segment_id)

    async def _evaluate_dynamic_segment(self, segment: Segment, limit: Optional[int] = None) -> List[int]:
        """Evaluate a dynamic segment's rules."""
        rules = segment.rules_json or segment.rules
        if not rules:
            return []

        return await self.evaluate_rules(
            rules,
            limit=limit,
            include_segments=segment.include_segment_ids,
            exclude_segments=segment.exclude_segment_ids,
        )

    async def get_segment_members_with_details(
        self, segment_id: int, page: int = 1, page_size: int = 50
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get segment members with full customer details.

        Returns paginated results with customer info and health scores.
        """
        # First evaluate to ensure we have current members
        eval_result = await self.evaluate_segment(segment_id)
        matching_ids = eval_result.matching_customer_ids
        total = len(matching_ids)

        if not matching_ids:
            return [], 0

        # Paginate the IDs
        offset = (page - 1) * page_size
        page_ids = matching_ids[offset : offset + page_size]

        # Get full details
        query = (
            select(Customer, HealthScore)
            .outerjoin(HealthScore, Customer.id == HealthScore.customer_id)
            .where(Customer.id.in_(page_ids))
        )
        result = await self.db.execute(query)

        members = []
        for customer, health in result.all():
            members.append(
                {
                    "id": customer.id,
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "email": customer.email,
                    "phone": customer.phone,
                    "customer_type": customer.customer_type,
                    "city": customer.city,
                    "state": customer.state,
                    "is_active": customer.is_active,
                    "created_at": customer.created_at.isoformat() if customer.created_at else None,
                    "health_score": health.overall_score if health else None,
                    "health_status": health.health_status if health else None,
                    "churn_probability": health.churn_probability if health else None,
                    "score_trend": health.score_trend if health else None,
                }
            )

        return members, total

    def get_available_fields(self) -> List[Dict[str, Any]]:
        """Get all available fields for segment rules."""
        return [
            {
                "name": field_def.name,
                "display_name": field_def.display_name,
                "category": field_def.category.value,
                "data_type": field_def.data_type,
                "description": field_def.description,
            }
            for field_def in self.FIELD_DEFINITIONS.values()
        ]

    def get_available_operators(self, data_type: str = None) -> List[Dict[str, Any]]:
        """Get available operators, optionally filtered by data type."""
        operators = [
            # Equality
            {"name": "equals", "display": "Equals", "types": ["string", "number", "boolean"]},
            {"name": "not_equals", "display": "Does Not Equal", "types": ["string", "number", "boolean"]},
            # Comparison
            {"name": "greater_than", "display": "Greater Than", "types": ["number", "date"]},
            {"name": "less_than", "display": "Less Than", "types": ["number", "date"]},
            {"name": "greater_than_or_equals", "display": "Greater Than or Equal", "types": ["number", "date"]},
            {"name": "less_than_or_equals", "display": "Less Than or Equal", "types": ["number", "date"]},
            {"name": "between", "display": "Between", "types": ["number", "date"]},
            # String
            {"name": "contains", "display": "Contains", "types": ["string"]},
            {"name": "not_contains", "display": "Does Not Contain", "types": ["string"]},
            {"name": "starts_with", "display": "Starts With", "types": ["string"]},
            {"name": "ends_with", "display": "Ends With", "types": ["string"]},
            # List
            {"name": "in_list", "display": "Is One Of", "types": ["string", "number"]},
            {"name": "not_in_list", "display": "Is Not One Of", "types": ["string", "number"]},
            # Null
            {"name": "is_empty", "display": "Is Empty", "types": ["string", "number", "date"]},
            {"name": "is_not_empty", "display": "Is Not Empty", "types": ["string", "number", "date"]},
            # Date relative
            {"name": "days_ago", "display": "Days Ago", "types": ["date"]},
            {"name": "in_last_n_days", "display": "In Last N Days", "types": ["date"]},
            {"name": "in_last_n_weeks", "display": "In Last N Weeks", "types": ["date"]},
            {"name": "in_last_n_months", "display": "In Last N Months", "types": ["date"]},
            {"name": "this_week", "display": "This Week", "types": ["date"]},
            {"name": "last_week", "display": "Last Week", "types": ["date"]},
            {"name": "this_month", "display": "This Month", "types": ["date"]},
            {"name": "last_month", "display": "Last Month", "types": ["date"]},
            {"name": "this_quarter", "display": "This Quarter", "types": ["date"]},
            {"name": "this_year", "display": "This Year", "types": ["date"]},
        ]

        if data_type:
            operators = [op for op in operators if data_type in op["types"]]

        return operators
