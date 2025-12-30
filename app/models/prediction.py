"""Prediction models for ML-powered business intelligence."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, JSON, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class LeadScore(Base):
    """Lead scoring prediction results."""

    __tablename__ = "lead_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Entity reference
    customer_id = Column(Integer, unique=True, nullable=False, index=True)

    # Score
    score = Column(Float, nullable=False)  # 0-100
    score_label = Column(String(20), nullable=False)  # hot, warm, cold
    confidence = Column(Float, nullable=True)  # Model confidence

    # Contributing factors
    factors = Column(JSON, nullable=True)
    # Example: {"recency": 0.3, "engagement": 0.25, "budget_fit": 0.2, "urgency": 0.25}

    # Model info
    model_version = Column(String(50), nullable=True)
    model_name = Column(String(100), default="lead_scoring_v1")

    # Timestamps
    scored_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<LeadScore customer:{self.customer_id} score:{self.score}>"


class ChurnPrediction(Base):
    """Customer churn prediction."""

    __tablename__ = "churn_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    customer_id = Column(Integer, unique=True, nullable=False, index=True)

    # Prediction
    churn_probability = Column(Float, nullable=False)  # 0-1
    risk_level = Column(String(20), nullable=False)  # low, medium, high, critical
    days_to_churn = Column(Integer, nullable=True)  # Estimated days until churn

    # Risk factors
    risk_factors = Column(JSON, nullable=True)
    # Example: {"no_service_12mo": true, "complaint_recent": true, "payment_late": false}

    # Recommended actions
    recommended_actions = Column(JSON, nullable=True)
    # Example: ["schedule_wellness_check", "offer_discount", "personal_outreach"]

    # Model info
    model_version = Column(String(50), nullable=True)

    # Timestamps
    predicted_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<ChurnPrediction customer:{self.customer_id} risk:{self.risk_level}>"


class RevenueForecast(Base):
    """Revenue forecasting predictions."""

    __tablename__ = "revenue_forecasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Forecast period
    forecast_date = Column(DateTime(timezone=True), nullable=False, index=True)
    period_type = Column(String(20), nullable=False)  # daily, weekly, monthly
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Predictions
    predicted_revenue = Column(Float, nullable=False)
    predicted_jobs = Column(Integer, nullable=True)
    confidence_lower = Column(Float, nullable=True)  # Lower bound (95% CI)
    confidence_upper = Column(Float, nullable=True)  # Upper bound (95% CI)

    # Actual (filled in later)
    actual_revenue = Column(Float, nullable=True)
    actual_jobs = Column(Integer, nullable=True)

    # Accuracy tracking
    accuracy = Column(Float, nullable=True)  # MAPE or similar

    # Breakdown
    breakdown = Column(JSON, nullable=True)
    # Example: {"pumping": 5000, "repair": 2000, "inspection": 500}

    # Model info
    model_version = Column(String(50), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<RevenueForecast {self.period_type} {self.period_start}>"


class DealHealth(Base):
    """Deal health/rotting detection for opportunities."""

    __tablename__ = "deal_health"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Reference (quote or opportunity)
    entity_type = Column(String(20), nullable=False)  # quote, prospect
    entity_id = Column(String(36), nullable=False, index=True)
    customer_id = Column(Integer, nullable=False, index=True)

    # Health metrics
    health_score = Column(Float, nullable=False)  # 0-100
    health_status = Column(String(20), nullable=False)  # healthy, at_risk, stale, dead
    days_in_stage = Column(Integer, nullable=True)
    days_since_activity = Column(Integer, nullable=True)

    # Warning signs
    warning_signs = Column(JSON, nullable=True)
    # Example: ["no_response_7d", "competitor_mentioned", "budget_concern"]

    # Recommended actions
    recommended_actions = Column(JSON, nullable=True)

    # Timestamps
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<DealHealth {self.entity_type}:{self.entity_id} status:{self.health_status}>"


class PredictionModel(Base):
    """Track ML model versions and performance."""

    __tablename__ = "prediction_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Model identification
    name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    model_type = Column(String(50), nullable=False)  # lead_scoring, churn, revenue, deal_health

    # Model details
    description = Column(Text, nullable=True)
    features = Column(JSON, nullable=True)  # List of input features
    hyperparameters = Column(JSON, nullable=True)

    # Performance metrics
    metrics = Column(JSON, nullable=True)
    # Example: {"accuracy": 0.85, "precision": 0.82, "recall": 0.88, "f1": 0.85}

    # Training info
    training_samples = Column(Integer, nullable=True)
    training_date = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, default=False)  # Only one active per type
    deployed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<PredictionModel {self.name} v{self.version}>"
