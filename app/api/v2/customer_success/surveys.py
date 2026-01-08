"""
Survey API Endpoints for Enterprise Customer Success Platform

Provides endpoints for managing NPS/CSAT/CES surveys and responses.

2025-2026 Enhancements:
- GET /surveys/detractors - Urgent attention queue (all detractors needing action)
- GET /surveys/trends - Cross-survey trend data over time
- POST /surveys/{id}/analyze - Trigger AI analysis for a survey
- GET /surveys/{id}/ai-insights - Get AI analysis results
- POST /surveys/{id}/actions - Create action from AI insight
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timedelta
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.customer_success import (
    Survey, SurveyQuestion, SurveyResponse, SurveyAnswer
)
from app.models.customer_success.survey import SurveyAnalysis, SurveyAction
from app.schemas.customer_success.survey import (
    SurveyCreate, SurveyUpdate, SurveyResponse as SurveyResponseSchema,
    SurveyListResponse, SurveyQuestionCreate, SurveyQuestionUpdate, SurveyQuestionResponse,
    SurveySubmissionCreate, SurveySubmissionResponse, SurveyResponseListResponse,
    SurveyAnalytics, NPSBreakdown,
    # 2025-2026 Enhancement schemas
    DetractorQueueResponse, DetractorItem, SurveyTrendResponse, TrendDataPoint,
    SurveyAnalysisCreate, SurveyAnalysisResponse,
    SurveyActionCreate, SurveyActionUpdate, SurveyActionResponse, SurveyActionListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# Survey CRUD

@router.get("/", response_model=SurveyListResponse)
async def list_surveys(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    survey_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    """List surveys with filtering."""
    try:
        query = select(Survey).options(selectinload(Survey.questions))

        if survey_type:
            query = query.where(Survey.survey_type == survey_type)
        if status:
            query = query.where(Survey.status == status)
        if search:
            query = query.where(Survey.name.ilike(f"%{search}%"))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Survey.created_at.desc())

        result = await db.execute(query)
        surveys = result.scalars().unique().all()

        return SurveyListResponse(
            items=surveys,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing surveys: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing surveys: {str(e)}"
        )


@router.get("/{survey_id}", response_model=SurveyResponseSchema)
async def get_survey(
    survey_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific survey with questions."""
    result = await db.execute(
        select(Survey)
        .options(selectinload(Survey.questions))
        .where(Survey.id == survey_id)
    )
    survey = result.scalar_one_or_none()

    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey not found",
        )

    return survey


