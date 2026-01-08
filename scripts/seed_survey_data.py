#!/usr/bin/env python3
"""
Survey Test Data Seeder for Enterprise Customer Success Platform

Creates comprehensive test data for the Survey System:
- 4 surveys (NPS, CSAT, CES, Custom)
- 500+ survey responses with realistic distribution
- Time-series data over 6 months showing trends
- Customer journeys with multiple responses
- AI-powered analysis records with insights

Run with: python scripts/seed_survey_data.py
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, engine, Base
from app.models.customer import Customer
from app.models.customer_success.survey import (
    Survey, SurveyQuestion, SurveyResponse, SurveyAnswer, SurveyAnalysis, SurveyAction
)


# =============================================================================
# FEEDBACK TEXT GENERATORS
# =============================================================================

PROMOTER_FEEDBACK = [
    "Great service! Highly recommend to everyone.",
    "Love the product, it's made my life so much easier.",
    "Very responsive team, always helpful.",
    "Exceeded my expectations in every way.",
    "The team really cares about their customers.",
    "Outstanding quality and excellent support.",
    "Best decision I ever made switching to you.",
    "Incredibly professional and reliable service.",
    "The service technicians are always on time and thorough.",
    "You've earned a customer for life.",
    "Impressed with the attention to detail.",
    "Quick response times and expert knowledge.",
    "The scheduling system is so convenient.",
    "Appreciate the proactive maintenance reminders.",
    "The whole experience has been wonderful.",
    "Really appreciate how you handle emergencies.",
    "Top-notch service from start to finish.",
    "Your team goes above and beyond every time.",
    "Couldn't be happier with the service quality.",
    "The technicians explain everything clearly.",
]

PASSIVE_FEEDBACK = [
    "Good but could be better.",
    "Decent experience overall.",
    "Met my expectations, nothing more.",
    "Service was fine, average experience.",
    "It's okay, does what it needs to do.",
    "Room for improvement but generally satisfied.",
    "Acceptable service for the price.",
    "Had some minor issues but resolved them.",
    "Not bad, not great either.",
    "Would consider alternatives if they offered more.",
    "Service is reliable but nothing special.",
    "Pricing seems a bit high for what we get.",
    "Communication could be improved.",
    "Sometimes have to wait longer than expected.",
    "The quality is inconsistent at times.",
]

DETRACTOR_FEEDBACK = [
    "Slow response time, need to improve.",
    "Too expensive for what you get.",
    "Had issues with support, very frustrating.",
    "Considering switching to another provider.",
    "Service quality has declined recently.",
    "Had to call multiple times for the same issue.",
    "Frustrated with the lack of communication.",
    "Not happy with the service at all.",
    "Feeling like just a number, not valued.",
    "Will be looking at competitors like ServicePro.",
    "Cancel my service if this doesn't improve.",
    "Leaving after this contract ends.",
    "Very disappointed with recent experience.",
    "Support team was unhelpful and rude.",
    "Billing errors are constant, very frustrating.",
    "The technician didn't fix the problem properly.",
    "Had to reschedule multiple times, inconvenient.",
    "Quality doesn't match the premium price.",
    "Thinking about switching to CompetitorX.",
    "Not worth the money anymore.",
]

# Keywords that indicate urgency
URGENT_KEYWORDS = ["cancel", "frustrated", "leaving", "switch", "angry", "disappointed", "terrible", "worst", "competitors"]

# Competitor names to mention
COMPETITORS = ["ServicePro", "CompetitorX", "ValueSeptic", "EcoTreatment", "QuickPump", "BudgetSeptic"]


# =============================================================================
# SURVEY DEFINITIONS
# =============================================================================

SURVEY_DEFINITIONS = [
    {
        "name": "Q4 2025 NPS Survey",
        "description": "Net Promoter Score survey for Q4 2025 to measure customer loyalty and satisfaction.",
        "survey_type": "nps",
        "status": "active",
        "trigger_type": "scheduled",
        "schedule_recurrence": "quarterly",
        "delivery_channel": "email",
        "target_responses": 200,
        "questions": [
            {
                "text": "On a scale of 0-10, how likely are you to recommend our services to a friend or colleague?",
                "question_type": "scale",
                "scale_min": 0,
                "scale_max": 10,
                "scale_min_label": "Not at all likely",
                "scale_max_label": "Extremely likely",
                "is_required": True,
                "order": 1
            },
            {
                "text": "What is the primary reason for your score?",
                "question_type": "text",
                "is_required": False,
                "order": 2
            },
            {
                "text": "What could we do to improve your experience?",
                "question_type": "text",
                "is_required": False,
                "order": 3
            }
        ]
    },
    {
        "name": "Post-Service CSAT",
        "description": "Customer Satisfaction survey sent after each service completion.",
        "survey_type": "csat",
        "status": "active",
        "trigger_type": "event",
        "trigger_event": "service_completed",
        "delivery_channel": "email",
        "target_responses": 150,
        "questions": [
            {
                "text": "How satisfied were you with the service you received today?",
                "question_type": "scale",
                "scale_min": 1,
                "scale_max": 5,
                "scale_min_label": "Very Dissatisfied",
                "scale_max_label": "Very Satisfied",
                "is_required": True,
                "order": 1
            },
            {
                "text": "How would you rate the professionalism of our technician?",
                "question_type": "scale",
                "scale_min": 1,
                "scale_max": 5,
                "scale_min_label": "Poor",
                "scale_max_label": "Excellent",
                "is_required": True,
                "order": 2
            },
            {
                "text": "Was the work completed on time?",
                "question_type": "single_choice",
                "options": ["Yes", "No", "N/A"],
                "is_required": True,
                "order": 3
            },
            {
                "text": "Please share any additional feedback about your experience.",
                "question_type": "text",
                "is_required": False,
                "order": 4
            }
        ]
    },
    {
        "name": "Support Interaction CES",
        "description": "Customer Effort Score survey to measure ease of support interactions.",
        "survey_type": "ces",
        "status": "active",
        "trigger_type": "event",
        "trigger_event": "support_ticket_resolved",
        "delivery_channel": "email",
        "target_responses": 100,
        "questions": [
            {
                "text": "How easy was it to get the help you needed?",
                "question_type": "scale",
                "scale_min": 1,
                "scale_max": 7,
                "scale_min_label": "Very Difficult",
                "scale_max_label": "Very Easy",
                "is_required": True,
                "order": 1
            },
            {
                "text": "Was your issue resolved to your satisfaction?",
                "question_type": "single_choice",
                "options": ["Yes, completely", "Partially", "No"],
                "is_required": True,
                "order": 2
            },
            {
                "text": "How could we make the support process easier?",
                "question_type": "text",
                "is_required": False,
                "order": 3
            }
        ]
    },
    {
        "name": "Product Feature Survey",
        "description": "Custom survey to gather feedback on potential new features and service offerings.",
        "survey_type": "custom",
        "status": "draft",
        "trigger_type": "manual",
        "delivery_channel": "email",
        "target_responses": 0,  # Draft, no responses
        "questions": [
            {
                "text": "Which of the following new services would you be interested in?",
                "question_type": "multiple_choice",
                "options": [
                    "Preventive maintenance plans",
                    "24/7 emergency services",
                    "Smart septic monitoring",
                    "Eco-friendly treatment options",
                    "Extended warranties"
                ],
                "is_required": True,
                "order": 1
            },
            {
                "text": "How much would you be willing to pay monthly for a premium maintenance plan?",
                "question_type": "single_choice",
                "options": ["$0 (not interested)", "$25-50", "$51-75", "$76-100", "$100+"],
                "is_required": True,
                "order": 2
            },
            {
                "text": "What additional services would you like us to offer?",
                "question_type": "text",
                "is_required": False,
                "order": 3
            }
        ]
    }
]


# Customer journey scenarios - customers with multiple responses showing progression
CUSTOMER_JOURNEY_SCENARIOS = [
    {
        "name": "Detractor to Promoter",
        "description": "Customer who had issues but became a fan after great service recovery",
        "responses": [
            {"months_ago": 5, "score_range": (2, 4), "sentiment": "negative", "feedback_type": "detractor"},
            {"months_ago": 3, "score_range": (6, 7), "sentiment": "neutral", "feedback_type": "passive"},
            {"months_ago": 1, "score_range": (9, 10), "sentiment": "positive", "feedback_type": "promoter"}
        ]
    },
    {
        "name": "Promoter to Passive (At Risk)",
        "description": "Previously happy customer showing signs of declining satisfaction",
        "responses": [
            {"months_ago": 6, "score_range": (9, 10), "sentiment": "positive", "feedback_type": "promoter"},
            {"months_ago": 3, "score_range": (8, 9), "sentiment": "positive", "feedback_type": "promoter"},
            {"months_ago": 0, "score_range": (6, 7), "sentiment": "neutral", "feedback_type": "passive"}
        ]
    },
    {
        "name": "Consistent Promoter",
        "description": "Loyal customer who has been consistently happy",
        "responses": [
            {"months_ago": 5, "score_range": (9, 10), "sentiment": "positive", "feedback_type": "promoter"},
            {"months_ago": 2, "score_range": (9, 10), "sentiment": "positive", "feedback_type": "promoter"}
        ]
    },
    {
        "name": "Churn Risk",
        "description": "Customer showing clear signs of wanting to leave",
        "responses": [
            {"months_ago": 4, "score_range": (7, 8), "sentiment": "neutral", "feedback_type": "passive"},
            {"months_ago": 2, "score_range": (4, 5), "sentiment": "negative", "feedback_type": "detractor"},
            {"months_ago": 0, "score_range": (1, 3), "sentiment": "negative", "feedback_type": "detractor"}
        ]
    }
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_feedback_text(feedback_type: str, include_competitor: bool = False) -> str:
    """Get appropriate feedback text based on sentiment type."""
    if feedback_type == "promoter":
        text = random.choice(PROMOTER_FEEDBACK)
    elif feedback_type == "passive":
        text = random.choice(PASSIVE_FEEDBACK)
    else:  # detractor
        text = random.choice(DETRACTOR_FEEDBACK)
        if include_competitor and random.random() < 0.3:
            competitor = random.choice(COMPETITORS)
            text += f" Thinking about {competitor}."
    return text


def check_urgency(text: str) -> Tuple[bool, List[str]]:
    """Check if feedback text contains urgent keywords."""
    found_keywords = []
    text_lower = text.lower()
    for keyword in URGENT_KEYWORDS:
        if keyword in text_lower:
            found_keywords.append(keyword)
    return len(found_keywords) > 0, found_keywords


def get_sentiment_from_score(score: float, survey_type: str) -> str:
    """Determine sentiment based on score and survey type."""
    if survey_type == "nps":
        if score >= 9:
            return "positive"
        elif score >= 7:
            return "neutral"
        else:
            return "negative"
    elif survey_type == "csat":
        if score >= 4:
            return "positive"
        elif score >= 3:
            return "neutral"
        else:
            return "negative"
    elif survey_type == "ces":
        if score >= 6:
            return "positive"
        elif score >= 4:
            return "neutral"
        else:
            return "negative"
    else:
        # Custom - default logic
        return "neutral"


def get_urgency_level(score: float, sentiment: str, has_urgent_keywords: bool) -> Optional[str]:
    """Determine urgency level based on score and sentiment."""
    if has_urgent_keywords:
        return "critical"
    if sentiment == "negative":
        if score <= 3:
            return "high"
        return "medium"
    if sentiment == "neutral":
        return "low"
    return None


def generate_score_for_type(survey_type: str, feedback_type: str) -> float:
    """Generate appropriate score based on survey type and desired feedback category."""
    if survey_type == "nps":
        if feedback_type == "promoter":
            return random.randint(9, 10)
        elif feedback_type == "passive":
            return random.randint(7, 8)
        else:  # detractor
            return random.randint(0, 6)
    elif survey_type == "csat":
        if feedback_type == "promoter":
            return random.randint(4, 5)
        elif feedback_type == "passive":
            return 3
        else:
            return random.randint(1, 2)
    elif survey_type == "ces":
        if feedback_type == "promoter":
            return random.randint(6, 7)
        elif feedback_type == "passive":
            return random.randint(4, 5)
        else:
            return random.randint(1, 3)
    else:
        return random.randint(1, 10)


def random_datetime_in_range(start: datetime, end: datetime) -> datetime:
    """Generate random datetime between start and end."""
    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=random_seconds)


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

async def clear_survey_data(session: AsyncSession):
    """Clear all existing survey data."""
    print("Clearing existing survey data...")

    # Delete in reverse order of dependencies
    await session.execute(delete(SurveyAction))
    await session.execute(delete(SurveyAnalysis))
    await session.execute(delete(SurveyAnswer))
    await session.execute(delete(SurveyResponse))
    await session.execute(delete(SurveyQuestion))
    await session.execute(delete(Survey))

    await session.commit()
    print("  Survey data cleared.")


async def get_or_create_customers(session: AsyncSession, min_count: int = 100) -> List[Customer]:
    """Get existing customers or create test customers if not enough exist."""
    print("\nChecking customers...")

    result = await session.execute(select(Customer).where(Customer.is_active == True))
    customers = list(result.scalars().all())

    print(f"  Found {len(customers)} active customers")

    if len(customers) < min_count:
        print(f"  Creating {min_count - len(customers)} test customers...")

        # Create basic test customers
        test_first_names = ["Testy", "Doug", "Sarah", "Mike", "Lisa", "Tom", "Jane", "Bob", "Alice", "Charlie"]
        test_last_names = ["McTesterson", "Carter", "Smith", "Johnson", "Williams", "Brown", "Davis", "Wilson", "Taylor", "Anderson"]
        cities = [("Houston", "TX", "77001"), ("Austin", "TX", "78701"), ("Dallas", "TX", "75201")]

        for i in range(min_count - len(customers)):
            first = test_first_names[i % len(test_first_names)]
            last = test_last_names[i % len(test_last_names)]
            city, state, postal = cities[i % len(cities)]

            customer = Customer(
                first_name=f"{first}_{i}",
                last_name=last,
                email=f"{first.lower()}.{last.lower()}{i}@example.com",
                phone=f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}",
                address_line1=f"{random.randint(100, 9999)} Test Street",
                city=city,
                state=state,
                postal_code=postal,
                is_active=True,
                customer_type=random.choice(["Residential", "Commercial"]),
                created_at=datetime.now() - timedelta(days=random.randint(30, 365)),
            )
            session.add(customer)
            customers.append(customer)

        await session.commit()
        print(f"  Created customers. Total: {len(customers)}")

    return customers


async def create_surveys(session: AsyncSession) -> List[Survey]:
    """Create the 4 defined surveys with their questions."""
    print("\nCreating surveys...")
    surveys = []

    now = datetime.now(timezone.utc)
    six_months_ago = now - timedelta(days=180)

    for survey_def in SURVEY_DEFINITIONS:
        survey = Survey(
            name=survey_def["name"],
            description=survey_def["description"],
            survey_type=survey_def["survey_type"],
            status=survey_def["status"],
            trigger_type=survey_def["trigger_type"],
            trigger_event=survey_def.get("trigger_event"),
            schedule_recurrence=survey_def.get("schedule_recurrence"),
            delivery_channel=survey_def.get("delivery_channel", "email"),
            is_anonymous=False,
            allow_multiple_responses=True,  # Allow tracking customer journey
            send_reminder=True,
            reminder_days=3,
            created_at=six_months_ago,
            started_at=six_months_ago if survey_def["status"] == "active" else None,
        )
        session.add(survey)
        await session.flush()  # Get the ID

        # Create questions
        for q_def in survey_def["questions"]:
            question = SurveyQuestion(
                survey_id=survey.id,
                text=q_def["text"],
                question_type=q_def["question_type"],
                is_required=q_def.get("is_required", True),
                order=q_def["order"],
                scale_min=q_def.get("scale_min", 0),
                scale_max=q_def.get("scale_max", 10),
                scale_min_label=q_def.get("scale_min_label"),
                scale_max_label=q_def.get("scale_max_label"),
                options=q_def.get("options"),
            )
            session.add(question)

        surveys.append(survey)
        survey._target_responses = survey_def["target_responses"]
        print(f"  Created survey: {survey.name} (type: {survey.survey_type}, status: {survey.status})")

    await session.commit()
    return surveys


async def create_survey_responses(
    session: AsyncSession,
    surveys: List[Survey],
    customers: List[Customer]
) -> Tuple[int, int, int, int]:
    """Create survey responses with realistic distribution over 6 months."""
    print("\nCreating survey responses...")

    now = datetime.now(timezone.utc)
    six_months_ago = now - timedelta(days=180)

    total_responses = 0
    total_promoters = 0
    total_passives = 0
    total_detractors = 0

    # For journey tracking
    journey_customers = {}

    # Assign some customers to journey scenarios
    journey_customer_ids = set()
    for i, scenario in enumerate(CUSTOMER_JOURNEY_SCENARIOS):
        if i < len(customers):
            journey_customers[customers[i].id] = scenario
            journey_customer_ids.add(customers[i].id)

    for survey in surveys:
        if survey.status == "draft":
            print(f"  Skipping draft survey: {survey.name}")
            continue

        target = getattr(survey, '_target_responses', 100)
        print(f"  Generating {target} responses for: {survey.name}")

        # Get questions for this survey
        result = await session.execute(
            select(SurveyQuestion)
            .where(SurveyQuestion.survey_id == survey.id)
            .order_by(SurveyQuestion.order)
        )
        questions = list(result.scalars().all())

        # Distribution: 60% promoters, 25% passives, 15% detractors
        # But vary over time to show improving trend
        responses_created = 0
        survey_promoters = 0
        survey_passives = 0
        survey_detractors = 0

        available_customers = [c for c in customers if c.id not in journey_customer_ids]

        for i in range(target):
            # Select a random customer (can have multiple responses due to allow_multiple_responses)
            customer = random.choice(available_customers)

            # Calculate time - spread over 6 months with more recent responses
            # Use exponential distribution to weight towards more recent
            days_ago = int(random.expovariate(0.02) % 180)  # 0-180 days ago
            response_date = now - timedelta(days=days_ago)

            # Determine feedback type based on distribution
            # Earlier responses are more likely to be negative, showing improvement
            months_ago = days_ago / 30

            # Adjust distribution based on time (earlier = more detractors)
            if months_ago >= 4:
                # 4-6 months ago: worse distribution
                promo_chance, pass_chance = 0.45, 0.30  # 45% promo, 30% passive, 25% detractor
            elif months_ago >= 2:
                # 2-4 months ago: improving
                promo_chance, pass_chance = 0.55, 0.27  # 55% promo, 27% passive, 18% detractor
            else:
                # Last 2 months: best
                promo_chance, pass_chance = 0.68, 0.22  # 68% promo, 22% passive, 10% detractor

            roll = random.random()
            if roll < promo_chance:
                feedback_type = "promoter"
                survey_promoters += 1
            elif roll < promo_chance + pass_chance:
                feedback_type = "passive"
                survey_passives += 1
            else:
                feedback_type = "detractor"
                survey_detractors += 1

            # Generate score
            main_score = generate_score_for_type(survey.survey_type, feedback_type)

            # Generate feedback text
            include_competitor = feedback_type == "detractor" and random.random() < 0.2
            feedback_text = get_feedback_text(feedback_type, include_competitor)
            is_urgent, urgent_keywords = check_urgency(feedback_text)

            # Determine sentiment and urgency
            sentiment = get_sentiment_from_score(main_score, survey.survey_type)
            urgency_level = get_urgency_level(main_score, sentiment, is_urgent)

            # Calculate sentiment score (-1 to 1)
            if sentiment == "positive":
                sentiment_score = random.uniform(0.5, 1.0)
            elif sentiment == "neutral":
                sentiment_score = random.uniform(-0.2, 0.3)
            else:
                sentiment_score = random.uniform(-1.0, -0.3)

            # Create the response
            response = SurveyResponse(
                survey_id=survey.id,
                customer_id=customer.id,
                overall_score=main_score,
                sentiment=sentiment,
                sentiment_score=sentiment_score,
                feedback_text=feedback_text,
                urgency_level=urgency_level,
                is_complete=True,
                source=random.choice(["email", "in_app", "sms"]),
                device=random.choice(["desktop", "mobile", "tablet"]),
                started_at=response_date,
                completed_at=response_date + timedelta(minutes=random.randint(1, 10)),
                completion_time_seconds=random.randint(60, 600),
                created_at=response_date,
            )
            session.add(response)
            await session.flush()

            # Create answers for each question
            for q in questions:
                answer = SurveyAnswer(
                    response_id=response.id,
                    question_id=q.id,
                )

                if q.question_type in ("scale", "rating"):
                    # Use main score for the primary scale question, random for others
                    if q.order == 1:
                        answer.rating_value = int(main_score)
                    else:
                        # Secondary rating questions
                        if feedback_type == "promoter":
                            answer.rating_value = random.randint(q.scale_max - 1, q.scale_max)
                        elif feedback_type == "passive":
                            mid = (q.scale_min + q.scale_max) // 2
                            answer.rating_value = random.randint(mid, mid + 1)
                        else:
                            answer.rating_value = random.randint(q.scale_min, (q.scale_min + q.scale_max) // 2)

                elif q.question_type == "text":
                    if q.order == 2:  # "Reason for score" question
                        answer.text_value = feedback_text
                    elif q.order == 3:  # "Improvement" question
                        if random.random() < 0.6:
                            if feedback_type == "detractor":
                                answer.text_value = random.choice([
                                    "Faster response times would help.",
                                    "Better communication is needed.",
                                    "More competitive pricing.",
                                    "Train your technicians better.",
                                ])
                            else:
                                answer.text_value = random.choice([
                                    "Keep up the good work!",
                                    "Maybe offer loyalty discounts.",
                                    "Nothing major, very satisfied.",
                                    "Online scheduling would be nice.",
                                ])

                elif q.question_type in ("single_choice", "multiple_choice"):
                    if q.options:
                        if q.question_type == "single_choice":
                            # For "Was work completed on time?" type questions
                            if feedback_type == "promoter":
                                answer.choice_values = [q.options[0]]  # Usually "Yes" or positive
                            elif feedback_type == "detractor":
                                answer.choice_values = [q.options[1] if len(q.options) > 1 else q.options[0]]
                            else:
                                answer.choice_values = [random.choice(q.options)]
                        else:
                            # Multiple choice - select 1-3 options
                            num_choices = random.randint(1, min(3, len(q.options)))
                            answer.choice_values = random.sample(q.options, num_choices)

                session.add(answer)

            responses_created += 1

        # Update survey metrics
        survey.responses_count = responses_created
        survey.promoters_count = survey_promoters
        survey.passives_count = survey_passives
        survey.detractors_count = survey_detractors
        survey.avg_score = (survey_promoters * 9.5 + survey_passives * 7.5 + survey_detractors * 4.0) / max(responses_created, 1)
        survey.completion_rate = random.uniform(0.65, 0.85)
        survey.response_rate = random.uniform(0.15, 0.35)

        total_responses += responses_created
        total_promoters += survey_promoters
        total_passives += survey_passives
        total_detractors += survey_detractors

        print(f"    Created {responses_created} responses (P:{survey_promoters} N:{survey_passives} D:{survey_detractors})")

    # Now create journey responses for journey customers
    print("\n  Creating customer journey responses...")
    nps_survey = next((s for s in surveys if s.survey_type == "nps"), surveys[0])

    result = await session.execute(
        select(SurveyQuestion)
        .where(SurveyQuestion.survey_id == nps_survey.id)
        .order_by(SurveyQuestion.order)
    )
    nps_questions = list(result.scalars().all())

    journey_responses = 0
    for customer_id, scenario in journey_customers.items():
        for resp_def in scenario["responses"]:
            months_ago = resp_def["months_ago"]
            score = random.randint(*resp_def["score_range"])
            feedback_type = resp_def["feedback_type"]

            response_date = now - timedelta(days=months_ago * 30 + random.randint(0, 15))
            feedback_text = get_feedback_text(feedback_type, feedback_type == "detractor")
            is_urgent, urgent_keywords = check_urgency(feedback_text)

            sentiment = resp_def["sentiment"]
            if sentiment == "positive":
                sentiment_score = random.uniform(0.5, 1.0)
            elif sentiment == "neutral":
                sentiment_score = random.uniform(-0.2, 0.3)
            else:
                sentiment_score = random.uniform(-1.0, -0.3)

            urgency_level = get_urgency_level(score, sentiment, is_urgent)

            response = SurveyResponse(
                survey_id=nps_survey.id,
                customer_id=customer_id,
                overall_score=score,
                sentiment=sentiment,
                sentiment_score=sentiment_score,
                feedback_text=feedback_text,
                urgency_level=urgency_level,
                is_complete=True,
                source="email",
                device=random.choice(["desktop", "mobile"]),
                started_at=response_date,
                completed_at=response_date + timedelta(minutes=random.randint(2, 8)),
                completion_time_seconds=random.randint(120, 480),
                created_at=response_date,
            )
            session.add(response)
            await session.flush()

            # Create answers
            for q in nps_questions:
                answer = SurveyAnswer(
                    response_id=response.id,
                    question_id=q.id,
                )
                if q.question_type in ("scale", "rating"):
                    answer.rating_value = score if q.order == 1 else random.randint(q.scale_min, q.scale_max)
                elif q.question_type == "text":
                    if q.order == 2:
                        answer.text_value = feedback_text
                session.add(answer)

            journey_responses += 1

            # Update counts
            if score >= 9:
                nps_survey.promoters_count += 1
            elif score >= 7:
                nps_survey.passives_count += 1
            else:
                nps_survey.detractors_count += 1

    nps_survey.responses_count += journey_responses
    total_responses += journey_responses

    print(f"    Created {journey_responses} journey responses across {len(journey_customers)} customers")

    await session.commit()

    return total_responses, total_promoters, total_passives, total_detractors


async def create_survey_analyses(session: AsyncSession, surveys: List[Survey]):
    """Create AI analysis records with insights for each active survey."""
    print("\nCreating survey analysis records...")

    now = datetime.now(timezone.utc)

    for survey in surveys:
        if survey.status == "draft":
            continue

        # Calculate NPS
        total = survey.promoters_count + survey.passives_count + survey.detractors_count
        if total == 0:
            continue

        promoters_pct = (survey.promoters_count / total) * 100
        detractors_pct = (survey.detractors_count / total) * 100
        nps = promoters_pct - detractors_pct

        # Create survey-level analysis
        analysis = SurveyAnalysis(
            survey_id=survey.id,
            response_id=None,  # Survey-level analysis
            sentiment_breakdown={
                "positive": survey.promoters_count,
                "neutral": survey.passives_count,
                "negative": survey.detractors_count
            },
            key_themes=[
                {"theme": "Service Quality", "mentions": random.randint(30, 80), "sentiment": "positive"},
                {"theme": "Response Time", "mentions": random.randint(20, 50), "sentiment": "mixed"},
                {"theme": "Pricing", "mentions": random.randint(15, 40), "sentiment": "negative"},
                {"theme": "Technician Professionalism", "mentions": random.randint(25, 60), "sentiment": "positive"},
                {"theme": "Communication", "mentions": random.randint(10, 30), "sentiment": "mixed"},
            ],
            urgent_issues=[
                {"issue": "Billing disputes", "count": random.randint(3, 12), "severity": "high"},
                {"issue": "Service delays", "count": random.randint(5, 15), "severity": "medium"},
                {"issue": "Cancel requests", "count": random.randint(2, 8), "severity": "critical"},
            ],
            competitor_mentions=[
                {"competitor": "ServicePro", "context": "considering switch", "count": random.randint(2, 8)},
                {"competitor": "ValueSeptic", "context": "price comparison", "count": random.randint(1, 5)},
                {"competitor": "EcoTreatment", "context": "environmental concerns", "count": random.randint(0, 3)},
            ],
            overall_sentiment_score=random.uniform(0.2, 0.6) if nps > 0 else random.uniform(-0.3, 0.2),
            churn_risk_score=max(0, min(100, 50 - nps)),  # Higher NPS = lower churn risk
            urgency_score=random.uniform(20, 60),
            executive_summary=f"""
