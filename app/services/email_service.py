"""Email Service - SendGrid integration for transactional emails.

Features:
- Send transactional emails via SendGrid
- HTML and plain text support
- Template support
- Delivery status tracking
"""

from app.config import settings
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Try to import sendgrid, but handle if not installed
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent

    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    logger.warning("SendGrid package not installed. Email sending disabled.")


class EmailService:
    """Service for sending emails via SendGrid API."""

    def __init__(self):
        self.api_key = settings.SENDGRID_API_KEY
        self.from_address = settings.EMAIL_FROM_ADDRESS
        self.from_name = settings.EMAIL_FROM_NAME

        if SENDGRID_AVAILABLE and self.api_key:
            self.client = SendGridAPIClient(api_key=self.api_key)
        else:
            self.client = None
            if not SENDGRID_AVAILABLE:
                logger.warning("SendGrid package not installed")
            elif not self.api_key:
                logger.warning("SendGrid API key not configured")

    @property
    def is_configured(self) -> bool:
        """Check if email service is properly configured."""
        return self.client is not None and bool(self.from_address)

    def get_status(self) -> Dict[str, Any]:
        """Get email service configuration status."""
        if not SENDGRID_AVAILABLE:
            return {
                "connected": False,
                "configured": False,
                "message": "SendGrid package not installed. Run: pip install sendgrid",
            }

        if not self.api_key:
            return {
                "connected": False,
                "configured": False,
                "message": "SendGrid API key not configured. Set SENDGRID_API_KEY environment variable.",
            }

        return {
            "connected": True,
            "configured": True,
            "from_address": self.from_address,
            "from_name": self.from_name,
            "message": "SendGrid email service configured",
        }

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an email via SendGrid.

        Args:
            to: Recipient email address
            subject: Email subject line
            body: Plain text body
            html_body: Optional HTML body (if not provided, plain text is used)
            reply_to: Optional reply-to address

        Returns:
            Dict with status_code, message_id, and success status
        """
        if not self.client:
            error_msg = "Email service not configured"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "status_code": None,
                "message_id": None,
            }

        try:
            from_email = Email(self.from_address, self.from_name)
            to_email = To(to)

            # Build message
            message = Mail(
                from_email=from_email,
                to_emails=to_email,
                subject=subject,
            )

            # Add plain text content
            message.add_content(Content("text/plain", body))

            # Add HTML content if provided
            if html_body:
                message.add_content(Content("text/html", html_body))

            # Add reply-to if provided
            if reply_to:
                message.reply_to = Email(reply_to)

            # Send email
            response = self.client.send(message)

            # Extract message ID from headers
            message_id = None
            if response.headers:
                message_id = response.headers.get("X-Message-Id")

            logger.info(
                f"Email sent successfully",
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

        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Failed to send email",
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
        template_id: str,
        dynamic_template_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send an email using a SendGrid dynamic template.

        Args:
            to: Recipient email address
            template_id: SendGrid template ID
            dynamic_template_data: Template variable substitutions

        Returns:
            Dict with status_code, message_id, and success status
        """
        if not self.client:
            error_msg = "Email service not configured"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "status_code": None,
                "message_id": None,
            }

        try:
            from_email = Email(self.from_address, self.from_name)
            to_email = To(to)

            message = Mail(
                from_email=from_email,
                to_emails=to_email,
            )
            message.template_id = template_id

            if dynamic_template_data:
                message.dynamic_template_data = dynamic_template_data

            response = self.client.send(message)

            message_id = None
            if response.headers:
                message_id = response.headers.get("X-Message-Id")

            logger.info(
                f"Template email sent successfully",
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

        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Failed to send template email",
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
        self.from_address = "test@example.com"
        self.from_name = "Test Sender"
        self.client = None
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
            "status_code": 202,
            "message_id": mock_message_id,
        }

    async def send_template_email(
        self,
        to: str,
        template_id: str,
        dynamic_template_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Mock sending a template email."""
        import uuid

        mock_message_id = f"mock-{uuid.uuid4().hex[:16]}"

        self._sent_emails.append(
            {
                "to": to,
                "template_id": template_id,
                "dynamic_template_data": dynamic_template_data,
                "message_id": mock_message_id,
            }
        )

        logger.info(f"Mock template email sent to {to}: template={template_id}")

        return {
            "success": True,
            "status_code": 202,
            "message_id": mock_message_id,
        }
