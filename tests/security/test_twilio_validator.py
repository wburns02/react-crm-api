"""
Tests for the Twilio webhook signature validator module.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from fastapi import HTTPException, Request

from app.security.twilio_validator import (
    TwilioSignatureValidator,
    validate_twilio_signature,
    twilio_webhook_validator,
)


class TestTwilioSignatureValidator:
    """Test TwilioSignatureValidator class."""

    def test_init_creates_none_validator(self):
        """Test that validator starts as None (lazy init)."""
        validator = TwilioSignatureValidator()
        assert validator._validator is None

    def test_validator_property_raises_without_auth_token(self):
        """Test ValueError raised when TWILIO_AUTH_TOKEN not configured."""
        validator = TwilioSignatureValidator()
        with patch("app.security.twilio_validator.settings") as mock_settings:
            mock_settings.TWILIO_AUTH_TOKEN = None
            with pytest.raises(ValueError) as exc:
                _ = validator.validator
            assert "TWILIO_AUTH_TOKEN not configured" in str(exc.value)

    def test_validator_property_creates_request_validator(self):
        """Test validator property creates RequestValidator with token."""
        validator = TwilioSignatureValidator()
        with patch("app.security.twilio_validator.settings") as mock_settings:
            mock_settings.TWILIO_AUTH_TOKEN = "test-token-12345"
            result = validator.validator
            assert result is not None
            # Should reuse the same validator on second access
            assert validator.validator is result


class TestGetFullUrl:
    """Test get_full_url method."""

    def _create_mock_request(self, headers=None, url_str="http://localhost/webhook",
                             path="/webhook", query=""):
        """Helper to create a properly mocked request."""
        mock_request = MagicMock()
        mock_request.headers = headers or {}
        mock_request.url = MagicMock()
        mock_request.url.path = path
        mock_request.url.query = query
        mock_request.url.__str__ = MagicMock(return_value=url_str)
        return mock_request

    def test_get_full_url_without_forwarded_headers(self):
        """Test URL is returned from request when no forwarded headers."""
        validator = TwilioSignatureValidator()
        mock_request = self._create_mock_request()

        result = validator.get_full_url(mock_request)
        assert result == "http://localhost/webhook"

    def test_get_full_url_with_forwarded_headers(self):
        """Test URL is built from forwarded headers when present."""
        validator = TwilioSignatureValidator()
        mock_request = self._create_mock_request(
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "api.example.com"
            },
            path="/sms/incoming",
            query=""
        )

        result = validator.get_full_url(mock_request)
        assert result == "https://api.example.com/sms/incoming"

    def test_get_full_url_with_forwarded_headers_and_query(self):
        """Test URL includes query string when present."""
        validator = TwilioSignatureValidator()
        mock_request = self._create_mock_request(
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "api.example.com"
            },
            path="/sms/incoming",
            query="foo=bar&baz=qux"
        )

        result = validator.get_full_url(mock_request)
        assert result == "https://api.example.com/sms/incoming?foo=bar&baz=qux"

    def test_get_full_url_partial_forwarded_headers(self):
        """Test fallback when only some forwarded headers present."""
        validator = TwilioSignatureValidator()
        mock_request = self._create_mock_request(
            headers={"x-forwarded-proto": "https"}  # Missing x-forwarded-host
        )

        result = validator.get_full_url(mock_request)
        assert result == "http://localhost/webhook"


class TestValidate:
    """Test validate method."""

    def _create_mock_request(self, signature="", path="/sms/incoming",
                             client_host="1.2.3.4", form_data=None):
        """Helper to create a properly mocked request for validate tests."""
        mock_request = MagicMock()

        # Create a headers dict-like object
        headers_dict = {"X-Twilio-Signature": signature}
        mock_request.headers = MagicMock()
        mock_request.headers.get = MagicMock(side_effect=lambda k, d="": headers_dict.get(k, d))

        mock_request.url = MagicMock()
        mock_request.url.path = path
        mock_request.url.query = ""
        mock_request.url.__str__ = MagicMock(return_value=f"http://localhost{path}")

        if client_host:
            mock_request.client = MagicMock()
            mock_request.client.host = client_host
        else:
            mock_request.client = None

        mock_request.form = AsyncMock(return_value=form_data or {})

        return mock_request

    @pytest.mark.asyncio
    async def test_validate_missing_signature_header(self):
        """Test HTTPException raised when signature header missing."""
        validator = TwilioSignatureValidator()
        mock_request = self._create_mock_request(signature="")

        with pytest.raises(HTTPException) as exc:
            await validator.validate(mock_request)
        assert exc.value.status_code == 403
        assert "Missing Twilio signature" in exc.value.detail

    @pytest.mark.asyncio
    async def test_validate_missing_signature_no_client(self):
        """Test handles missing client info gracefully."""
        validator = TwilioSignatureValidator()
        mock_request = self._create_mock_request(signature="", client_host=None)

        with pytest.raises(HTTPException) as exc:
            await validator.validate(mock_request)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_validate_invalid_signature(self):
        """Test HTTPException raised when signature is invalid."""
        validator = TwilioSignatureValidator()
        validator._validator = MagicMock()
        validator._validator.validate = MagicMock(return_value=False)

        mock_request = self._create_mock_request(
            signature="invalid-signature",
            form_data={"Body": "test message", "From": "+15551234567"}
        )

        with pytest.raises(HTTPException) as exc:
            await validator.validate(mock_request)
        assert exc.value.status_code == 403
        assert "Invalid Twilio signature" in exc.value.detail

    @pytest.mark.asyncio
    async def test_validate_valid_signature(self):
        """Test True returned when signature is valid."""
        validator = TwilioSignatureValidator()
        validator._validator = MagicMock()
        validator._validator.validate = MagicMock(return_value=True)

        mock_request = self._create_mock_request(
            signature="valid-signature",
            form_data={"Body": "test message"}
        )

        result = await validator.validate(mock_request)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_exception_during_validation(self):
        """Test HTTPException raised when validator throws exception."""
        validator = TwilioSignatureValidator()
        validator._validator = MagicMock()
        validator._validator.validate = MagicMock(side_effect=Exception("Validation error"))

        mock_request = self._create_mock_request(signature="some-signature")

        with pytest.raises(HTTPException) as exc:
            await validator.validate(mock_request)
        assert exc.value.status_code == 403
        assert "Signature validation error" in exc.value.detail


class TestValidateTwilioSignature:
    """Test validate_twilio_signature dependency function."""

    @pytest.mark.asyncio
    async def test_validate_twilio_signature_calls_validator(self):
        """Test the dependency function calls the global validator."""
        mock_request = MagicMock()
        headers_dict = {"X-Twilio-Signature": "valid-sig"}
        mock_request.headers = MagicMock()
        mock_request.headers.get = MagicMock(side_effect=lambda k, d="": headers_dict.get(k, d))
        mock_request.url = MagicMock()
        mock_request.url.path = "/test"
        mock_request.url.query = ""
        mock_request.url.__str__ = MagicMock(return_value="http://test/test")
        mock_request.form = AsyncMock(return_value={})
        mock_request.client = MagicMock()
        mock_request.client.host = "1.2.3.4"

        # Patch the global validator's internal validator
        with patch("app.security.twilio_validator._twilio_validator") as mock_global:
            mock_global.validate = AsyncMock(return_value=True)
            result = await validate_twilio_signature(mock_request)
            assert result is True
            mock_global.validate.assert_called_once_with(mock_request)


class TestTwilioWebhookValidator:
    """Test twilio_webhook_validator decorator."""

    @pytest.mark.asyncio
    async def test_decorator_validates_before_calling_func(self):
        """Test decorator validates signature before calling wrapped function."""
        mock_request = MagicMock()
        headers_dict = {"X-Twilio-Signature": "valid-sig"}
        mock_request.headers = MagicMock()
        mock_request.headers.get = MagicMock(side_effect=lambda k, d="": headers_dict.get(k, d))
        mock_request.url = MagicMock()
        mock_request.url.path = "/test"
        mock_request.url.query = ""
        mock_request.url.__str__ = MagicMock(return_value="http://test/test")
        mock_request.form = AsyncMock(return_value={})
        mock_request.client = MagicMock()
        mock_request.client.host = "1.2.3.4"

        # Create a wrapped function
        @twilio_webhook_validator
        async def my_webhook(request: Request):
            return {"status": "ok"}

        with patch("app.security.twilio_validator._twilio_validator") as mock_global:
            mock_global.validate = AsyncMock(return_value=True)
            result = await my_webhook(mock_request)
            assert result == {"status": "ok"}
            mock_global.validate.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_decorator_rejects_invalid_signature(self):
        """Test decorator raises HTTPException for invalid signature."""
        mock_request = MagicMock()
        headers_dict = {"X-Twilio-Signature": ""}
        mock_request.headers = MagicMock()
        mock_request.headers.get = MagicMock(side_effect=lambda k, d="": headers_dict.get(k, d))
        mock_request.url = MagicMock()
        mock_request.url.path = "/test"
        mock_request.client = MagicMock()
        mock_request.client.host = "1.2.3.4"

        @twilio_webhook_validator
        async def my_webhook(request: Request):
            return {"status": "ok"}

        with patch("app.security.twilio_validator._twilio_validator") as mock_global:
            mock_global.validate = AsyncMock(side_effect=HTTPException(
                status_code=403, detail="Missing Twilio signature"
            ))
            with pytest.raises(HTTPException) as exc:
                await my_webhook(mock_request)
            assert exc.value.status_code == 403

    def test_decorator_preserves_function_name(self):
        """Test decorator preserves the wrapped function's metadata."""
        @twilio_webhook_validator
        async def my_webhook_handler(request: Request):
            """My docstring."""
            return {"status": "ok"}

        assert my_webhook_handler.__name__ == "my_webhook_handler"
        assert my_webhook_handler.__doc__ == "My docstring."
