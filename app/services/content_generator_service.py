"""Content Generator Service - World-Class AI Content Orchestration.

Orchestrates AI content generation across multiple providers:
- Local Ollama (qwen2.5:7b, llama3.1:70b)
- OpenAI (gpt-4o, gpt-4o-mini)
- Anthropic (claude-3.5-sonnet)

Features:
- Auto model selection based on availability and task complexity
- Multi-variant generation for A/B testing
- SEO and readability analysis
- Septic industry-specific prompts
"""

import httpx
import logging
import os
import re
import time
import uuid
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from app.config import settings
from app.services.ai_gateway import ai_gateway
from app.schemas.content_generator import (
    AIModel, ContentType, ToneType, AudienceType,
    AIModelInfo, ContentIdea, GeneratedContent, ContentVariant,
    KeywordAnalysis,
)

logger = logging.getLogger(__name__)


# =============================================================================
# AI MODEL CONFIGURATION
# =============================================================================

AI_MODELS: Dict[str, AIModelInfo] = {
    AIModel.AUTO: AIModelInfo(
        id="auto",
        display_name="Auto (Recommended)",
        description="Automatically selects the best available model",
        provider="auto",
        speed="fast",
        quality="excellent",
        cost="medium",
        recommended_for=["all"],
    ),
    AIModel.OPENAI_GPT4O: AIModelInfo(
        id="openai/gpt-4o",
        display_name="OpenAI GPT-4o",
        description="Best quality, fast, great for all content types",
        provider="openai",
        speed="fast",
        quality="excellent",
        cost="medium",
        recommended_for=["blog", "service_description"],
    ),
    AIModel.OPENAI_GPT4O_MINI: AIModelInfo(
        id="openai/gpt-4o-mini",
        display_name="OpenAI GPT-4o Mini",
        description="Fast and affordable, good for shorter content",
        provider="openai",
        speed="fast",
        quality="great",
        cost="low",
        recommended_for=["faq", "gbp_post"],
    ),
    AIModel.ANTHROPIC_CLAUDE_SONNET: AIModelInfo(
        id="anthropic/claude-3.5-sonnet",
        display_name="Claude 3.5 Sonnet",
        description="Excellent writing quality, nuanced and natural tone",
        provider="anthropic",
        speed="medium",
        quality="excellent",
        cost="medium",
        recommended_for=["blog", "service_description"],
    ),
    AIModel.LOCAL_QWEN_7B: AIModelInfo(
        id="local/qwen2.5:7b",
        display_name="Local Fast (Qwen 7B)",
        description="Free, fast, runs on local GPU",
        provider="local",
        speed="fast",
        quality="good",
        cost="free",
        recommended_for=["faq", "gbp_post"],
    ),
    AIModel.LOCAL_LLAMA_70B: AIModelInfo(
        id="local/llama3.1:70b",
        display_name="Local Heavy (Llama 70B)",
        description="Free, high quality, slower (uses 70B model)",
        provider="local",
        speed="slow",
        quality="great",
        cost="free",
        recommended_for=["blog", "service_description"],
    ),
}


# =============================================================================
# SEPTIC INDUSTRY PROMPTS
# =============================================================================

INDUSTRY_CONTEXT = """You are a professional content writer for MAC Septic, a septic tank
services company serving East Texas (Nacogdoches, Lufkin, Angelina County area).

Key company facts:
- Family-owned business with decades of experience
- Services: septic pumping, repair, installation, grease trap cleaning, aerobic systems
- 24/7 emergency service available
- Licensed and insured technicians
- Serving residential and commercial customers

Regional considerations:
- East Texas soil conditions (sandy loam, clay in some areas)
- Hot, humid summers affecting bacteria activity
- Local regulations in Nacogdoches, Angelina, and Cherokee counties
- Rural properties often on well water and septic systems
"""

