"""
A/B Test API Endpoints for Campaign Optimization

Provides endpoints for creating, managing, and analyzing A/B tests.
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.customer_success import Campaign
from app.models.customer_success.ab_test import ABTest
from app.schemas.customer_success.ab_test import (
    ABTestCreate, ABTestUpdate, ABTestResponse, ABTestListResponse,
    ABTestResults, MetricUpdateRequest, CompleteTestRequest,
    AssignVariantResponse, ActionResponse,
)
from app.services.customer_success.ab_test_service import ABTestService

logger = logging.getLogger(__name__)
router = APIRouter()


# CRUD Operations

@router.get("/", response_model=ABTestListResponse)
async def list_ab_tests(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    campaign_id: Optional[int] = None,
    status: Optional[str] = None,
    test_type: Optional[str] = None,
):
    """
    List A/B tests with optional filtering.

    - **campaign_id**: Filter by campaign
    - **status**: Filter by status (draft, running, paused, completed)
    - **test_type**: Filter by type (subject, content, send_time, channel)
    """
    try:
        query = select(ABTest)

        if campaign_id:
            query = query.where(ABTest.campaign_id == campaign_id)
        if status:
            query = query.where(ABTest.status == status)
        if test_type:
            query = query.where(ABTest.test_type == test_type)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(ABTest.created_at.desc())

        result = await db.execute(query)
        tests = result.scalars().all()

        return ABTestListResponse(
            items=tests,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing A/B tests: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing A/B tests: {str(e)}"
        )


@router.get("/{test_id}", response_model=ABTestResponse)
async def get_ab_test(
    test_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific A/B test by ID."""
    result = await db.execute(
        select(ABTest).where(ABTest.id == test_id)
    )
    test = result.scalar_one_or_none()

    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A/B test not found",
        )

    return test


@router.post("/", response_model=ABTestResponse, status_code=status.HTTP_201_CREATED)
async def create_ab_test(
    data: ABTestCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Create a new A/B test for a campaign.

    The test starts in 'draft' status and must be explicitly started.
    """
    try:
        # Verify campaign exists
        campaign_result = await db.execute(
            select(Campaign).where(Campaign.id == data.campaign_id)
        )
        campaign = campaign_result.scalar_one_or_none()

        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        # Create the test
        test = ABTest(
            campaign_id=data.campaign_id,
            name=data.name,
            description=data.description,
            test_type=data.test_type.value if hasattr(data.test_type, 'value') else data.test_type,
            variant_a_name=data.variant_a_name,
            variant_a_config=data.variant_a_config,
            variant_b_name=data.variant_b_name,
            variant_b_config=data.variant_b_config,
            traffic_split=data.traffic_split,
            min_sample_size=data.min_sample_size,
            significance_threshold=data.significance_threshold,
            auto_winner=data.auto_winner,
            primary_metric=data.primary_metric.value if hasattr(data.primary_metric, 'value') else data.primary_metric,
        )

        db.add(test)
        await db.commit()
        await db.refresh(test)

        logger.info(f"Created A/B test {test.id} for campaign {data.campaign_id}")
        return test

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating A/B test: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating A/B test: {str(e)}"
        )


@router.patch("/{test_id}", response_model=ABTestResponse)
async def update_ab_test(
    test_id: int,
    data: ABTestUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Update an A/B test.

    Note: Only tests in 'draft' status can have their core configuration changed.
    Running tests can only update min_sample_size, significance_threshold, and auto_winner.
    """
    result = await db.execute(
        select(ABTest).where(ABTest.id == test_id)
    )
    test = result.scalar_one_or_none()

    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A/B test not found",
        )

    # Restrict updates for non-draft tests
    if test.status != 'draft':
        allowed_fields = {'min_sample_size', 'significance_threshold', 'auto_winner'}
        update_data = data.model_dump(exclude_unset=True)
        restricted_fields = set(update_data.keys()) - allowed_fields

        if restricted_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot update {restricted_fields} for a test that is not in draft status",
            )

    update_data = data.model_dump(exclude_unset=True)

    # Handle enum values
    if 'primary_metric' in update_data and hasattr(update_data['primary_metric'], 'value'):
        update_data['primary_metric'] = update_data['primary_metric'].value

    for field, value in update_data.items():
        setattr(test, field, value)

    await db.commit()
    await db.refresh(test)
    return test


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ab_test(
    test_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Delete an A/B test.

    Note: Only tests in 'draft' or 'completed' status can be deleted.
    """
    result = await db.execute(
        select(ABTest).where(ABTest.id == test_id)
    )
    test = result.scalar_one_or_none()

    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A/B test not found",
        )

    if test.status not in ('draft', 'completed'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only delete tests in draft or completed status",
        )

    await db.delete(test)
    await db.commit()


# Results and Analysis

@router.get("/{test_id}/results", response_model=ABTestResults)
async def get_ab_test_results(
    test_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Get comprehensive results and statistical analysis for an A/B test.

    Returns:
    - Variant metrics (sent, opened, clicked, converted, rates)
    - Chi-square and z-score statistics
    - Confidence level and significance
    - Winner determination
    - Lift calculation (improvement of B over A)
    - Recommendation text
    """
    service = ABTestService(db)
    results = await service.get_test_results(test_id)

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A/B test not found",
        )

    return results