Survey Analysis Summary for {survey.name}:

Overall NPS: {nps:.1f} (Promoters: {promoters_pct:.1f}%, Detractors: {detractors_pct:.1f}%)

Key Findings:
- Service quality remains our strongest attribute with high mentions and positive sentiment
- Response time is a recurring concern that needs attention
- Pricing perception is mixed, with some customers feeling premium pricing isn't justified
- Technician professionalism continues to be praised

Urgent Actions Required:
1. Address {random.randint(3, 8)} billing disputes within 24 hours
2. Follow up with {random.randint(2, 5)} customers who mentioned cancellation
3. Review {random.randint(5, 10)} cases of service delays

Competitor Insights:
- ServicePro mentioned {random.randint(2, 8)} times, primarily around switching consideration
- Price comparisons with ValueSeptic suggest need for value communication

Recommendations:
1. Implement proactive communication for service appointments
2. Review billing processes to reduce disputes
3. Consider loyalty program to improve retention
4. Schedule callbacks for at-risk customers within 48 hours
            """.strip(),
            analyzed_at=now - timedelta(hours=random.randint(1, 48)),
            analysis_version="v2.0",
            analysis_model="claude-3-opus",
            tokens_used=random.randint(2000, 5000),
            status="completed",
        )
        session.add(analysis)
        print(f"  Created analysis for: {survey.name}")

    await session.commit()


async def create_survey_actions(session: AsyncSession, surveys: List[Survey], customers: List[Customer]):
    """Create sample actions from survey insights."""
    print("\nCreating survey actions...")

    now = datetime.now(timezone.utc)

    for survey in surveys:
        if survey.status == "draft" or survey.detractors_count == 0:
            continue

        # Create some actions for detractor responses
        result = await session.execute(
            select(SurveyResponse)
            .where(SurveyResponse.survey_id == survey.id)
            .where(SurveyResponse.sentiment == "negative")
            .limit(5)
        )
        detractor_responses = list(result.scalars().all())

        for resp in detractor_responses:
            if random.random() < 0.7:  # 70% chance of action
                action = SurveyAction(
                    survey_id=survey.id,
                    response_id=resp.id,
                    customer_id=resp.customer_id,
                    action_type=random.choice(["callback", "task", "ticket", "offer"]),
                    title=f"Follow up on negative {survey.survey_type.upper()} feedback",
                    description=f"Customer scored {resp.overall_score}. Feedback: {resp.feedback_text}",
                    priority=random.choice(["high", "critical"]) if resp.overall_score <= 3 else "medium",
                    source="ai_recommendation",
                    ai_confidence=random.uniform(0.75, 0.95),
                    status=random.choice(["pending", "in_progress", "completed"]),
                    due_date=now + timedelta(days=random.randint(1, 7)),
                    created_at=now - timedelta(hours=random.randint(1, 72)),
                )
                if action.status == "completed":
                    action.completed_at = now - timedelta(hours=random.randint(1, 24))
                    action.outcome = random.choice([
                        "Customer satisfied after callback",
                        "Offered discount, customer retained",
                        "Issue escalated to management",
                        "Scheduled follow-up service visit"
                    ])
                session.add(action)

        print(f"  Created actions for: {survey.name}")

    await session.commit()


# =============================================================================
# MAIN EXECUTION
# =============================================================================

async def main():
    """Main function to seed all survey data."""
    print("=" * 60)
    print("Survey Test Data Seeder")
    print("=" * 60)

    async with async_session_maker() as session:
        # Clear existing data
        await clear_survey_data(session)

        # Get or create customers
        customers = await get_or_create_customers(session, min_count=100)

        # Create surveys with questions
        surveys = await create_surveys(session)

        # Create responses with realistic distribution
        total, promoters, passives, detractors = await create_survey_responses(
            session, surveys, customers
        )

        # Create AI analysis records
        await create_survey_analyses(session, surveys)

        # Create actions from insights
        await create_survey_actions(session, surveys, customers)

        print("\n" + "=" * 60)
        print("Survey Data Seeding Complete!")
        print("=" * 60)
        print(f"\nSummary:")
        print(f"  Surveys created: {len(surveys)}")
        print(f"  Total responses: {total}")
        print(f"  Promoters (9-10): {promoters} ({promoters/max(total,1)*100:.1f}%)")
        print(f"  Passives (7-8): {passives} ({passives/max(total,1)*100:.1f}%)")
        print(f"  Detractors (0-6): {detractors} ({detractors/max(total,1)*100:.1f}%)")

        # Calculate overall NPS
        if total > 0:
            nps = ((promoters - detractors) / total) * 100
            print(f"  Overall NPS: {nps:.1f}")

        print("\nCustomer Journey Scenarios:")
        for scenario in CUSTOMER_JOURNEY_SCENARIOS:
            print(f"  - {scenario['name']}: {scenario['description']}")


if __name__ == "__main__":
    asyncio.run(main())
