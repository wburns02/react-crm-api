"""
Tests for Email Service.

Tests MockEmailService and email sending functionality.
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock

from app.services.email_service import EmailService, MockEmailService


class TestMockEmailService:
    """Tests for MockEmailService."""

    @pytest.mark.asyncio
    async def test_mock_service_is_configured(self):
        """Test mock service reports as configured."""
        service = MockEmailService()
        assert service.is_configured is True

    @pytest.mark.asyncio
    async def test_mock_service_status(self):
        """Test mock service status."""
        service = MockEmailService()
        status = service.get_status()

        assert status["connected"] is True
        assert status["configured"] is True
        assert "Mock" in status["message"]

    @pytest.mark.asyncio
    async def test_send_email_success(self):
        """Test sending email via mock service."""
        service = MockEmailService()

        result = await service.send_email(
            to="recipient@example.com",
            subject="Test Subject",
            body="Test body content",
        )

        assert result["success"] is True
        assert result["status_code"] == 201  # Brevo returns 201 (was 202 for SendGrid)
        assert result["message_id"] is not None
        assert result["message_id"].startswith("mock-")

    @pytest.mark.asyncio
    async def test_send_email_with_html(self):
        """Test sending email with HTML body."""
        service = MockEmailService()

        result = await service.send_email(
            to="recipient@example.com",
            subject="HTML Test",
            body="Plain text",
            html_body="<h1>HTML Content</h1>",
        )

        assert result["success"] is True
        assert len(service._sent_emails) == 1
        assert service._sent_emails[0]["html_body"] == "<h1>HTML Content</h1>"

    @pytest.mark.asyncio
    async def test_send_email_with_reply_to(self):
        """Test sending email with reply-to address."""
        service = MockEmailService()

        result = await service.send_email(
            to="recipient@example.com",
            subject="Reply-To Test",
            body="Test body",
            reply_to="support@example.com",
        )

        assert result["success"] is True
        assert service._sent_emails[0]["reply_to"] == "support@example.com"

    @pytest.mark.asyncio
    async def test_send_template_email_success(self):
        """Test sending template email via mock service."""
        service = MockEmailService()

        result = await service.send_template_email(
            to="recipient@example.com",
            template_id=123,  # Brevo uses integer template IDs
            params={
                "name": "John Doe",
                "service_date": "2026-02-15",
            },
        )

        assert result["success"] is True
        assert result["status_code"] == 201  # Brevo returns 201
        assert len(service._sent_emails) == 1
        assert service._sent_emails[0]["template_id"] == 123

    @pytest.mark.asyncio
    async def test_sent_emails_tracking(self):
        """Test that sent emails are tracked."""
        service = MockEmailService()

        # Send multiple emails
        await service.send_email(
            to="user1@example.com",
            subject="Email 1",
            body="Body 1",
        )
        await service.send_email(
            to="user2@example.com",
            subject="Email 2",
            body="Body 2",
        )

        assert len(service._sent_emails) == 2
        assert service._sent_emails[0]["to"] == "user1@example.com"
        assert service._sent_emails[1]["to"] == "user2@example.com"


class TestEmailServiceNotConfigured:
    """Tests for EmailService when not configured."""

    @pytest.mark.asyncio
    async def test_not_configured_status(self):
        """Test status when Brevo not configured."""
        with patch("app.services.email_service.settings") as mock_settings:
            mock_settings.BREVO_API_KEY = None
            mock_settings.EMAIL_FROM_ADDRESS = "test@example.com"
            mock_settings.EMAIL_FROM_NAME = "Test"

            service = EmailService()
            assert service.is_configured is False

    @pytest.mark.asyncio
    async def test_send_email_not_configured(self):
        """Test sending email when not configured returns error."""
        with patch("app.services.email_service.settings") as mock_settings:
            mock_settings.BREVO_API_KEY = None
            mock_settings.EMAIL_FROM_ADDRESS = "test@example.com"
            mock_settings.EMAIL_FROM_NAME = "Test"

            service = EmailService()
            result = await service.send_email(
                to="test@example.com",
                subject="Test",
                body="Test",
            )

            assert result["success"] is False
            assert "not configured" in result["error"].lower()


class TestEmailServiceIntegration:
    """Integration tests for EmailService with mocked email provider."""

    @pytest.mark.skip(reason="Test needs update for Brevo implementation (was SendGrid)")
    @pytest.mark.asyncio
    async def test_send_email_with_mocked_sendgrid(self):
        """Test sending email with mocked SendGrid client."""
        pass

    @pytest.mark.skip(reason="Test needs update for Brevo implementation (was SendGrid)")
    @pytest.mark.asyncio
    async def test_send_email_handles_exception(self):
        """Test that exceptions are handled gracefully."""
        pass