CONTENT_TYPE_PROMPTS = {
    ContentType.BLOG: """Write an engaging, informative blog post that:
- Educates readers about the topic
- Uses clear, accessible language (8th grade reading level)
- Includes practical tips and actionable advice
- Naturally incorporates the target keywords
- Has an attention-grabbing introduction
- Uses subheadings (##) to organize content
- Ends with a call-to-action encouraging readers to contact MAC Septic

Format: Use Markdown with proper heading hierarchy (##, ###).""",

    ContentType.FAQ: """Write a helpful FAQ answer that:
- Directly answers the question in the first sentence
- Provides additional context and details
- Uses bullet points for lists when appropriate
- Is concise but thorough (150-300 words ideal)
- Includes a soft call-to-action at the end

Format: Start with ## for the question, then the answer.""",

    ContentType.GBP_POST: """Write a Google Business Profile post that:
- Is attention-grabbing and concise (100-150 words max)
- Starts with an engaging hook or emoji
- Highlights a specific service or benefit
- Includes a clear call-to-action
- Uses relevant hashtags at the end (3-5 hashtags)

Format: Plain text with emojis, ends with hashtags.""",

    ContentType.SERVICE_DESCRIPTION: """Write a professional service page description that:
- Clearly explains what the service includes
- Highlights benefits for the customer
- Addresses common concerns or questions
- Builds trust and credibility
- Includes pricing context if appropriate (without specific numbers)
- Ends with a call-to-action

Format: Use Markdown with ## headings for sections.""",
}

TONE_INSTRUCTIONS = {
    ToneType.PROFESSIONAL: "Maintain a professional, knowledgeable tone that builds trust and authority.",
    ToneType.FRIENDLY: "Use a warm, approachable tone like talking to a neighbor.",
    ToneType.CASUAL: "Keep it relaxed and conversational, avoiding jargon.",
    ToneType.AUTHORITATIVE: "Write with expertise and confidence, establishing thought leadership.",
    ToneType.EDUCATIONAL: "Focus on teaching and explaining, breaking down complex concepts.",
}

AUDIENCE_INSTRUCTIONS = {
    AudienceType.HOMEOWNERS: "Write for homeowners who may not be familiar with septic systems.",
    AudienceType.BUSINESSES: "Address commercial property owners and managers.",
    AudienceType.PROPERTY_MANAGERS: "Focus on property management concerns like maintenance schedules and costs.",
    AudienceType.CONTRACTORS: "Write for construction and plumbing professionals.",
    AudienceType.GENERAL: "Write for a general audience with mixed knowledge levels.",
}


# =============================================================================
# CONTENT GENERATOR SERVICE
# =============================================================================

