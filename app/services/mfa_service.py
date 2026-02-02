"""MFA Service - TOTP-based Multi-Factor Authentication.

Provides functionality for:
- Generating TOTP secrets
- Creating QR codes for authenticator apps
- Verifying TOTP codes
- Managing backup codes
"""

import secrets
import hashlib
import io
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
import logging

import pyotp
import qrcode
import bcrypt
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mfa import UserMFASettings, UserBackupCode, MFASession
from app.config import settings

logger = logging.getLogger(__name__)

# Configuration
MFA_ISSUER = "Mac Septic CRM"
MFA_SESSION_EXPIRE_MINUTES = 5
MFA_MAX_ATTEMPTS = 3
BACKUP_CODES_COUNT = 10
TOTP_VALID_WINDOW = 1  # Accept codes from ±1 time period (30 seconds)


class MFAService:
    """Service for managing Multi-Factor Authentication."""

    @staticmethod
    def generate_totp_secret() -> str:
        """Generate a new TOTP secret (Base32 encoded)."""
        return pyotp.random_base32()

    @staticmethod
    def get_totp_uri(secret: str, email: str, issuer: str = MFA_ISSUER) -> str:
        """Generate the provisioning URI for authenticator apps."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=issuer)

    @staticmethod
    def generate_qr_code(uri: str) -> bytes:
        """Generate a QR code image for the provisioning URI.

        Returns PNG image as bytes.
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    @staticmethod
    def generate_qr_code_base64(uri: str) -> str:
        """Generate a QR code as a base64-encoded data URI."""
        qr_bytes = MFAService.generate_qr_code(uri)
        b64 = base64.b64encode(qr_bytes).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    @staticmethod
    def verify_totp(secret: str, code: str, window: int = TOTP_VALID_WINDOW) -> bool:
        """Verify a TOTP code.

        Args:
            secret: The user's TOTP secret
            code: The 6-digit code to verify
            window: Number of time periods to check before/after current time

        Returns:
            True if the code is valid
        """
        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(code, valid_window=window)
        except Exception as e:
            logger.error(f"TOTP verification error: {e}")
            return False

    @staticmethod
    def generate_backup_codes(count: int = BACKUP_CODES_COUNT) -> List[str]:
        """Generate a list of single-use backup codes.

        Returns plain text codes (display to user once, then hash for storage).
        """
        codes = []
        for _ in range(count):
            # Generate 8-character alphanumeric code
            code = secrets.token_hex(4).upper()
            # Format as XXXX-XXXX for readability
            formatted = f"{code[:4]}-{code[4:]}"
            codes.append(formatted)
        return codes

    @staticmethod
    def hash_backup_code(code: str) -> str:
        """Hash a backup code for secure storage."""
        # Remove formatting (dashes, spaces)
        clean_code = code.replace("-", "").replace(" ", "").upper()
        return bcrypt.hashpw(clean_code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_backup_code(code: str, code_hash: str) -> bool:
        """Verify a backup code against its hash."""
        clean_code = code.replace("-", "").replace(" ", "").upper()
        try:
            return bcrypt.checkpw(clean_code.encode("utf-8"), code_hash.encode("utf-8"))
        except Exception:
            return False

    @staticmethod
    def generate_session_token() -> str:
        """Generate a secure session token for MFA verification."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_session_token(token: str) -> str:
        """Hash a session token for storage."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


class MFAManager:
    """Manager for MFA operations with database access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_mfa_settings(self, user_id: int) -> Optional[UserMFASettings]:
        """Get MFA settings for a user."""
        result = await self.db.execute(
            select(UserMFASettings).where(UserMFASettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def setup_mfa(self, user_id: int) -> Tuple[str, str]:
        """Initialize MFA setup for a user.

        Returns tuple of (secret, qr_code_data_uri).
        """
        # Generate new secret
        secret = MFAService.generate_totp_secret()

        # Get or create MFA settings
        mfa_settings = await self.get_user_mfa_settings(user_id)

        if mfa_settings:
            # Update existing settings
            mfa_settings.totp_secret = secret
            mfa_settings.totp_enabled = False
            mfa_settings.totp_verified = False
        else:
            # Create new settings
            mfa_settings = UserMFASettings(
                user_id=user_id,
                totp_secret=secret,
                totp_enabled=False,
                totp_verified=False,
                mfa_enabled=False,
            )
            self.db.add(mfa_settings)

        await self.db.commit()
        await self.db.refresh(mfa_settings)

        # Get user email for provisioning URI
        from app.models.user import User
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one()

        # Generate QR code
        uri = MFAService.get_totp_uri(secret, user.email)
        qr_code = MFAService.generate_qr_code_base64(uri)

        return secret, qr_code

    async def verify_setup(self, user_id: int, code: str) -> bool:
        """Verify MFA setup with the first TOTP code.

        This confirms the user has successfully configured their authenticator app.
        """
        mfa_settings = await self.get_user_mfa_settings(user_id)

        if not mfa_settings or not mfa_settings.totp_secret:
            return False

        if MFAService.verify_totp(mfa_settings.totp_secret, code):
            mfa_settings.totp_verified = True
            mfa_settings.totp_enabled = True
            mfa_settings.mfa_enabled = True
            mfa_settings.last_used_at = datetime.now(timezone.utc)
            await self.db.commit()
            return True

        return False

    async def generate_backup_codes(self, user_id: int) -> List[str]:
        """Generate and store new backup codes for a user.

        Returns the plain text codes (display once to user).
        """
        mfa_settings = await self.get_user_mfa_settings(user_id)

        if not mfa_settings:
            raise ValueError("MFA not configured for user")

        # Delete existing backup codes
        await self.db.execute(
            UserBackupCode.__table__.delete().where(
                UserBackupCode.mfa_settings_id == mfa_settings.id
            )
        )

        # Generate new codes
        codes = MFAService.generate_backup_codes()

        # Store hashed codes
        for code in codes:
            backup_code = UserBackupCode(
                user_id=user_id,
                mfa_settings_id=mfa_settings.id,
                code_hash=MFAService.hash_backup_code(code),
            )
            self.db.add(backup_code)

        # Update count
        mfa_settings.backup_codes_count = len(codes)
        mfa_settings.backup_codes_generated_at = datetime.now(timezone.utc)

        await self.db.commit()

        return codes

    async def verify_backup_code(self, user_id: int, code: str) -> bool:
        """Verify and consume a backup code."""
        result = await self.db.execute(
            select(UserBackupCode).where(
                and_(
                    UserBackupCode.user_id == user_id,
                    UserBackupCode.used == False,
                )
            )
        )
        backup_codes = result.scalars().all()

        for backup_code in backup_codes:
            if MFAService.verify_backup_code(code, backup_code.code_hash):
                # Mark as used
                backup_code.used = True
                backup_code.used_at = datetime.now(timezone.utc)

                # Update count in settings
                mfa_settings = await self.get_user_mfa_settings(user_id)
                if mfa_settings:
                    mfa_settings.backup_codes_count = max(0, mfa_settings.backup_codes_count - 1)

                await self.db.commit()
                return True

        return False

    async def create_mfa_session(self, user_id: int) -> str:
        """Create a temporary MFA session for login verification.

        Returns the session token (show to client for subsequent MFA verification).
        """
        token = MFAService.generate_session_token()
        token_hash = MFAService.hash_session_token(token)

        session = MFASession(
            user_id=user_id,
            session_token_hash=token_hash,
            challenge_type="totp",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=MFA_SESSION_EXPIRE_MINUTES),
        )
        self.db.add(session)
        await self.db.commit()

        return token

    async def verify_mfa_session(
        self, session_token: str, code: str, use_backup: bool = False
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Verify MFA code for a session.

        Returns tuple of (success, user_id, error_message).
        """
        token_hash = MFAService.hash_session_token(session_token)

        result = await self.db.execute(
            select(MFASession).where(MFASession.session_token_hash == token_hash)
        )
        session = result.scalar_one_or_none()

        if not session:
            return False, None, "Invalid or expired session"

        if session.is_expired:
            await self.db.delete(session)
            await self.db.commit()
            return False, None, "Session expired"

        if session.attempts >= session.max_attempts:
            await self.db.delete(session)
            await self.db.commit()
            return False, None, "Maximum attempts exceeded"

        # Increment attempts
        session.attempts += 1

        # Get user's MFA settings
        mfa_settings = await self.get_user_mfa_settings(session.user_id)

        if not mfa_settings or not mfa_settings.mfa_enabled:
            await self.db.delete(session)
            await self.db.commit()
            return False, None, "MFA not enabled"

        # Verify code
        verified = False
        if use_backup:
            verified = await self.verify_backup_code(session.user_id, code)
        else:
            verified = MFAService.verify_totp(mfa_settings.totp_secret, code)

        if verified:
            # Update last used
            mfa_settings.last_used_at = datetime.now(timezone.utc)
            session.verified_at = datetime.now(timezone.utc)

            # Delete session (single use)
            user_id = session.user_id
            await self.db.delete(session)
            await self.db.commit()

            return True, user_id, None

        await self.db.commit()
        return False, None, f"Invalid code ({session.attempts_remaining} attempts remaining)"

    async def disable_mfa(self, user_id: int, code: str) -> bool:
        """Disable MFA for a user (requires valid TOTP code)."""
        mfa_settings = await self.get_user_mfa_settings(user_id)

        if not mfa_settings or not mfa_settings.mfa_enabled:
            return False

        # Verify current code before disabling
        if not MFAService.verify_totp(mfa_settings.totp_secret, code):
            return False

        # Disable MFA
        mfa_settings.mfa_enabled = False
        mfa_settings.totp_enabled = False
        mfa_settings.totp_verified = False
        mfa_settings.totp_secret = None

        # Delete backup codes
        await self.db.execute(
            UserBackupCode.__table__.delete().where(
                UserBackupCode.mfa_settings_id == mfa_settings.id
            )
        )
        mfa_settings.backup_codes_count = 0

        await self.db.commit()
        return True

    async def get_mfa_status(self, user_id: int) -> dict:
        """Get MFA status for a user."""
        mfa_settings = await self.get_user_mfa_settings(user_id)

        if not mfa_settings:
            return {
                "mfa_enabled": False,
                "totp_enabled": False,
                "totp_verified": False,
                "backup_codes_count": 0,
                "backup_codes_generated_at": None,
                "last_used_at": None,
            }

        return {
            "mfa_enabled": mfa_settings.mfa_enabled,
            "totp_enabled": mfa_settings.totp_enabled,
            "totp_verified": mfa_settings.totp_verified,
            "backup_codes_count": mfa_settings.backup_codes_count,
            "backup_codes_generated_at": mfa_settings.backup_codes_generated_at,
            "last_used_at": mfa_settings.last_used_at,
        }
