"""
Shared Pydantic types for schema validation.

UUIDStr: Accepts both str and uuid.UUID objects, coercing UUID to str.
This is needed because SQLAlchemy UUID columns return Python uuid.UUID objects,
but Pydantic v2 does not auto-coerce UUID to str, causing validation errors.
"""

from typing import Annotated
from pydantic import BeforeValidator

# Coerces uuid.UUID objects to str for JSON serialization
UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if not isinstance(v, str) else v)]
