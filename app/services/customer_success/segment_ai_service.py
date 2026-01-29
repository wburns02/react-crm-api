"""
Segment AI Service for Enterprise Customer Success Platform

AI-powered features for segmentation:
- Natural language to segment query converter
- Segment suggestion engine based on patterns
- Revenue opportunity scoring per segment
- Prepared for local LLM integration (Ollama/vLLM ready)

This service uses a hybrid approach:
1. Rule-based parsing for common patterns (fast, no LLM needed)
2. LLM-based parsing for complex queries (when available)
3. Fallback suggestions when parsing fails
"""

from __future__ import annotations

import logging
import re
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional, List, Dict, Tuple
from enum import Enum
import asyncio

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_success import Segment, CustomerSegment, HealthScore, Touchpoint
from app.models.work_order import WorkOrder


logger = logging.getLogger(__name__)


@dataclass
class ParsedSegmentQuery:
    """Result of parsing a natural language query."""

    success: bool
    rules: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    explanation: str = ""
    suggestions: List[str] = field(default_factory=list)
    parsed_entities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SegmentSuggestion:
    """AI-generated segment suggestion."""

    name: str
    description: str
    rules: Dict[str, Any]
    reasoning: str
    estimated_count: int = 0
    revenue_opportunity: Decimal = Decimal("0")
    priority: int = 0  # 1-10, higher is more important
    category: str = "general"
    tags: List[str] = field(default_factory=list)


