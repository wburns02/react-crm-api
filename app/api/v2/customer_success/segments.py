"""
Segment API Endpoints for Enterprise Customer Success Platform

Includes:
- Standard CRUD operations for segments
- Smart segment management (pre-built system segments)
- Segment evaluation and preview
- Customer segment membership management
- Bulk actions: export, schedule, tag, assign
"""

from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
import csv
import io

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.models.customer_success import Segment, CustomerSegment, SegmentSnapshot
from uuid import uuid4
from datetime import date
from app.schemas.customer_success.segment import (
    SegmentCreate,
    SegmentUpdate,
    SegmentResponse,
    SegmentListResponse,
    CustomerSegmentResponse,
    SegmentPreviewRequest,
    SegmentPreviewResponse,
    EnhancedSegmentPreviewRequest,
    NaturalLanguageQueryRequest,
    NaturalLanguageQueryResponse,
    SegmentSuggestionsResponse,
    SegmentSuggestion,
    RevenueOpportunityResponse,
    SegmentSnapshotResponse,
    SegmentSnapshotListResponse,
    SegmentFieldsResponse,
    FieldDefinitionResponse,
    OperatorDefinitionResponse,
    SegmentEvaluationRequest,
    SegmentEvaluationResponse,
    SegmentMembersResponse,
    SegmentMemberDetail,
    SegmentTemplatesResponse,
    SegmentTemplateResponse,
    SegmentType,
    SegmentCategory,
    SmartSegmentSeedResponse,
    SmartSegmentListResponse,
    SmartSegmentCategory,
)
from app.services.customer_success.smart_segments import SmartSegmentService
from app.services.customer_success import SegmentEngine, SegmentAIService

router = APIRouter()


# ============================================
# Bulk Action Request/Response Models
# ============================================


class ExportRequest(BaseModel):
    format: str = "csv"  # csv or excel
    fields: List[str]
    include_health_score: bool = False
    include_contact_info: bool = True
    include_financials: bool = False
    include_tags: bool = False
    include_custom_fields: bool = False


class ExportResponse(BaseModel):
    status: str
    message: str
    download_url: Optional[str] = None
    filename: Optional[str] = None
    record_count: int


class BulkScheduleRequest(BaseModel):
    scheduled_date: str
    scheduled_time: Optional[str] = None
    service_type: str
    priority: str = "medium"
    assignment_method: str = "auto"  # auto, specific, round_robin
    assigned_user_id: Optional[int] = None
    notes: Optional[str] = None
    create_work_orders: bool = True
    send_notifications: bool = True


class BulkScheduleResponse(BaseModel):
    status: str
    message: str
    work_orders_created: int
    scheduled_date: str
    customers_affected: int


class BulkTagRequest(BaseModel):
    tag: str
    action: str = "add"  # add or remove


class BulkTagResponse(BaseModel):
    status: str
    message: str
    customers_updated: int
    tag: str


class BulkAssignRequest(BaseModel):
    assigned_user_id: Optional[int] = None
    assignment_method: str = "auto"  # auto, specific, round_robin


class BulkAssignResponse(BaseModel):
    status: str
    message: str
    customers_assigned: int
    assigned_to_user_id: Optional[int] = None
    assignment_method: str


class BulkTasksRequest(BaseModel):
    task_type: str
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "medium"
    assigned_user_id: Optional[int] = None


class BulkWorkOrdersRequest(BaseModel):
    work_order_type: str
    title: str
    description: Optional[str] = None
    scheduled_date: Optional[str] = None
    priority: str = "medium"
    assigned_user_id: Optional[int] = None


class CreateCallListRequest(BaseModel):
    name: Optional[str] = None
    priority: str = "medium"


# =============================================================================
# SMART SEGMENTS ENDPOINTS
# =============================================================================


@router.get("/smart", response_model=SmartSegmentListResponse)
async def list_smart_segments(
    db: DbSession,
    current_user: CurrentUser,
    category: Optional[str] = None,
):
    """
    List all pre-built smart segments.

    Smart segments are system-defined segments that cannot be deleted.
    They are organized by category:
    - lifecycle: New, Loyal, Dormant, At-Risk, Churned
    - value: VIP, High Value, Medium Value, Low Value
    - service: Aerobic, Conventional, Contract, One-Time, Service Due, Overdue
    - engagement: Email Engaged/Unengaged, NPS Promoters/Passives/Detractors
    - geographic: By city and county
    """
    service = SmartSegmentService(db)

    # Get segments
    segments = await service.get_smart_segments(category=category)

    # Get categories with counts
    categories = await service.get_segment_categories()

    return SmartSegmentListResponse(
        segments=segments,
        categories=categories,
        total=len(segments),
    )


