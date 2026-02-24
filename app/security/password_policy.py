"""Password complexity validation."""

import re


SPECIAL_CHARACTERS = r"!@#$%^&*()_+\-="


def validate_password(password: str) -> list[str]:
    """Validate password complexity. Returns list of failure messages (empty if valid)."""
    errors = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least 1 uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least 1 lowercase letter")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least 1 digit")
    if not re.search(r"[!@#$%^&*()_+\-=]", password):
        errors.append("Password must contain at least 1 special character (!@#$%^&*()_+-=)")

    return errors
