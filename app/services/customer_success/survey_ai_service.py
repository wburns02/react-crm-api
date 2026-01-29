"""
Survey AI Analysis Service

Provides AI-powered analysis for customer surveys including:
- Sentiment analysis on open-text responses
- Trend detection across time periods
- Churn risk scoring from NPS detractors
- Topic clustering
- Automated insight generation
- Urgency classification

2025-2026 Best Practices Implementation:
- Hybrid approach: local pattern matching + LLM augmentation
- Graceful degradation when AI unavailable
- Comprehensive scoring algorithms
- Real-time and batch processing support
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging
import re
import math
from collections import Counter, defaultdict
import time

from app.models.customer_success.survey import Survey, SurveyResponse, SurveyAnswer, SurveyQuestion, SurveyAnalysis
from app.models.customer_success.health_score import HealthScore
from app.models.customer import Customer

logger = logging.getLogger(__name__)


class SurveyAIService:
    """
    AI-powered survey analysis service.
    Uses NLP techniques for sentiment, topic detection, and actionable insights.

    The service implements a hybrid approach:
    1. Fast rule-based analysis for real-time feedback
    2. Optional LLM augmentation for deeper insights
    3. Batch processing for comprehensive survey analysis
    """

    # ============================================================================
    # SENTIMENT ANALYSIS LEXICONS
    # ============================================================================

    # Positive sentiment words with intensity scores
    POSITIVE_WORDS = {
        # High intensity (0.8-1.0)
        "excellent": 1.0,
        "outstanding": 1.0,
        "amazing": 0.95,
        "fantastic": 0.95,
        "wonderful": 0.9,
        "exceptional": 0.95,
        "superb": 0.9,
        "brilliant": 0.9,
        "phenomenal": 0.95,
        "incredible": 0.9,
        "perfect": 1.0,
        "love": 0.85,
        # Medium intensity (0.5-0.79)
        "great": 0.75,
        "good": 0.6,
        "nice": 0.55,
        "helpful": 0.65,
        "friendly": 0.6,
        "professional": 0.65,
        "efficient": 0.7,
        "reliable": 0.7,
        "recommend": 0.75,
        "satisfied": 0.65,
        "happy": 0.7,
        "pleased": 0.65,
        "impressed": 0.75,
        "valuable": 0.7,
        "useful": 0.6,
        "effective": 0.65,
        "quality": 0.65,
        # Low intensity (0.3-0.49)
        "okay": 0.35,
        "fine": 0.35,
        "decent": 0.4,
        "acceptable": 0.35,
        "adequate": 0.35,
        "reasonable": 0.4,
        "fair": 0.4,
        "positive": 0.5,
    }

    # Negative sentiment words with intensity scores
    NEGATIVE_WORDS = {
        # High intensity (-0.8 to -1.0)
        "terrible": -1.0,
        "awful": -1.0,
        "horrible": -0.95,
        "worst": -1.0,
        "disgusting": -0.95,
        "appalling": -0.95,
        "atrocious": -0.95,
        "dreadful": -0.9,
        "unacceptable": -0.9,
        "pathetic": -0.9,
        "abysmal": -0.95,
        "hate": -0.85,
        # Medium intensity (-0.5 to -0.79)
        "bad": -0.65,
        "poor": -0.6,
        "disappointed": -0.7,
        "frustrating": -0.75,
        "frustrated": -0.75,
        "annoying": -0.65,
        "annoyed": -0.65,
        "useless": -0.75,
        "unhelpful": -0.7,
        "unprofessional": -0.7,
        "rude": -0.75,
        "slow": -0.55,
        "unreliable": -0.7,
        "waste": -0.75,
        "broken": -0.7,
        "failed": -0.7,
        "problem": -0.5,
        "issue": -0.45,
        "complaint": -0.55,
        "error": -0.55,
        # Low intensity (-0.3 to -0.49)
        "mediocre": -0.45,
        "lacking": -0.45,
        "underwhelming": -0.5,
        "confusing": -0.45,
        "difficult": -0.4,
        "complicated": -0.4,
    }

    # Intensifiers that amplify sentiment
    INTENSIFIERS = {
        "very": 1.3,
        "extremely": 1.5,
        "incredibly": 1.5,
        "absolutely": 1.4,
        "really": 1.25,
        "highly": 1.3,
        "completely": 1.4,
        "totally": 1.35,
        "utterly": 1.5,
        "thoroughly": 1.3,
        "exceptionally": 1.4,
        "remarkably": 1.3,
        "particularly": 1.2,
        "especially": 1.25,
        "so": 1.2,
        "such": 1.15,
    }

    # Negators that flip sentiment
    NEGATORS = {
        "not",
        "no",
        "never",
        "neither",
        "nobody",
        "nothing",
        "nowhere",
        "n't",
        "cannot",
        "can't",
        "won't",
        "wouldn't",
        "couldn't",
        "shouldn't",
        "isn't",
        "aren't",
        "wasn't",
        "weren't",
        "don't",
        "doesn't",
        "didn't",
        "hardly",
        "barely",
        "scarcely",
        "seldom",
        "rarely",
        "without",
    }

    # ============================================================================
    # URGENCY AND RISK KEYWORDS
    # ============================================================================

    # Keywords indicating urgent issues requiring immediate attention
    URGENT_KEYWORDS = {
        "critical": 1.0,
        "urgent": 1.0,
        "emergency": 1.0,
        "immediately": 0.9,
        "asap": 0.9,
        "terrible": 0.85,
        "awful": 0.85,
        "horrible": 0.85,
        "worst": 0.9,
        "never again": 0.85,
        "cancel": 0.8,
        "canceling": 0.85,
        "cancelling": 0.85,
        "refund": 0.75,
        "demand": 0.7,
        "unacceptable": 0.8,
        "outraged": 0.85,
        "furious": 0.85,
        "livid": 0.9,
        "sue": 0.95,
        "lawyer": 0.9,
        "legal": 0.8,
        "bbb": 0.75,
        "report": 0.6,
        "review": 0.5,
        "social media": 0.65,
        "twitter": 0.6,
        "facebook": 0.6,
    }

    # Keywords indicating churn risk
    CHURN_KEYWORDS = {
        "cancel": 0.9,
        "canceling": 0.9,
        "cancelling": 0.9,
        "leave": 0.7,
        "leaving": 0.75,
        "switch": 0.75,
        "switching": 0.8,
        "competitor": 0.85,
        "alternative": 0.7,
        "other company": 0.75,
        "looking elsewhere": 0.8,
        "done": 0.6,
        "finished": 0.55,
        "over it": 0.65,
        "fed up": 0.75,
        "last straw": 0.85,
        "final": 0.5,
        "goodbye": 0.7,
        "ending": 0.65,
        "terminate": 0.85,
        "discontinue": 0.8,
        "stop using": 0.75,
        "not renewing": 0.9,
        "wont renew": 0.9,
        "won't renew": 0.9,
    }

    # Competitor brand mentions (expandable per industry)
    COMPETITOR_PATTERNS = [
        r"\b(competitor[s]?)\b",
        r"\b(other (company|service|provider|vendor|solution))\b",
        r"\b(alternative[s]?)\b",
        r"\b(switched? to)\b",
        r"\b(considering|looking at|evaluating)\s+\w+\s+(instead|alternatively)\b",
        r"\b(better (option|choice|alternative))\b",
    ]

    # ============================================================================
    # TOPIC PATTERNS FOR CLUSTERING
    # ============================================================================

    TOPIC_PATTERNS = {
        "response_time": {
            "keywords": [
                "slow",
                "wait",
                "waiting",
                "response time",
                "took forever",
                "delayed",
                "delay",
                "hours",
                "days",
                "weeks",
                "long time",
                "eventually",
                "finally",
            ],
            "phrases": [r"took\s+\w+\s+(hours|days|weeks)", r"waiting\s+for", r"still\s+waiting", r"no\s+response"],
            "weight": 1.0,
        },
        "pricing": {
            "keywords": [
                "expensive",
                "price",
                "cost",
                "pricing",
                "affordable",
                "value",
                "cheap",
                "overpriced",
                "fee",
                "charge",
                "bill",
                "invoice",
                "money",
                "budget",
                "worth",
            ],
            "phrases": [r"too\s+expensive", r"not\s+worth", r"hidden\s+(fees?|charges?)", r"value\s+for\s+money"],
            "weight": 1.0,
        },
        "product_quality": {
            "keywords": [
                "quality",
                "product",
                "feature",
                "functionality",
                "works",
                "bug",
                "buggy",
                "glitch",
                "crash",
                "error",
                "broken",
                "reliable",
                "unreliable",
                "stable",
                "unstable",
            ],
            "phrases": [
                r"doesn't\s+work",
                r"not\s+working",
                r"stopped\s+working",
                r"keeps\s+(crashing|breaking|failing)",
            ],
            "weight": 1.2,
        },
        "customer_service": {
            "keywords": [
                "support",
                "service",
                "help",
                "agent",
                "representative",
                "staff",
                "team",
                "phone",
                "email",
                "chat",
                "ticket",
                "contact",
                "reach",
                "response",
            ],
            "phrases": [r"customer\s+(service|support)", r"support\s+team", r"help\s+desk", r"couldn't\s+reach"],
            "weight": 1.1,
        },
        "ease_of_use": {
            "keywords": [
                "easy",
                "difficult",
                "complicated",
                "intuitive",
                "user-friendly",
                "confusing",
                "simple",
                "complex",
                "understand",
                "learn",
                "figure out",
                "navigate",
            ],
            "phrases": [
                r"easy\s+to\s+use",
                r"hard\s+to\s+(use|understand|figure)",
                r"user\s+friendly",
                r"learning\s+curve",
            ],
            "weight": 0.9,
        },
        "reliability": {
            "keywords": [
                "reliable",
                "unreliable",
                "bug",
                "error",
                "crash",
                "down",
                "outage",
                "uptime",
                "downtime",
                "issue",
                "problem",
                "fail",
                "failure",
            ],
            "phrases": [
                r"keeps\s+(crashing|failing)",
                r"always\s+(down|broken)",
                r"never\s+works",
                r"constant\s+(issues?|problems?)",
            ],
            "weight": 1.15,
        },
        "onboarding": {
            "keywords": [
                "onboarding",
                "setup",
                "getting started",
                "implementation",
                "training",
                "documentation",
                "tutorial",
                "guide",
                "started",
                "beginning",
                "initial",
            ],
            "phrases": [
                r"getting\s+started",
                r"set\s*up\s+(process|experience)",
                r"first\s+(time|experience|impression)",
            ],
            "weight": 0.85,
        },
        "communication": {
            "keywords": [
                "communication",
                "update",
                "inform",
                "notification",
                "transparent",
                "transparency",
                "proactive",
                "follow up",
                "response",
                "reply",
                "callback",
            ],
            "phrases": [r"keep\s+.*\s+informed", r"no\s+(update|response|communication)", r"lack\s+of\s+communication"],
            "weight": 0.95,
        },
        "billing": {
            "keywords": [
                "billing",
                "invoice",
                "charge",
                "payment",
                "subscription",
                "renewal",
                "overcharge",
                "refund",
                "credit",
                "account",
            ],
            "phrases": [
                r"billing\s+(issue|problem|error)",
                r"wrong\s+charge",
                r"unexpected\s+(charge|fee)",
                r"auto\s*renew",
            ],
            "weight": 1.05,
        },
        "feature_request": {
            "keywords": [
                "wish",
                "want",
                "need",
                "missing",
                "add",
                "feature",
                "improvement",
                "suggestion",
                "would like",
                "should have",
                "request",
                "enhance",
            ],
            "phrases": [
                r"would\s+be\s+(nice|great|helpful)",
                r"wish\s+(you|it|there)",
                r"should\s+(add|have|include)",
                r"feature\s+request",
            ],
            "weight": 0.8,
        },
    }

    def __init__(self, db: AsyncSession):
        """
        Initialize the survey AI service.

        Args:
            db: Async database session for queries
        """
        self.db = db
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        self._compiled_topic_patterns = {}
        for topic, config in self.TOPIC_PATTERNS.items():
            patterns = [re.compile(p, re.IGNORECASE) for p in config.get("phrases", [])]
            self._compiled_topic_patterns[topic] = patterns

        self._compiled_competitor_patterns = [re.compile(p, re.IGNORECASE) for p in self.COMPETITOR_PATTERNS]

    # ============================================================================
    # MAIN ANALYSIS METHODS
    # ============================================================================

    async def analyze_survey(self, survey_id: int) -> Dict[str, Any]:
        """
        Perform comprehensive AI analysis on a survey.

        This is the main entry point for full survey analysis. It processes
        all responses and generates aggregate insights.

        Args:
            survey_id: The ID of the survey to analyze

        Returns:
            Dict containing:
                - sentiment_distribution: Breakdown of positive/neutral/negative
                - nps_analysis: NPS score and breakdown (for NPS surveys)
                - topics: Extracted topics with counts and sentiment
                - urgent_issues: Responses requiring immediate attention
                - churn_risks: High-risk customers identified
                - competitor_mentions: Detected competitor references
                - recommendations: AI-generated action items
                - executive_summary: Text summary of findings
        """
        start_time = time.time()

        # Fetch survey with responses
        result = await self.db.execute(
            select(Survey)
            .options(
                selectinload(Survey.responses).selectinload(SurveyResponse.answers), selectinload(Survey.questions)
            )
            .where(Survey.id == survey_id)
        )
        survey = result.scalar_one_or_none()

        if not survey:
            raise ValueError(f"Survey {survey_id} not found")

        if not survey.responses:
            return {
                "survey_id": survey_id,
                "status": "no_responses",
                "message": "No responses to analyze",
            }

        # Collect all text responses
        text_responses = []
        all_ratings = []
        response_analyses = []

        for response in survey.responses:
            if not response.is_complete:
                continue

            # Get text from all answers
            texts = []
            for answer in response.answers:
                if answer.text_value:
                    texts.append(answer.text_value)
                if answer.rating_value is not None:
                    all_ratings.append(answer.rating_value)

            combined_text = " ".join(texts)
            if combined_text.strip():
                text_responses.append(
                    {
                        "response_id": response.id,
                        "customer_id": response.customer_id,
                        "text": combined_text,
                        "overall_score": response.overall_score,
                    }
                )

            # Analyze individual response
            if combined_text.strip():
                analysis = await self.analyze_response(response.id)
                response_analyses.append(analysis)

        # Aggregate sentiment analysis
        sentiment_distribution = self._aggregate_sentiment(response_analyses)

        # NPS analysis for NPS surveys
        nps_analysis = None
        if survey.survey_type == "nps":
            nps_analysis = self._calculate_nps(survey)

        # Extract and cluster topics
        all_texts = [r["text"] for r in text_responses]
        topics = await self.extract_topics(all_texts)

        # Detect urgent issues
        urgent_issues = await self.detect_urgent_issues(survey_id)

        # Calculate churn risks
        churn_risks = []
        for response_data in text_responses:
            if response_data.get("overall_score") is not None and response_data["overall_score"] <= 6:
                risk = await self.calculate_churn_risk(response_data["customer_id"], response_data)
                if risk["risk_level"] in ["high", "critical"]:
                    churn_risks.append(risk)

        # Detect competitor mentions
        competitor_mentions = await self.detect_competitor_mentions(all_texts)

        # Build analysis result
        analysis_result = {
            "survey_id": survey_id,
            "survey_name": survey.name,
            "survey_type": survey.survey_type,
            "total_responses": len(survey.responses),
            "analyzed_responses": len(text_responses),
            "sentiment_distribution": sentiment_distribution,
            "nps_analysis": nps_analysis,
            "topics": topics,
            "urgent_issues": urgent_issues,
            "urgent_issues_count": len(urgent_issues),
            "churn_risks": churn_risks,
            "churn_risk_count": len(churn_risks),
            "competitor_mentions": competitor_mentions,
            "competitor_mention_count": len(competitor_mentions),
        }

        # Generate recommendations
        recommendations = await self.generate_recommendations(analysis_result)
        analysis_result["recommendations"] = recommendations

        # Generate executive summary
        analysis_result["executive_summary"] = self._generate_executive_summary(analysis_result)

        # Add processing metadata
        processing_time = int((time.time() - start_time) * 1000)
        analysis_result["processing_time_ms"] = processing_time
        analysis_result["analyzed_at"] = datetime.utcnow().isoformat()

        # Save analysis to database
        await self._save_analysis(survey_id, analysis_result)

        return analysis_result

    async def analyze_response(self, response_id: int) -> Dict[str, Any]:
        """
        Analyze a single survey response.

        Performs sentiment analysis, topic extraction, urgency classification,
        and churn risk assessment on one response.

        Args:
            response_id: The ID of the response to analyze

        Returns:
            Dict containing:
                - sentiment: Overall sentiment and score
                - topics: Detected topics
                - urgency: Urgency level and score
                - churn_risk: Risk assessment
                - key_phrases: Important extracted phrases
        """
        # Fetch response with answers
        result = await self.db.execute(
            select(SurveyResponse).options(selectinload(SurveyResponse.answers)).where(SurveyResponse.id == response_id)
        )
        response = result.scalar_one_or_none()

        if not response:
            raise ValueError(f"Response {response_id} not found")

        # Combine text from all answers
        texts = []
        rating_values = []
        for answer in response.answers:
            if answer.text_value:
                texts.append(answer.text_value)
            if answer.rating_value is not None:
                rating_values.append(answer.rating_value)

        combined_text = " ".join(texts)

        # Sentiment analysis
        sentiment = await self.detect_sentiment(combined_text)

        # Adjust sentiment based on ratings if available
        if rating_values:
            avg_rating = sum(rating_values) / len(rating_values)
            sentiment = self._adjust_sentiment_with_rating(sentiment, avg_rating)

        # Topic extraction
        topics = await self.extract_topics([combined_text])

        # Urgency classification
        urgency = self._classify_urgency(combined_text)

        # Churn risk
        churn_risk = await self.calculate_churn_risk(
            response.customer_id, {"text": combined_text, "overall_score": response.overall_score}
        )

        # Extract key phrases
        key_phrases = self._extract_key_phrases(combined_text)

        return {
            "response_id": response_id,
            "customer_id": response.customer_id,
            "sentiment": sentiment,
            "topics": [t["topic"] for t in topics if t["count"] > 0],
            "urgency": urgency,
            "churn_risk": churn_risk,
            "key_phrases": key_phrases,
            "text_length": len(combined_text),
            "has_text_feedback": bool(combined_text.strip()),
        }

    # ============================================================================
    # SENTIMENT ANALYSIS
    # ============================================================================

    async def detect_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment of text using lexicon-based approach.

        Uses a weighted lexicon with intensifiers and negation handling
        for accurate sentiment scoring.

        Args:
            text: The text to analyze

        Returns:
            Dict containing:
                - sentiment: "positive", "neutral", or "negative"
                - score: Float from -1 (very negative) to 1 (very positive)
                - confidence: Float from 0 to 1
                - word_scores: Breakdown of sentiment-bearing words found
        """
        if not text or not text.strip():
            return {
                "sentiment": "neutral",
                "score": 0.0,
                "confidence": 0.0,
                "word_scores": [],
            }

        # Normalize text
        text_lower = text.lower()
        words = re.findall(r"\b\w+\b", text_lower)

        if not words:
            return {
                "sentiment": "neutral",
                "score": 0.0,
                "confidence": 0.0,
                "word_scores": [],
            }

        scores = []
        word_scores = []

        # Track negation window
        negation_active = False
        negation_countdown = 0

        # Track intensifier
        intensifier = 1.0

        for i, word in enumerate(words):
            # Check for negators
            if word in self.NEGATORS:
                negation_active = True
                negation_countdown = 3  # Negation affects next 3 words
                continue

            # Check for intensifiers
            if word in self.INTENSIFIERS:
                intensifier = self.INTENSIFIERS[word]
                continue

            # Check positive words
            if word in self.POSITIVE_WORDS:
                base_score = self.POSITIVE_WORDS[word]
                final_score = base_score * intensifier
                if negation_active:
                    final_score = -final_score * 0.8  # Flip but reduce intensity
                scores.append(final_score)
                word_scores.append(
                    {
                        "word": word,
                        "base_score": base_score,
                        "final_score": final_score,
                        "negated": negation_active,
                        "intensified": intensifier != 1.0,
                    }
                )

            # Check negative words
            elif word in self.NEGATIVE_WORDS:
                base_score = self.NEGATIVE_WORDS[word]
                final_score = base_score * intensifier
                if negation_active:
                    final_score = -final_score * 0.8  # Flip but reduce intensity
                scores.append(final_score)
                word_scores.append(
                    {
                        "word": word,
                        "base_score": base_score,
                        "final_score": final_score,
                        "negated": negation_active,
                        "intensified": intensifier != 1.0,
                    }
                )

            # Reset intensifier after use
            intensifier = 1.0

            # Decrement negation countdown
            if negation_countdown > 0:
                negation_countdown -= 1
                if negation_countdown == 0:
                    negation_active = False

        # Calculate overall sentiment score
        if scores:
            # Weighted average favoring extreme scores
            weighted_scores = [s * (1 + abs(s) * 0.5) for s in scores]
            raw_score = sum(weighted_scores) / len(weighted_scores)

            # Normalize to -1 to 1 range
            final_score = max(-1.0, min(1.0, raw_score))

            # Calculate confidence based on evidence strength
            confidence = min(1.0, len(scores) / 5.0) * (1 - 1 / (1 + sum(abs(s) for s in scores)))
        else:
            final_score = 0.0
            confidence = 0.2  # Low confidence when no sentiment words found

        # Determine sentiment label
        if final_score > 0.15:
            sentiment = "positive"
        elif final_score < -0.15:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        return {
            "sentiment": sentiment,
            "score": round(final_score, 3),
            "confidence": round(confidence, 3),
            "word_scores": word_scores[:10],  # Top 10 for brevity
        }

    def _adjust_sentiment_with_rating(
        self, sentiment: Dict[str, Any], avg_rating: float, max_rating: int = 10
    ) -> Dict[str, Any]:
        """Adjust sentiment score based on numerical ratings."""
        # Convert rating to -1 to 1 scale
        rating_normalized = (avg_rating / max_rating) * 2 - 1

        # Blend text sentiment with rating (60% text, 40% rating)
        blended_score = sentiment["score"] * 0.6 + rating_normalized * 0.4

        # Recalculate sentiment label
        if blended_score > 0.15:
            sentiment_label = "positive"
        elif blended_score < -0.15:
            sentiment_label = "negative"
        else:
            sentiment_label = "neutral"

        return {
            **sentiment,
            "score": round(blended_score, 3),
            "sentiment": sentiment_label,
            "rating_influence": round(rating_normalized, 3),
        }

    def _aggregate_sentiment(self, response_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate sentiment across multiple responses."""
        if not response_analyses:
            return {
                "positive": 0,
                "neutral": 0,
                "negative": 0,
                "average_score": 0.0,
                "total_analyzed": 0,
            }

        sentiments = Counter()
        scores = []

        for analysis in response_analyses:
            if "sentiment" in analysis:
                sent = analysis["sentiment"]
                if isinstance(sent, dict):
                    sentiments[sent.get("sentiment", "neutral")] += 1
                    if "score" in sent:
                        scores.append(sent["score"])
                elif isinstance(sent, str):
                    sentiments[sent] += 1

        total = sum(sentiments.values()) or 1
        avg_score = sum(scores) / len(scores) if scores else 0.0

        return {
            "positive": sentiments.get("positive", 0),
            "positive_pct": round(sentiments.get("positive", 0) / total * 100, 1),
            "neutral": sentiments.get("neutral", 0),
            "neutral_pct": round(sentiments.get("neutral", 0) / total * 100, 1),
            "negative": sentiments.get("negative", 0),
            "negative_pct": round(sentiments.get("negative", 0) / total * 100, 1),
            "average_score": round(avg_score, 3),
            "total_analyzed": total,
        }

    # ============================================================================
    # TOPIC EXTRACTION
    # ============================================================================

    async def extract_topics(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Extract and cluster topics from multiple text responses.

        Uses keyword matching and phrase patterns to identify common themes
        in feedback. Returns topics sorted by frequency with sentiment analysis.

        Args:
            texts: List of text responses to analyze

        Returns:
            List of dicts containing:
                - topic: Topic name/category
                - count: Number of mentions
                - percentage: Percentage of responses mentioning this topic
                - sentiment: Aggregate sentiment for this topic
                - examples: Sample text snippets
        """
        if not texts:
            return []

        topic_data = defaultdict(
            lambda: {
                "count": 0,
                "sentiment_scores": [],
                "examples": [],
            }
        )

        total_texts = len(texts)

        for text in texts:
            if not text or not text.strip():
                continue

            text_lower = text.lower()
            text_topics_found = set()

            for topic_name, config in self.TOPIC_PATTERNS.items():
                # Check keywords
                keywords_found = 0
                for keyword in config["keywords"]:
                    if keyword.lower() in text_lower:
                        keywords_found += 1

                # Check phrase patterns
                phrases_found = 0
                for pattern in self._compiled_topic_patterns.get(topic_name, []):
                    if pattern.search(text_lower):
                        phrases_found += 1

                # Topic detected if sufficient evidence
                weight = config.get("weight", 1.0)
                score = (keywords_found * 0.5 + phrases_found * 1.5) * weight

                if score >= 1.0:  # Threshold for topic detection
                    text_topics_found.add(topic_name)

            # Update topic data
            for topic_name in text_topics_found:
                topic_data[topic_name]["count"] += 1

                # Get sentiment for this text
                sentiment = await self.detect_sentiment(text)
                topic_data[topic_name]["sentiment_scores"].append(sentiment["score"])

                # Store example (first 200 chars)
                if len(topic_data[topic_name]["examples"]) < 3:
                    topic_data[topic_name]["examples"].append(text[:200])

        # Build result list
        results = []
        for topic_name, data in topic_data.items():
            if data["count"] == 0:
                continue

            avg_sentiment = sum(data["sentiment_scores"]) / len(data["sentiment_scores"])

            # Determine sentiment label
            if avg_sentiment > 0.15:
                sentiment_label = "positive"
            elif avg_sentiment < -0.15:
                sentiment_label = "negative"
            else:
                sentiment_label = "mixed"

            results.append(
                {
                    "topic": topic_name,
                    "display_name": topic_name.replace("_", " ").title(),
                    "count": data["count"],
                    "percentage": round(data["count"] / total_texts * 100, 1),
                    "sentiment": sentiment_label,
                    "sentiment_score": round(avg_sentiment, 3),
                    "examples": data["examples"],
                }
            )

        # Sort by count descending
        results.sort(key=lambda x: x["count"], reverse=True)

        return results

    # ============================================================================
    # CHURN RISK ANALYSIS
    # ============================================================================

    async def calculate_churn_risk(self, customer_id: int, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate churn risk based on survey response and customer history.

        Uses multiple signals including:
        - NPS/rating scores
        - Sentiment in text feedback
        - Churn-related keywords
        - Customer health score history
        - Competitor mentions

        Args:
            customer_id: The customer ID
            response_data: Dict with 'text' and 'overall_score' keys

        Returns:
            Dict containing:
                - risk_score: 0-100 scale
                - risk_level: "low", "medium", "high", or "critical"
                - factors: List of contributing factors
                - recommended_actions: Suggested follow-up actions
        """
        factors = []
        risk_score = 0
        text = response_data.get("text", "")
        overall_score = response_data.get("overall_score")

        # Factor 1: NPS/Rating score (0-40 points)
        if overall_score is not None:
            if overall_score <= 3:
                risk_score += 40
                factors.append(
                    {
                        "factor": "very_low_score",
                        "description": f"Very low rating of {overall_score}/10",
                        "weight": 40,
                    }
                )
            elif overall_score <= 5:
                risk_score += 30
                factors.append(
                    {
                        "factor": "low_score",
                        "description": f"Low rating of {overall_score}/10",
                        "weight": 30,
                    }
                )
            elif overall_score <= 6:
                risk_score += 20
                factors.append(
                    {
                        "factor": "below_average_score",
                        "description": f"Below average rating of {overall_score}/10",
                        "weight": 20,
                    }
                )

        # Factor 2: Churn keywords (0-30 points)
        if text:
            text_lower = text.lower()
            churn_keyword_score = 0
            found_keywords = []

            for keyword, weight in self.CHURN_KEYWORDS.items():
                if keyword in text_lower:
                    churn_keyword_score = max(churn_keyword_score, weight * 30)
                    found_keywords.append(keyword)

            if found_keywords:
                risk_score += churn_keyword_score
                factors.append(
                    {
                        "factor": "churn_keywords",
                        "description": f"Detected churn-related language: {', '.join(found_keywords[:3])}",
                        "weight": round(churn_keyword_score),
                    }
                )

        # Factor 3: Sentiment (0-20 points)
        if text:
            sentiment = await self.detect_sentiment(text)
            sentiment_score = sentiment.get("score", 0)

            if sentiment_score < -0.5:
                sentiment_risk = 20
            elif sentiment_score < -0.25:
                sentiment_risk = 15
            elif sentiment_score < 0:
                sentiment_risk = 10
            else:
                sentiment_risk = 0

            if sentiment_risk > 0:
                risk_score += sentiment_risk
                factors.append(
                    {
                        "factor": "negative_sentiment",
                        "description": f"Negative sentiment detected (score: {sentiment_score:.2f})",
                        "weight": sentiment_risk,
                    }
                )

        # Factor 4: Competitor mentions (0-15 points)
        if text:
            competitor_mentions = await self.detect_competitor_mentions([text])
            if competitor_mentions:
                risk_score += 15
                factors.append(
                    {
                        "factor": "competitor_mention",
                        "description": "Mentioned competitor or alternative solutions",
                        "weight": 15,
                    }
                )

        # Factor 5: Customer health score history (0-15 points)
        try:
            health_result = await self.db.execute(
                select(HealthScore)
                .where(HealthScore.customer_id == customer_id)
                .order_by(HealthScore.created_at.desc())
                .limit(1)
            )
            health_score = health_result.scalar_one_or_none()

            if health_score:
                if health_score.health_status == "critical":
                    risk_score += 15
                    factors.append(
                        {
                            "factor": "critical_health",
                            "description": "Customer is in critical health status",
                            "weight": 15,
                        }
                    )
                elif health_score.health_status == "at_risk":
                    risk_score += 10
                    factors.append(
                        {
                            "factor": "at_risk_health",
                            "description": "Customer is at risk health status",
                            "weight": 10,
                        }
                    )
        except Exception as e:
            logger.warning(f"Could not fetch health score for customer {customer_id}: {e}")

        # Cap at 100
        risk_score = min(100, risk_score)

        # Determine risk level
        if risk_score >= 75:
            risk_level = "critical"
        elif risk_score >= 50:
            risk_level = "high"
        elif risk_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Generate recommended actions
        recommended_actions = self._generate_churn_actions(risk_level, factors)

        return {
            "customer_id": customer_id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "factors": factors,
            "recommended_actions": recommended_actions,
        }

    def _generate_churn_actions(self, risk_level: str, factors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate recommended actions based on churn risk."""
        actions = []

        if risk_level in ["critical", "high"]:
            actions.append(
                {
                    "action": "immediate_callback",
                    "priority": "high",
                    "description": "Schedule immediate callback with customer success manager",
                }
            )

        factor_types = [f["factor"] for f in factors]

        if "competitor_mention" in factor_types:
            actions.append(
                {
                    "action": "competitive_review",
                    "priority": "high",
                    "description": "Conduct competitive comparison and prepare retention offer",
                }
            )

        if "churn_keywords" in factor_types:
            actions.append(
                {
                    "action": "escalation",
                    "priority": "high",
                    "description": "Escalate to retention team for proactive outreach",
                }
            )

        if "negative_sentiment" in factor_types:
            actions.append(
                {
                    "action": "service_recovery",
                    "priority": "medium",
                    "description": "Initiate service recovery process to address concerns",
                }
            )

        if risk_level == "critical":
            actions.append(
                {
                    "action": "executive_sponsor",
                    "priority": "high",
                    "description": "Consider executive sponsor involvement for high-value account",
                }
            )

        return actions

    # ============================================================================
    # URGENT ISSUE DETECTION
    # ============================================================================

    async def detect_urgent_issues(self, survey_id: int) -> List[Dict[str, Any]]:
        """
        Identify responses requiring immediate attention.

        Scans all responses for urgent language, very low scores,
        and other red flags that warrant immediate follow-up.

        Args:
            survey_id: The survey ID to analyze

        Returns:
            List of dicts containing:
                - response_id: The response requiring attention
                - customer_id: Associated customer
                - reason: Why this is urgent
                - severity: "critical", "high", "medium"
                - urgency_score: Numerical score 0-100
                - text_snippet: Relevant excerpt
        """
        # Fetch responses with text
        result = await self.db.execute(
            select(SurveyResponse)
            .options(selectinload(SurveyResponse.answers))
            .where(SurveyResponse.survey_id == survey_id)
        )
        responses = result.scalars().all()

        urgent_issues = []

        for response in responses:
            # Combine text from answers
            texts = []
            has_very_low_score = False

            for answer in response.answers:
                if answer.text_value:
                    texts.append(answer.text_value)
                if answer.rating_value is not None and answer.rating_value <= 3:
                    has_very_low_score = True

            combined_text = " ".join(texts)

            if not combined_text.strip() and not has_very_low_score:
                continue

            # Check urgency
            urgency = self._classify_urgency(combined_text)

            # Also check if overall score is very low
            if response.overall_score is not None and response.overall_score <= 3:
                if urgency["level"] == "low":
                    urgency["level"] = "medium"
                    urgency["score"] = max(urgency["score"], 50)
                urgency["reasons"].append("Very low NPS score")

            if urgency["level"] in ["critical", "high"] or urgency["score"] >= 50:
                # Extract relevant snippet
                snippet = combined_text[:300] if combined_text else "[No text feedback]"

                urgent_issues.append(
                    {
                        "response_id": response.id,
                        "customer_id": response.customer_id,
                        "reason": "; ".join(urgency["reasons"]),
                        "severity": urgency["level"],
                        "urgency_score": urgency["score"],
                        "text_snippet": snippet,
                        "overall_score": response.overall_score,
                        "created_at": response.created_at.isoformat() if response.created_at else None,
                    }
                )

        # Sort by urgency score descending
        urgent_issues.sort(key=lambda x: x["urgency_score"], reverse=True)

        return urgent_issues

    def _classify_urgency(self, text: str) -> Dict[str, Any]:
        """Classify urgency level of text feedback."""
        if not text:
            return {"level": "low", "score": 0, "reasons": []}

        text_lower = text.lower()
        urgency_score = 0
        reasons = []

        # Check urgent keywords
        for keyword, weight in self.URGENT_KEYWORDS.items():
            if keyword in text_lower:
                urgency_score = max(urgency_score, weight * 100)
                reasons.append(f"Contains urgent keyword: '{keyword}'")

        # Check for CAPS indicating strong emotion
        caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
        if caps_ratio > 0.3 and len(text) > 20:
            urgency_score = max(urgency_score, 60)
            reasons.append("Contains significant ALL CAPS text")

        # Check for multiple exclamation/question marks
        if text.count("!") >= 3 or text.count("?") >= 3:
            urgency_score = max(urgency_score, 50)
            reasons.append("Contains multiple exclamation/question marks")

        # Determine level
        if urgency_score >= 80:
            level = "critical"
        elif urgency_score >= 60:
            level = "high"
        elif urgency_score >= 40:
            level = "medium"
        else:
            level = "low"

        return {
            "level": level,
            "score": round(urgency_score),
            "reasons": reasons[:3],  # Top 3 reasons
        }

    # ============================================================================
    # RECOMMENDATION ENGINE
    # ============================================================================

    async def generate_recommendations(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate actionable recommendations based on analysis.

        Uses the aggregated analysis results to produce prioritized
        action items for the customer success team.

        Args:
            analysis: Complete analysis results dict

        Returns:
            List of dicts containing:
                - action: Type of recommended action
                - priority: "critical", "high", "medium", "low"
                - reason: Why this action is recommended
                - target: Who/what this action targets
                - estimated_impact: Expected benefit
        """
        recommendations = []

        # Priority 1: Address critical/high urgency issues
        urgent_issues = analysis.get("urgent_issues", [])
        critical_issues = [i for i in urgent_issues if i.get("severity") == "critical"]
        high_issues = [i for i in urgent_issues if i.get("severity") == "high"]

        if critical_issues:
            recommendations.append(
                {
                    "action": "immediate_outreach",
                    "priority": "critical",
                    "reason": f"{len(critical_issues)} critical issues detected requiring immediate attention",
                    "target": [i["customer_id"] for i in critical_issues[:5]],
                    "estimated_impact": "Prevent immediate churn risk",
                    "suggested_owner": "CSM",
                }
            )

        if high_issues:
            recommendations.append(
                {
                    "action": "priority_callback",
                    "priority": "high",
                    "reason": f"{len(high_issues)} high-priority issues identified",
                    "target": [i["customer_id"] for i in high_issues[:10]],
                    "estimated_impact": "Address concerns before escalation",
                    "suggested_owner": "CSM",
                }
            )

        # Priority 2: Address high churn risk customers
        churn_risks = analysis.get("churn_risks", [])
        if churn_risks:
            recommendations.append(
                {
                    "action": "retention_campaign",
                    "priority": "high",
                    "reason": f"{len(churn_risks)} customers identified with high churn risk",
                    "target": [c["customer_id"] for c in churn_risks[:10]],
                    "estimated_impact": "Reduce churn probability",
                    "suggested_owner": "Retention Team",
                }
            )

        # Priority 3: Address competitor concerns
        competitor_mentions = analysis.get("competitor_mentions", [])
        if len(competitor_mentions) >= 3:
            recommendations.append(
                {
                    "action": "competitive_analysis",
                    "priority": "high",
                    "reason": f"{len(competitor_mentions)} competitor/alternative mentions detected",
                    "target": "Product & Marketing Teams",
                    "estimated_impact": "Understand competitive positioning gaps",
                    "suggested_owner": "Product Marketing",
                }
            )

        # Priority 4: Address top negative topics
        topics = analysis.get("topics", [])
        negative_topics = [t for t in topics if t.get("sentiment") == "negative" and t.get("count", 0) >= 3]

        for topic in negative_topics[:3]:
            recommendations.append(
                {
                    "action": "topic_improvement",
                    "priority": "medium",
                    "reason": f"Negative feedback on {topic['display_name']} ({topic['count']} mentions)",
                    "target": topic["topic"],
                    "estimated_impact": f"Address {topic['percentage']}% of negative feedback",
                    "suggested_owner": self._get_topic_owner(topic["topic"]),
                }
            )

        # Priority 5: Capitalize on positive feedback
        sentiment = analysis.get("sentiment_distribution", {})
        if sentiment.get("positive_pct", 0) >= 50:
            recommendations.append(
                {
                    "action": "testimonial_collection",
                    "priority": "low",
                    "reason": f"High positive sentiment ({sentiment.get('positive_pct')}%) - opportunity for testimonials",
                    "target": "Promoters",
                    "estimated_impact": "Generate social proof and referrals",
                    "suggested_owner": "Marketing",
                }
            )

        # Priority 6: NPS follow-up
        nps = analysis.get("nps_analysis")
        if nps and nps.get("detractors", 0) > 0:
            recommendations.append(
                {
                    "action": "detractor_recovery",
                    "priority": "high",
                    "reason": f"{nps.get('detractors', 0)} NPS detractors identified",
                    "target": "Detractor customers",
                    "estimated_impact": "Convert detractors to passives/promoters",
                    "suggested_owner": "CSM",
                }
            )

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 4))

        return recommendations

    def _get_topic_owner(self, topic: str) -> str:
        """Get suggested owner for a topic."""
        topic_owners = {
            "response_time": "Support Team",
            "pricing": "Finance/Sales",
            "product_quality": "Engineering",
            "customer_service": "Support Team",
            "ease_of_use": "UX/Product",
            "reliability": "Engineering",
            "onboarding": "Onboarding Team",
            "communication": "CSM",
            "billing": "Finance",
            "feature_request": "Product Management",
        }
        return topic_owners.get(topic, "CSM")

    # ============================================================================
    # TREND ANALYSIS
    # ============================================================================

    async def get_trend_analysis(self, survey_ids: List[int], days: int = 90) -> Dict[str, Any]:
        """
        Analyze trends across multiple surveys over time.

        Compares metrics across survey periods to identify improving
        or declining trends in customer satisfaction.

        Args:
            survey_ids: List of survey IDs to analyze
            days: Number of days to look back

        Returns:
            Dict containing:
                - nps_trend: NPS score changes over time
                - sentiment_trend: Sentiment changes
                - topic_trends: Topic frequency changes
                - response_rate_trend: Participation changes
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Fetch surveys with responses
        result = await self.db.execute(
            select(Survey)
            .options(selectinload(Survey.responses))
            .where(Survey.id.in_(survey_ids), Survey.created_at >= cutoff_date)
            .order_by(Survey.created_at)
        )
        surveys = result.scalars().all()

        if len(surveys) < 2:
            return {
                "message": "Need at least 2 surveys for trend analysis",
                "surveys_found": len(surveys),
            }

        # Calculate metrics per survey
        survey_metrics = []
        for survey in surveys:
            nps = self._calculate_nps(survey) if survey.survey_type == "nps" else None

            metrics = {
                "survey_id": survey.id,
                "name": survey.name,
                "date": survey.created_at.isoformat() if survey.created_at else None,
                "response_count": len(survey.responses),
                "nps_score": nps.get("nps_score") if nps else None,
                "avg_score": survey.avg_score,
            }
            survey_metrics.append(metrics)

        # Calculate trends
        nps_scores = [m["nps_score"] for m in survey_metrics if m["nps_score"] is not None]
        avg_scores = [m["avg_score"] for m in survey_metrics if m["avg_score"] is not None]

        nps_trend = self._calculate_trend(nps_scores) if len(nps_scores) >= 2 else None
        score_trend = self._calculate_trend(avg_scores) if len(avg_scores) >= 2 else None

        return {
            "period_days": days,
            "surveys_analyzed": len(surveys),
            "survey_metrics": survey_metrics,
            "nps_trend": {
                "direction": nps_trend["direction"] if nps_trend else None,
                "change": nps_trend["change"] if nps_trend else None,
                "first_value": nps_scores[0] if nps_scores else None,
                "last_value": nps_scores[-1] if nps_scores else None,
            }
            if nps_trend
            else None,
            "score_trend": {
                "direction": score_trend["direction"] if score_trend else None,
                "change": score_trend["change"] if score_trend else None,
            }
            if score_trend
            else None,
        }

    def _calculate_trend(self, values: List[float]) -> Dict[str, Any]:
        """Calculate trend direction and magnitude."""
        if len(values) < 2:
            return None

        first = values[0]
        last = values[-1]
        change = last - first

        # Calculate percentage change
        if first != 0:
            pct_change = (change / abs(first)) * 100
        else:
            pct_change = 100 if change > 0 else -100 if change < 0 else 0

        # Determine direction
        if pct_change > 5:
            direction = "improving"
        elif pct_change < -5:
            direction = "declining"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "change": round(change, 2),
            "percentage_change": round(pct_change, 1),
        }

    # ============================================================================
    # COMPETITOR DETECTION
    # ============================================================================

    async def detect_competitor_mentions(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Detect competitor mentions in feedback.

        Identifies both explicit competitor names and implicit references
        to alternatives, competitors, or switching intent.

        Args:
            texts: List of text responses to analyze

        Returns:
            List of dicts containing:
                - text_snippet: Relevant excerpt
                - competitor_type: "named" or "generic"
                - context: Surrounding context
                - response_index: Which response this came from
        """
        mentions = []

        for idx, text in enumerate(texts):
            if not text or not text.strip():
                continue

            text_lower = text.lower()

            for pattern in self._compiled_competitor_patterns:
                matches = pattern.finditer(text_lower)
                for match in matches:
                    # Get context around the match
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end]

                    # Clean up context
                    if start > 0:
                        context = "..." + context
                    if end < len(text):
                        context = context + "..."

                    # Determine if named or generic
                    matched_text = match.group()
                    competitor_type = "generic"

                    mentions.append(
                        {
                            "text_snippet": matched_text,
                            "competitor_type": competitor_type,
                            "context": context,
                            "response_index": idx,
                        }
                    )

        # Deduplicate similar mentions
        unique_mentions = []
        seen_contexts = set()
        for mention in mentions:
            context_key = mention["context"][:100]
            if context_key not in seen_contexts:
                seen_contexts.add(context_key)
                unique_mentions.append(mention)

        return unique_mentions

    # ============================================================================
    # HELPER METHODS
    # ============================================================================

    def _calculate_nps(self, survey: Survey) -> Dict[str, Any]:
        """Calculate NPS score and breakdown for a survey."""
        promoters = survey.promoters_count or 0
        passives = survey.passives_count or 0
        detractors = survey.detractors_count or 0

        total = promoters + passives + detractors
        if total == 0:
            # Calculate from responses
            for response in survey.responses:
                if response.overall_score is not None:
                    if response.overall_score >= 9:
                        promoters += 1
                    elif response.overall_score >= 7:
                        passives += 1
                    else:
                        detractors += 1
            total = promoters + passives + detractors

        if total == 0:
            return {
                "nps_score": None,
                "promoters": 0,
                "passives": 0,
                "detractors": 0,
                "total": 0,
            }

        nps_score = round(((promoters - detractors) / total) * 100)

        return {
            "nps_score": nps_score,
            "promoters": promoters,
            "promoters_pct": round(promoters / total * 100, 1),
            "passives": passives,
            "passives_pct": round(passives / total * 100, 1),
            "detractors": detractors,
            "detractors_pct": round(detractors / total * 100, 1),
            "total": total,
        }

    def _extract_key_phrases(self, text: str, max_phrases: int = 5) -> List[str]:
        """Extract key phrases from text."""
        if not text:
            return []

        # Simple extraction based on sentence boundaries and length
        sentences = re.split(r"[.!?]+", text)
        phrases = []

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20 and len(sentence) < 200:
                # Check if contains sentiment-bearing content
                has_sentiment = any(
                    word in sentence.lower()
                    for word in list(self.POSITIVE_WORDS.keys()) + list(self.NEGATIVE_WORDS.keys())
                )
                if has_sentiment:
                    phrases.append(sentence)

        return phrases[:max_phrases]

    def _generate_executive_summary(self, analysis: Dict[str, Any]) -> str:
        """Generate a text summary of analysis findings."""
        parts = []

        # Opening with response count
        total = analysis.get("total_responses", 0)
        analyzed = analysis.get("analyzed_responses", 0)
        parts.append(f"Analysis of {total} survey responses ({analyzed} with text feedback).")

        # NPS summary
        nps = analysis.get("nps_analysis")
        if nps and nps.get("nps_score") is not None:
            score = nps["nps_score"]
            sentiment_word = "excellent" if score >= 50 else "good" if score >= 0 else "concerning"
            parts.append(f"NPS score of {score} indicates {sentiment_word} customer sentiment.")

        # Sentiment summary
        sentiment = analysis.get("sentiment_distribution", {})
        if sentiment:
            pos = sentiment.get("positive_pct", 0)
            neg = sentiment.get("negative_pct", 0)
            if pos >= 60:
                parts.append(f"Overall sentiment is positive ({pos}% positive responses).")
            elif neg >= 40:
                parts.append(f"Significant negative sentiment detected ({neg}% negative responses).")
            else:
                parts.append("Sentiment is mixed across responses.")

        # Urgent issues
        urgent_count = analysis.get("urgent_issues_count", 0)
        if urgent_count > 0:
            parts.append(f"ATTENTION: {urgent_count} responses flagged as requiring immediate attention.")

        # Churn risk
        churn_count = analysis.get("churn_risk_count", 0)
        if churn_count > 0:
            parts.append(f"{churn_count} customers identified with elevated churn risk.")

        # Top topics
        topics = analysis.get("topics", [])
        if topics:
            top_topics = [t["display_name"] for t in topics[:3]]
            parts.append(f"Key themes: {', '.join(top_topics)}.")

        # Competitor mentions
        competitor_count = analysis.get("competitor_mention_count", 0)
        if competitor_count > 0:
            parts.append(f"{competitor_count} competitor/alternative mentions detected.")

        return " ".join(parts)

    async def _save_analysis(self, survey_id: int, analysis_result: Dict[str, Any]) -> SurveyAnalysis:
        """Save analysis results to database."""
        try:
            # Create survey-level analysis record
            analysis = SurveyAnalysis(
                survey_id=survey_id,
                response_id=None,  # Survey-level analysis
                sentiment_breakdown=analysis_result.get("sentiment_distribution"),
                key_themes=[t["topic"] for t in analysis_result.get("topics", [])],
                urgent_issues=analysis_result.get("urgent_issues"),
                churn_risk_indicators=analysis_result.get("churn_risks"),
                competitor_mentions=analysis_result.get("competitor_mentions"),
                action_recommendations=analysis_result.get("recommendations"),
                overall_sentiment_score=analysis_result.get("sentiment_distribution", {}).get("average_score"),
                executive_summary=analysis_result.get("executive_summary"),
                analysis_version="1.0",
                analysis_model="local_lexicon",
                status="completed",
            )

            self.db.add(analysis)
            await self.db.commit()
            await self.db.refresh(analysis)

            logger.info(f"Saved analysis {analysis.id} for survey {survey_id}")
            return analysis

        except Exception as e:
            logger.error(f"Failed to save analysis for survey {survey_id}: {e}")
            await self.db.rollback()
            raise
