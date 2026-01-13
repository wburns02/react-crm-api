"""
API endpoints for local AI service (R730 ML Workstation).
Provides health checks, testing, and configuration management.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List
import logging
import base64

from app.config import settings
from app.services.local_ai_service import local_ai_service, LocalAIError

logger = logging.getLogger(__name__)
router = APIRouter()


class AnalysisRequest(BaseModel):
    """Request model for transcript analysis."""
    transcript: str
    call_metadata: Optional[dict] = None


class TranscriptionRequest(BaseModel):
    """Request model for audio transcription."""
    audio_url: str
    language: str = "en"


class DispositionRequest(BaseModel):
    """Request model for disposition suggestion."""
    transcript: str
    available_dispositions: List[str]


@router.get("/health")
async def local_ai_health():
    """
    Check health of local AI services on R730.
    Returns status of Ollama and Whisper services.
    """
    try:
        health = await local_ai_service.health_check()
        return {
            "status": "healthy" if health["ollama"] else "degraded",
            "use_local_ai": settings.USE_LOCAL_AI,
            "services": health,
            "config": {
                "ollama_url": settings.OLLAMA_BASE_URL,
                "ollama_model": settings.OLLAMA_MODEL,
                "whisper_url": settings.WHISPER_BASE_URL,
                "whisper_model": settings.LOCAL_WHISPER_MODEL
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "use_local_ai": settings.USE_LOCAL_AI
        }


@router.post("/analyze")
async def analyze_transcript(request: AnalysisRequest):
    """
    Analyze a call transcript using local Ollama LLM.

    Returns comprehensive analysis including sentiment, quality scores,
    disposition suggestion, and coaching insights.
    """
    if not settings.USE_LOCAL_AI:
        raise HTTPException(
            status_code=400,
            detail="Local AI is disabled. Set USE_LOCAL_AI=true in config."
        )

    try:
        result = await local_ai_service.analyze_call_transcript(
            transcript=request.transcript,
            call_metadata=request.call_metadata
        )
        return result
    except LocalAIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/transcribe")
async def transcribe_audio(request: TranscriptionRequest):
    """
    Transcribe audio from URL using local Whisper on R730.

    Returns full transcript with segment-level timestamps.
    """
    if not settings.USE_LOCAL_AI:
        raise HTTPException(
            status_code=400,
            detail="Local AI is disabled. Set USE_LOCAL_AI=true in config."
        )

    try:
        result = await local_ai_service.transcribe_audio(
            audio_url=request.audio_url,
            language=request.language
        )
        return result
    except LocalAIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@router.post("/suggest-disposition")
async def suggest_disposition(request: DispositionRequest):
    """
    Get AI-suggested disposition for a call transcript.

    Returns the suggested disposition from available options with confidence score.
    """
    if not settings.USE_LOCAL_AI:
        raise HTTPException(
            status_code=400,
            detail="Local AI is disabled. Set USE_LOCAL_AI=true in config."
        )

    try:
        result = await local_ai_service.suggest_disposition(
            transcript=request.transcript,
            available_dispositions=request.available_dispositions
        )
        return result
    except LocalAIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Disposition suggestion error: {e}")
        raise HTTPException(status_code=500, detail=f"Suggestion failed: {str(e)}")


@router.post("/summarize")
async def summarize_call(transcript: str):
    """
    Generate a brief summary of a call transcript.
    """
    if not settings.USE_LOCAL_AI:
        raise HTTPException(
            status_code=400,
            detail="Local AI is disabled. Set USE_LOCAL_AI=true in config."
        )

    try:
        summary = await local_ai_service.generate_call_summary(transcript)
        return {"summary": summary}
    except Exception as e:
        logger.error(f"Summary error: {e}")
        raise HTTPException(status_code=500, detail=f"Summary failed: {str(e)}")


@router.get("/config")
async def get_local_ai_config():
    """
    Get current local AI configuration.
    """
    return {
        "use_local_ai": settings.USE_LOCAL_AI,
        "ollama": {
            "base_url": settings.OLLAMA_BASE_URL,
            "model": settings.OLLAMA_MODEL
        },
        "whisper": {
            "base_url": settings.WHISPER_BASE_URL,
            "model": settings.LOCAL_WHISPER_MODEL
        },
        "vision": {
            "model": settings.LLAVA_MODEL,
            "capabilities": ["photo_analysis", "ocr", "document_extraction"]
        },
        "heavy_processing": {
            "url": settings.HCTG_AI_URL,
            "model": settings.HCTG_AI_MODEL
        },
        "fallback_to_openai": not settings.USE_LOCAL_AI,
        "openai_model": settings.GPT_ANALYSIS_MODEL if not settings.USE_LOCAL_AI else None
    }


# ===== VISION / OCR ENDPOINTS =====

class ImageAnalysisRequest(BaseModel):
    """Request model for image analysis."""
    image_base64: str
    prompt: Optional[str] = None
    context: Optional[str] = None


class WorkOrderPhotoRequest(BaseModel):
    """Request model for work order photo analysis."""
    image_base64: str
    work_order_type: str = "septic"


class DocumentExtractionRequest(BaseModel):
    """Request model for document OCR extraction."""
    image_base64: str
    document_type: str = "service_record"


@router.post("/vision/analyze")
async def analyze_image(request: ImageAnalysisRequest):
    """
    Analyze an image using LLaVA vision model.

    Send a base64-encoded image and get AI analysis of the contents.
    Ideal for work order photos, equipment inspection, etc.
    """
    if not settings.USE_LOCAL_AI:
        raise HTTPException(
            status_code=400,
            detail="Local AI is disabled. Set USE_LOCAL_AI=true in config."
        )

    try:
        result = await local_ai_service.analyze_image(
            image_base64=request.image_base64,
            prompt=request.prompt,
            context=request.context
        )
        return result
    except LocalAIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/vision/analyze-photo")
async def analyze_work_order_photo(request: WorkOrderPhotoRequest):
    """
    Analyze a work order photo with structured output.

    Returns equipment identified, issues detected, condition rating,
    and recommendations in a structured JSON format.
    """
    if not settings.USE_LOCAL_AI:
        raise HTTPException(
            status_code=400,
            detail="Local AI is disabled. Set USE_LOCAL_AI=true in config."
        )

    try:
        result = await local_ai_service.analyze_work_order_photo(
            image_base64=request.image_base64,
            work_order_type=request.work_order_type
        )
        return result
    except LocalAIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Photo analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/vision/upload-photo")
async def upload_and_analyze_photo(
    file: UploadFile = File(...),
    work_order_type: str = Form("septic")
):
    """
    Upload a photo file and analyze it with LLaVA.

    Accepts image files (JPEG, PNG) and returns structured analysis.
    """
    if not settings.USE_LOCAL_AI:
        raise HTTPException(
            status_code=400,
            detail="Local AI is disabled. Set USE_LOCAL_AI=true in config."
        )

    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        # Read and encode file
        contents = await file.read()
        image_base64 = base64.b64encode(contents).decode("utf-8")

        result = await local_ai_service.analyze_work_order_photo(
            image_base64=image_base64,
            work_order_type=work_order_type
        )
        result["filename"] = file.filename
        result["file_size_bytes"] = len(contents)
        return result
    except LocalAIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Photo upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/ocr/extract")
async def extract_document_data(request: DocumentExtractionRequest):
    """
    Extract structured data from a scanned document using LLaVA OCR.

    Supports service records, invoices, permits, inspections.
    Returns extracted text and structured data fields.
    """
    if not settings.USE_LOCAL_AI:
        raise HTTPException(
            status_code=400,
            detail="Local AI is disabled. Set USE_LOCAL_AI=true in config."
        )

    try:
        result = await local_ai_service.extract_document_data(
            image_base64=request.image_base64,
            document_type=request.document_type
        )
        return result
    except LocalAIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Document extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@router.post("/ocr/upload-document")
async def upload_and_extract_document(
    file: UploadFile = File(...),
    document_type: str = Form("service_record")
):
    """
    Upload a document (image or PDF page) and extract data.

    Returns raw text and structured fields (customer info, dates, amounts, etc.)
    """
    if not settings.USE_LOCAL_AI:
        raise HTTPException(
            status_code=400,
            detail="Local AI is disabled. Set USE_LOCAL_AI=true in config."
        )

    # Validate file type
    valid_types = ["image/jpeg", "image/png", "image/tiff", "application/pdf"]
    if file.content_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"File must be an image or PDF. Got: {file.content_type}"
        )

    try:
        contents = await file.read()
        image_base64 = base64.b64encode(contents).decode("utf-8")

        result = await local_ai_service.extract_document_data(
            image_base64=image_base64,
            document_type=document_type
        )
        result["filename"] = file.filename
        result["file_size_bytes"] = len(contents)
        return result
    except LocalAIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Document upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


# ===== HEAVY PROCESSING (HCTG-AI / 5090) =====

class HeavyAnalysisRequest(BaseModel):
    """Request model for heavy AI analysis using qwen2.5:32b."""
    prompt: str
    context: Optional[str] = None


@router.post("/heavy/analyze")
async def heavy_analysis(request: HeavyAnalysisRequest):
    """
    Perform heavy AI analysis using qwen2.5:32b on hctg-ai server.

    Use for complex reasoning, detailed analysis, or long-form generation.
    Routes to the RTX 5090 server with 32B parameter model.
    """
    if not settings.USE_LOCAL_AI:
        raise HTTPException(
            status_code=400,
            detail="Local AI is disabled. Set USE_LOCAL_AI=true in config."
        )

    try:
        result = await local_ai_service.heavy_analysis(
            prompt=request.prompt,
            context=request.context
        )
        return result
    except LocalAIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Heavy analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
