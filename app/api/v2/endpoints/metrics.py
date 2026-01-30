"""
Prometheus metrics endpoint.

Exposes application metrics in Prometheus text format for scraping.
"""

from fastapi import APIRouter, Response
from app.core.metrics import get_registry

router = APIRouter()


@router.get(
    "",
    summary="Prometheus metrics",
    description="Returns application metrics in Prometheus text exposition format",
    response_class=Response,
    responses={
        200: {
            "description": "Prometheus metrics",
            "content": {"text/plain": {"example": "# HELP http_requests_total Total HTTP requests\n..."}},
        }
    },
)
async def get_metrics():
    """
    Get Prometheus metrics.

    Returns metrics in Prometheus text exposition format for scraping
    by Prometheus server or compatible monitoring systems.
    """
    registry = get_registry()
    metrics_text = registry.format_prometheus()

    return Response(content=metrics_text, media_type="text/plain; version=0.0.4; charset=utf-8")
