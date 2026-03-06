"""
Live Chat API — stub endpoints for the frontend Live Chat page.

Returns empty/default data so the page loads without 404/500 errors.
Replace with real implementation when ready.
"""
from datetime import datetime
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


@router.get("/status")
async def chat_status():
    now = datetime.utcnow()
    hour = now.hour - 6  # rough CST
    online = 8 <= hour < 17
    return {
        "online": online,
        "hours": "8:00 AM - 5:00 PM",
        "days": "Monday - Friday",
        "message": "We're here to help!" if online else "We'll be back during business hours.",
        "current_time_cst": now.isoformat(),
    }


@router.get("/conversations")
async def list_conversations(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    raise HTTPException(status_code=404, detail="Conversation not found")


class ReplyRequest(BaseModel):
    content: str


@router.post("/conversations/{conversation_id}/reply")
async def reply_to_conversation(conversation_id: str, data: ReplyRequest):
    raise HTTPException(status_code=404, detail="Conversation not found")


@router.patch("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str):
    raise HTTPException(status_code=404, detail="Conversation not found")


@router.post("/conversations/{conversation_id}/mark-read")
async def mark_read(conversation_id: str):
    return {"ok": True}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    raise HTTPException(status_code=404, detail="Conversation not found")
