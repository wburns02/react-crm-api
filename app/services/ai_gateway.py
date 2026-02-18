"""AI Gateway Service - Connection to local GPU-powered AI server.

This service provides access to:
- LLM inference (Llama 3.1 via Ollama)
- Embeddings (nomic-embed-text)
- Speech-to-text (Whisper)
- Semantic search (pgvector)

The AI server runs on Dell PowerEdge R730 with 2x RTX 3090 (48GB VRAM)
and 768GB system RAM, running Ollama 0.13.5.

Falls back to OpenAI/Anthropic when local AI is unreachable.
"""

import httpx
import logging
import time as _time
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import json
import traceback
import os
import uuid

from app.config import settings

logger = logging.getLogger(__name__)


class AIGatewayConfig(BaseModel):
    """Configuration for AI gateway connection."""

    base_url: str = "https://localhost-0.tailad2d5f.ts.net/ollama"  # ML workstation via Tailscale
    whisper_url: str = "https://localhost-0.tailad2d5f.ts.net/whisper"  # Whisper API via Tailscale
    api_key: Optional[str] = None  # API key for authentication (not needed for Ollama)
    timeout: float = 300.0  # 70B models need more time
    max_retries: int = 3
    # Ollama model names for R730 (2x RTX 3090, 48GB VRAM, 768GB RAM)
    default_model: str = "qwen2.5:7b"  # Fast model for quick tasks
    heavy_model: str = "llama3.1:70b"  # 70B model for complex analysis
    embed_model: str = "nomic-embed-text"  # Embedding model


class ChatMessage(BaseModel):
    """Chat message format."""

    role: str  # system, user, assistant
    content: str


class ChatRequest(BaseModel):
    """Request format for chat completion."""

    messages: List[ChatMessage]
    max_tokens: int = 1024
    temperature: float = 0.7
    stream: bool = False


class EmbeddingRequest(BaseModel):
    """Request format for embeddings."""

    texts: List[str]
    model: str = "embed"


class TranscribeRequest(BaseModel):
    """Request format for audio transcription."""

    audio_url: str  # URL to audio file
    language: Optional[str] = "en"


