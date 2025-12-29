"""
RingCentral integration stub endpoints.

Returns 'not configured' status when RingCentral is not set up.
This prevents frontend 404 errors while allowing the integration
to be implemented later.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def get_ringcentral_status():
    """
    Get RingCentral connection status.

    Returns a 'not configured' status since RingCentral integration
    is not yet implemented. The frontend handles this gracefully.
    """
    return {
        "connected": False,
        "configured": False,
        "message": "RingCentral integration not configured",
    }
