"""Encryption utilities for securely storing API keys and secrets."""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)


def _get_fernet_key() -> bytes:
    """Derive a Fernet-compatible key from the app's SECRET_KEY."""
    key_bytes = settings.SECRET_KEY.encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns base64-encoded ciphertext."""
    f = Fernet(_get_fernet_key())
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str) -> str | None:
    """Decrypt a ciphertext string. Returns None if decryption fails."""
    try:
        f = Fernet(_get_fernet_key())
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception) as e:
        logger.warning(f"Failed to decrypt value: {e}")
        return None
