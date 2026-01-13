"""
Local AI service using Ollama on the R730 ML Workstation.
Provides transcription (via Whisper) and analysis (via LLaMA) without external API costs.
"""

import logging
import asyncio
import time
import json
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class LocalAIError(Exception):
    """Custom exception for local AI service errors."""
    pass


class LocalAIService:
    """
    Service for AI processing using local R730 ML Workstation.
    Uses Ollama for LLM analysis and local Whisper for transcription.
    """

    def __init__(self):
        """Initialize local AI service with R730 endpoints."""
        # R730 ML Workstation endpoints via Tailscale Funnel
        self.ollama_base_url = getattr(settings, 'OLLAMA_BASE_URL', 'https://localhost-0.tailad2d5f.ts.net/ollama')
        self.whisper_base_url = getattr(settings, 'WHISPER_BASE_URL', 'https://localhost-0.tailad2d5f.ts.net/whisper')
        self.model = getattr(settings, 'OLLAMA_MODEL', 'llama3.2:3b')
        self.whisper_model = getattr(settings, 'LOCAL_WHISPER_MODEL', 'medium')
        self.timeout = aiohttp.ClientTimeout(total=300)  # 5 minute timeout

        # Additional AI servers
        self.llava_model = getattr(settings, 'LLAVA_MODEL', 'llava:13b')
        self.hctg_ai_url = getattr(settings, 'HCTG_AI_URL', 'https://hctg-ai.tailad2d5f.ts.net')
        self.hctg_ai_model = getattr(settings, 'HCTG_AI_MODEL', 'qwen2.5:32b')

    async def health_check(self) -> Dict[str, Any]:
        """Check if local AI services are available."""
        results = {
            "ollama": False,
            "whisper": False,
            "ollama_models": [],
            "timestamp": datetime.utcnow().isoformat()
        }

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # Check Ollama
            try:
                async with session.get(f"{self.ollama_base_url}/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results["ollama"] = True
                        results["ollama_models"] = [m["name"] for m in data.get("models", [])]
            except Exception as e:
                logger.warning(f"Ollama health check failed: {e}")

            # Check Whisper API
            try:
                async with session.get(f"{self.whisper_base_url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results["whisper"] = True
                        results["whisper_info"] = data
            except Exception as e:
                logger.warning(f"Whisper health check failed: {e}")

        return results

    async def analyze_call_transcript(
        self,
        transcript: str,
        call_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze a call transcript using Ollama LLM.

        Args:
            transcript: The call transcript text
            call_metadata: Optional metadata about the call

        Returns:
            Dict with analysis results
        """
        start_time = time.time()

        # Build analysis prompt
        prompt = self._build_analysis_prompt(transcript, call_metadata)

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                }

                async with session.post(
                    f"{self.ollama_base_url}/api/generate",
                    json=payload
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise LocalAIError(f"Ollama request failed: {resp.status} - {error_text}")

                    result = await resp.json()
                    response_text = result.get("response", "")

                    # Parse JSON response
                    try:
                        analysis = json.loads(response_text)
                    except json.JSONDecodeError:
                        # If not valid JSON, wrap in structure
                        analysis = {
                            "raw_analysis": response_text,
                            "parse_error": True
                        }

                    processing_time = time.time() - start_time

                    return {
                        "status": "success",
                        "analysis": analysis,
                        "model": self.model,
                        "processing_time_seconds": processing_time,
                        "tokens": {
                            "prompt": result.get("prompt_eval_count", 0),
                            "response": result.get("eval_count", 0)
                        }
                    }

        except aiohttp.ClientError as e:
            logger.error(f"Ollama connection error: {e}")
            raise LocalAIError(f"Failed to connect to Ollama: {str(e)}")
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            raise LocalAIError(f"Analysis failed: {str(e)}")

    def _build_analysis_prompt(
        self,
        transcript: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build the analysis prompt for Ollama."""
        context = ""
        if metadata:
            context = f"""
Call Information:
- Direction: {metadata.get('direction', 'unknown')}
- Duration: {metadata.get('duration_seconds', 0)} seconds
- From: {metadata.get('from_number', 'unknown')}
- To: {metadata.get('to_number', 'unknown')}
"""

        return f"""You are a CRM call analysis assistant for an HVAC service company. Analyze the following call transcript and provide a structured JSON response.

{context}

Transcript:
{transcript}

Provide your analysis in the following JSON format:
{{
    "overall_sentiment": "positive" | "neutral" | "negative",
    "sentiment_score": <number from -100 to 100>,
    "sentiment_trajectory": "improving" | "stable" | "declining",
    "quality_scores": {{
        "professionalism": <0-100>,
        "empathy": <0-100>,
        "clarity": <0-100>,
        "resolution": <0-100>,
        "overall": <0-100>
    }},
    "escalation_risk": "low" | "medium" | "high",
    "escalation_factors": [<list of risk factors if any>],
    "key_topics": [<list of main topics discussed>],
    "action_items": [<list of follow-up actions needed>],
    "customer_intent": "<brief description of what customer wanted>",
    "call_outcome": "<brief description of call result>",
    "predicted_disposition": "<suggested call disposition category>",
    "disposition_confidence": <0-100>,
    "disposition_reasoning": [<list of reasons for disposition choice>],
    "coaching_insights": {{
        "strengths": [<what agent did well>],
        "improvements": [<areas for improvement>],
        "recommendations": [<specific coaching tips>]
    }},
    "summary": "<2-3 sentence summary of the call>"
}}

Respond ONLY with valid JSON, no additional text."""

    async def transcribe_audio(
        self,
        audio_url: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Transcribe audio using local Whisper on R730.

        Args:
            audio_url: URL to the audio file
            language: Language code (default: en)

        Returns:
            Dict with transcription results
        """
        start_time = time.time()

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Use the URL transcription endpoint
                params = {"url": audio_url, "language": language}

                async with session.post(
                    f"{self.whisper_base_url}/transcribe_url",
                    params=params
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise LocalAIError(f"Whisper request failed: {resp.status} - {error_text}")

                    result = await resp.json()
                    processing_time = time.time() - start_time

                    return {
                        "status": "success",
                        "text": result.get("text", ""),
                        "language": result.get("language", language),
                        "segments": result.get("segments", []),
                        "processing_time_seconds": processing_time,
                        "model": self.whisper_model
                    }

        except aiohttp.ClientError as e:
            logger.error(f"Whisper connection error: {e}")
            raise LocalAIError(f"Failed to connect to Whisper: {str(e)}")
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            raise LocalAIError(f"Transcription failed: {str(e)}")

    async def transcribe_audio_file(
        self,
        file_path: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Transcribe a local audio file using Whisper on R730.

        Args:
            file_path: Path to the audio file
            language: Language code (default: en)

        Returns:
            Dict with transcription results
        """
        start_time = time.time()

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Read file and upload
                with open(file_path, 'rb') as f:
                    data = aiohttp.FormData()
                    data.add_field('file', f, filename=file_path.split('/')[-1])
                    data.add_field('language', language)

                    async with session.post(
                        f"{self.whisper_base_url}/transcribe",
                        data=data
                    ) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            raise LocalAIError(f"Whisper request failed: {resp.status} - {error_text}")

                        result = await resp.json()
                        processing_time = time.time() - start_time

                        return {
                            "status": "success",
                            "text": result.get("text", ""),
                            "language": result.get("language", language),
                            "segments": result.get("segments", []),
                            "processing_time_seconds": processing_time,
                            "model": self.whisper_model
                        }

        except FileNotFoundError:
            raise LocalAIError(f"Audio file not found: {file_path}")
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            raise LocalAIError(f"Transcription failed: {str(e)}")

    async def transcribe_audio_base64(
        self,
        audio_base64: str,
        language: str = "en",
        filename: str = "recording.webm"
    ) -> Dict[str, Any]:
        """
        Transcribe audio from base64-encoded data using Whisper on R730.

        Args:
            audio_base64: Base64-encoded audio data
            language: Language code (default: en)
            filename: Original filename for content type detection

        Returns:
            Dict with transcription results including text and segments
        """
        import base64
        start_time = time.time()

        try:
            # Decode base64 to bytes
            audio_bytes = base64.b64decode(audio_base64)

            # Determine content type from filename
            ext = filename.split('.')[-1].lower() if '.' in filename else 'webm'
            content_types = {
                'wav': 'audio/wav',
                'mp3': 'audio/mpeg',
                'webm': 'audio/webm',
                'm4a': 'audio/mp4',
                'mp4': 'audio/mp4',
                'ogg': 'audio/ogg',
            }
            content_type = content_types.get(ext, 'audio/webm')

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Create form data with audio bytes
                data = aiohttp.FormData()
                data.add_field(
                    'file',
                    audio_bytes,
                    filename=filename,
                    content_type=content_type
                )
                data.add_field('language', language)

                async with session.post(
                    f"{self.whisper_base_url}/transcribe",
                    data=data
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise LocalAIError(f"Whisper request failed: {resp.status} - {error_text}")

                    result = await resp.json()
                    processing_time = time.time() - start_time

                    return {
                        "status": "success",
                        "transcript": result.get("text", ""),
                        "text": result.get("text", ""),  # Alias for compatibility
                        "language": result.get("language", language),
                        "segments": result.get("segments", []),
                        "duration_seconds": result.get("duration", 0),
                        "processing_time_seconds": processing_time,
                        "model_used": self.whisper_model
                    }

        except Exception as e:
            logger.error(f"Base64 transcription error: {e}")
            raise LocalAIError(f"Transcription failed: {str(e)}")

    async def generate_call_summary(self, transcript: str) -> str:
        """Generate a brief summary of a call transcript."""
        prompt = f"""Summarize this customer service call in 2-3 sentences:

{transcript}

Summary:"""

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                }

                async with session.post(
                    f"{self.ollama_base_url}/api/generate",
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("response", "").strip()
                    else:
                        return "Unable to generate summary"

        except Exception as e:
            logger.error(f"Summary generation error: {e}")
            return "Unable to generate summary"

    async def suggest_disposition(
        self,
        transcript: str,
        available_dispositions: List[str]
    ) -> Dict[str, Any]:
        """
        Suggest the best disposition for a call.

        Args:
            transcript: Call transcript
            available_dispositions: List of valid disposition options

        Returns:
            Dict with suggested disposition and confidence
        """
        dispositions_str = "\n".join(f"- {d}" for d in available_dispositions)

        prompt = f"""Based on this call transcript, select the most appropriate disposition from the list below.

Available Dispositions:
{dispositions_str}

Transcript:
{transcript}

Respond in JSON format:
{{
    "disposition": "<selected disposition from list>",
    "confidence": <0-100>,
    "reasoning": "<brief explanation>"
}}"""

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                }

                async with session.post(
                    f"{self.ollama_base_url}/api/generate",
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        try:
                            return json.loads(result.get("response", "{}"))
                        except json.JSONDecodeError:
                            return {
                                "disposition": None,
                                "confidence": 0,
                                "reasoning": "Failed to parse response"
                            }
                    else:
                        return {
                            "disposition": None,
                            "confidence": 0,
                            "reasoning": f"Request failed: {resp.status}"
                        }

        except Exception as e:
            logger.error(f"Disposition suggestion error: {e}")
            return {
                "disposition": None,
                "confidence": 0,
                "reasoning": str(e)
            }

    async def analyze_image(
        self,
        image_base64: str,
        prompt: str = "Describe this image in detail. If it's a septic system or plumbing equipment, identify any issues or equipment visible.",
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze an image using LLaVA vision model.

        Args:
            image_base64: Base64 encoded image
            prompt: Analysis prompt
            context: Optional context about the image

        Returns:
            Dict with analysis results
        """
        start_time = time.time()

        full_prompt = prompt
        if context:
            full_prompt = f"Context: {context}\n\n{prompt}"

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                payload = {
                    "model": self.llava_model,
                    "prompt": full_prompt,
                    "images": [image_base64],
                    "stream": False
                }

                async with session.post(
                    f"{self.ollama_base_url}/api/generate",
                    json=payload
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise LocalAIError(f"LLaVA request failed: {resp.status} - {error_text}")

                    result = await resp.json()
                    processing_time = time.time() - start_time

                    return {
                        "status": "success",
                        "analysis": result.get("response", ""),
                        "model": self.llava_model,
                        "processing_time_seconds": processing_time
                    }

        except aiohttp.ClientError as e:
            logger.error(f"LLaVA connection error: {e}")
            raise LocalAIError(f"Failed to connect to LLaVA: {str(e)}")
        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            raise LocalAIError(f"Image analysis failed: {str(e)}")

    async def analyze_work_order_photo(
        self,
        image_base64: str,
        work_order_type: str = "septic"
    ) -> Dict[str, Any]:
        """
        Analyze a work order photo for equipment issues and recommendations.

        Args:
            image_base64: Base64 encoded image
            work_order_type: Type of work (septic, hvac, plumbing)

        Returns:
            Structured analysis with issues, equipment, and recommendations
        """
        prompt = f"""Analyze this {work_order_type} service photo. Provide your analysis in JSON format:

{{
    "description": "Brief description of what's shown",
    "equipment_identified": ["list of equipment/components visible"],
    "issues_detected": ["list of any problems or concerns"],
    "condition_rating": "excellent/good/fair/poor/critical",
    "recommendations": ["list of recommended actions"],
    "urgency": "none/low/medium/high/emergency",
    "additional_notes": "any other relevant observations"
}}

Respond ONLY with valid JSON."""

        try:
            result = await self.analyze_image(image_base64, prompt)

            if result["status"] == "success":
                try:
                    analysis = json.loads(result["analysis"])
                    return {
                        "status": "success",
                        "structured_analysis": analysis,
                        "raw_response": result["analysis"],
                        "model": result["model"],
                        "processing_time_seconds": result["processing_time_seconds"]
                    }
                except json.JSONDecodeError:
                    return {
                        "status": "success",
                        "structured_analysis": None,
                        "raw_response": result["analysis"],
                        "model": result["model"],
                        "processing_time_seconds": result["processing_time_seconds"],
                        "parse_warning": "Response was not valid JSON"
                    }
            else:
                return result

        except Exception as e:
            logger.error(f"Work order photo analysis error: {e}")
            raise LocalAIError(f"Photo analysis failed: {str(e)}")

    async def extract_document_data(
        self,
        image_base64: str,
        document_type: str = "service_record"
    ) -> Dict[str, Any]:
        """
        Extract structured data from a scanned document using LLaVA OCR.

        Args:
            image_base64: Base64 encoded document image
            document_type: Type of document (service_record, invoice, permit, inspection)

        Returns:
            Extracted structured data
        """
        prompt = f"""This is a scanned {document_type} document. Extract all text and data visible.

Return your extraction in JSON format:
{{
    "raw_text": "All text visible in the document",
    "extracted_data": {{
        "customer_name": "extracted if found or null",
        "address": "extracted if found or null",
        "phone": "extracted if found or null",
        "email": "extracted if found or null",
        "date": "any dates found or null",
        "amount": "any dollar amounts found or null",
        "service_type": "type of service if mentioned or null",
        "tank_info": "septic tank details if found or null",
        "permit_number": "permit/license number if found or null",
        "technician": "technician name if found or null",
        "notes": "any handwritten or typed notes"
    }},
    "confidence": 0.95,
    "handwriting_detected": true,
    "document_quality": "good/fair/poor",
    "needs_review": false
}}

Extract as much information as possible. For handwritten text, do your best to interpret it.
Respond ONLY with valid JSON."""

        try:
            result = await self.analyze_image(image_base64, prompt)

            if result["status"] == "success":
                try:
                    extracted = json.loads(result["analysis"])
                    return {
                        "status": "success",
                        "extraction": extracted,
                        "model": result["model"],
                        "processing_time_seconds": result["processing_time_seconds"]
                    }
                except json.JSONDecodeError:
                    return {
                        "status": "partial",
                        "raw_text": result["analysis"],
                        "extraction": None,
                        "model": result["model"],
                        "processing_time_seconds": result["processing_time_seconds"],
                        "error": "Could not parse structured data"
                    }
            else:
                return result

        except Exception as e:
            logger.error(f"Document extraction error: {e}")
            raise LocalAIError(f"Document extraction failed: {str(e)}")

    async def heavy_analysis(
        self,
        prompt: str,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Use the heavy qwen2.5:32b model on hctg-ai for complex reasoning tasks.

        Args:
            prompt: The analysis prompt
            context: Optional additional context

        Returns:
            Analysis results from the 32B model
        """
        start_time = time.time()

        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nTask:\n{prompt}"

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                payload = {
                    "model": self.hctg_ai_model,
                    "prompt": full_prompt,
                    "stream": False
                }

                async with session.post(
                    f"{self.hctg_ai_url}/api/generate",
                    json=payload
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise LocalAIError(f"Heavy analysis request failed: {resp.status} - {error_text}")

                    result = await resp.json()
                    processing_time = time.time() - start_time

                    return {
                        "status": "success",
                        "response": result.get("response", ""),
                        "model": self.hctg_ai_model,
                        "server": "hctg-ai",
                        "processing_time_seconds": processing_time
                    }

        except aiohttp.ClientError as e:
            logger.error(f"Heavy analysis connection error: {e}")
            raise LocalAIError(f"Failed to connect to hctg-ai: {str(e)}")
        except Exception as e:
            logger.error(f"Heavy analysis error: {e}")
            raise LocalAIError(f"Heavy analysis failed: {str(e)}")


# Create singleton instance
local_ai_service = LocalAIService()