# Test Actions

@router.post("/{test_id}/start", response_model=ActionResponse)
async def start_ab_test(
    test_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Start an A/B test.

    The test must be in 'draft' status to be started.
    """
    try:
        service = ABTestService(db)
        test = await service.start_test(test_id)

        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="A/B test not found",
            )

        return ActionResponse(
            status="success",
            message="A/B test started successfully",
            test_id=test.id,
            new_status=test.status,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{test_id}/pause", response_model=ActionResponse)
async def pause_ab_test(
    test_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Pause a running A/B test.

    Paused tests can be resumed later.
    """
    try:
        service = ABTestService(db)
        test = await service.pause_test(test_id)

        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="A/B test not found",
            )

        return ActionResponse(
            status="success",
            message="A/B test paused successfully",
            test_id=test.id,
            new_status=test.status,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{test_id}/resume", response_model=ActionResponse)
async def resume_ab_test(
    test_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Resume a paused A/B test.
    """
    try:
        service = ABTestService(db)
        test = await service.resume_test(test_id)

        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="A/B test not found",
            )

        return ActionResponse(
            status="success",
            message="A/B test resumed successfully",
            test_id=test.id,
            new_status=test.status,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{test_id}/complete", response_model=ActionResponse)
async def complete_ab_test(
    test_id: int,
    data: Optional[CompleteTestRequest] = None,
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """
    Complete an A/B test.

    Optionally specify a manual winner ('a' or 'b').
    If no winner is specified, the statistical winner is used.
    """
    try:
        service = ABTestService(db)
        winner = data.winner if data else None
        test = await service.complete_test(test_id, winner=winner)

        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="A/B test not found",
            )

        return ActionResponse(
            status="success",
            message=f"A/B test completed. Winner: Variant {test.winning_variant.upper() if test.winning_variant else 'None'}",
            test_id=test.id,
            new_status=test.status,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# Metric Updates

@router.post("/{test_id}/metrics", response_model=ABTestResponse)
async def update_ab_test_metrics(
    test_id: int,
    data: MetricUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Update metrics for an A/B test variant.

    Used to record events (sent, opened, clicked, converted) for each variant.
    """
    try:
        service = ABTestService(db)
        test = await service.update_metrics(
            test_id=test_id,
            variant=data.variant,
            metric=data.metric,
            increment=data.increment,
        )

        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="A/B test not found",
            )

        return test
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# Variant Assignment

@router.post("/{test_id}/assign", response_model=AssignVariantResponse)
async def assign_variant(
    test_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Assign a variant to a new recipient based on traffic split.

    Returns the assigned variant ('a' or 'b') along with its configuration.
    """
    service = ABTestService(db)

    # Get variant assignment
    assigned = await service.assign_variant(test_id)
    if not assigned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Test not found or not running",
        )

    # Get test details for response
    test = await service.get_test_by_id(test_id)

    variant_name = test.variant_a_name if assigned == 'a' else test.variant_b_name
    variant_config = test.variant_a_config if assigned == 'a' else test.variant_b_config

    return AssignVariantResponse(
        test_id=test_id,
        assigned_variant=assigned,
        variant_name=variant_name,
        variant_config=variant_config,
    )


# Campaign-specific endpoints

@router.get("/campaign/{campaign_id}", response_model=ABTestListResponse)
async def get_campaign_ab_tests(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    Get all A/B tests for a specific campaign.
    """
    # Verify campaign exists
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    if not campaign_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    service = ABTestService(db)
    tests = await service.get_campaign_tests(campaign_id)

    # Apply pagination
    total = len(tests)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_tests = tests[start:end]

    return ABTestListResponse(
        items=paginated_tests,
        total=total,
        page=page,
        page_size=page_size,
    )