@router.post("/", response_model=SurveyResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_survey(
    data: SurveyCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new survey."""
    survey_data = data.model_dump(exclude={"questions"})
    survey = Survey(
        **survey_data,
        created_by_user_id=current_user.id,
    )
    db.add(survey)
    await db.flush()

    # Create questions if provided
    if data.questions:
        for i, q_data in enumerate(data.questions):
            question = SurveyQuestion(
                survey_id=survey.id,
                order=q_data.order if q_data.order else i,
                **q_data.model_dump(exclude={"order"}),
            )
            db.add(question)

    await db.commit()
    await db.refresh(survey)

    # Load questions
    result = await db.execute(
        select(Survey)
        .options(selectinload(Survey.questions))
        .where(Survey.id == survey.id)
    )
    return result.scalar_one()


@router.patch("/{survey_id}", response_model=SurveyResponseSchema)
async def update_survey(
    survey_id: int,
    data: SurveyUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a survey."""
    result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = result.scalar_one_or_none()

    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(survey, field, value)

    # Handle status transitions
    if data.status == "active" and not survey.started_at:
        survey.started_at = datetime.utcnow()
    elif data.status == "completed" and not survey.completed_at:
        survey.completed_at = datetime.utcnow()

    await db.commit()

    # Load questions
    result = await db.execute(
        select(Survey)
        .options(selectinload(Survey.questions))
        .where(Survey.id == survey.id)
    )
    return result.scalar_one()


@router.delete("/{survey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_survey(
    survey_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a survey."""
    result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = result.scalar_one_or_none()

    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey not found",
        )

    # Check for active status
    if survey.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete an active survey",
        )

    await db.delete(survey)
    await db.commit()


# Survey Questions

@router.post("/{survey_id}/questions", response_model=SurveyQuestionResponse, status_code=status.HTTP_201_CREATED)
async def create_question(
    survey_id: int,
    data: SurveyQuestionCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Add a question to a survey."""
    # Check survey exists
    survey_result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    if not survey_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey not found",
        )

    question = SurveyQuestion(
        survey_id=survey_id,
        **data.model_dump(),
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


@router.patch("/{survey_id}/questions/{question_id}", response_model=SurveyQuestionResponse)
async def update_question(
    survey_id: int,
    question_id: int,
    data: SurveyQuestionUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a survey question."""
    result = await db.execute(
        select(SurveyQuestion).where(
            SurveyQuestion.id == question_id,
            SurveyQuestion.survey_id == survey_id,
        )
    )
    question = result.scalar_one_or_none()

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(question, field, value)

    await db.commit()
    await db.refresh(question)
    return question


@router.delete("/{survey_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    survey_id: int,
    question_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a survey question."""
    result = await db.execute(
        select(SurveyQuestion).where(
            SurveyQuestion.id == question_id,
            SurveyQuestion.survey_id == survey_id,
        )
    )
    question = result.scalar_one_or_none()

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )

    await db.delete(question)
    await db.commit()


# Survey Responses (from customers)

@router.get("/{survey_id}/responses", response_model=SurveyResponseListResponse)
async def list_survey_responses(
    survey_id: int,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sentiment: Optional[str] = None,
):
    """List responses for a survey."""
    query = (
        select(SurveyResponse)
        .options(selectinload(SurveyResponse.answers))
        .where(SurveyResponse.survey_id == survey_id)
    )

    if sentiment:
        query = query.where(SurveyResponse.sentiment == sentiment)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(SurveyResponse.created_at.desc())

    result = await db.execute(query)
    responses = result.scalars().unique().all()

    # Enhance with customer names
    items = []
    for resp in responses:
        resp_dict = {
            "id": resp.id,
            "survey_id": resp.survey_id,
            "customer_id": resp.customer_id,
            "overall_score": resp.overall_score,
            "sentiment": resp.sentiment,
            "sentiment_score": resp.sentiment_score,
            "is_complete": resp.is_complete,
            "started_at": resp.started_at,
            "completed_at": resp.completed_at,
            "created_at": resp.created_at,
            "answers": resp.answers,
        }
        # Get customer name
        cust_result = await db.execute(select(Customer.name).where(Customer.id == resp.customer_id))
        cust_name = cust_result.scalar_one_or_none()
        resp_dict["customer_name"] = cust_name
        items.append(resp_dict)

    return SurveyResponseListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{survey_id}/submit", response_model=SurveySubmissionResponse)
async def submit_survey_response(
    survey_id: int,
    data: SurveySubmissionCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Submit a survey response from a customer."""
    # Verify survey exists and is active
    survey_result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = survey_result.scalar_one_or_none()

    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey not found",
        )

    if survey.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Survey is not active",
        )

    # Check for existing response if not allowing multiple
    if not survey.allow_multiple_responses:
        existing = await db.execute(
            select(SurveyResponse).where(
                SurveyResponse.survey_id == survey_id,
                SurveyResponse.customer_id == data.customer_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer has already responded to this survey",
            )

    # Create response
    survey_response = SurveyResponse(
        survey_id=survey_id,
        customer_id=data.customer_id,
        source=data.source,
        device=data.device,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        is_complete=True,
    )
    db.add(survey_response)
    await db.flush()

    # Create answers and calculate overall score
    scores = []
    for answer_data in data.answers:
        answer = SurveyAnswer(
            response_id=survey_response.id,
            question_id=answer_data.question_id,
            rating_value=answer_data.rating_value,
            text_value=answer_data.text_value,
            choice_values=answer_data.choice_values,
        )
        db.add(answer)
        if answer_data.rating_value is not None:
            scores.append(answer_data.rating_value)

    # Calculate overall score
    if scores:
        survey_response.overall_score = sum(scores) / len(scores)
        # Determine sentiment based on NPS-style scoring
        avg_score = survey_response.overall_score
        if avg_score >= 9:
            survey_response.sentiment = "positive"
            survey_response.sentiment_score = 1.0
        elif avg_score >= 7:
            survey_response.sentiment = "neutral"
            survey_response.sentiment_score = 0.5
        else:
            survey_response.sentiment = "negative"
            survey_response.sentiment_score = 0.0

    # Update survey metrics
    survey.responses_count = (survey.responses_count or 0) + 1
    if scores:
        # Recalculate average
        all_responses = await db.execute(
            select(SurveyResponse.overall_score).where(
                SurveyResponse.survey_id == survey_id,
                SurveyResponse.overall_score.isnot(None),
            )
        )
        all_scores = [r[0] for r in all_responses.fetchall()]
        all_scores.append(survey_response.overall_score)
        survey.avg_score = sum(all_scores) / len(all_scores)

        # Update NPS categories
        if survey_response.overall_score >= 9:
            survey.promoters_count = (survey.promoters_count or 0) + 1
        elif survey_response.overall_score >= 7:
            survey.passives_count = (survey.passives_count or 0) + 1
        else:
            survey.detractors_count = (survey.detractors_count or 0) + 1

    await db.commit()
    await db.refresh(survey_response)

    # Load answers
    result = await db.execute(
        select(SurveyResponse)
        .options(selectinload(SurveyResponse.answers))
        .where(SurveyResponse.id == survey_response.id)
    )
    return result.scalar_one()


# Survey Analytics

@router.get("/{survey_id}/analytics", response_model=SurveyAnalytics)
async def get_survey_analytics(
    survey_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get analytics for a survey."""
    # Verify survey exists
    survey_result = await db.execute(
        select(Survey)
        .options(selectinload(Survey.questions))
        .where(Survey.id == survey_id)
    )
    survey = survey_result.scalar_one_or_none()

    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey not found",
        )

    # Get response count
    total_responses = survey.responses_count or 0

    # Calculate NPS breakdown
    nps_breakdown = None
    if survey.survey_type == "nps":
        promoters = survey.promoters_count or 0
        passives = survey.passives_count or 0
        detractors = survey.detractors_count or 0

        if total_responses > 0:
            nps_score = ((promoters - detractors) / total_responses) * 100
        else:
            nps_score = 0

        nps_breakdown = NPSBreakdown(
            promoters=promoters,
            passives=passives,
            detractors=detractors,
            nps_score=nps_score,
            total_responses=total_responses,
        )

    # Get response trend (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    trend_result = await db.execute(
        select(
            func.date(SurveyResponse.created_at).label("date"),
            func.count(SurveyResponse.id).label("count"),
            func.avg(SurveyResponse.overall_score).label("avg_score"),
        )
        .where(
            SurveyResponse.survey_id == survey_id,
            SurveyResponse.created_at >= thirty_days_ago,
        )
        .group_by(func.date(SurveyResponse.created_at))
        .order_by(func.date(SurveyResponse.created_at))
    )
    response_trend = [
        {"date": str(row.date), "count": row.count, "avg_score": float(row.avg_score) if row.avg_score else None}
        for row in trend_result.fetchall()
    ]

    # Get per-question stats
    question_stats = []
    for question in survey.questions:
        answer_result = await db.execute(
            select(
                func.count(SurveyAnswer.id).label("count"),
                func.avg(SurveyAnswer.rating_value).label("avg_rating"),
            )
            .where(SurveyAnswer.question_id == question.id)
        )
        stats = answer_result.fetchone()
        question_stats.append({
            "question_id": question.id,
            "question_text": question.text,
            "response_count": stats.count if stats else 0,
            "avg_rating": float(stats.avg_rating) if stats and stats.avg_rating else None,
        })

    return SurveyAnalytics(
        survey_id=survey_id,
        total_responses=total_responses,
        avg_score=survey.avg_score,
        completion_rate=survey.completion_rate,
        nps_breakdown=nps_breakdown,
        response_trend=response_trend,
        question_stats=question_stats,
    )


# Survey Actions

@router.post("/{survey_id}/activate")
async def activate_survey(
    survey_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Activate a survey."""
    result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = result.scalar_one_or_none()

    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey not found",
        )

    if survey.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Survey is already active",
        )

    survey.status = "active"
    survey.started_at = datetime.utcnow()
    await db.commit()

    return {"status": "success", "message": "Survey activated"}


@router.post("/{survey_id}/pause")
async def pause_survey(
    survey_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Pause an active survey."""
    result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = result.scalar_one_or_none()

    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey not found",
        )

    if survey.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only pause active surveys",
        )

    survey.status = "paused"
    await db.commit()

    return {"status": "success", "message": "Survey paused"}


@router.post("/{survey_id}/complete")
async def complete_survey(
    survey_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark a survey as completed."""
    result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = result.scalar_one_or_none()

    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey not found",
        )

    survey.status = "completed"
    survey.completed_at = datetime.utcnow()
    await db.commit()

    return {"status": "success", "message": "Survey completed"}


# ============ 2025-2026 Enhancement Endpoints ============

@router.get("/detractors", response_model=DetractorQueueResponse)
async def get_detractors_queue(
    db: DbSession,
    current_user: CurrentUser,
    survey_id: Optional[int] = None,
    urgency_level: Optional[str] = None,
    action_taken: Optional[bool] = None,
    days_back: int = Query(30, ge=1, le=365),
):
    """
    Get urgent attention queue with all detractors needing action.

    Returns all survey responses with scores < 7 (NPS detractors) that may
    need follow-up action. Can be filtered by survey, urgency level, and
    whether action has been taken.
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)

        # Build query for detractor responses (score < 7)
        query = (
            select(SurveyResponse)
            .join(Survey)
            .join(Customer)
            .where(
                SurveyResponse.overall_score < 7,
                SurveyResponse.is_complete == True,
                SurveyResponse.created_at >= cutoff_date,
            )
        )

        if survey_id:
            query = query.where(SurveyResponse.survey_id == survey_id)
        if urgency_level:
            query = query.where(SurveyResponse.urgency_level == urgency_level)
        if action_taken is not None:
            query = query.where(SurveyResponse.action_taken == action_taken)

        query = query.order_by(
            # Order by urgency: critical first, then by score (lower first)
            case(
                (SurveyResponse.urgency_level == 'critical', 1),
                (SurveyResponse.urgency_level == 'high', 2),
                (SurveyResponse.urgency_level == 'medium', 3),
                (SurveyResponse.urgency_level == 'low', 4),
                else_=5
            ),
            SurveyResponse.overall_score.asc(),
            SurveyResponse.created_at.desc(),
        )

        result = await db.execute(query)
        responses = result.scalars().all()

        # Build detractor items with customer info
        items = []
        critical_count = 0
        high_count = 0
        action_needed_count = 0

        for resp in responses:
            # Get survey name
            survey_result = await db.execute(
                select(Survey.name).where(Survey.id == resp.survey_id)
            )
            survey_name = survey_result.scalar_one_or_none() or "Unknown Survey"

            # Get customer name
            cust_result = await db.execute(
                select(Customer.name).where(Customer.id == resp.customer_id)
            )
            customer_name = cust_result.scalar_one_or_none() or "Unknown Customer"

            # Calculate days since response
            days_since = (datetime.utcnow() - resp.created_at).days if resp.created_at else 0

            item = DetractorItem(
                response_id=resp.id,
                survey_id=resp.survey_id,
                survey_name=survey_name,
                customer_id=resp.customer_id,
                customer_name=customer_name,
                score=resp.overall_score or 0,
                sentiment=resp.sentiment,
                feedback_text=resp.feedback_text,
                topics_detected=resp.topics_detected,
                urgency_level=resp.urgency_level,
                action_taken=resp.action_taken or False,
                action_type=resp.action_type,
                responded_at=resp.created_at,
                days_since_response=days_since,
            )
            items.append(item)

            # Count by urgency
            if resp.urgency_level == 'critical':
                critical_count += 1
            elif resp.urgency_level == 'high':
                high_count += 1

            if not resp.action_taken:
                action_needed_count += 1

        return DetractorQueueResponse(
            items=items,
            total=len(items),
            critical_count=critical_count,
            high_count=high_count,
            action_needed_count=action_needed_count,
        )
    except Exception as e:
        logger.error(f"Error getting detractors queue: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting detractors queue: {str(e)}"
        )


@router.get("/trends", response_model=SurveyTrendResponse)
async def get_survey_trends(
    db: DbSession,
    current_user: CurrentUser,
    period: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    days_back: int = Query(30, ge=7, le=365),
    survey_type: Optional[str] = None,
):
    """
    Get cross-survey trend data over time.

    Returns aggregated survey metrics (responses, scores, NPS, sentiment)
    grouped by day/week/month for trend analysis.
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days_back)
        end_date = datetime.utcnow()

        # Build base query
        query = (
            select(SurveyResponse)
            .join(Survey)
            .where(
                SurveyResponse.is_complete == True,
                SurveyResponse.created_at >= start_date,
            )
        )

        if survey_type:
            query = query.where(Survey.survey_type == survey_type)

        result = await db.execute(query)
        responses = result.scalars().all()

        # Group responses by period
        data_by_period = {}

        for resp in responses:
            if not resp.created_at:
                continue

            # Determine period key
            if period == "daily":
                period_key = resp.created_at.strftime("%Y-%m-%d")
            elif period == "weekly":
                # Get Monday of the week
                week_start = resp.created_at - timedelta(days=resp.created_at.weekday())
                period_key = week_start.strftime("%Y-%m-%d")
            else:  # monthly
                period_key = resp.created_at.strftime("%Y-%m-01")

            if period_key not in data_by_period:
                data_by_period[period_key] = {
                    "responses": [],
                    "scores": [],
                    "promoters": 0,
                    "passives": 0,
                    "detractors": 0,
                    "positive": 0,
                    "neutral": 0,
                    "negative": 0,
                }

            data = data_by_period[period_key]
            data["responses"].append(resp)

            if resp.overall_score is not None:
                data["scores"].append(resp.overall_score)
                # NPS categorization
                if resp.overall_score >= 9:
                    data["promoters"] += 1
                elif resp.overall_score >= 7:
                    data["passives"] += 1
                else:
                    data["detractors"] += 1

            # Sentiment counting
            if resp.sentiment == "positive":
                data["positive"] += 1
            elif resp.sentiment == "neutral":
                data["neutral"] += 1
            elif resp.sentiment == "negative":
                data["negative"] += 1

        # Build trend data points
        data_points = []
        all_scores = []
        total_promoters = 0
        total_detractors = 0
        total_responses = 0

        for date_key in sorted(data_by_period.keys()):
            data = data_by_period[date_key]
            count = len(data["responses"])
            total_responses += count

            avg_score = None
            if data["scores"]:
                avg_score = sum(data["scores"]) / len(data["scores"])
                all_scores.extend(data["scores"])

            nps_score = None
            period_total = data["promoters"] + data["passives"] + data["detractors"]
            if period_total > 0:
                nps_score = ((data["promoters"] - data["detractors"]) / period_total) * 100

            total_promoters += data["promoters"]
            total_detractors += data["detractors"]

            data_points.append(TrendDataPoint(
                date=date_key,
                responses_count=count,
                avg_score=avg_score,
                nps_score=nps_score,
                promoters=data["promoters"],
                passives=data["passives"],
                detractors=data["detractors"],
                sentiment_positive=data["positive"],
                sentiment_neutral=data["neutral"],
                sentiment_negative=data["negative"],
            ))

        # Calculate overall trends
        avg_nps = None
        if total_responses > 0:
            avg_nps = ((total_promoters - total_detractors) / total_responses) * 100

        avg_score = None
        if all_scores:
            avg_score = sum(all_scores) / len(all_scores)

        # Determine trend direction
        trend_direction = "stable"
        if len(data_points) >= 2:
            first_half = data_points[:len(data_points)//2]
            second_half = data_points[len(data_points)//2:]

            first_avg = sum(dp.avg_score or 0 for dp in first_half) / len(first_half) if first_half else 0
            second_avg = sum(dp.avg_score or 0 for dp in second_half) / len(second_half) if second_half else 0

            if second_avg > first_avg + 0.5:
                trend_direction = "improving"
            elif second_avg < first_avg - 0.5:
                trend_direction = "declining"

        # Get surveys included
        surveys_query = select(Survey.id, Survey.name, func.count(SurveyResponse.id).label("responses")).join(
            SurveyResponse
        ).where(
            SurveyResponse.created_at >= start_date
        ).group_by(Survey.id, Survey.name)

        if survey_type:
            surveys_query = surveys_query.where(Survey.survey_type == survey_type)

        surveys_result = await db.execute(surveys_query)
        surveys_included = [
            {"id": row.id, "name": row.name, "responses": row.responses}
            for row in surveys_result.fetchall()
        ]

        return SurveyTrendResponse(
            period=period,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            data_points=data_points,
            total_responses=total_responses,
            avg_nps_score=avg_nps,
            avg_score=avg_score,
            trend_direction=trend_direction,
            top_themes=[],  # Would be populated by AI analysis aggregation
            surveys_included=surveys_included,
        )
    except Exception as e:
        logger.error(f"Error getting survey trends: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting survey trends: {str(e)}"
        )


@router.post("/{survey_id}/analyze", response_model=SurveyAnalysisResponse)
async def trigger_survey_analysis(
    survey_id: int,
    data: SurveyAnalysisCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Trigger AI analysis for a survey.

    Creates an analysis record and queues the survey for AI processing.
    The analysis will extract sentiment, themes, urgent issues, churn risks,
    competitor mentions, and generate action recommendations.
    """
    try:
        # Verify survey exists
        survey_result = await db.execute(
            select(Survey).where(Survey.id == survey_id)
        )
        survey = survey_result.scalar_one_or_none()

        if not survey:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Survey not found",
            )

        # Check for existing analysis (unless force_reanalyze)
        if not data.force_reanalyze:
            existing = await db.execute(
                select(SurveyAnalysis).where(
                    SurveyAnalysis.survey_id == survey_id,
                    SurveyAnalysis.response_id.is_(None),  # Survey-level analysis
                    SurveyAnalysis.status.in_(['pending', 'processing', 'completed']),
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Analysis already exists. Use force_reanalyze=true to re-run.",
                )

        # Create analysis record
        analysis = SurveyAnalysis(
            survey_id=survey_id,
            response_id=None,  # Survey-level analysis
            status='pending',
            analysis_version='v1.0',
        )
        db.add(analysis)
        await db.commit()
        await db.refresh(analysis)

        # In production, this would queue the analysis for async processing
        # For now, we'll do a simple synchronous analysis

        # Get all responses for this survey
        responses_result = await db.execute(
            select(SurveyResponse)
            .options(selectinload(SurveyResponse.answers))
            .where(
                SurveyResponse.survey_id == survey_id,
                SurveyResponse.is_complete == True,
            )
        )
        responses = responses_result.scalars().all()

        # Simple analysis (in production, this would use AI)
        positive_count = sum(1 for r in responses if r.sentiment == 'positive')
        neutral_count = sum(1 for r in responses if r.sentiment == 'neutral')
        negative_count = sum(1 for r in responses if r.sentiment == 'negative')
        total = len(responses)

        sentiment_breakdown = {
            "positive": round((positive_count / total * 100) if total else 0, 1),
            "neutral": round((neutral_count / total * 100) if total else 0, 1),
            "negative": round((negative_count / total * 100) if total else 0, 1),
        }

        # Calculate scores
        scores = [r.overall_score for r in responses if r.overall_score is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        sentiment_score = (positive_count - negative_count) / total if total else 0

        # Identify urgent issues (low scores)
        urgent_issues = []
        for r in responses:
            if r.overall_score and r.overall_score < 5:
                urgent_issues.append({
                    "text": r.feedback_text or "Low score without feedback",
                    "customer_id": r.customer_id,
                    "severity": "critical" if r.overall_score < 3 else "high",
                    "response_id": r.id,
                })

        # Calculate churn risk
        detractor_count = sum(1 for r in responses if r.overall_score and r.overall_score < 7)
        churn_risk = (detractor_count / total * 100) if total else 0

        # Update analysis with results
        analysis.sentiment_breakdown = sentiment_breakdown
        analysis.overall_sentiment_score = sentiment_score
        analysis.urgent_issues = urgent_issues[:10]  # Top 10
        analysis.churn_risk_score = churn_risk
        analysis.urgency_score = min(churn_risk * 1.5, 100)  # Simple urgency calc
        analysis.key_themes = []  # Would be extracted by AI
        analysis.action_recommendations = []
        analysis.status = 'completed'
        analysis.analyzed_at = datetime.utcnow()
        analysis.executive_summary = (
            f"Analysis of {total} responses. "
            f"Sentiment: {sentiment_breakdown['positive']:.0f}% positive, "
            f"{sentiment_breakdown['negative']:.0f}% negative. "
            f"Churn risk: {churn_risk:.0f}%. "
            f"{len(urgent_issues)} urgent issues identified."
        )

        await db.commit()
        await db.refresh(analysis)

        return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering survey analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error triggering survey analysis: {str(e)}"
        )


@router.get("/{survey_id}/ai-insights", response_model=SurveyAnalysisResponse)
async def get_ai_insights(
    survey_id: int,
    db: DbSession,
    current_user: CurrentUser,
    response_id: Optional[int] = None,
):
    """
    Get AI analysis results for a survey.

    Returns the most recent completed analysis for the survey.
    Optionally filter by specific response_id for response-level analysis.
    """
    try:
        # Verify survey exists
        survey_result = await db.execute(
            select(Survey).where(Survey.id == survey_id)
        )
        if not survey_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Survey not found",
            )

        # Get analysis
        query = select(SurveyAnalysis).where(
            SurveyAnalysis.survey_id == survey_id,
        )

        if response_id:
            query = query.where(SurveyAnalysis.response_id == response_id)
        else:
            query = query.where(SurveyAnalysis.response_id.is_(None))

        query = query.order_by(SurveyAnalysis.analyzed_at.desc())

        result = await db.execute(query)
        analysis = result.scalar_one_or_none()

        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No analysis found. Trigger analysis first using POST /surveys/{id}/analyze",
            )

        return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting AI insights: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting AI insights: {str(e)}"
        )


