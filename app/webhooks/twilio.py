from fastapi import APIRouter, Request, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import logging

from app.database import async_session_maker
from app.models.message import Message, MessageStatus
from app.config import settings

logger = logging.getLogger(__name__)

twilio_router = APIRouter()


@twilio_router.post("/incoming")
async def handle_incoming_sms(request: Request):
    """
    Handle incoming SMS from Twilio.

    Routes messages based on source:
    - If message is a reply to a React-originated message → handle here
    - If message is a reply to a Legacy-originated message → forward to legacy backend
    """
    form_data = await request.form()

    message_sid = form_data.get("MessageSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    body = form_data.get("Body", "")

    logger.info(f"Incoming SMS: {message_sid} from {from_number}")

    # Try to find if this is a reply to an existing conversation
    async with async_session_maker() as db:
        # Look for recent messages to this phone number
        result = await db.execute(
            select(Message)
            .where(Message.to_address == from_number)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        last_message = result.scalar_one_or_none()

        if last_message and last_message.source == "react":
            # This is a reply to a React message - handle it
            logger.info(f"Handling React reply from {from_number}")

            # Create incoming message record
            incoming = Message(
                customer_id=last_message.customer_id,
                type="sms",
                direction="inbound",
                status=MessageStatus.received,
                to_address=to_number,
                from_address=from_number,
                content=body,
                twilio_sid=message_sid,
                source="react",
            )
            db.add(incoming)
            await db.commit()

            # Return TwiML response (empty = no auto-reply)
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml",
            )

        else:
            # Forward to legacy backend
            logger.info(f"Forwarding to legacy backend: {from_number}")
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{settings.LEGACY_BACKEND_URL}/twilio/incoming",
                        data=dict(form_data),
                        timeout=10.0,
                    )
                    return Response(
                        content=response.content,
                        status_code=response.status_code,
                        media_type=response.headers.get("content-type", "application/xml"),
                    )
            except httpx.RequestError as e:
                logger.error(f"Failed to forward to legacy: {e}")
                # Still return success to Twilio to prevent retries
                return Response(
                    content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                    media_type="application/xml",
                )


@twilio_router.post("/status")
async def handle_status_callback(request: Request):
    """
    Handle Twilio status callbacks.

    Updates message status when Twilio reports delivery status changes.
    """
    form_data = await request.form()

    message_sid = form_data.get("MessageSid")
    message_status = form_data.get("MessageStatus")
    error_code = form_data.get("ErrorCode")
    error_message = form_data.get("ErrorMessage")

    logger.info(f"Status callback: {message_sid} -> {message_status}")

    async with async_session_maker() as db:
        # Find the message
        result = await db.execute(
            select(Message).where(Message.twilio_sid == message_sid)
        )
        message = result.scalar_one_or_none()

        if message:
            # Only update if it's a React message
            if message.source == "react":
                # Map Twilio status to our status
                status_map = {
                    "queued": MessageStatus.queued,
                    "sending": MessageStatus.queued,
                    "sent": MessageStatus.sent,
                    "delivered": MessageStatus.delivered,
                    "undelivered": MessageStatus.failed,
                    "failed": MessageStatus.failed,
                }

                message.status = status_map.get(message_status, message.status)
                message.twilio_status = message_status

                if error_code:
                    message.error_code = error_code
                    message.error_message = error_message

                await db.commit()
                logger.info(f"Updated message {message.id} status to {message.status}")
            else:
                # Forward to legacy
                logger.info(f"Forwarding status to legacy for message {message_sid}")
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"{settings.LEGACY_BACKEND_URL}/twilio/status",
                            data=dict(form_data),
                            timeout=10.0,
                        )
                except httpx.RequestError as e:
                    logger.error(f"Failed to forward status to legacy: {e}")
        else:
            # Message not found in React DB - might be legacy
            logger.info(f"Message {message_sid} not found, forwarding to legacy")
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{settings.LEGACY_BACKEND_URL}/twilio/status",
                        data=dict(form_data),
                        timeout=10.0,
                    )
            except httpx.RequestError as e:
                logger.error(f"Failed to forward status to legacy: {e}")

    return {"status": "ok"}