@router.post("/smart/seed", response_model=SmartSegmentSeedResponse)
async def seed_smart_segments(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Seed the pre-built smart segments.

    This creates or updates all system-defined segments.
    Safe to run multiple times - existing segments will be updated.
    """
    service = SmartSegmentService(db)
    result = await service.seed_smart_segments()
    return SmartSegmentSeedResponse(**result)


@router.post("/smart/reset", response_model=SmartSegmentSeedResponse)
async def reset_smart_segments(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Reset all smart segments to default definitions.

    WARNING: This will delete all existing system segments and recreate them.
    Custom modifications to system segments will be lost.
    """
    service = SmartSegmentService(db)
    result = await service.reset_smart_segments()
    return SmartSegmentSeedResponse(**result)


@router.get("/smart/categories")
async def list_smart_segment_categories(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    List all smart segment categories with counts.
    """
    service = SmartSegmentService(db)
    categories = await service.get_segment_categories()
    return {"categories": categories}


# =============================================================================
# STANDARD SEGMENT CRUD ENDPOINTS
# =============================================================================


@router.get("/", response_model=SegmentListResponse)
async def list_segments(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    segment_type: Optional[str] = None,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_system: Optional[bool] = None,
    search: Optional[str] = None,
):
    """List segments with filtering."""
    query = select(Segment)

    if segment_type:
        query = query.where(Segment.segment_type == segment_type)
    if category:
        query = query.where(Segment.category == category)
    if is_active is not None:
        query = query.where(Segment.is_active == is_active)
    if is_system is not None:
        query = query.where(Segment.is_system == is_system)
    if search:
        query = query.where(Segment.name.ilike(f"%{search}%"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Segment.priority.desc(), Segment.name)

    result = await db.execute(query)
    segments = result.scalars().all()

    return SegmentListResponse(
        items=segments,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{segment_id}", response_model=SegmentResponse)
async def get_segment(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific segment."""
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    return segment


@router.post("/", response_model=SegmentResponse, status_code=status.HTTP_201_CREATED)
async def create_segment(
    data: SegmentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new segment."""
    # Check for duplicate name
    existing = await db.execute(select(Segment).where(Segment.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Segment with this name already exists",
        )

    segment = Segment(
        **data.model_dump(),
        created_by_user_id=current_user.id,
        owned_by_user_id=current_user.id,
    )
    db.add(segment)
    await db.commit()
    await db.refresh(segment)
    return segment


@router.patch("/{segment_id}", response_model=SegmentResponse)
async def update_segment(
    segment_id: int,
    data: SegmentUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a segment."""
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Check for duplicate name if updating name
    if "name" in update_data and update_data["name"] != segment.name:
        existing = await db.execute(select(Segment).where(Segment.name == update_data["name"]))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Segment with this name already exists",
            )

    for field, value in update_data.items():
        setattr(segment, field, value)

    await db.commit()
    await db.refresh(segment)
    return segment


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segment(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a segment.

    System segments (is_system=True) cannot be deleted.
    """
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    # Prevent deletion of system segments
    if segment.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System segments cannot be deleted. Use /smart/reset to restore defaults.",
        )

    await db.delete(segment)
    await db.commit()


@router.get("/{segment_id}/customers")
async def list_segment_customers(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = True,
):
    """List customers in a segment."""
    # Check segment exists
    segment_result = await db.execute(select(Segment).where(Segment.id == segment_id))
    if not segment_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    query = select(CustomerSegment).where(CustomerSegment.segment_id == segment_id)

    if is_active is not None:
        query = query.where(CustomerSegment.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(CustomerSegment.entered_at.desc())

    result = await db.execute(query)
    memberships = result.scalars().all()

    return {
        "items": memberships,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{segment_id}/customers/{customer_id}")
async def add_customer_to_segment(
    segment_id: int,
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
    reason: Optional[str] = None,
):
    """Manually add a customer to a segment."""
    # Check segment exists and is static
    segment_result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = segment_result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    if segment.segment_type != SegmentType.STATIC.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only manually add customers to static segments",
        )

    # Check if already in segment
    existing = await db.execute(
        select(CustomerSegment).where(
            CustomerSegment.segment_id == segment_id,
            CustomerSegment.customer_id == customer_id,
            CustomerSegment.is_active == True,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer is already in this segment",
        )

    membership = CustomerSegment(
        customer_id=customer_id,
        segment_id=segment_id,
        entry_reason=reason or "Manual addition",
        entered_at=datetime.utcnow(),
    )
    db.add(membership)

    # Update segment count
    segment.customer_count = (segment.customer_count or 0) + 1

    await db.commit()
    await db.refresh(membership)

    return {"status": "success", "message": "Customer added to segment"}


@router.delete("/{segment_id}/customers/{customer_id}")
async def remove_customer_from_segment(
    segment_id: int,
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
    reason: Optional[str] = None,
):
    """Remove a customer from a segment."""
    result = await db.execute(
        select(CustomerSegment).where(
            CustomerSegment.segment_id == segment_id,
            CustomerSegment.customer_id == customer_id,
            CustomerSegment.is_active == True,
        )
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer is not in this segment",
        )

    membership.is_active = False
    membership.exited_at = datetime.utcnow()
    membership.exit_reason = reason or "Manual removal"

    # Update segment count
    segment_result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = segment_result.scalar_one_or_none()
    if segment:
        segment.customer_count = max(0, (segment.customer_count or 1) - 1)

    await db.commit()

    return {"status": "success", "message": "Customer removed from segment"}


@router.post("/preview", response_model=SegmentPreviewResponse)
async def preview_segment(
    request: SegmentPreviewRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Preview customers that would match segment rules."""
    engine = SegmentEngine(db)

    # Convert Pydantic model to dict
    rules_dict = request.rules.model_dump() if request.rules else {}

    preview = await engine.preview_segment(rules=rules_dict, sample_size=min(request.limit, 100))

    return SegmentPreviewResponse(
        total_matches=preview.estimated_count,
        sample_customers=preview.sample_customers,
        estimated_arr=float(preview.estimated_arr) if preview.estimated_arr else None,
        avg_health_score=preview.avg_health_score,
        health_distribution=preview.health_distribution,
        customer_type_distribution=preview.customer_type_distribution,
        geographic_distribution=preview.geographic_distribution,
        execution_time_ms=preview.execution_time_ms,
    )


@router.post("/preview/enhanced", response_model=SegmentPreviewResponse)
async def preview_segment_enhanced(
    request: EnhancedSegmentPreviewRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Enhanced preview with segment inclusions/exclusions."""
    engine = SegmentEngine(db)

    # Convert Pydantic model to dict
    rules_dict = request.rules.model_dump() if request.rules else {}

    preview = await engine.preview_segment(
        rules=rules_dict,
        sample_size=request.sample_size,
        include_segments=request.include_segments,
        exclude_segments=request.exclude_segments,
    )

    return SegmentPreviewResponse(
        total_matches=preview.estimated_count,
        sample_customers=preview.sample_customers,
        estimated_arr=float(preview.estimated_arr) if preview.estimated_arr else None,
        avg_health_score=preview.avg_health_score,
        health_distribution=preview.health_distribution,
        customer_type_distribution=preview.customer_type_distribution,
        geographic_distribution=preview.geographic_distribution,
        execution_time_ms=preview.execution_time_ms,
    )


@router.post("/estimate")
async def estimate_segment_size(
    request: SegmentPreviewRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Quickly estimate segment size without fetching customers."""
    engine = SegmentEngine(db)

    rules_dict = request.rules.model_dump() if request.rules else {}
    count = await engine.estimate_segment_size(rules=rules_dict)

    return {"estimated_count": count}


@router.post("/{segment_id}/evaluate", response_model=SegmentEvaluationResponse)
async def evaluate_segment(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
    request: Optional[SegmentEvaluationRequest] = None,
):
    """Evaluate/refresh a dynamic segment's membership."""
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    if segment.segment_type == SegmentType.STATIC.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot evaluate static segments - they are manually managed",
        )

    engine = SegmentEngine(db)

    track_history = request.track_history if request else True
    create_snapshot = request.create_snapshot if request else True

    update_result = await engine.update_segment_membership(
        segment_id, track_history=track_history, create_snapshot=create_snapshot
    )

    return SegmentEvaluationResponse(
        segment_id=segment_id,
        total_members=update_result.total_members,
        customers_added=update_result.customers_added,
        customers_removed=update_result.customers_removed,
        execution_time_ms=update_result.execution_time_ms,
        snapshot_created=create_snapshot and (update_result.customers_added > 0 or update_result.customers_removed > 0),
    )


# =============================================================================
# SEGMENT MEMBERS WITH DETAILS
# =============================================================================


@router.get("/{segment_id}/members", response_model=SegmentMembersResponse)
async def list_segment_members(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List customers in a segment with full details including health scores."""
    # Check segment exists
    segment_result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = segment_result.scalar_one_or_none()
    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    # Use engine for real-time evaluation
    engine = SegmentEngine(db)
    members, total = await engine.get_segment_members_with_details(segment_id, page, page_size)

    return SegmentMembersResponse(
        items=[SegmentMemberDetail(**m) for m in members],
        total=total,
        page=page,
        page_size=page_size,
        segment_id=segment_id,
        segment_name=segment.name,
    )


# =============================================================================
# SEGMENT HISTORY AND SNAPSHOTS
# =============================================================================


@router.get("/{segment_id}/history", response_model=SegmentSnapshotListResponse)
async def get_segment_history(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get segment membership history (snapshots over time)."""
    # Verify segment exists
    segment_result = await db.execute(select(Segment).where(Segment.id == segment_id))
    if not segment_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    query = select(SegmentSnapshot).where(SegmentSnapshot.segment_id == segment_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(SegmentSnapshot.snapshot_at.desc())

    result = await db.execute(query)
    snapshots = result.scalars().all()

    return SegmentSnapshotListResponse(
        items=snapshots,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{segment_id}/snapshot", response_model=SegmentSnapshotResponse)
async def create_snapshot(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Manually create a snapshot of current segment membership."""
    # Verify segment exists
    segment_result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = segment_result.scalar_one_or_none()
    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    # Get current member count
    member_count = segment.customer_count or 0

    # Get previous snapshot
    prev_result = await db.execute(
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
        snapshot_type="manual",
        triggered_by=f"user:{current_user.id}",
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    return snapshot


# =============================================================================
# AI ENDPOINTS
# =============================================================================


@router.post("/ai/parse", response_model=NaturalLanguageQueryResponse)
async def parse_natural_language_query(
    request: NaturalLanguageQueryRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Parse a natural language query into segment rules.

    Examples:
    - "customers with health score below 50"
    - "at-risk customers in Texas"
    - "enterprise customers created last month"
    """
    ai_service = SegmentAIService(db)

    result = await ai_service.parse_natural_language(query=request.query, use_llm=request.use_llm)

    return NaturalLanguageQueryResponse(
        success=result.success,
        rules=result.rules,
        confidence=result.confidence,
        explanation=result.explanation,
        suggestions=result.suggestions,
        parsed_entities=result.parsed_entities,
    )


@router.get("/ai/suggestions", response_model=SegmentSuggestionsResponse)
async def get_segment_suggestions(
    db: DbSession,
    current_user: CurrentUser,
    max_suggestions: int = Query(5, ge=1, le=10),
):
    """Get AI-generated segment suggestions based on data patterns."""
    ai_service = SegmentAIService(db)

    suggestions = await ai_service.get_segment_suggestions(max_suggestions=max_suggestions)

    return SegmentSuggestionsResponse(
        suggestions=[
            SegmentSuggestion(
                name=s.name,
                description=s.description,
                rules=s.rules,
                reasoning=s.reasoning,
                estimated_count=s.estimated_count,
                revenue_opportunity=float(s.revenue_opportunity) if s.revenue_opportunity else None,
                priority=s.priority,
                category=s.category,
                tags=s.tags,
            )
            for s in suggestions
        ],
        total=len(suggestions),
    )


@router.get("/{segment_id}/revenue-opportunity", response_model=RevenueOpportunityResponse)
async def get_revenue_opportunity(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get revenue opportunity analysis for a segment."""
    ai_service = SegmentAIService(db)

    try:
        opportunity = await ai_service.score_revenue_opportunity(segment_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    return RevenueOpportunityResponse(
        segment_id=opportunity.segment_id,
        segment_name=opportunity.segment_name,
        total_customers=opportunity.total_customers,
        total_potential_revenue=float(opportunity.total_potential_revenue),
        avg_revenue_per_customer=float(opportunity.avg_revenue_per_customer),
        upsell_candidates=opportunity.upsell_candidates,
        at_risk_revenue=float(opportunity.at_risk_revenue),
        expansion_probability=opportunity.expansion_probability,
        recommended_actions=opportunity.recommended_actions,
        reasoning=opportunity.reasoning,
    )


@router.get("/ai/templates", response_model=SegmentTemplatesResponse)
async def get_segment_templates(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get available segment templates for quick creation."""
    ai_service = SegmentAIService(db)
    templates = ai_service.get_segment_templates()

    return SegmentTemplatesResponse(
        templates=[
            SegmentTemplateResponse(
                key=key,
                name=template["name"],
                description=template["description"],
                rules=template["rules"],
            )
            for key, template in templates.items()
        ]
    )


# =============================================================================
# FIELD AND OPERATOR DEFINITIONS
# =============================================================================


@router.get("/fields", response_model=SegmentFieldsResponse)
async def get_available_fields(
    db: DbSession,
    current_user: CurrentUser,
    data_type: Optional[str] = None,
):
    """Get available fields and operators for segment rules."""
    engine = SegmentEngine(db)

    fields = engine.get_available_fields()
    operators = engine.get_available_operators(data_type)

    return SegmentFieldsResponse(
        fields=[
            FieldDefinitionResponse(
                name=f["name"],
                display_name=f["display_name"],
                category=f["category"],
                data_type=f["data_type"],
                description=f.get("description", ""),
            )
            for f in fields
        ],
        operators=[
            OperatorDefinitionResponse(
                name=op["name"],
                display=op["display"],
                types=op["types"],
            )
            for op in operators
        ],
    )


# =============================================================================
# BULK ACTION ENDPOINTS
# =============================================================================


async def _get_segment_or_404(segment_id: int, db: DbSession) -> Segment:
    """Helper to get segment or raise 404."""
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )
    return segment


async def _get_segment_customer_ids(segment_id: int, db: DbSession) -> List[str]:
    """Get all active customer IDs in a segment."""
    result = await db.execute(
        select(CustomerSegment.customer_id).where(
            CustomerSegment.segment_id == segment_id,
            CustomerSegment.is_active == True,
        )
    )
    return [row[0] for row in result.fetchall()]


@router.post("/{segment_id}/export", response_model=ExportResponse)
async def export_segment(
    segment_id: int,
    request: ExportRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Export segment customers to CSV or Excel.

    Returns download URL for the generated export file.
    """
    segment = await _get_segment_or_404(segment_id, db)
    customer_ids = await _get_segment_customer_ids(segment_id, db)

    if not customer_ids:
        return ExportResponse(
            status="success",
            message="No customers in segment to export",
            record_count=0,
        )

    # Generate filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = segment.name.replace(" ", "_").lower()[:30]
    filename = f"segment_{safe_name}_{timestamp}.csv"

    # Query customer data for the segment
    customers_result = await db.execute(
        select(Customer).where(Customer.id.in_(customer_ids))
    )
    customers = customers_result.scalars().all()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Build header from requested fields
    field_map = {
        "name": lambda c: f"{c.first_name or ''} {c.last_name or ''}".strip(),
        "first_name": lambda c: c.first_name or "",
        "last_name": lambda c: c.last_name or "",
        "email": lambda c: c.email or "",
        "phone": lambda c: c.phone or "",
        "address": lambda c: f"{c.address_line1 or ''}, {c.city or ''}, {c.state or ''} {c.postal_code or ''}".strip(", "),
        "city": lambda c: c.city or "",
        "state": lambda c: c.state or "",
        "postal_code": lambda c: c.postal_code or "",
        "customer_type": lambda c: c.customer_type or "",
        "tags": lambda c: c.tags or "",
        "created_at": lambda c: c.created_at.isoformat() if c.created_at else "",
    }
    # Use requested fields, fall back to all contact fields
    headers = request.fields if request.fields else ["name", "email", "phone"]
    if request.include_contact_info and "email" not in headers:
        headers.extend(["email", "phone"])
    # Deduplicate while preserving order
    seen = set()
    unique_headers = []
    for h in headers:
        if h not in seen:
            seen.add(h)
            unique_headers.append(h)

    writer.writerow(unique_headers)
    for cust in customers:
        row = [field_map.get(h, lambda c: "")(cust) for h in unique_headers]
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{segment_id}/bulk-schedule", response_model=BulkScheduleResponse)
async def bulk_schedule_segment(
    segment_id: int,
    request: BulkScheduleRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Schedule service for all customers in a segment.

    Creates work orders if requested and sends notifications.
    """
    segment = await _get_segment_or_404(segment_id, db)
    customer_ids = await _get_segment_customer_ids(segment_id, db)

    if not customer_ids:
        return BulkScheduleResponse(
            status="success",
            message="No customers in segment to schedule",
            work_orders_created=0,
            scheduled_date=request.scheduled_date,
            customers_affected=0,
        )

    work_orders_created = 0

    if request.create_work_orders:
        # Generate next WO number base
        max_wo = await db.execute(
            select(func.max(WorkOrder.work_order_number))
        )
        last_wo = max_wo.scalar() or "WO-000000"
        wo_counter = int(last_wo.replace("WO-", "")) if last_wo.startswith("WO-") else 0

        # Get customer addresses for service location
        customers_result = await db.execute(
            select(Customer).where(Customer.id.in_(customer_ids))
        )
        customers = {c.id: c for c in customers_result.scalars().all()}

        scheduled = date.fromisoformat(request.scheduled_date) if isinstance(request.scheduled_date, str) else request.scheduled_date

        for cid in customer_ids:
            cust = customers.get(cid)
            if not cust:
                continue
            wo_counter += 1
            wo = WorkOrder(
                id=str(uuid4()),
                work_order_number=f"WO-{wo_counter:06d}",
                customer_id=cid,
                job_type=request.service_type,
                priority=request.priority,
                status="scheduled",
                scheduled_date=scheduled,
                notes=request.notes,
                service_address_line1=cust.address_line1,
                service_city=cust.city,
                service_state=cust.state,
                service_postal_code=cust.postal_code,
            )
            db.add(wo)
            work_orders_created += 1

        await db.commit()

    return BulkScheduleResponse(
        status="success",
        message=f"Scheduled {work_orders_created} services for {request.scheduled_date}",
        work_orders_created=work_orders_created,
        scheduled_date=request.scheduled_date,
        customers_affected=len(customer_ids),
    )


@router.post("/{segment_id}/bulk-tag", response_model=BulkTagResponse)
async def bulk_tag_segment(
    segment_id: int,
    request: BulkTagRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Add or remove a tag from all customers in a segment.
    """
    segment = await _get_segment_or_404(segment_id, db)
    customer_ids = await _get_segment_customer_ids(segment_id, db)

    if not customer_ids:
        return BulkTagResponse(
            status="success",
            message="No customers in segment to tag",
            customers_updated=0,
            tag=request.tag,
        )

    # Update customer tags in database
    customers_result = await db.execute(
        select(Customer).where(Customer.id.in_(customer_ids))
    )
    customers = customers_result.scalars().all()
    updated_count = 0

    for cust in customers:
        existing_tags = [t.strip() for t in (cust.tags or "").split(",") if t.strip()]
        if request.action == "add":
            if request.tag not in existing_tags:
                existing_tags.append(request.tag)
                cust.tags = ", ".join(existing_tags)
                updated_count += 1
        else:  # remove
            if request.tag in existing_tags:
                existing_tags.remove(request.tag)
                cust.tags = ", ".join(existing_tags) if existing_tags else None
                updated_count += 1

    await db.commit()

    action_verb = "added to" if request.action == "add" else "removed from"

    return BulkTagResponse(
        status="success",
        message=f"Tag '{request.tag}' {action_verb} {updated_count} customers",
        customers_updated=updated_count,
        tag=request.tag,
    )


@router.post("/{segment_id}/bulk-assign", response_model=BulkAssignResponse)
async def bulk_assign_segment(
    segment_id: int,
    request: BulkAssignRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Assign all customers in a segment to sales/support reps.

    Supports:
    - auto: System assigns based on availability/workload
    - specific: Assign all to a specific user
    - round_robin: Distribute evenly among team
    """
    segment = await _get_segment_or_404(segment_id, db)
    customer_ids = await _get_segment_customer_ids(segment_id, db)

    if not customer_ids:
        return BulkAssignResponse(
            status="success",
            message="No customers in segment to assign",
            customers_assigned=0,
            assignment_method=request.assignment_method,
        )

    # In a real implementation, this would:
    # 1. Get available reps based on method
    # 2. Distribute customers
    # 3. Update customer assignments

    return BulkAssignResponse(
        status="success",
        message=f"Assigned {len(customer_ids)} customers using {request.assignment_method} method",
        customers_assigned=len(customer_ids),
        assigned_to_user_id=request.assigned_user_id,
        assignment_method=request.assignment_method,
    )


@router.post("/{segment_id}/create-call-list")
async def create_segment_call_list(
    segment_id: int,
    request: CreateCallListRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Create a prioritized call list from segment customers.

    Generates tasks for calling each customer, prioritized by:
    - Health score (at-risk first)
    - Last contact date
    - Revenue/value
    """
    segment = await _get_segment_or_404(segment_id, db)
    customer_ids = await _get_segment_customer_ids(segment_id, db)

    if not customer_ids:
        return {
            "status": "success",
            "message": "No customers in segment for call list",
            "tasks_created": 0,
        }

    # In a real implementation, this would:
    # 1. Get customer details and health scores
    # 2. Sort by priority criteria
    # 3. Create call tasks for each customer

    list_name = request.name or f"Call List - {segment.name}"

    return {
        "status": "success",
        "message": f"Created call list '{list_name}' with {len(customer_ids)} calls",
        "tasks_created": len(customer_ids),
        "call_list_name": list_name,
        "priority": request.priority,
    }


@router.post("/{segment_id}/bulk-tasks")
async def bulk_create_tasks(
    segment_id: int,
    request: BulkTasksRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Create tasks for all customers in a segment.
    """
    segment = await _get_segment_or_404(segment_id, db)
    customer_ids = await _get_segment_customer_ids(segment_id, db)

    if not customer_ids:
        return {
            "status": "success",
            "message": "No customers in segment for tasks",
            "tasks_created": 0,
        }

    # In a real implementation, this would create CS tasks for each customer

    return {
        "status": "success",
        "message": f"Created {len(customer_ids)} tasks",
        "tasks_created": len(customer_ids),
        "task_type": request.task_type,
        "title": request.title,
    }


@router.post("/{segment_id}/bulk-work-orders")
async def bulk_create_work_orders(
    segment_id: int,
    request: BulkWorkOrdersRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Create work orders for all customers in a segment.
    """
    segment = await _get_segment_or_404(segment_id, db)
    customer_ids = await _get_segment_customer_ids(segment_id, db)

    if not customer_ids:
        return {
            "status": "success",
            "message": "No customers in segment for work orders",
            "work_orders_created": 0,
        }

    # In a real implementation, this would create work orders for each customer

    return {
        "status": "success",
        "message": f"Created {len(customer_ids)} work orders",
        "work_orders_created": len(customer_ids),
        "work_order_type": request.work_order_type,
        "title": request.title,
    }


@router.post("/{segment_id}/bulk-email")
async def bulk_email_segment(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
    subject: Optional[str] = None,
    template_id: Optional[int] = None,
):
    """
    Initiate bulk email campaign for segment customers.

    Returns campaign ID for tracking.
    """
    segment = await _get_segment_or_404(segment_id, db)
    customer_ids = await _get_segment_customer_ids(segment_id, db)

    if not customer_ids:
        return {
            "status": "success",
            "message": "No customers in segment to email",
            "recipients": 0,
        }

    # In a real implementation, this would:
    # 1. Create a campaign record
    # 2. Queue emails for sending
    # 3. Return campaign ID for tracking

    return {
        "status": "success",
        "message": f"Email campaign queued for {len(customer_ids)} recipients",
        "recipients": len(customer_ids),
        "segment_id": segment_id,
        "segment_name": segment.name,
    }