@router.post("/{survey_id}/actions", response_model=SurveyActionResponse, status_code=status.HTTP_201_CREATED)
async def create_survey_action(
    survey_id: int,
    data: SurveyActionCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Create an action from AI insight or manual review.

    Creates a follow-up action linked to a survey response or AI analysis.
    Actions can be callbacks, tasks, tickets, offers, escalations, etc.
    """
    try:
        # Verify survey exists
        survey_result = await db.execute(
            select(Survey).where(Survey.id == survey_id)
        )
        if not survey_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Survey not found",
            )

        # Verify customer exists
        customer_result = await db.execute(
            select(Customer).where(Customer.id == data.customer_id)
        )
        customer = customer_result.scalar_one_or_none()
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )

        # Create action
        action = SurveyAction(
            survey_id=survey_id,
            response_id=data.response_id,
            analysis_id=data.analysis_id,
            customer_id=data.customer_id,
            action_type=data.action_type.value,
            title=data.title,
            description=data.description,
            priority=data.priority.value,
            source=data.source,
            ai_confidence=data.ai_confidence,
            assigned_to_user_id=data.assigned_to_user_id,
            created_by_user_id=current_user.id,
            status='pending',
            due_date=data.due_date,
        )
        db.add(action)

        # If action is linked to a response, mark action taken on the response
        if data.response_id:
            response_result = await db.execute(
                select(SurveyResponse).where(SurveyResponse.id == data.response_id)
            )
            response = response_result.scalar_one_or_none()
            if response:
                response.action_taken = True
                response.action_type = data.action_type.value
                response.action_taken_at = datetime.utcnow()
                response.action_taken_by = current_user.id

        await db.commit()
        await db.refresh(action)

        # Build response with names
        response_data = SurveyActionResponse(
            id=action.id,
            survey_id=action.survey_id,
            response_id=action.response_id,
            analysis_id=action.analysis_id,
            customer_id=action.customer_id,
            customer_name=customer.name,
            action_type=action.action_type,
            title=action.title,
            description=action.description,
            priority=action.priority,
            source=action.source,
            ai_confidence=action.ai_confidence,
            assigned_to_user_id=action.assigned_to_user_id,
            created_by_user_id=action.created_by_user_id,
            status=action.status,
            due_date=action.due_date,
            created_at=action.created_at,
        )

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating survey action: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating survey action: {str(e)}"
        )


@router.get("/{survey_id}/actions", response_model=SurveyActionListResponse)
async def list_survey_actions(
    survey_id: int,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = None,
    action_type: Optional[str] = None,
):
    """List actions for a survey."""
    try:
        # Verify survey exists
        survey_result = await db.execute(
            select(Survey).where(Survey.id == survey_id)
        )
        if not survey_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Survey not found",
            )

        query = select(SurveyAction).where(SurveyAction.survey_id == survey_id)

        if status_filter:
            query = query.where(SurveyAction.status == status_filter)
        if action_type:
            query = query.where(SurveyAction.action_type == action_type)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(SurveyAction.created_at.desc())

        result = await db.execute(query)
        actions = result.scalars().all()

        # Build response items with customer names
        items = []
        for action in actions:
            cust_result = await db.execute(
                select(Customer.name).where(Customer.id == action.customer_id)
            )
            customer_name = cust_result.scalar_one_or_none() or "Unknown"

            items.append(SurveyActionResponse(
                id=action.id,
                survey_id=action.survey_id,
                response_id=action.response_id,
                analysis_id=action.analysis_id,
                customer_id=action.customer_id,
                customer_name=customer_name,
                action_type=action.action_type,
                title=action.title,
                description=action.description,
                priority=action.priority,
                source=action.source,
                ai_confidence=action.ai_confidence,
                assigned_to_user_id=action.assigned_to_user_id,
                created_by_user_id=action.created_by_user_id,
                status=action.status,
                due_date=action.due_date,
                completed_at=action.completed_at,
                outcome=action.outcome,
                linked_entity_type=action.linked_entity_type,
                linked_entity_id=action.linked_entity_id,
                created_at=action.created_at,
                updated_at=action.updated_at,
            ))

        return SurveyActionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing survey actions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing survey actions: {str(e)}"
        )


@router.patch("/{survey_id}/actions/{action_id}", response_model=SurveyActionResponse)
async def update_survey_action(
    survey_id: int,
    action_id: int,
    data: SurveyActionUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a survey action."""
    try:
        result = await db.execute(
            select(SurveyAction).where(
                SurveyAction.id == action_id,
                SurveyAction.survey_id == survey_id,
            )
        )
        action = result.scalar_one_or_none()

        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Action not found",
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == 'priority' and value:
                setattr(action, field, value.value)
            elif field == 'status' and value:
                setattr(action, field, value.value)
                if value.value == 'completed':
                    action.completed_at = datetime.utcnow()
            else:
                setattr(action, field, value)

        await db.commit()
        await db.refresh(action)

        # Get customer name
        cust_result = await db.execute(
            select(Customer.name).where(Customer.id == action.customer_id)
        )
        customer_name = cust_result.scalar_one_or_none() or "Unknown"

        return SurveyActionResponse(
            id=action.id,
            survey_id=action.survey_id,
            response_id=action.response_id,
            analysis_id=action.analysis_id,
            customer_id=action.customer_id,
            customer_name=customer_name,
            action_type=action.action_type,
            title=action.title,
            description=action.description,
            priority=action.priority,
            source=action.source,
            ai_confidence=action.ai_confidence,
            assigned_to_user_id=action.assigned_to_user_id,
            created_by_user_id=action.created_by_user_id,
            status=action.status,
            due_date=action.due_date,
            completed_at=action.completed_at,
            outcome=action.outcome,
            linked_entity_type=action.linked_entity_type,
            linked_entity_id=action.linked_entity_id,
            created_at=action.created_at,
            updated_at=action.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating survey action: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating survey action: {str(e)}"
        )


# ============ Survey Eligibility (Fatigue Prevention) ============

@router.get("/customers/{customer_id}/survey-eligibility")
async def check_survey_eligibility(
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
    min_days_between: int = Query(30, ge=1, le=365, description="Minimum days between surveys"),
    max_per_month: int = Query(2, ge=1, le=10, description="Maximum surveys per month"),
):
    """
    Check if a customer is eligible to receive a survey.

    Implements survey fatigue prevention by checking:
    - When the customer was last surveyed
    - How many surveys they've received recently
    - Customer status (churned, new, etc.)
    - Opt-out preferences

    Returns eligibility status, reason, and next eligible date.
    """
    from app.schemas.customer_success.survey import SurveyEligibilityResponse

    try:
        # Verify customer exists
        customer_result = await db.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        customer = customer_result.scalar_one_or_none()

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )

        # Determine customer status
        customer_status = "active"
        if hasattr(customer, 'status') and customer.status:
            customer_status = customer.status
        elif hasattr(customer, 'is_churned') and customer.is_churned:
            customer_status = "churned"

        # Check if customer is churned
        if customer_status == "churned":
            return SurveyEligibilityResponse(
                eligible=False,
                reason="Customer has churned and should not be surveyed",
                customer_status=customer_status,
                opt_out=False,
                recent_surveys=[],
            )

        # Check if customer is new (created within last 14 days)
        is_new_customer = False
        if hasattr(customer, 'created_at') and customer.created_at:
            days_since_created = (datetime.utcnow() - customer.created_at).days
            if days_since_created < 14:
                is_new_customer = True
                return SurveyEligibilityResponse(
                    eligible=False,
                    reason=f"Customer is new (joined {days_since_created} days ago). Wait until 14 days after signup.",
                    next_eligible_date=(customer.created_at + timedelta(days=14)).strftime("%Y-%m-%d"),
                    customer_status="new",
                    opt_out=False,
                    recent_surveys=[],
                )

        # Check for opt-out preference (if stored on customer)
        opt_out = False
        if hasattr(customer, 'survey_opt_out'):
            opt_out = customer.survey_opt_out or False
        if opt_out:
            return SurveyEligibilityResponse(
                eligible=False,
                reason="Customer has opted out of surveys",
                customer_status=customer_status,
                opt_out=True,
                recent_surveys=[],
            )

        # Get recent survey responses for this customer
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_responses_result = await db.execute(
            select(SurveyResponse)
            .join(Survey)
            .where(
                SurveyResponse.customer_id == customer_id,
                SurveyResponse.created_at >= thirty_days_ago,
            )
            .order_by(SurveyResponse.created_at.desc())
        )
        recent_responses = recent_responses_result.scalars().all()

        # Build recent surveys list
        recent_surveys = []
        for resp in recent_responses:
            survey_result = await db.execute(
                select(Survey.name).where(Survey.id == resp.survey_id)
            )
            survey_name = survey_result.scalar_one_or_none() or "Unknown Survey"
            recent_surveys.append({
                "survey_id": resp.survey_id,
                "name": survey_name,
                "responded_at": resp.created_at.isoformat() if resp.created_at else None,
            })

        # Check if max surveys per month exceeded
        surveys_this_month = len(recent_responses)
        if surveys_this_month >= max_per_month:
            return SurveyEligibilityResponse(
                eligible=False,
                reason=f"Customer has already received {surveys_this_month} surveys this month (max: {max_per_month})",
                customer_status=customer_status,
                opt_out=False,
                recent_surveys=recent_surveys,
                fatigue_score=min(100, surveys_this_month * 40),
            )

        # Check last survey date
        if recent_responses:
            last_survey_date = recent_responses[0].created_at
            days_since_last = (datetime.utcnow() - last_survey_date).days

            if days_since_last < min_days_between:
                next_eligible = last_survey_date + timedelta(days=min_days_between)
                return SurveyEligibilityResponse(
                    eligible=False,
                    reason=f"Customer was surveyed {days_since_last} days ago (min: {min_days_between} days)",
                    next_eligible_date=next_eligible.strftime("%Y-%m-%d"),
                    customer_status=customer_status,
                    opt_out=False,
                    recent_surveys=recent_surveys,
                    fatigue_score=max(0, 100 - (days_since_last * 3)),
                )

        # Customer is eligible
        fatigue_score = 0
        if recent_responses:
            # Calculate fatigue based on frequency
            days_since_last = (datetime.utcnow() - recent_responses[0].created_at).days
            fatigue_score = max(0, 100 - (days_since_last * 2) - (surveys_this_month * 20))

        return SurveyEligibilityResponse(
            eligible=True,
            reason="Customer is eligible to receive a survey",
            customer_status=customer_status,
            opt_out=False,
            recent_surveys=recent_surveys,
            fatigue_score=max(0, fatigue_score),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking survey eligibility: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking survey eligibility: {str(e)}"
        )