class AIGateway:
    """Gateway to local AI server."""

    def __init__(self, config: Optional[AIGatewayConfig] = None):
        self.config = config or AIGatewayConfig(
            api_key=getattr(settings, "AI_SERVER_API_KEY", None),
            base_url=getattr(settings, "OLLAMA_BASE_URL", "https://localhost-0.tailad2d5f.ts.net/ollama"),
        )
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with auth headers."""
        if self._client is None or self._client.is_closed:
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                headers=headers,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def health_check(self) -> Dict[str, Any]:
        """Check if AI server is healthy."""
        try:
            client = await self.get_client()
            # Ollama uses /api/tags to list models, which confirms it's running
            response = await client.get("/api/tags")
            data = response.json()
            models = [m.get("name", m.get("model", "unknown")) for m in data.get("models", [])]
            return {
                "status": "healthy",
                "server": "ollama",
                "models": models,
                "base_url": self.config.base_url,
            }
        except httpx.ConnectError:
            return {"status": "unavailable", "error": "Cannot connect to AI server"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # --- Provider routing for configurable AI providers ---

    _provider_cache: Dict[str, Any] = {}
    _provider_cache_time: float = 0
    _CACHE_TTL: float = 300.0  # 5 minutes

    async def _get_provider_config(self) -> Optional[Any]:
        """Get cached provider config from DB. Returns AIProviderConfig or None."""
        now = _time.time()
        if now - self._provider_cache_time < self._CACHE_TTL and "config" in self._provider_cache:
            return self._provider_cache.get("config")

        try:
            from app.database import async_session_maker
            from app.models.ai_provider_config import AIProviderConfig
            from sqlalchemy import select

            async with async_session_maker() as db:
                result = await db.execute(
                    select(AIProviderConfig).where(
                        AIProviderConfig.provider == "anthropic",
                        AIProviderConfig.is_active == True,
                        AIProviderConfig.is_primary == True,
                    )
                )
                config = result.scalar_one_or_none()
                self._provider_cache["config"] = config
                self._provider_cache_time = now
                return config
        except Exception as e:
            logger.debug(f"Provider config lookup failed: {e}")
            return None

    def invalidate_provider_cache(self):
        """Clear the provider config cache (call after connect/disconnect)."""
        self._provider_cache.clear()
        self._provider_cache_time = 0

    async def _should_use_claude(self, feature: str = "chat") -> bool:
        """Check if Claude should be used for a given feature."""
        config = await self._get_provider_config()
        if not config or not config.api_key_encrypted:
            return False
        features = config.feature_config or {}
        return features.get(feature, False)

    async def _claude_primary(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        feature: str = "chat",
    ) -> Dict[str, Any]:
        """Route request through Claude as primary provider."""
        from app.services.encryption import decrypt_value

        config = await self._get_provider_config()
        if not config or not config.api_key_encrypted:
            logger.warning("Claude primary called but no config, falling back to Ollama")
            return await self._ollama_chat(messages, max_tokens, temperature, system_prompt)

        api_key = decrypt_value(config.api_key_encrypted)
        if not api_key:
            # Try env var fallback
            api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
        if not api_key:
            logger.warning("Claude API key decrypt failed, falling back to Ollama")
            return await self._ollama_chat(messages, max_tokens, temperature, system_prompt)

        model = (config.model_config_data or {}).get("default_model", "claude-sonnet-4-6")

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system_prompt:
            payload["system"] = system_prompt

        start = _time.time()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                content = ""
                if "content" in data and len(data["content"]) > 0:
                    content = data["content"][0].get("text", "")

                usage = data.get("usage", {})
                duration_ms = int((_time.time() - start) * 1000)

                logger.info(f"Claude primary response: model={model}, tokens={usage}, {duration_ms}ms")

                # Log usage asynchronously
                await self._log_usage("anthropic", model, feature, usage, duration_ms)

                # Update last_used_at
                try:
                    from app.database import async_session_maker
                    from app.models.ai_provider_config import AIProviderConfig
                    from sqlalchemy import select
                    from datetime import datetime, timezone

                    async with async_session_maker() as db:
                        result = await db.execute(
                            select(AIProviderConfig).where(AIProviderConfig.provider == "anthropic")
                        )
                        cfg = result.scalar_one_or_none()
                        if cfg:
                            cfg.last_used_at = datetime.now(timezone.utc)
                            await db.commit()
                except Exception:
                    pass  # Non-critical

                return {
                    "content": content,
                    "usage": usage,
                    "model": model,
                }
        except Exception as e:
            duration_ms = int((_time.time() - start) * 1000)
            logger.warning(f"Claude primary failed ({e}), falling back to Ollama")
            await self._log_usage("anthropic", model, feature, {}, duration_ms, success=False, error=str(e))
            return await self._ollama_chat(messages, max_tokens, temperature, system_prompt)

    async def _log_usage(
        self,
        provider: str,
        model: str,
        feature: str,
        usage: dict,
        duration_ms: int,
        success: bool = True,
        error: Optional[str] = None,
    ):
        """Log AI usage to database. Fire-and-forget."""
        try:
            from app.database import async_session_maker
            from app.models.ai_provider_config import AIUsageLog

            prompt_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
            completion_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
            total = prompt_tokens + completion_tokens

            # Sonnet: $3/MTok input, $15/MTok output
            cost_cents = int((prompt_tokens * 0.3 + completion_tokens * 1.5) / 100)

            async with async_session_maker() as db:
                log = AIUsageLog(
                    provider=provider,
                    model=model,
                    feature=feature,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total,
                    cost_cents=cost_cents,
                    request_duration_ms=duration_ms,
                    success=success,
                    error_message=error,
                )
                db.add(log)
                await db.commit()
        except Exception as e:
            logger.debug(f"Failed to log AI usage: {e}")

    async def _ollama_chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        use_heavy_model: bool = False,
    ) -> Dict[str, Any]:
        """Original Ollama chat logic (extracted for fallback)."""
        try:
            client = await self.get_client()
            if system_prompt:
                messages = [{"role": "system", "content": system_prompt}] + messages
            model = self.config.heavy_model if use_heavy_model else self.config.default_model
            logger.info(f"Attempting chat with model={model}, base_url={self.config.base_url}")
            payload = {"model": model, "messages": messages, "stream": False}
            try:
                response = await client.post("/v1/chat/completions", json=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError:
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                if "message" in choice:
                    content = choice["message"].get("content", "")
                elif "text" in choice:
                    content = choice["text"]
                else:
                    content = str(choice)
            elif "message" in data:
                content = data["message"].get("content", "")
            elif "response" in data:
                content = data["response"]
            elif "content" in data:
                content = data["content"]
            else:
                content = str(data)
            return {"content": content, "usage": data.get("usage", {}), "model": data.get("model", self.config.default_model)}
        except (httpx.ConnectError, httpx.HTTPStatusError) as conn_err:
            logger.warning(f"Local AI unavailable ({conn_err}), trying OpenAI fallback...")
            return await self._openai_fallback(messages, max_tokens, temperature, system_prompt)
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            return await self._openai_fallback(messages, max_tokens, temperature, system_prompt)

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        use_heavy_model: bool = False,
        feature: str = "chat",
    ) -> Dict[str, Any]:
        """Generate chat completion using configured AI provider.

        Routes through Claude when configured as primary for this feature,
        otherwise falls back to local Ollama -> OpenAI -> Anthropic fallback chain.
        """
        # Check if Claude is configured as primary for this feature
        if not use_heavy_model and await self._should_use_claude(feature):
            return await self._claude_primary(messages, max_tokens, temperature, system_prompt, feature)

        # Default: Ollama with OpenAI/Anthropic fallback chain
        return await self._ollama_chat(messages, max_tokens, temperature, system_prompt, use_heavy_model)

    async def _openai_fallback(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fallback to OpenAI when local AI is unavailable."""
        openai_key = getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")

        if not openai_key:
            # Try Anthropic as second fallback
            return await self._anthropic_fallback(messages, max_tokens, temperature, system_prompt)

        try:
            # Prepend system prompt if provided
            if system_prompt:
                messages = [{"role": "system", "content": system_prompt}] + messages

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",  # Fast and cheap
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
                response.raise_for_status()
                data = response.json()

                content = data["choices"][0]["message"]["content"]
                logger.info("Successfully used OpenAI fallback")

                return {
                    "content": content,
                    "usage": data.get("usage", {}),
                    "model": "gpt-4o-mini (fallback)",
                }
        except Exception as e:
            logger.error(f"OpenAI fallback error: {e}")
            # Try Anthropic as final fallback
            return await self._anthropic_fallback(messages, max_tokens, temperature, system_prompt)

    async def _anthropic_fallback(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fallback to Anthropic Claude when OpenAI is unavailable."""
        anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", None) or os.getenv("ANTHROPIC_API_KEY")

        if not anthropic_key:
            logger.error("No Anthropic API key configured for fallback")
            return {
                "content": "[AI server unavailable and no cloud fallback configured]",
                "error": "no_fallback_available",
            }

        try:
            # Build Anthropic request format — strip system role from messages
            # (Ollama fallback chain may prepend {"role": "system"} to messages,
            # but Anthropic requires system as a top-level parameter, not in messages)
            filtered_messages = [m for m in messages if m.get("role") != "system"]
            extracted_system = next(
                (m["content"] for m in messages if m.get("role") == "system"), None
            )
            effective_system = system_prompt or extracted_system

            payload: dict = {
                "model": "claude-sonnet-4-6",
                "max_tokens": max_tokens,
                "messages": filtered_messages,
            }

            if effective_system:
                payload["system"] = effective_system

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                # Extract content from Anthropic response
                content = ""
                if "content" in data and len(data["content"]) > 0:
                    content = data["content"][0].get("text", "")

                logger.info("Successfully used Anthropic fallback")

                return {
                    "content": content,
                    "usage": data.get("usage", {}),
                    "model": "claude-sonnet-4-6 (fallback)",
                }
        except Exception as e:
            logger.error(f"Anthropic fallback error: {e}")
            return {
                "content": f"[AI temporarily unavailable - {str(e)[:50]}]",
                "error": str(e),
            }

    async def generate_embeddings(
        self,
        texts: List[str],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate embeddings for texts.

        Args:
            texts: List of texts to embed
            model: Embedding model to use

        Returns:
            Dict with 'embeddings' key containing list of vectors
        """
        try:
            client = await self.get_client()
            embed_model = model or self.config.embed_model

            payload = {
                "input": texts,
                "model": embed_model,
            }

            response = await client.post("/v1/embeddings", json=payload)
            response.raise_for_status()

            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]

            return {
                "embeddings": embeddings,
                "model": embed_model,
                "dimensions": len(embeddings[0]) if embeddings else 0,
            }
        except httpx.ConnectError:
            logger.warning("AI server unavailable for embeddings")
            return {"embeddings": [], "error": "connection_failed"}
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return {"embeddings": [], "error": str(e)}

    async def transcribe_audio(
        self,
        audio_url: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Transcribe audio using Whisper API.

        Args:
            audio_url: URL to audio file (must be accessible by the Whisper server)
            language: Language code

        Returns:
            Dict with 'text' key containing transcription
        """
        try:
            # Use separate Whisper client (different from Ollama)
            async with httpx.AsyncClient(timeout=self.config.timeout) as whisper_client:
                logger.info(f"Transcribing audio from URL: {audio_url[:80]}...")

                # Use /transcribe_url endpoint with query parameters
                response = await whisper_client.post(
                    f"{self.config.whisper_url}/transcribe_url", params={"url": audio_url, "language": language}
                )
                response.raise_for_status()

                data = response.json()
                text = data.get("text", "")
                logger.info(f"Transcription complete, length: {len(text)} chars")
                return {
                    "text": text,
                    "language": data.get("language", language),
                    "duration": data.get("duration"),
                }
        except httpx.ConnectError as e:
            logger.warning(f"Whisper server unavailable: {e}")
            return {"text": "", "error": "connection_failed"}
        except httpx.HTTPStatusError as e:
            logger.error(f"Whisper API error: {e.response.status_code} - {e.response.text}")
            return {"text": "", "error": f"http_{e.response.status_code}"}
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {"text": "", "error": str(e)}

    async def transcribe_audio_bytes(
        self,
        audio_data: bytes,
        filename: str = "recording.mp3",
        language: str = "en",
    ) -> Dict[str, Any]:
        """Transcribe audio from raw bytes using Whisper API.

        Args:
            audio_data: Raw audio bytes
            filename: Filename to use in multipart upload
            language: Language code

        Returns:
            Dict with 'text' key containing transcription
        """
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as whisper_client:
                logger.info(f"Transcribing {len(audio_data)} bytes of audio...")

                # Use multipart file upload to /transcribe endpoint
                files = {"file": (filename, audio_data, "audio/mpeg")}
                response = await whisper_client.post(
                    f"{self.config.whisper_url}/transcribe", files=files, params={"language": language}
                )
                response.raise_for_status()

                data = response.json()
                text = data.get("text", "")
                logger.info(f"Transcription complete, length: {len(text)} chars")
                return {
                    "text": text,
                    "language": data.get("language", language),
                    "duration": data.get("duration"),
                }
        except httpx.ConnectError as e:
            logger.warning(f"Whisper server unavailable: {e}")
            return {"text": "", "error": "connection_failed"}
        except httpx.HTTPStatusError as e:
            logger.error(f"Whisper API error: {e.response.status_code} - {e.response.text}")
            return {"text": "", "error": f"http_{e.response.status_code}"}
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {"text": "", "error": str(e)}

    async def summarize_text(
        self,
        text: str,
        max_length: int = 200,
        style: str = "concise",
    ) -> Dict[str, Any]:
        """Summarize text using LLM.

        Args:
            text: Text to summarize
            max_length: Target summary length in words
            style: Summary style (concise, detailed, bullet_points)

        Returns:
            Dict with 'summary' key
        """
        style_prompts = {
            "concise": f"Summarize this in {max_length} words or less:",
            "detailed": f"Provide a detailed summary in about {max_length} words:",
            "bullet_points": "Summarize this as bullet points (max 5 points):",
        }

        prompt = style_prompts.get(style, style_prompts["concise"])

        result = await self.chat_completion(
            messages=[{"role": "user", "content": f"{prompt}\n\n{text}"}],
            max_tokens=max_length * 2,
            temperature=0.3,
            feature="summarization",
        )

        return {
            "summary": result.get("content", ""),
            "style": style,
            "error": result.get("error"),
        }

    async def analyze_sentiment(
        self,
        text: str,
    ) -> Dict[str, Any]:
        """Analyze sentiment of text.

        Returns:
            Dict with sentiment (positive/negative/neutral) and score
        """
        result = await self.chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze the sentiment of this text. Respond with JSON only:
{{"sentiment": "positive|negative|neutral", "score": 0.0-1.0, "reason": "brief explanation"}}

Text: {text}""",
                }
            ],
            max_tokens=100,
            temperature=0.1,
            feature="sentiment",
        )

        try:
            # Try to parse JSON from response
            content = result.get("content", "{}")
            # Handle markdown code blocks
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            sentiment_data = json.loads(content.strip())
            return sentiment_data
        except json.JSONDecodeError:
            return {
                "sentiment": "neutral",
                "score": 0.5,
                "reason": "Could not analyze",
                "error": "parse_failed",
            }

    async def analyze_call_quality(
        self,
        transcript: str,
        call_direction: str = "inbound",
        duration_seconds: int = 0,
    ) -> Dict[str, Any]:
        """Comprehensive call quality analysis using LLM.

        Analyzes a call transcript for:
        - Sentiment (-100 to +100)
        - Quality score (0-100)
        - CSAT prediction (1-5)
        - Escalation risk (low/medium/high/critical)
        - Quality breakdown scores
        - Topics discussed

        Args:
            transcript: Full call transcript text
            call_direction: inbound or outbound
            duration_seconds: Call duration for context

        Returns:
            Dict with all analysis metrics
        """
        analysis_prompt = f"""Analyze this customer service call transcript and provide detailed quality metrics.

Call Direction: {call_direction}
Duration: {duration_seconds} seconds

TRANSCRIPT:
{transcript}

Respond with ONLY valid JSON (no markdown, no explanation):
{{
    "sentiment": "positive" or "negative" or "neutral",
    "sentiment_score": number from -100 (very negative) to +100 (very positive),
    "quality_score": number 0-100 (overall call quality),
    "csat_prediction": number 1.0-5.0 (predicted customer satisfaction),
    "escalation_risk": "low" or "medium" or "high" or "critical",
    "professionalism_score": number 0-100,
    "empathy_score": number 0-100,
    "clarity_score": number 0-100,
    "resolution_score": number 0-100,
    "topics": ["topic1", "topic2", "topic3"],
    "summary": "2-3 sentence call summary"
}}

Scoring guidelines:
- sentiment_score: Base on customer emotion, frustration level, satisfaction expressed
- quality_score: Overall agent performance combining all factors
- csat_prediction: 1=very dissatisfied, 3=neutral, 5=very satisfied
- escalation_risk: "critical" if customer threatens to cancel/escalate, "high" if very frustrated
- professionalism_score: Agent's professional demeanor and language
- empathy_score: How well agent acknowledged customer feelings/concerns
- clarity_score: How clearly agent explained information/solutions
- resolution_score: How effectively the issue was resolved"""

        result = await self.chat_completion(
            messages=[{"role": "user", "content": analysis_prompt}],
            max_tokens=500,
            temperature=0.2,
            use_heavy_model=True,
            feature="call_analysis",
        )

        try:
            content = result.get("content", "{}")
            # Strip markdown code blocks if present
            if "```" in content:
                parts = content.split("```")
                for part in parts:
                    if part.strip().startswith("{"):
                        content = part.strip()
                        break
                    elif part.strip().startswith("json"):
                        content = part.strip()[4:].strip()
                        break

            analysis = json.loads(content.strip())

            # Validate and clamp values
            return {
                "sentiment": analysis.get("sentiment", "neutral"),
                "sentiment_score": max(-100, min(100, float(analysis.get("sentiment_score", 0)))),
                "quality_score": max(0, min(100, float(analysis.get("quality_score", 50)))),
                "csat_prediction": max(1.0, min(5.0, float(analysis.get("csat_prediction", 3.0)))),
                "escalation_risk": analysis.get("escalation_risk", "low")
                if analysis.get("escalation_risk") in ["low", "medium", "high", "critical"]
                else "low",
                "professionalism_score": max(0, min(100, float(analysis.get("professionalism_score", 50)))),
                "empathy_score": max(0, min(100, float(analysis.get("empathy_score", 50)))),
                "clarity_score": max(0, min(100, float(analysis.get("clarity_score", 50)))),
                "resolution_score": max(0, min(100, float(analysis.get("resolution_score", 50)))),
                "topics": analysis.get("topics", [])[:10],  # Limit to 10 topics
                "summary": analysis.get("summary", ""),
            }
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse call analysis: {e}")
            return {
                "sentiment": "neutral",
                "sentiment_score": 0,
                "quality_score": 50,
                "csat_prediction": 3.0,
                "escalation_risk": "low",
                "professionalism_score": 50,
                "empathy_score": 50,
                "clarity_score": 50,
                "resolution_score": 50,
                "topics": [],
                "summary": "",
                "error": "analysis_parse_failed",
            }


# Singleton instance
ai_gateway = AIGateway()


async def get_ai_gateway() -> AIGateway:
    """Dependency injection for AI gateway."""
    return ai_gateway
