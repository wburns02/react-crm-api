"""Email Service - Brevo (formerly Sendinblue) integration for transactional emails.

Features:
- Send transactional emails via Brevo API
- HTML and plain text support
- Template support
- Delivery status tracking
- No external SDK required (uses httpx)
"""

from app.config import settings
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)

# Brevo API endpoint
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class EmailService:
    """Service for sending emails via Brevo API."""

    def __init__(self):
        self.api_key = self._extract_api_key(settings.BREVO_API_KEY)
        self.from_address = settings.EMAIL_FROM_ADDRESS
        self.from_name = settings.EMAIL_FROM_NAME

    @staticmethod
    def _extract_api_key(raw_key: str | None) -> str | None:
        """Extract raw API key from potential base64 JSON wrapper."""
        if not raw_key:
            return None
        # If it starts with xkeysib-, it's already a raw key
        if raw_key.startswith("xkeysib-"):
            return raw_key
        # Try base64 decode (MCP-wrapped keys are base64 JSON)
        try:
            import base64
            import json
            decoded = base64.b64decode(raw_key + "==").decode()
            data = json.loads(decoded)
            if isinstance(data, dict) and "api_key" in data:
                return data["api_key"]
        except Exception:
            pass
        return raw_key

    @property
    def is_configured(self) -> bool:
        """Check if email service is properly configured."""
        return bool(self.api_key) and bool(self.from_address)

    def get_status(self) -> Dict[str, Any]:
        """Get email service configuration status."""
        if not self.api_key:
            return {
                "connected": False,
                "configured": False,
                "provider": "brevo",
                "message": "Brevo API key not configured. Set BREVO_API_KEY environment variable.",
            }

        return {
            "connected": True,
            "configured": True,
            "provider": "brevo",
            "from_address": self.from_address,
            "from_name": self.from_name,
            "message": "Brevo email service configured",
        }

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Send an email via Brevo API.

        Args:
            to: Recipient email address
            subject: Email subject line
            body: Plain text body
            html_body: Optional HTML body (if not provided, plain text wrapped in basic HTML)
            reply_to: Optional reply-to address
            attachments: Optional list of dicts with 'content' (base64) and 'name' (filename)

        Returns:
            Dict with status_code, message_id, and success status
        """
        if not self.api_key:
            error_msg = "Brevo API key not configured"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "status_code": None,
                "message_id": None,
            }

        # Build request payload
        payload = {
            "sender": {
                "name": self.from_name,
                "email": self.from_address,
            },
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        }

        # Add HTML content
        if html_body:
            payload["htmlContent"] = html_body
        else:
            # Wrap plain text in basic HTML
            payload["htmlContent"] = f"<html><body><p>{body.replace(chr(10), '<br>')}</p></body></html>"

        # Add reply-to if provided
        if reply_to:
            payload["replyTo"] = {"email": reply_to}

        # Add attachments (Brevo format: [{content: base64, name: filename}])
        if attachments:
            payload["attachment"] = attachments

        headers = {
            "accept": "application/json",
            "api-key": self.api_key,
            "content-type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    BREVO_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )

            if response.status_code in (200, 201):
                result = response.json()
                message_id = result.get("messageId")

                logger.info(
                    "Email sent successfully via Brevo",
                    extra={
                        "to": to,
                        "subject": subject[:50],
                        "status_code": response.status_code,
                        "message_id": message_id,
                    },
                )

                return {
                    "success": True,
                    "status_code": response.status_code,
                    "message_id": message_id,
                }
            else:
                error_detail = response.text
                logger.error(
                    "Brevo API error",
                    extra={
                        "status_code": response.status_code,
                        "error": error_detail,
                    },
                )
                return {
                    "success": False,
                    "error": f"Brevo API error: {error_detail}",
                    "status_code": response.status_code,
                    "message_id": None,
                }

        except httpx.TimeoutException:
            error_msg = "Brevo API request timed out"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "status_code": None,
                "message_id": None,
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Failed to send email via Brevo",
                extra={
                    "to": to,
                    "error": error_msg,
                },
            )
            return {
                "success": False,
                "error": error_msg,
                "status_code": None,
                "message_id": None,
            }

    async def send_template_email(
        self,
        to: str,
        template_id: int,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send an email using a Brevo template.

        Args:
            to: Recipient email address
            template_id: Brevo template ID (integer)
            params: Template variable substitutions

        Returns:
            Dict with status_code, message_id, and success status
        """
        if not self.api_key:
            error_msg = "Brevo API key not configured"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "status_code": None,
                "message_id": None,
            }

        payload = {
            "to": [{"email": to}],
            "templateId": template_id,
        }

        if params:
            payload["params"] = params

        headers = {
            "accept": "application/json",
            "api-key": self.api_key,
            "content-type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    BREVO_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )

            if response.status_code in (200, 201):
                result = response.json()
                message_id = result.get("messageId")

                logger.info(
                    "Template email sent successfully via Brevo",
                    extra={
                        "to": to,
                        "template_id": template_id,
                        "status_code": response.status_code,
                        "message_id": message_id,
                    },
                )

                return {
                    "success": True,
                    "status_code": response.status_code,
                    "message_id": message_id,
                }
            else:
                error_detail = response.text
                logger.error(
                    "Brevo API template error",
                    extra={
                        "status_code": response.status_code,
                        "error": error_detail,
                    },
                )
                return {
                    "success": False,
                    "error": f"Brevo API error: {error_detail}",
                    "status_code": response.status_code,
                    "message_id": None,
                }

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Failed to send template email via Brevo",
                extra={
                    "to": to,
                    "template_id": template_id,
                    "error": error_msg,
                },
            )
            return {
                "success": False,
                "error": error_msg,
                "status_code": None,
                "message_id": None,
            }


class MockEmailService(EmailService):
    """Mock email service for testing and development."""

    def __init__(self):
        self.api_key = "mock-key"
        self.from_address = "test@example.com"
        self.from_name = "Test Sender"
        self._sent_emails = []

    @property
    def is_configured(self) -> bool:
        """Mock service is always configured."""
        return True

    def get_status(self) -> Dict[str, Any]:
        """Mock status."""
        return {
            "connected": True,
            "configured": True,
            "provider": "mock",
            "from_address": self.from_address,
            "from_name": self.from_name,
            "message": "Mock email service (emails not actually sent)",
        }

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mock sending an email."""
        import uuid

        mock_message_id = f"mock-{uuid.uuid4().hex[:16]}"

        self._sent_emails.append(
            {
                "to": to,
                "subject": subject,
                "body": body,
                "html_body": html_body,
                "reply_to": reply_to,
                "message_id": mock_message_id,
            }
        )

        logger.info(f"Mock email sent to {to}: {subject}")

        return {
            "success": True,
            "status_code": 201,
            "message_id": mock_message_id,
        }

    async def send_template_email(
        self,
        to: str,
        template_id: int,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Mock sending a template email."""
        import uuid

        mock_message_id = f"mock-{uuid.uuid4().hex[:16]}"

        self._sent_emails.append(
            {
                "to": to,
                "template_id": template_id,
                "params": params,
                "message_id": mock_message_id,
            }
        )

        logger.info(f"Mock template email sent to {to}: template={template_id}")

        return {
            "success": True,
            "status_code": 201,
            "message_id": mock_message_id,
        }