@dataclass
class RevenueOpportunity:
    """Revenue opportunity analysis for a segment."""

    segment_id: int
    segment_name: str
    total_customers: int
    total_potential_revenue: Decimal
    avg_revenue_per_customer: Decimal
    upsell_candidates: int
    at_risk_revenue: Decimal
    expansion_probability: float
    recommended_actions: List[str]
    reasoning: str


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    NONE = "none"  # Rule-based only
    OLLAMA = "ollama"
    VLLM = "vllm"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class SegmentAIService:
    """
    AI-powered segment service for natural language processing
    and intelligent segment suggestions.

    Features:
    - Parse natural language queries into segment rules
    - Suggest segments based on data patterns
    - Score revenue opportunities per segment
    - Ready for local LLM integration
    """

    # Common field aliases for natural language parsing
    FIELD_ALIASES = {
        # Health score variations
        "health": "health_score",
        "health score": "health_score",
        "healthscore": "health_score",
        "score": "health_score",
        # Status variations
        "status": "health_status",
        "health status": "health_status",
        # Churn variations
        "churn": "churn_probability",
        "churn risk": "churn_probability",
        "churn probability": "churn_probability",
        "risk": "churn_probability",
        # Customer type variations
        "type": "customer_type",
        "customer type": "customer_type",
        # Location variations
        "location": "city",
        "city": "city",
        "state": "state",
        # Date variations
        "created": "created_at",
        "created date": "created_at",
        "signup": "created_at",
        "signup date": "created_at",
        "joined": "created_at",
        # Activity variations
        "active": "is_active",
        "inactive": "is_active",
        # Engagement variations
        "engagement": "engagement_score",
        "engaged": "engagement_score",
        # Financial
        "value": "estimated_value",
        "worth": "estimated_value",
        "revenue": "estimated_value",
    }

    # Operator patterns for natural language
    OPERATOR_PATTERNS = [
        # Comparison
        (r"(?:is )?greater than (\d+)", "greater_than"),
        (r"(?:is )?more than (\d+)", "greater_than"),
        (r"(?:is )?above (\d+)", "greater_than"),
        (r"(?:is )?over (\d+)", "greater_than"),
        (r"> ?(\d+)", "greater_than"),
        (r"(?:is )?less than (\d+)", "less_than"),
        (r"(?:is )?under (\d+)", "less_than"),
        (r"(?:is )?below (\d+)", "less_than"),
        (r"< ?(\d+)", "less_than"),
        (r"(?:is )?at least (\d+)", "greater_than_or_equals"),
        (r">= ?(\d+)", "greater_than_or_equals"),
        (r"(?:is )?at most (\d+)", "less_than_or_equals"),
        (r"<= ?(\d+)", "less_than_or_equals"),
        (r"between (\d+) and (\d+)", "between"),
        (r"from (\d+) to (\d+)", "between"),
        # Equality
        (r"(?:is )?equal(?:s)? (?:to )?['\"]?([^'\"]+)['\"]?", "equals"),
        (r"(?:is )?exactly ['\"]?([^'\"]+)['\"]?", "equals"),
        (r"= ?['\"]?([^'\"]+)['\"]?", "equals"),
        # Contains
        (r"contains ['\"]?([^'\"]+)['\"]?", "contains"),
        (r"includes ['\"]?([^'\"]+)['\"]?", "contains"),
        (r"has ['\"]?([^'\"]+)['\"]?", "contains"),
        # List
        (r"(?:is )?(?:one of|in) \[([^\]]+)\]", "in_list"),
        (r"(?:is )?(?:one of|in) \(([^\)]+)\)", "in_list"),
        # Date relative
        (r"in (?:the )?last (\d+) days?", "in_last_n_days"),
        (r"within (\d+) days?", "in_last_n_days"),
        (r"past (\d+) days?", "in_last_n_days"),
        (r"in (?:the )?last (\d+) weeks?", "in_last_n_weeks"),
        (r"in (?:the )?last (\d+) months?", "in_last_n_months"),
        (r"this week", "this_week"),
        (r"last week", "last_week"),
        (r"this month", "this_month"),
        (r"last month", "last_month"),
        (r"this quarter", "this_quarter"),
        (r"this year", "this_year"),
        # Status keywords
        (r"(?:is |are )?at[- ]risk", "at_risk_status"),
        (r"(?:is |are )?healthy", "healthy_status"),
        (r"(?:is |are )?critical", "critical_status"),
        (r"(?:is |are )?churned", "churned_status"),
        # Empty/null
        (r"(?:is )?empty", "is_empty"),
        (r"(?:is )?null", "is_empty"),
        (r"(?:is )?not empty", "is_not_empty"),
        (r"(?:is )?not null", "is_not_empty"),
        (r"has no", "is_empty"),
    ]

    # Pre-built segment templates
    SEGMENT_TEMPLATES = {
        "at_risk_customers": {
            "name": "At-Risk Customers",
            "description": "Customers with declining health scores or high churn probability",
            "rules": {
                "logic": "or",
                "rules": [
                    {"field": "health_status", "operator": "equals", "value": "at_risk"},
                    {"field": "churn_probability", "operator": "greater_than", "value": 0.5},
                    {"field": "score_trend", "operator": "equals", "value": "declining"},
                ],
            },
        },
        "high_value_customers": {
            "name": "High Value Customers",
            "description": "Enterprise and VIP customers with high estimated value",
            "rules": {
                "logic": "or",
                "rules": [
                    {"field": "customer_type", "operator": "in_list", "value": ["enterprise", "vip"]},
                    {"field": "estimated_value", "operator": "greater_than", "value": 10000},
                ],
            },
        },
        "new_customers": {
            "name": "New Customers",
            "description": "Customers who joined in the last 30 days",
            "rules": {
                "logic": "and",
                "rules": [
                    {"field": "created_at", "operator": "in_last_n_days", "value": 30},
                ],
            },
        },
        "inactive_customers": {
            "name": "Inactive Customers",
            "description": "Customers with no recent activity",
            "rules": {
                "logic": "and",
                "rules": [
                    {"field": "is_active", "operator": "equals", "value": True},
                    {"field": "engagement_score", "operator": "less_than", "value": 30},
                ],
            },
        },
        "expansion_ready": {
            "name": "Expansion Ready",
            "description": "Healthy customers with high expansion probability",
            "rules": {
                "logic": "and",
                "rules": [
                    {"field": "health_status", "operator": "equals", "value": "healthy"},
                    {"field": "expansion_probability", "operator": "greater_than", "value": 0.5},
                ],
            },
        },
    }

    def __init__(
        self, db: AsyncSession, llm_provider: LLMProvider = LLMProvider.NONE, llm_endpoint: Optional[str] = None
    ):
        """
        Initialize the AI service.

        Args:
            db: Database session
            llm_provider: LLM provider to use (default: rule-based only)
            llm_endpoint: Endpoint URL for LLM API (for Ollama/vLLM)
        """
        self.db = db
        self.llm_provider = llm_provider
        self.llm_endpoint = llm_endpoint

    # =========================================================================
    # NATURAL LANGUAGE PARSING
    # =========================================================================

    async def parse_natural_language(self, query: str, use_llm: bool = False) -> ParsedSegmentQuery:
        """
        Parse a natural language query into segment rules.

        Examples:
        - "customers with health score below 50"
        - "at-risk customers in Texas"
        - "enterprise customers created last month"
        - "customers who haven't engaged in 30 days"

        Args:
            query: Natural language query
            use_llm: Whether to use LLM for complex queries

        Returns:
            ParsedSegmentQuery with rules and confidence
        """
        query = query.strip().lower()

        # Try rule-based parsing first
        result = self._parse_with_rules(query)

        if result.success and result.confidence >= 0.7:
            return result

        # If rule-based parsing fails or has low confidence, try LLM
        if use_llm and self.llm_provider != LLMProvider.NONE:
            llm_result = await self._parse_with_llm(query)
            if llm_result.success and llm_result.confidence > result.confidence:
                return llm_result

        # Return best result (even if partial)
        if not result.success:
            # Provide helpful suggestions
            result.suggestions = self._generate_query_suggestions(query)

        return result

    def _parse_with_rules(self, query: str) -> ParsedSegmentQuery:
        """Parse query using rule-based pattern matching."""
        rules = []
        entities = {}
        confidence = 0.0

        # Check for template matches first
        for template_key, template in self.SEGMENT_TEMPLATES.items():
            if template_key.replace("_", " ") in query or template_key.replace("_", "-") in query:
                return ParsedSegmentQuery(
                    success=True,
                    rules=template["rules"],
                    confidence=0.9,
                    explanation=f"Matched template: {template['name']}",
                    parsed_entities={"template": template_key},
                )

        # Check for status keywords
        status_rules = self._parse_status_keywords(query)
        if status_rules:
            rules.extend(status_rules)
            confidence += 0.3

        # Extract field-operator-value patterns
        field_rules = self._parse_field_patterns(query)
        if field_rules:
            rules.extend(field_rules)
            confidence += 0.4

        # Extract location patterns
        location_rules = self._parse_location_patterns(query)
        if location_rules:
            rules.extend(location_rules)
            confidence += 0.2

        # Extract time patterns
        time_rules = self._parse_time_patterns(query)
        if time_rules:
            rules.extend(time_rules)
            confidence += 0.2

        if not rules:
            return ParsedSegmentQuery(
                success=False,
                explanation="Could not parse query into segment rules",
                suggestions=self._generate_query_suggestions(query),
            )

        # Determine logic (AND vs OR)
        logic = "or" if " or " in query else "and"

        return ParsedSegmentQuery(
            success=True,
            rules={"logic": logic, "rules": rules},
            confidence=min(confidence, 0.95),
            explanation=f"Parsed {len(rules)} rule(s) with {logic.upper()} logic",
            parsed_entities=entities,
        )

    def _parse_status_keywords(self, query: str) -> List[Dict[str, Any]]:
        """Parse health status keywords."""
        rules = []

        if "at-risk" in query or "at risk" in query:
            rules.append({"field": "health_status", "operator": "equals", "value": "at_risk"})
        elif "healthy" in query:
            rules.append({"field": "health_status", "operator": "equals", "value": "healthy"})
        elif "critical" in query:
            rules.append({"field": "health_status", "operator": "equals", "value": "critical"})
        elif "churned" in query:
            rules.append({"field": "health_status", "operator": "equals", "value": "churned"})

        if "declining" in query:
            rules.append({"field": "score_trend", "operator": "equals", "value": "declining"})
        elif "improving" in query:
            rules.append({"field": "score_trend", "operator": "equals", "value": "improving"})

        if "high churn" in query or "high risk" in query:
            rules.append({"field": "churn_probability", "operator": "greater_than", "value": 0.5})
        elif "low churn" in query or "low risk" in query:
            rules.append({"field": "churn_probability", "operator": "less_than", "value": 0.3})

        return rules

    def _parse_field_patterns(self, query: str) -> List[Dict[str, Any]]:
        """Parse field-operator-value patterns."""
        rules = []

        # Try each operator pattern
        for pattern, operator in self.OPERATOR_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                # Find the field this operator applies to
                field = self._find_field_in_query(query, match.start())
                if field:
                    if operator == "between" and len(match.groups()) >= 2:
                        rules.append(
                            {
                                "field": field,
                                "operator": operator,
                                "value": int(match.group(1)),
                                "value2": int(match.group(2)),
                            }
                        )
                    elif operator in ("at_risk_status", "healthy_status", "critical_status", "churned_status"):
                        status_value = operator.replace("_status", "").replace("_", "-")
                        rules.append({"field": "health_status", "operator": "equals", "value": status_value})
                    elif operator in (
                        "this_week",
                        "last_week",
                        "this_month",
                        "last_month",
                        "this_quarter",
                        "this_year",
                    ):
                        rules.append({"field": field, "operator": operator, "value": None})
                    elif match.groups():
                        value = match.group(1)
                        # Try to convert to number
                        try:
                            value = float(value) if "." in value else int(value)
                        except ValueError:
                            pass  # Keep as string
                        rules.append({"field": field, "operator": operator, "value": value})

        return rules

    def _parse_location_patterns(self, query: str) -> List[Dict[str, Any]]:
        """Parse location-related patterns."""
        rules = []

        # State patterns
        state_match = re.search(r"(?:in|from) ([A-Z]{2}|[A-Za-z]+)\b", query)
        if state_match:
            state = state_match.group(1)
            # Check if it's a 2-letter state code or full name
            if len(state) == 2:
                rules.append({"field": "state", "operator": "equals", "value": state.upper()})
            else:
                rules.append({"field": "state", "operator": "contains", "value": state})

        # City patterns
        city_match = re.search(r"city (?:is |= )?['\"]?([^'\"]+)['\"]?", query)
        if city_match:
            rules.append({"field": "city", "operator": "equals", "value": city_match.group(1)})

        return rules

    def _parse_time_patterns(self, query: str) -> List[Dict[str, Any]]:
        """Parse time-related patterns."""
        rules = []

        # "in the last X days/weeks/months"
        time_match = re.search(r"(?:in |within )?(?:the )?last (\d+) (days?|weeks?|months?)", query)
        if time_match:
            value = int(time_match.group(1))
            unit = time_match.group(2).rstrip("s")
            field = self._find_date_field_in_query(query)

            if unit == "day":
                rules.append({"field": field, "operator": "in_last_n_days", "value": value})
            elif unit == "week":
                rules.append({"field": field, "operator": "in_last_n_weeks", "value": value})
            elif unit == "month":
                rules.append({"field": field, "operator": "in_last_n_months", "value": value})

        # Relative periods
        if "this week" in query:
            field = self._find_date_field_in_query(query)
            rules.append({"field": field, "operator": "this_week", "value": None})
        elif "last week" in query:
            field = self._find_date_field_in_query(query)
            rules.append({"field": field, "operator": "last_week", "value": None})
        elif "this month" in query:
            field = self._find_date_field_in_query(query)
            rules.append({"field": field, "operator": "this_month", "value": None})
        elif "last month" in query:
            field = self._find_date_field_in_query(query)
            rules.append({"field": field, "operator": "last_month", "value": None})

        return rules

    def _find_field_in_query(self, query: str, operator_pos: int) -> Optional[str]:
        """Find which field an operator applies to based on position."""
        # Look backwards from operator position for field mention
        before_operator = query[:operator_pos].lower()

        for alias, field in sorted(self.FIELD_ALIASES.items(), key=lambda x: -len(x[0])):
            if alias in before_operator:
                return field

        # Default to health_score for numeric comparisons
        return "health_score"

    def _find_date_field_in_query(self, query: str) -> str:
        """Find the date field mentioned in the query."""
        query = query.lower()

        if "created" in query or "signed up" in query or "joined" in query:
            return "created_at"
        elif "service" in query or "visited" in query:
            return "last_service_date"
        elif "engaged" in query or "contact" in query or "touchpoint" in query:
            return "last_touchpoint_date"

        # Default to created_at
        return "created_at"

    def _generate_query_suggestions(self, query: str) -> List[str]:
        """Generate helpful suggestions when parsing fails."""
        return [
            "Try: 'customers with health score below 50'",
            "Try: 'at-risk customers in Texas'",
            "Try: 'enterprise customers created last month'",
            "Try: 'customers with churn risk above 0.5'",
            "Try: 'new customers in the last 30 days'",
        ]

    async def _parse_with_llm(self, query: str) -> ParsedSegmentQuery:
        """Parse query using LLM for complex patterns."""
        if self.llm_provider == LLMProvider.NONE:
            return ParsedSegmentQuery(success=False, explanation="LLM not configured")

        # Prepare prompt for LLM
        prompt = self._build_llm_prompt(query)

        try:
            if self.llm_provider == LLMProvider.OLLAMA:
                response = await self._call_ollama(prompt)
            elif self.llm_provider == LLMProvider.VLLM:
                response = await self._call_vllm(prompt)
            else:
                return ParsedSegmentQuery(success=False, explanation="LLM provider not supported")

            # Parse LLM response
            rules = self._parse_llm_response(response)
            if rules:
                return ParsedSegmentQuery(success=True, rules=rules, confidence=0.85, explanation="Parsed using LLM")

        except Exception as e:
            logger.exception(f"LLM parsing failed: {e}")

        return ParsedSegmentQuery(success=False, explanation="LLM parsing failed")

    def _build_llm_prompt(self, query: str) -> str:
        """Build prompt for LLM-based parsing."""
        return f"""Convert this natural language query to segment rules.

Query: "{query}"

Available fields: health_score (0-100), health_status (healthy/at_risk/critical/churned),
churn_probability (0-1), customer_type, city, state, created_at, is_active,
engagement_score, expansion_probability, score_trend (improving/stable/declining)

Available operators: equals, not_equals, greater_than, less_than, between,
contains, in_list, is_empty, in_last_n_days, this_week, last_month

Return JSON in this format:
{{
  "logic": "and" or "or",
  "rules": [
    {{"field": "field_name", "operator": "operator_name", "value": value}}
  ]
}}

JSON output only, no explanation:"""

    async def _call_ollama(self, prompt: str) -> str:
        """Call Ollama API for LLM inference."""
        import aiohttp

        endpoint = self.llm_endpoint or "http://localhost:11434/api/generate"

        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, json={"model": "llama2", "prompt": prompt, "stream": False}) as response:
                result = await response.json()
                return result.get("response", "")

    async def _call_vllm(self, prompt: str) -> str:
        """Call vLLM API for LLM inference."""
        import aiohttp

        endpoint = self.llm_endpoint or "http://localhost:8000/v1/completions"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint, json={"prompt": prompt, "max_tokens": 500, "temperature": 0.1}
            ) as response:
                result = await response.json()
                return result.get("choices", [{}])[0].get("text", "")

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response."""
        try:
            # Find JSON in response
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        return None

    # =========================================================================
    # SEGMENT SUGGESTIONS
    # =========================================================================

    async def get_segment_suggestions(self, max_suggestions: int = 5) -> List[SegmentSuggestion]:
        """
        Generate intelligent segment suggestions based on data patterns.

        Analyzes customer data to find:
        - High-value customer groups
        - At-risk customer groups
        - Underserved customer groups
        - Growth opportunity segments
        """
        suggestions = []

        # 1. At-risk customers suggestion
        at_risk = await self._suggest_at_risk_segment()
        if at_risk:
            suggestions.append(at_risk)

        # 2. High-value customers suggestion
        high_value = await self._suggest_high_value_segment()
        if high_value:
            suggestions.append(high_value)

        # 3. Engagement-based suggestions
        low_engagement = await self._suggest_low_engagement_segment()
        if low_engagement:
            suggestions.append(low_engagement)

        # 4. Geographic opportunity
        geo_opportunity = await self._suggest_geographic_segment()
        if geo_opportunity:
            suggestions.append(geo_opportunity)

        # 5. New customer onboarding
        new_customers = await self._suggest_new_customer_segment()
        if new_customers:
            suggestions.append(new_customers)

        # Sort by priority
        suggestions.sort(key=lambda x: x.priority, reverse=True)

        return suggestions[:max_suggestions]

    async def _suggest_at_risk_segment(self) -> Optional[SegmentSuggestion]:
        """Suggest segment for at-risk customers."""
        # Count at-risk customers
        result = await self.db.execute(
            select(func.count(HealthScore.id)).where(
                or_(HealthScore.health_status == "at_risk", HealthScore.churn_probability > 0.5)
            )
        )
        count = result.scalar() or 0

        if count > 0:
            return SegmentSuggestion(
                name="At-Risk Customer Watch",
                description="Customers showing signs of churn risk that need immediate attention",
                rules={
                    "logic": "or",
                    "rules": [
                        {"field": "health_status", "operator": "equals", "value": "at_risk"},
                        {"field": "churn_probability", "operator": "greater_than", "value": 0.5},
                    ],
                },
                reasoning=f"Found {count} customers at risk of churning. Proactive engagement can help retain them.",
                estimated_count=count,
                priority=9,
                category="retention",
                tags=["at-risk", "churn-prevention", "urgent"],
            )
        return None

    async def _suggest_high_value_segment(self) -> Optional[SegmentSuggestion]:
        """Suggest segment for high-value customers."""
        result = await self.db.execute(
            select(func.count(Customer.id)).where(
                or_(Customer.customer_type.in_(["enterprise", "vip"]), Customer.estimated_value > 10000)
            )
        )
        count = result.scalar() or 0

        if count > 0:
            # Calculate total value
            value_result = await self.db.execute(
                select(func.sum(Customer.estimated_value)).where(
                    or_(Customer.customer_type.in_(["enterprise", "vip"]), Customer.estimated_value > 10000)
                )
            )
            total_value = value_result.scalar() or 0

            return SegmentSuggestion(
                name="VIP & Enterprise Customers",
                description="High-value customers requiring premium support and attention",
                rules={
                    "logic": "or",
                    "rules": [
                        {"field": "customer_type", "operator": "in_list", "value": ["enterprise", "vip"]},
                        {"field": "estimated_value", "operator": "greater_than", "value": 10000},
                    ],
                },
                reasoning=f"Your {count} high-value customers represent ${total_value:,.0f} in potential value.",
                estimated_count=count,
                revenue_opportunity=Decimal(str(total_value * 0.1)),  # 10% expansion potential
                priority=8,
                category="value",
                tags=["high-value", "vip", "enterprise"],
            )
        return None

    async def _suggest_low_engagement_segment(self) -> Optional[SegmentSuggestion]:
        """Suggest segment for customers with low engagement."""
        result = await self.db.execute(select(func.count(HealthScore.id)).where(HealthScore.engagement_score < 30))
        count = result.scalar() or 0

        if count > 0:
            return SegmentSuggestion(
                name="Re-Engagement Needed",
                description="Active customers with declining engagement who may need outreach",
                rules={
                    "logic": "and",
                    "rules": [
                        {"field": "is_active", "operator": "equals", "value": True},
                        {"field": "engagement_score", "operator": "less_than", "value": 30},
                    ],
                },
                reasoning=f"{count} customers have low engagement scores. Re-engagement campaigns could improve retention.",
                estimated_count=count,
                priority=7,
                category="engagement",
                tags=["low-engagement", "re-engage", "outreach"],
            )
        return None

    async def _suggest_geographic_segment(self) -> Optional[SegmentSuggestion]:
        """Suggest segment based on geographic concentration."""
        result = await self.db.execute(
            select(Customer.state, func.count(Customer.id).label("count"))
            .group_by(Customer.state)
            .order_by(desc("count"))
            .limit(1)
        )
        top_state = result.first()

        if top_state and top_state.state and top_state.count > 10:
            return SegmentSuggestion(
                name=f"{top_state.state} Market Focus",
                description=f"Customers concentrated in {top_state.state} - your largest market",
                rules={
                    "logic": "and",
                    "rules": [
                        {"field": "state", "operator": "equals", "value": top_state.state},
                    ],
                },
                reasoning=f"{top_state.state} has {top_state.count} customers - your largest geographic concentration. Consider localized campaigns.",
                estimated_count=top_state.count,
                priority=5,
                category="geographic",
                tags=["regional", top_state.state.lower(), "market-focus"],
            )
        return None

    async def _suggest_new_customer_segment(self) -> Optional[SegmentSuggestion]:
        """Suggest segment for new customer onboarding."""
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        result = await self.db.execute(select(func.count(Customer.id)).where(Customer.created_at >= thirty_days_ago))
        count = result.scalar() or 0

        if count > 0:
            return SegmentSuggestion(
                name="New Customer Onboarding",
                description="Customers who joined in the last 30 days - focus on successful onboarding",
                rules={
                    "logic": "and",
                    "rules": [
                        {"field": "created_at", "operator": "in_last_n_days", "value": 30},
                    ],
                },
                reasoning=f"{count} new customers joined in the last 30 days. Ensure they have a great first experience.",
                estimated_count=count,
                priority=6,
                category="lifecycle",
                tags=["new", "onboarding", "welcome"],
            )
        return None

    # =========================================================================
    # REVENUE OPPORTUNITY SCORING
    # =========================================================================

    async def score_revenue_opportunity(self, segment_id: int) -> RevenueOpportunity:
        """
        Calculate revenue opportunity for a segment.

        Analyzes:
        - Total potential revenue
        - Upsell candidates
        - At-risk revenue
        - Expansion probability
        """
        # Get segment
        result = await self.db.execute(select(Segment).where(Segment.id == segment_id))
        segment = result.scalar_one_or_none()

        if not segment:
            raise ValueError(f"Segment {segment_id} not found")

        # Get member IDs
        members_result = await self.db.execute(
            select(CustomerSegment.customer_id).where(
                CustomerSegment.segment_id == segment_id, CustomerSegment.is_active == True
            )
        )
        member_ids = [row[0] for row in members_result.all()]

        if not member_ids:
            return RevenueOpportunity(
                segment_id=segment_id,
                segment_name=segment.name,
                total_customers=0,
                total_potential_revenue=Decimal("0"),
                avg_revenue_per_customer=Decimal("0"),
                upsell_candidates=0,
                at_risk_revenue=Decimal("0"),
                expansion_probability=0,
                recommended_actions=[],
                reasoning="Segment has no members",
            )

        # Calculate metrics
        stats_result = await self.db.execute(
            select(
                func.count(Customer.id).label("count"),
                func.sum(Customer.estimated_value).label("total_value"),
                func.avg(Customer.estimated_value).label("avg_value"),
            ).where(Customer.id.in_(member_ids))
        )
        stats = stats_result.first()

        # Get expansion candidates (healthy with high expansion probability)
        expansion_result = await self.db.execute(
            select(func.count(HealthScore.id), func.avg(HealthScore.expansion_probability)).where(
                HealthScore.customer_id.in_(member_ids),
                HealthScore.health_status == "healthy",
                HealthScore.expansion_probability > 0.5,
            )
        )
        expansion_stats = expansion_result.first()
        upsell_candidates = expansion_stats[0] or 0
        avg_expansion_prob = expansion_stats[1] or 0

        # Get at-risk revenue
        at_risk_result = await self.db.execute(
            select(func.sum(Customer.estimated_value))
            .outerjoin(HealthScore, Customer.id == HealthScore.customer_id)
            .where(
                Customer.id.in_(member_ids),
                or_(HealthScore.health_status == "at_risk", HealthScore.churn_probability > 0.5),
            )
        )
        at_risk_revenue = at_risk_result.scalar() or 0

        total_value = stats.total_value or 0
        avg_value = stats.avg_value or 0
        total_customers = stats.count or 0

        # Generate recommendations
        actions = []
        if upsell_candidates > 0:
            actions.append(f"Target {upsell_candidates} customers for expansion campaigns")
        if at_risk_revenue > 0:
            actions.append(f"Protect ${at_risk_revenue:,.0f} at-risk revenue with retention efforts")
        if avg_expansion_prob > 0.5:
            actions.append("Launch upsell campaigns - high expansion probability detected")
        if total_customers > 10:
            actions.append("Consider personalized outreach for top 10 customers by value")

        return RevenueOpportunity(
            segment_id=segment_id,
            segment_name=segment.name,
            total_customers=total_customers,
            total_potential_revenue=Decimal(str(total_value)),
            avg_revenue_per_customer=Decimal(str(avg_value)),
            upsell_candidates=upsell_candidates,
            at_risk_revenue=Decimal(str(at_risk_revenue)),
            expansion_probability=float(avg_expansion_prob),
            recommended_actions=actions,
            reasoning=f"Segment contains {total_customers} customers with ${total_value:,.0f} in potential value. "
            f"{upsell_candidates} are ready for expansion.",
        )

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_segment_templates(self) -> Dict[str, Dict[str, Any]]:
        """Get all available segment templates."""
        return self.SEGMENT_TEMPLATES

    def get_available_fields_for_nl(self) -> List[Dict[str, Any]]:
        """Get available fields formatted for natural language help."""
        fields = []
        seen = set()
        for alias, field in self.FIELD_ALIASES.items():
            if field not in seen:
                fields.append(
                    {
                        "field": field,
                        "aliases": [a for a, f in self.FIELD_ALIASES.items() if f == field],
                        "examples": self._get_field_examples(field),
                    }
                )
                seen.add(field)
        return fields

    def _get_field_examples(self, field: str) -> List[str]:
        """Get example queries for a field."""
        examples = {
            "health_score": ["health score below 50", "score greater than 80"],
            "health_status": ["at-risk customers", "healthy customers"],
            "customer_type": ["enterprise customers", "residential customers"],
            "created_at": ["created in the last 30 days", "customers who joined last month"],
            "churn_probability": ["high churn risk", "churn probability above 0.5"],
        }
        return examples.get(field, [])