class ContentGeneratorService:
    """Service for AI-powered content generation."""

    def __init__(self):
        self._anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", None) or os.getenv("ANTHROPIC_API_KEY")
        self._openai_key = getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")

    async def check_model_availability(self) -> Dict[str, bool]:
        """Check which AI models are currently available."""
        availability = {
            "local": False,
            "openai": bool(self._openai_key),
            "anthropic": bool(self._anthropic_key),
        }

        # Check local Ollama
        try:
            health = await ai_gateway.health_check()
            availability["local"] = health.get("status") == "healthy"
        except Exception:
            pass

        return availability

    async def get_available_models(self) -> List[AIModelInfo]:
        """Get list of available models with current status."""
        availability = await self.check_model_availability()

        models = []
        for model_enum, info in AI_MODELS.items():
            model_info = info.model_copy()

            # Update availability based on provider
            if info.provider == "local":
                model_info.available = availability["local"]
            elif info.provider == "openai":
                model_info.available = availability["openai"]
            elif info.provider == "anthropic":
                model_info.available = availability["anthropic"]
            elif info.provider == "auto":
                model_info.available = any(availability.values())

            models.append(model_info)

        return models

    def select_best_model(
        self,
        requested: AIModel,
        availability: Dict[str, bool],
        content_type: Optional[ContentType] = None,
    ) -> Tuple[str, str]:
        """Select the best available model based on request and availability.

        Returns: (provider, model_id)
        """
        if requested != AIModel.AUTO:
            info = AI_MODELS.get(requested)
            if info and info.provider != "auto":
                # Check if requested model's provider is available
                if availability.get(info.provider, False):
                    return (info.provider, requested.value)
                # Fall through to auto selection

        # Auto selection priority
        # 1. Try local first (free)
        if availability.get("local"):
            if content_type in [ContentType.BLOG, ContentType.SERVICE_DESCRIPTION]:
                return ("local", "llama3.1:70b")  # Heavy model for long content
            return ("local", "qwen2.5:7b")  # Fast model for short content

        # 2. Try Anthropic (excellent quality)
        if availability.get("anthropic"):
            return ("anthropic", "claude-3-5-sonnet-20241022")

        # 3. Fall back to OpenAI
        if availability.get("openai"):
            if content_type in [ContentType.FAQ, ContentType.GBP_POST]:
                return ("openai", "gpt-4o-mini")
            return ("openai", "gpt-4o")

        # No models available
        return ("demo", "demo")

    async def _call_anthropic(
        self,
        messages: List[Dict[str, str]],
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call Anthropic Claude API."""
        if not self._anthropic_key:
            return {"content": "", "error": "anthropic_not_configured"}

        try:
            # Build request
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
            }

            if system_prompt:
                payload["system"] = system_prompt

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self._anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                # Extract content from response
                content = ""
                if "content" in data and len(data["content"]) > 0:
                    content = data["content"][0].get("text", "")

                return {
                    "content": content,
                    "model": model,
                    "usage": data.get("usage", {}),
                }
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return {"content": "", "error": str(e)}

    async def _call_openai(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call OpenAI API."""
        if not self._openai_key:
            return {"content": "", "error": "openai_not_configured"}

        try:
            # Prepend system prompt if provided
            full_messages = messages.copy()
            if system_prompt:
                full_messages = [{"role": "system", "content": system_prompt}] + full_messages

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": full_messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
                response.raise_for_status()
                data = response.json()

                content = data["choices"][0]["message"]["content"]
                return {
                    "content": content,
                    "model": model,
                    "usage": data.get("usage", {}),
                }
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {"content": "", "error": str(e)}

    async def _call_local(
        self,
        messages: List[Dict[str, str]],
        model: str = "qwen2.5:7b",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call local Ollama via AI Gateway."""
        use_heavy = model in ["llama3.1:70b", "local/llama3.1:70b"]
        return await ai_gateway.chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
            use_heavy_model=use_heavy,
        )

    async def generate_content(
        self,
        content_type: ContentType,
        topic: str,
        tone: ToneType = ToneType.PROFESSIONAL,
        audience: AudienceType = AudienceType.HOMEOWNERS,
        target_keywords: List[str] = None,
        word_count: int = 500,
        model: AIModel = AIModel.AUTO,
        include_cta: bool = True,
        include_meta: bool = True,
    ) -> Tuple[GeneratedContent, bool]:
        """Generate content using AI.

        Returns: (GeneratedContent, is_demo_mode)
        """
        start_time = time.time()
        target_keywords = target_keywords or []

        # Check model availability
        availability = await self.check_model_availability()
        provider, model_id = self.select_best_model(model, availability, content_type)

        if provider == "demo":
            # Return demo content
            return self._generate_demo_content(content_type, topic, tone), True

        # Build the prompt
        system_prompt = self._build_system_prompt(content_type, tone, audience)
        user_prompt = self._build_user_prompt(
            content_type, topic, target_keywords, word_count, include_cta, include_meta
        )

        # Call the appropriate provider
        messages = [{"role": "user", "content": user_prompt}]

        if provider == "anthropic":
            result = await self._call_anthropic(
                messages, model=model_id, system_prompt=system_prompt
            )
        elif provider == "openai":
            result = await self._call_openai(
                messages, model=model_id, system_prompt=system_prompt
            )
        else:  # local
            result = await self._call_local(
                messages, model=model_id, system_prompt=system_prompt
            )

        if result.get("error"):
            logger.warning(f"AI error: {result['error']}, falling back to demo")
            return self._generate_demo_content(content_type, topic, tone), True

        content_text = result.get("content", "")
        generation_time = int((time.time() - start_time) * 1000)

        # Parse title from content
        title = self._extract_title(content_text, topic)

        # Parse meta description if included
        meta_description = None
        if include_meta:
            meta_description = self._extract_meta_description(content_text)

        # Count words
        actual_word_count = len(content_text.split())

        return GeneratedContent(
            id=str(uuid.uuid4()),
            title=title,
            content=content_text,
            content_type=content_type,
            meta_description=meta_description,
            model_used=f"{provider}/{model_id}",
            generation_time_ms=generation_time,
            word_count=actual_word_count,
        ), False

    async def generate_ideas(
        self,
        keywords: List[str],
        content_type: Optional[ContentType] = None,
        audience: AudienceType = AudienceType.HOMEOWNERS,
        count: int = 5,
        seasonality: Optional[str] = None,
        model: AIModel = AIModel.AUTO,
    ) -> Tuple[List[ContentIdea], str, bool]:
        """Generate content ideas based on keywords.

        Returns: (ideas, model_used, is_demo_mode)
        """
        availability = await self.check_model_availability()
        provider, model_id = self.select_best_model(model, availability, None)

        if provider == "demo":
            return self._generate_demo_ideas(keywords, content_type, count), "demo", True

        # Build idea generation prompt
        system_prompt = f"""{INDUSTRY_CONTEXT}

You are a content strategist generating topic ideas for blog posts, FAQs, and social media.
Generate creative, engaging content ideas that will resonate with {audience.value}.
"""

        type_instruction = ""
        if content_type:
            type_instruction = f"\nFocus specifically on ideas for: {content_type.value}"

        season_instruction = ""
        if seasonality:
            season_instruction = f"\nConsider seasonal relevance for: {seasonality}"

        user_prompt = f"""Generate {count} content ideas based on these keywords: {', '.join(keywords)}
{type_instruction}{season_instruction}

For each idea, provide:
1. A compelling topic/title
2. A brief description (1-2 sentences)
3. The best content type (blog, faq, gbp_post, or service_description)
4. Relevant keywords to target (3-5)
5. Estimated word count
6. Difficulty level (easy, medium, hard)
7. An attention-grabbing opening hook

Format your response as JSON array:
[
  {{
    "topic": "...",
    "description": "...",
    "suggested_type": "blog|faq|gbp_post|service_description",
    "keywords": ["...", "..."],
    "estimated_word_count": 500,
    "difficulty": "easy|medium|hard",
    "hook": "..."
  }}
]

Return ONLY the JSON array, no other text."""

        messages = [{"role": "user", "content": user_prompt}]

        if provider == "anthropic":
            result = await self._call_anthropic(messages, model=model_id, system_prompt=system_prompt)
        elif provider == "openai":
            result = await self._call_openai(messages, model=model_id, system_prompt=system_prompt)
        else:
            result = await self._call_local(messages, model=model_id, system_prompt=system_prompt)

        if result.get("error"):
            return self._generate_demo_ideas(keywords, content_type, count), "demo", True

        # Parse JSON response
        try:
            import json
            content = result.get("content", "[]")
            # Clean up markdown code blocks if present
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            ideas_data = json.loads(content.strip())

            ideas = []
            for i, idea in enumerate(ideas_data[:count]):
                ideas.append(ContentIdea(
                    id=str(uuid.uuid4()),
                    topic=idea.get("topic", f"Idea {i+1}"),
                    description=idea.get("description", ""),
                    suggested_type=ContentType(idea.get("suggested_type", "blog")),
                    keywords=idea.get("keywords", keywords[:3]),
                    estimated_word_count=idea.get("estimated_word_count", 500),
                    difficulty=idea.get("difficulty", "medium"),
                    seasonality=seasonality,
                    hook=idea.get("hook", ""),
                ))

            return ideas, f"{provider}/{model_id}", False
        except Exception as e:
            logger.error(f"Failed to parse ideas: {e}")
            return self._generate_demo_ideas(keywords, content_type, count), "demo", True

    async def generate_variants(
        self,
        content_type: ContentType,
        topic: str,
        tone: ToneType = ToneType.PROFESSIONAL,
        audience: AudienceType = AudienceType.HOMEOWNERS,
        target_keywords: List[str] = None,
        word_count: int = 500,
        model: AIModel = AIModel.AUTO,
        variant_count: int = 3,
        variation_style: str = "mixed",
    ) -> Tuple[str, List[ContentVariant], str, int, bool]:
        """Generate multiple content variants for A/B testing.

        Returns: (variant_group_id, variants, model_used, total_time_ms, is_demo_mode)
        """
        start_time = time.time()
        target_keywords = target_keywords or []
        variant_group_id = str(uuid.uuid4())

        availability = await self.check_model_availability()
        provider, model_id = self.select_best_model(model, availability, content_type)

        if provider == "demo":
            variants = self._generate_demo_variants(content_type, topic, variant_count)
            return variant_group_id, variants, "demo", 0, True

        variants = []
        variant_labels = ["A", "B", "C", "D", "E"]

        for i in range(variant_count):
            label = variant_labels[i] if i < len(variant_labels) else str(i + 1)

            # Vary the approach based on variation_style
            hook_style = self._get_hook_style(i, variation_style)

            system_prompt = self._build_system_prompt(content_type, tone, audience)
            user_prompt = self._build_variant_prompt(
                content_type, topic, target_keywords, word_count, hook_style, label
            )

            messages = [{"role": "user", "content": user_prompt}]

            if provider == "anthropic":
                result = await self._call_anthropic(messages, model=model_id, system_prompt=system_prompt)
            elif provider == "openai":
                result = await self._call_openai(messages, model=model_id, system_prompt=system_prompt)
            else:
                result = await self._call_local(messages, model=model_id, system_prompt=system_prompt)

            content_text = result.get("content", "")
            title = self._extract_title(content_text, f"{topic} - Variant {label}")

            variants.append(ContentVariant(
                variant_label=label,
                title=title,
                content=content_text,
                hook_style=hook_style,
            ))

        total_time = int((time.time() - start_time) * 1000)
        return variant_group_id, variants, f"{provider}/{model_id}", total_time, False

    def analyze_seo(
        self,
        content: str,
        target_keywords: List[str] = None,
    ) -> Dict[str, Any]:
        """Analyze content for SEO factors."""
        target_keywords = target_keywords or []
        content_lower = content.lower()
        words = content_lower.split()
        word_count = len(words)

        # Analyze each keyword
        keyword_analysis = []
        for keyword in target_keywords:
            kw_lower = keyword.lower()
            count = content_lower.count(kw_lower)
            density = (count / word_count * 100) if word_count > 0 else 0

            # Check positions
            first_para = content[:500].lower() if len(content) > 500 else content_lower
            headings_text = " ".join(re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)).lower()

            keyword_analysis.append(KeywordAnalysis(
                keyword=keyword,
                count=count,
                density=round(density, 2),
                in_title=kw_lower in content[:100].lower(),  # Approximate title check
                in_first_paragraph=kw_lower in first_para,
                in_headings=kw_lower in headings_text,
                optimal=1.0 <= density <= 3.0,
            ))

        # Find missing keywords
        missing = [kw for kw in target_keywords if kw.lower() not in content_lower]

        # Structure analysis
        headings = re.findall(r'^#+\s+.+$', content, re.MULTILINE)
        has_headings = len(headings) > 0

        # Calculate overall score
        score = 50  # Base score

        # Keyword presence: +30 max
        if target_keywords:
            found_ratio = (len(target_keywords) - len(missing)) / len(target_keywords)
            score += int(found_ratio * 20)

            # Optimal density bonus
            optimal_count = sum(1 for ka in keyword_analysis if ka.optimal)
            if target_keywords:
                score += int((optimal_count / len(target_keywords)) * 10)

        # Structure: +20 max
        if has_headings:
            score += 10
        if len(headings) >= 3:
            score += 5
        if word_count >= 300:
            score += 5

        # Generate suggestions
        suggestions = []
        if missing:
            suggestions.append(f"Add missing keywords: {', '.join(missing[:3])}")
        if not has_headings:
            suggestions.append("Add headings (## and ###) to improve structure")
        if word_count < 300:
            suggestions.append("Consider expanding content to at least 300 words")

        low_density = [ka for ka in keyword_analysis if ka.density < 1.0 and ka.count > 0]
        if low_density:
            suggestions.append(f"Increase usage of: {', '.join(ka.keyword for ka in low_density[:2])}")

        return {
            "overall_score": min(100, score),
            "keyword_analysis": keyword_analysis,
            "missing_keywords": missing,
            "has_headings": has_headings,
            "heading_count": len(headings),
            "suggestions": suggestions,
        }

    def analyze_readability(self, content: str) -> Dict[str, Any]:
        """Analyze content readability using Flesch-Kincaid metrics."""
        # Clean content
        text = re.sub(r'[#*`_\[\]()]', '', content)  # Remove markdown
        text = re.sub(r'\s+', ' ', text).strip()

        # Count sentences
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_count = len(sentences) or 1

        # Count words
        words = text.split()
        word_count = len(words) or 1

        # Count syllables (simplified estimation)
        def count_syllables(word: str) -> int:
            word = word.lower()
            vowels = "aeiou"
            count = 0
            prev_vowel = False
            for char in word:
                is_vowel = char in vowels
                if is_vowel and not prev_vowel:
                    count += 1
                prev_vowel = is_vowel
            # Handle silent e
            if word.endswith('e') and count > 1:
                count -= 1
            return max(1, count)

        syllable_count = sum(count_syllables(w) for w in words)

        # Calculate metrics
        avg_words_per_sentence = word_count / sentence_count
        avg_syllables_per_word = syllable_count / word_count

        # Flesch Reading Ease: 206.835 - 1.015*(words/sentences) - 84.6*(syllables/words)
        flesch_reading_ease = 206.835 - (1.015 * avg_words_per_sentence) - (84.6 * avg_syllables_per_word)
        flesch_reading_ease = max(0, min(100, flesch_reading_ease))

        # Flesch-Kincaid Grade: 0.39*(words/sentences) + 11.8*(syllables/words) - 15.59
        flesch_kincaid_grade = (0.39 * avg_words_per_sentence) + (11.8 * avg_syllables_per_word) - 15.59
        flesch_kincaid_grade = max(0, flesch_kincaid_grade)

        # Interpret reading level
        if flesch_reading_ease >= 90:
            reading_level = "very_easy"
            target_audience = "5th graders and below"
        elif flesch_reading_ease >= 80:
            reading_level = "easy"
            target_audience = "6th graders"
        elif flesch_reading_ease >= 70:
            reading_level = "fairly_easy"
            target_audience = "7th graders"
        elif flesch_reading_ease >= 60:
            reading_level = "standard"
            target_audience = "8th-9th graders (general public)"
        elif flesch_reading_ease >= 50:
            reading_level = "fairly_difficult"
            target_audience = "High school students"
        elif flesch_reading_ease >= 30:
            reading_level = "difficult"
            target_audience = "College students"
        else:
            reading_level = "very_difficult"
            target_audience = "College graduates"

        # Generate suggestions
        suggestions = []
        if avg_words_per_sentence > 20:
            suggestions.append("Try shorter sentences (aim for 15-20 words average)")
        if avg_syllables_per_word > 1.5:
            suggestions.append("Use simpler words with fewer syllables")
        if flesch_kincaid_grade > 12:
            suggestions.append("Content may be too complex for general audience")
        if reading_level in ["very_easy", "easy"]:
            suggestions.append("Great readability! Accessible to most readers.")

        return {
            "flesch_reading_ease": round(flesch_reading_ease, 1),
            "flesch_kincaid_grade": round(flesch_kincaid_grade, 1),
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_words_per_sentence": round(avg_words_per_sentence, 1),
            "avg_syllables_per_word": round(avg_syllables_per_word, 2),
            "reading_level": reading_level,
            "target_audience": target_audience,
            "suggestions": suggestions,
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _build_system_prompt(
        self,
        content_type: ContentType,
        tone: ToneType,
        audience: AudienceType,
    ) -> str:
        """Build the system prompt for content generation."""
        return f"""{INDUSTRY_CONTEXT}

{CONTENT_TYPE_PROMPTS.get(content_type, CONTENT_TYPE_PROMPTS[ContentType.BLOG])}

{TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS[ToneType.PROFESSIONAL])}

{AUDIENCE_INSTRUCTIONS.get(audience, AUDIENCE_INSTRUCTIONS[AudienceType.HOMEOWNERS])}
"""

    def _build_user_prompt(
        self,
        content_type: ContentType,
        topic: str,
        target_keywords: List[str],
        word_count: int,
        include_cta: bool,
        include_meta: bool,
    ) -> str:
        """Build the user prompt for content generation."""
        keywords_instruction = ""
        if target_keywords:
            keywords_instruction = f"\nTarget keywords to include naturally: {', '.join(target_keywords)}"

        cta_instruction = ""
        if include_cta:
            cta_instruction = "\nInclude a call-to-action encouraging readers to contact MAC Septic."

        meta_instruction = ""
        if include_meta:
            meta_instruction = "\n\nAt the end, add a line: META_DESCRIPTION: [150-160 character description for search results]"

        return f"""Write a {content_type.value} about: {topic}

Target length: approximately {word_count} words{keywords_instruction}{cta_instruction}{meta_instruction}

Begin the content now:"""

    def _build_variant_prompt(
        self,
        content_type: ContentType,
        topic: str,
        target_keywords: List[str],
        word_count: int,
        hook_style: str,
        variant_label: str,
    ) -> str:
        """Build prompt for variant generation."""
        keywords_instruction = ""
        if target_keywords:
            keywords_instruction = f"\nTarget keywords: {', '.join(target_keywords)}"

        return f"""Write a {content_type.value} about: {topic}

This is Variant {variant_label}. Use this opening style: {hook_style}

Target length: approximately {word_count} words{keywords_instruction}

Begin the content now:"""

    def _get_hook_style(self, variant_index: int, variation_style: str) -> str:
        """Get the hook style for a variant."""
        hook_styles = {
            "tone": ["Professional and authoritative", "Friendly and conversational", "Direct and action-oriented"],
            "structure": ["Start with a question", "Start with a statistic or fact", "Start with a story or scenario"],
            "hook": ["Problem-solution approach", "Benefit-focused opening", "Curiosity-driven hook"],
            "mixed": [
                "Start with a common problem homeowners face",
                "Open with a surprising fact or statistic",
                "Begin with a relatable scenario or question",
                "Lead with the main benefit or solution",
                "Use a direct, action-oriented approach",
            ],
        }

        styles = hook_styles.get(variation_style, hook_styles["mixed"])
        return styles[variant_index % len(styles)]

    def _extract_title(self, content: str, fallback: str) -> str:
        """Extract title from content."""
        # Look for # heading
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()

        # Look for first line if it's short enough
        first_line = content.split('\n')[0].strip()
        if len(first_line) < 100 and not first_line.startswith('#'):
            return first_line

        return fallback

    def _extract_meta_description(self, content: str) -> Optional[str]:
        """Extract meta description from content."""
        match = re.search(r'META_DESCRIPTION:\s*(.+?)(?:\n|$)', content, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:160]
        return None

    def _generate_demo_content(
        self,
        content_type: ContentType,
        topic: str,
        tone: ToneType,
    ) -> GeneratedContent:
        """Generate demo content when AI is unavailable."""
        demo_contents = {
            ContentType.BLOG: f"""# {topic.title()}: What Every Homeowner Should Know

Regular maintenance of your {topic.lower()} is crucial for keeping your home running smoothly. Here's what you need to know.

## Why {topic.title()} Matters

Understanding {topic.lower()} helps you avoid costly repairs and emergencies. Most homeowners don't realize how important regular attention is until something goes wrong.

## Top Tips for Success

1. **Schedule Regular Inspections** - Don't wait for problems to appear
2. **Know the Warning Signs** - Slow drains, odors, and wet spots need attention
3. **Work with Professionals** - DIY isn't always the best approach

## When to Call the Experts

If you notice any issues, don't hesitate to reach out. Early intervention saves money and prevents headaches.

*Need help with {topic.lower()}? Contact MAC Septic today for a free consultation!*

META_DESCRIPTION: Learn essential {topic.lower()} tips from MAC Septic's experts. Discover maintenance best practices and when to call a professional.""",

            ContentType.FAQ: f"""## {topic.title()}?

The answer depends on several factors specific to your situation. Generally speaking, most experts recommend addressing {topic.lower()} proactively rather than waiting for issues to develop.

**Key considerations:**
- Your property's specific needs
- Local regulations and requirements
- Seasonal factors

For personalized advice, contact our team for a free assessment.""",

            ContentType.GBP_POST: f"""🏠 **{topic.title()}**

Taking care of your {topic.lower()} doesn't have to be complicated! Our expert team is here to help.

✅ Professional service
✅ Fair pricing
✅ Fast response times

📞 Call today for your free estimate!

#SepticService #EastTexas #{topic.replace(' ', '')}""",

            ContentType.SERVICE_DESCRIPTION: f"""## {topic.title()} Services

Our professional {topic.lower()} services keep your property running smoothly.

### What We Offer

- Comprehensive inspections
- Expert repairs and maintenance
- 24/7 emergency service

### Why Choose MAC Septic

- Family-owned business
- Licensed and insured technicians
- Competitive pricing

*Contact us today to learn more about our {topic.lower()} services!*""",
        }

        content = demo_contents.get(content_type, demo_contents[ContentType.BLOG])

        return GeneratedContent(
            id=str(uuid.uuid4()),
            title=f"{topic.title()}: What Every Homeowner Should Know",
            content=content,
            content_type=content_type,
            meta_description=f"Learn about {topic.lower()} from MAC Septic's experts.",
            model_used="demo",
            generation_time_ms=100,
            word_count=len(content.split()),
        )

    def _generate_demo_ideas(
        self,
        keywords: List[str],
        content_type: Optional[ContentType],
        count: int,
    ) -> List[ContentIdea]:
        """Generate demo ideas when AI is unavailable."""
        base_ideas = [
            ("5 Signs You Need Professional Help", "Early warning signs that indicate it's time to call an expert", ContentType.BLOG, "hard", "Did you know that 60% of homeowners miss these critical warning signs?"),
            ("Common Questions Answered", "A quick guide to the most frequently asked questions", ContentType.FAQ, "easy", "We hear this question almost every day..."),
            ("Seasonal Maintenance Tips", "What you need to know as the seasons change", ContentType.GBP_POST, "easy", "🌡️ The weather is changing - is your system ready?"),
            ("The Complete Guide", "Everything homeowners need to know in one place", ContentType.BLOG, "hard", "This comprehensive guide will save you thousands of dollars."),
            ("Cost Breakdown: What to Expect", "Transparent pricing information for informed decisions", ContentType.SERVICE_DESCRIPTION, "medium", "Understanding costs helps you budget and avoid surprises."),
        ]

        ideas = []
        for i, (title_template, desc, suggested_type, difficulty, hook) in enumerate(base_ideas[:count]):
            if content_type and suggested_type != content_type:
                suggested_type = content_type

            topic = f"{keywords[0].title() if keywords else 'Your System'} - {title_template}"

            ideas.append(ContentIdea(
                id=str(uuid.uuid4()),
                topic=topic,
                description=desc,
                suggested_type=suggested_type,
                keywords=keywords[:3] if keywords else ["maintenance", "service"],
                estimated_word_count=500 if suggested_type == ContentType.BLOG else 200,
                difficulty=difficulty,
                hook=hook,
            ))

        return ideas

    def _generate_demo_variants(
        self,
        content_type: ContentType,
        topic: str,
        count: int,
    ) -> List[ContentVariant]:
        """Generate demo variants when AI is unavailable."""
        hooks = [
            ("Question hook", f"Have you ever wondered about {topic.lower()}?"),
            ("Problem hook", f"If you're struggling with {topic.lower()}, you're not alone."),
            ("Benefit hook", f"Save time and money with proper {topic.lower()} management."),
        ]

        variants = []
        labels = ["A", "B", "C", "D", "E"]

        for i in range(min(count, len(hooks))):
            hook_style, opening = hooks[i]
            label = labels[i]

            content = f"""# {topic.title()} - Approach {label}

{opening}

This is demo content for Variant {label}. In production, this would be unique AI-generated content using a different approach.

## Key Points

- Point 1: Important information
- Point 2: Helpful tips
- Point 3: Expert advice

*Contact MAC Septic today!*"""

            variants.append(ContentVariant(
                variant_label=label,
                title=f"{topic.title()} - Approach {label}",
                content=content,
                hook_style=hook_style,
            ))

        return variants


# Singleton instance
content_generator_service = ContentGeneratorService()


async def get_content_generator() -> ContentGeneratorService:
    """Dependency injection for content generator service."""
    return content_generator_service
