"""
Touchpoint API Endpoints for Enterprise Customer Success Platform
"""

from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import datetime, timedelta

import logging

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.customer_success import Touchpoint
from app.services.ai_gateway import ai_gateway

logger = logging.getLogger(__name__)
from app.schemas.customer_success.touchpoint import (
    TouchpointCreate,
    TouchpointUpdate,
    TouchpointResponse,
    TouchpointListResponse,
    TouchpointSentimentAnalysis,
    TouchpointTimelineResponse,
    TouchpointType,
    TouchpointChannel,
    SentimentLabel,
)

router = APIRouter()


@router.get("/", response_model=TouchpointListResponse)
async def list_touchpoints(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[str] = None,
    touchpoint_type: Optional[str] = None,
    channel: Optional[str] = None,
    direction: Optional[str] = None,
    sentiment_label: Optional[str] = None,
    user_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    """List touchpoints with filtering."""
    query = select(Touchpoint)

    if customer_id:
        query = query.where(Touchpoint.customer_id == customer_id)
    if touchpoint_type:
        query = query.where(Touchpoint.touchpoint_type == touchpoint_type)
    if channel:
        query = query.where(Touchpoint.channel == channel)
    if direction:
        query = query.where(Touchpoint.direction == direction)
    if sentiment_label:
        query = query.where(Touchpoint.sentiment_label == sentiment_label)
    if user_id:
        query = query.where(Touchpoint.user_id == user_id)
    if start_date:
        query = query.where(Touchpoint.occurred_at >= start_date)
    if end_date:
        query = query.where(Touchpoint.occurred_at <= end_date)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Touchpoint.occurred_at.desc())

    result = await db.execute(query)
    touchpoints = result.scalars().all()

    return TouchpointListResponse(
        items=touchpoints,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{touchpoint_id}", response_model=TouchpointResponse)
async def get_touchpoint(
    touchpoint_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific touchpoint."""
    result = await db.execute(select(Touchpoint).where(Touchpoint.id == touchpoint_id))
    touchpoint = result.scalar_one_or_none()

    if not touchpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Touchpoint not found",
        )

    return touchpoint


@router.post("/", response_model=TouchpointResponse, status_code=status.HTTP_201_CREATED)
async def create_touchpoint(
    data: TouchpointCreate,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new touchpoint."""
    # Check customer exists
    customer_result = await db.execute(select(Customer).where(Customer.id == data.customer_id))
    if not customer_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    touchpoint_data = data.model_dump()

    # Set user if not specified
    if not touchpoint_data.get("user_id"):
        touchpoint_data["user_id"] = current_user.id

    # Set occurred_at if not specified
    if not touchpoint_data.get("occurred_at"):
        touchpoint_data["occurred_at"] = datetime.utcnow()

    touchpoint = Touchpoint(**touchpoint_data)
    db.add(touchpoint)
    await db.commit()
    await db.refresh(touchpoint)

    # Queue sentiment analysis for text-based touchpoints
    if data.description or data.summary:
        # In production, this would queue a background job for AI sentiment analysis
        pass

    return touchpoint


@router.patch("/{touchpoint_id}", response_model=TouchpointResponse)
async def update_touchpoint(
    touchpoint_id: int,
    data: TouchpointUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a touchpoint."""
    result = await db.execute(select(Touchpoint).where(Touchpoint.id == touchpoint_id))
    touchpoint = result.scalar_one_or_none()

    if not touchpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Touchpoint not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(touchpoint, field, value)

    await db.commit()
    await db.refresh(touchpoint)
    return touchpoint


@router.delete("/{touchpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_touchpoint(
    touchpoint_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a touchpoint."""
    result = await db.execute(select(Touchpoint).where(Touchpoint.id == touchpoint_id))
    touchpoint = result.scalar_one_or_none()

    if not touchpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Touchpoint not found",
        )

    await db.delete(touchpoint)
    await db.commit()


@router.get("/customer/{customer_id}/timeline", response_model=TouchpointTimelineResponse)
async def get_customer_timeline(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
    days: int = Query(90, ge=7, le=365),
    limit: int = Query(100, ge=1, le=500),
):
    """Get touchpoint timeline for a customer."""
    # Check customer exists
    customer_result = await db.execute(select(Customer).where(Customer.id == customer_id))
    if not customer_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    period_end = datetime.utcnow()
    period_start = period_end - timedelta(days=days)

    # Get touchpoints
    result = await db.execute(
        select(Touchpoint)
        .where(
            Touchpoint.customer_id == customer_id,
            Touchpoint.occurred_at >= period_start,
        )
        .order_by(Touchpoint.occurred_at.desc())
        .limit(limit)
    )
    touchpoints = result.scalars().all()

    # Calculate summary stats
    total = len(touchpoints)
    positive_count = sum(1 for t in touchpoints if t.was_positive)
    negative_count = sum(1 for t in touchpoints if t.was_positive is False)

    sentiment_scores = [t.sentiment_score for t in touchpoints if t.sentiment_score is not None]
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else None

    # Find most common type and channel
    type_counts = {}
    channel_counts = {}
    for t in touchpoints:
        if t.touchpoint_type:
            type_counts[t.touchpoint_type] = type_counts.get(t.touchpoint_type, 0) + 1
        if t.channel:
            channel_counts[t.channel] = channel_counts.get(t.channel, 0) + 1

    most_common_type = max(type_counts, key=type_counts.get) if type_counts else None
    most_common_channel = max(channel_counts, key=channel_counts.get) if channel_counts else None

    # Last interaction
    last_interaction = touchpoints[0].occurred_at if touchpoints else None
    days_since_last = (period_end - last_interaction).days if last_interaction else None

    return TouchpointTimelineResponse(
        customer_id=customer_id,
        touchpoints=touchpoints,
        total=total,
        period_start=period_start,
        period_end=period_end,
        total_interactions=total,
        positive_interactions=positive_count,
        negative_interactions=negative_count,
        avg_sentiment=avg_sentiment,
        most_common_type=most_common_type,
        most_common_channel=most_common_channel,
        last_interaction=last_interaction,
        days_since_last_interaction=days_since_last,
    )


@router.post("/{touchpoint_id}/analyze-sentiment", response_model=TouchpointSentimentAnalysis)
async def analyze_touchpoint_sentiment(
    touchpoint_id: int,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
):
    """Trigger sentiment analysis for a touchpoint."""
    result = await db.execute(select(Touchpoint).where(Touchpoint.id == touchpoint_id))
    touchpoint = result.scalar_one_or_none()

    if not touchpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Touchpoint not found",
        )

    # Build text content from touchpoint fields
    text_parts = []
    if touchpoint.subject:
        text_parts.append(f"Subject: {touchpoint.subject}")
    if touchpoint.summary:
        text_parts.append(f"Summary: {touchpoint.summary}")
    if touchpoint.description:
        text_parts.append(touchpoint.description)
    if touchpoint.notes:
        text_parts.append(f"Notes: {touchpoint.notes}")

    text_content = "\n".join(text_parts) if text_parts else "No content available"

    # Call AI gateway for comprehensive sentiment analysis
    try:
        ai_result = await ai_gateway.chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze this customer touchpoint interaction. Return JSON only:
{{
  "sentiment_score": <float -1.0 to 1.0>,
  "sentiment_label": "<very_negative|negative|neutral|positive|very_positive>",
  "sentiment_confidence": <float 0.0 to 1.0>,
  "key_topics": ["topic1", "topic2"],
  "action_items": ["action1", "action2"],
  "risk_signals": ["risk1"],
  "expansion_signals": ["signal1"],
  "key_quotes": ["quote1"],
  "engagement_score": <int 0-100>,
  "was_positive": <true|false>
}}

Touchpoint type: {touchpoint.touchpoint_type}
Channel: {touchpoint.channel or 'unknown'}
Content:
{text_content}""",
                }
            ],
            max_tokens=500,
            temperature=0.1,
        )

        import json
        content = ai_result.get("content", "{}")
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        parsed = json.loads(content.strip())

        # Map sentiment label
        label_map = {
            "very_negative": SentimentLabel.VERY_NEGATIVE,
            "negative": SentimentLabel.NEGATIVE,
            "neutral": SentimentLabel.NEUTRAL,
            "positive": SentimentLabel.POSITIVE,
            "very_positive": SentimentLabel.VERY_POSITIVE,
        }

        sentiment_label = label_map.get(parsed.get("sentiment_label", "neutral"), SentimentLabel.NEUTRAL)
        sentiment_score = float(parsed.get("sentiment_score", 0.0))
        was_positive = parsed.get("was_positive", sentiment_score > 0)

        # Persist to touchpoint record
        touchpoint.sentiment_score = sentiment_score
        touchpoint.sentiment_label = sentiment_label.value
        touchpoint.sentiment_confidence = float(parsed.get("sentiment_confidence", 0.5))
        touchpoint.key_topics = parsed.get("key_topics", [])
        touchpoint.action_items = parsed.get("action_items", [])
        touchpoint.risk_signals = parsed.get("risk_signals", [])
        touchpoint.expansion_signals = parsed.get("expansion_signals", [])
        touchpoint.key_quotes = parsed.get("key_quotes", [])
        touchpoint.engagement_score = int(parsed.get("engagement_score", 50))
        touchpoint.was_positive = was_positive
        await db.commit()

        analysis = TouchpointSentimentAnalysis(
            touchpoint_id=touchpoint_id,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            sentiment_confidence=float(parsed.get("sentiment_confidence", 0.5)),
            key_topics=parsed.get("key_topics", []),
            action_items=parsed.get("action_items", []),
            risk_signals=parsed.get("risk_signals", []),
            expansion_signals=parsed.get("expansion_signals", []),
            key_quotes=parsed.get("key_quotes", []),
            engagement_score=int(parsed.get("engagement_score", 50)),
            was_positive=was_positive,
        )
    except Exception as e:
        logger.warning(f"AI sentiment analysis failed, using basic analysis: {e}")
        # Fallback: basic keyword-based sentiment
        positive_words = {"great", "excellent", "happy", "thank", "good", "love", "perfect", "awesome"}
        negative_words = {"bad", "terrible", "unhappy", "cancel", "frustrated", "angry", "worst", "issue", "problem"}
        words = set(text_content.lower().split())
        pos_count = len(words & positive_words)
        neg_count = len(words & negative_words)
        if pos_count > neg_count:
            score, label = 0.5, SentimentLabel.POSITIVE
        elif neg_count > pos_count:
            score, label = -0.5, SentimentLabel.NEGATIVE
        else:
            score, label = 0.0, SentimentLabel.NEUTRAL

        analysis = TouchpointSentimentAnalysis(
            touchpoint_id=touchpoint_id,
            sentiment_score=score,
            sentiment_label=label,
            sentiment_confidence=0.3,
            key_topics=[],
            action_items=[],
            risk_signals=[],
            expansion_signals=[],
            key_quotes=[],
            engagement_score=50,
            was_positive=score > 0,
        )

    return analysis


@router.get("/summary")
async def get_touchpoint_summary(
    db: DbSession,
    current_user: CurrentUser,
    customer_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
):
    """Get touchpoint summary statistics."""
    period_start = datetime.utcnow() - timedelta(days=days)

    base_filter = [Touchpoint.occurred_at >= period_start]
    if customer_id:
        base_filter.append(Touchpoint.customer_id == customer_id)

    # Total count
    total_result = await db.execute(select(func.count()).where(*base_filter))
    total = total_result.scalar()

    # Count by type
    type_counts = {}
    for tp_type in TouchpointType:
        count_result = await db.execute(
            select(func.count()).where(
                Touchpoint.touchpoint_type == tp_type.value,
                *base_filter,
            )
        )
        count = count_result.scalar()
        if count > 0:
            type_counts[tp_type.value] = count

    # Count by channel
    channel_counts = {}
    for channel in TouchpointChannel:
        count_result = await db.execute(
            select(func.count()).where(
                Touchpoint.channel == channel.value,
                *base_filter,
            )
        )
        count = count_result.scalar()
        if count > 0:
            channel_counts[channel.value] = count

    # Sentiment breakdown
    sentiment_counts = {}
    for sentiment in SentimentLabel:
        count_result = await db.execute(
            select(func.count()).where(
                Touchpoint.sentiment_label == sentiment.value,
                *base_filter,
            )
        )
        count = count_result.scalar()
        if count > 0:
            sentiment_counts[sentiment.value] = count

    # Average sentiment score
    avg_sentiment_result = await db.execute(select(func.avg(Touchpoint.sentiment_score)).where(*base_filter))
    avg_sentiment = avg_sentiment_result.scalar()

    return {
        "period_days": days,
        "total_touchpoints": total,
        "by_type": type_counts,
        "by_channel": channel_counts,
        "by_sentiment": sentiment_counts,
        "avg_sentiment_score": round(avg_sentiment, 2) if avg_sentiment else None,
    }


@router.get("/recent-activity")
async def get_recent_activity(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    customer_id: Optional[str] = None,
    exclude_internal: bool = True,
):
    """Get recent touchpoint activity."""
    query = select(Touchpoint)

    if customer_id:
        query = query.where(Touchpoint.customer_id == customer_id)
    if exclude_internal:
        query = query.where(Touchpoint.is_internal == False)

    query = query.order_by(Touchpoint.occurred_at.desc()).limit(limit)

    result = await db.execute(query)
    touchpoints = result.scalars().all()

    return {"items": touchpoints, "total": len(touchpoints)}
