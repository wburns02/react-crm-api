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
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import json
import traceback
import os

from app.config import settings

logger = logging.getLogger(__name__)


class AIGatewayConfig(BaseModel):
    """Configuration for AI gateway connection."""
    base_url: str = "https://localhost-0.tailad2d5f.ts.net/ollama"  # ML workstation via Tailscale
    api_key: Optional[str] = None  # API key for authentication (not needed for Ollama)
    timeout: float = 120.0  # LLM inference can take time
    max_retries: int = 3
    # Ollama model names
    default_model: str = "llama3.1:8b"  # Fast model for quick tasks
    heavy_model: str = "llama3.1:70b"   # Large model for complex analysis
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
            api_key=getattr(settings, 'AI_SERVER_API_KEY', None),
            base_url=getattr(settings, 'OLLAMA_BASE_URL', 'https://localhost-0.tailad2d5f.ts.net/ollama')
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

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        use_heavy_model: bool = False,
    ) -> Dict[str, Any]:
        """Generate chat completion using local LLM.

        Args:
            messages: List of {role, content} messages
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)
            system_prompt: Optional system prompt to prepend
            use_heavy_model: Use the larger 70B model for complex analysis

        Returns:
            Dict with 'content' key containing generated text
        """
        try:
            client = await self.get_client()

            # Prepend system prompt if provided
            if system_prompt:
                messages = [{"role": "system", "content": system_prompt}] + messages

            # Select model based on task complexity
            model = self.config.heavy_model if use_heavy_model else self.config.default_model

            payload = {
                "model": model,  # Ollama model name
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
            }

            response = await client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()

            data = response.json()
            logger.info(f"LLM response keys: {data.keys()}")
            
            # Handle different response formats
            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                if "message" in choice:
                    content = choice["message"].get("content", "")
                elif "text" in choice:
                    content = choice["text"]
                else:
                    content = str(choice)
            elif "response" in data:
                content = data["response"]
            elif "content" in data:
                content = data["content"]
            else:
                logger.warning(f"Unexpected LLM response format: {data}")
                content = str(data)
            
            return {
                "content": content,
                "usage": data.get("usage", {}),
                "model": data.get("model", self.config.default_model),
            }
        except (httpx.ConnectError, httpx.HTTPStatusError) as conn_err:
            logger.warning(f"Local AI unavailable ({conn_err}), trying OpenAI fallback...")
            return await self._openai_fallback(messages, max_tokens, temperature, system_prompt)
        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            logger.error(traceback.format_exc())
            # Try fallback on any error
            return await self._openai_fallback(messages, max_tokens, temperature, system_prompt)

    async def _openai_fallback(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fallback to OpenAI when local AI is unavailable."""
        openai_key = getattr(settings, 'OPENAI_API_KEY', None) or os.getenv('OPENAI_API_KEY')

        if not openai_key:
            logger.error("No OpenAI API key configured for fallback")
            return {
                "content": "[AI server unavailable and no cloud fallback configured]",
                "error": "no_fallback_available",
            }

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
                    }
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
        """Transcribe audio using Whisper.

        Args:
            audio_url: URL to audio file
            language: Language code

        Returns:
            Dict with 'text' key containing transcription
        """
        try:
            client = await self.get_client()

            payload = {
                "audio_url": audio_url,
                "language": language,
            }

            response = await client.post("/v1/audio/transcriptions", json=payload)
            response.raise_for_status()

            data = response.json()
            return {
                "text": data.get("text", ""),
                "language": language,
                "duration": data.get("duration"),
            }
        except httpx.ConnectError:
            logger.warning("AI server unavailable for transcription")
            return {"text": "", "error": "connection_failed"}
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
            max_tokens=max_length * 2,  # Rough estimate
            temperature=0.3,  # Lower temp for summarization
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
            messages=[{
                "role": "user",
                "content": f"""Analyze the sentiment of this text. Respond with JSON only:
{{"sentiment": "positive|negative|neutral", "score": 0.0-1.0, "reason": "brief explanation"}}

Text: {text}"""
            }],
            max_tokens=100,
            temperature=0.1,
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


# Singleton instance
ai_gateway = AIGateway()


async def get_ai_gateway() -> AIGateway:
    """Dependency injection for AI gateway."""
    return ai_gateway
