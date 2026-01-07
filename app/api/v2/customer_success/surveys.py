"""
Survey API Endpoints for Enterprise Customer Success Platform

Provides endpoints for managing NPS/CSAT/CES surveys and responses.
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timedelta
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.customer_success import (
    Survey, SurveyQuestion, SurveyResponse, SurveyAnswer
)
from app.schemas.customer_success.survey import (
    SurveyCreate, SurveyUpdate, SurveyResponse as SurveyResponseSchema,
    SurveyListResponse, SurveyQuestionCreate, SurveyQuestionUpdate, SurveyQuestionResponse,
    SurveySubmissionCreate, SurveySubmissionResponse, SurveyResponseListResponse,
    SurveyAnalytics, NPSBreakdown,
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
