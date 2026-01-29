"""
Shared error response schemas for OpenAPI documentation.

Import these in endpoint files to add consistent error responses.

Note: These definitions use inline examples rather than model references
to avoid circular imports with the exceptions module.
"""

from typing import Dict, Any


# Reusable response definitions for OpenAPI
ERROR_RESPONSES: Dict[int, Dict[str, Any]] = {
    400: {
        "description": "Bad Request - Invalid input data",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://api.ecbtx.com/problems/val-001",
                    "title": "Bad Request",
                    "status": 400,
                    "detail": "Invalid request format",
                    "code": "VAL_001",
                    "timestamp": "2026-01-29T10:30:00Z",
                    "trace_id": "abc123def456"
                }
            }
        }
    },
    401: {
        "description": "Unauthorized - Authentication required",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://api.ecbtx.com/problems/auth-001",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "Authentication required",
                    "code": "AUTH_001",
                    "timestamp": "2026-01-29T10:30:00Z",
                    "trace_id": "abc123def456"
                }
            }
        }
    },
    403: {
        "description": "Forbidden - Insufficient permissions",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://api.ecbtx.com/problems/auth-002",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": "Permission denied",
                    "code": "AUTH_002",
                    "timestamp": "2026-01-29T10:30:00Z",
                    "trace_id": "abc123def456"
                }
            }
        }
    },
    404: {
        "description": "Not Found - Resource does not exist",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://api.ecbtx.com/problems/res-001",
                    "title": "Not Found",
                    "status": 404,
                    "detail": "Customer with ID 123 was not found",
                    "code": "RES_001",
                    "timestamp": "2026-01-29T10:30:00Z",
                    "trace_id": "abc123def456"
                }
            }
        }
    },
    409: {
        "description": "Conflict - Resource already exists",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://api.ecbtx.com/problems/res-003",
                    "title": "Conflict",
                    "status": 409,
                    "detail": "A customer with this email already exists",
                    "code": "RES_003",
                    "timestamp": "2026-01-29T10:30:00Z",
                    "trace_id": "abc123def456"
                }
            }
        }
    },
    422: {
        "description": "Validation Error - Invalid field values",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://api.ecbtx.com/problems/val-001",
                    "title": "Validation Error",
                    "status": 422,
                    "detail": "Request validation failed",
                    "code": "VAL_001",
                    "timestamp": "2026-01-29T10:30:00Z",
                    "trace_id": "abc123def456",
                    "errors": [
                        {
                            "field": "body.email",
                            "message": "Invalid email format",
                            "type": "value_error"
                        }
                    ]
                }
            }
        }
    },
    429: {
        "description": "Too Many Requests - Rate limit exceeded",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://api.ecbtx.com/problems/biz-002",
                    "title": "Too Many Requests",
                    "status": 429,
                    "detail": "Rate limit exceeded. Try again in 60 seconds.",
                    "code": "BIZ_002",
                    "timestamp": "2026-01-29T10:30:00Z",
                    "trace_id": "abc123def456",
                    "retry_after": 60
                }
            }
        }
    },
    500: {
        "description": "Internal Server Error",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://api.ecbtx.com/problems/srv-001",
                    "title": "Internal Server Error",
                    "status": 500,
                    "detail": "An unexpected error occurred",
                    "code": "SRV_001",
                    "timestamp": "2026-01-29T10:30:00Z",
                    "trace_id": "abc123def456"
                }
            }
        }
    },
    502: {
        "description": "Bad Gateway - External service error",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://api.ecbtx.com/problems/ext-001",
                    "title": "Bad Gateway",
                    "status": 502,
                    "detail": "External service error: Connection timeout",
                    "code": "EXT_001",
                    "timestamp": "2026-01-29T10:30:00Z",
                    "trace_id": "abc123def456"
                }
            }
        }
    },
    503: {
        "description": "Service Unavailable",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://api.ecbtx.com/problems/srv-002",
                    "title": "Service Unavailable",
                    "status": 503,
                    "detail": "Service temporarily unavailable",
                    "code": "SRV_002",
                    "timestamp": "2026-01-29T10:30:00Z",
                    "trace_id": "abc123def456"
                }
            }
        }
    },
}


def get_error_responses(*status_codes: int) -> Dict[int, Dict[str, Any]]:
    """
    Get error response definitions for specified status codes.

    Usage in endpoint:
        @router.get(
            "/{id}",
            responses=get_error_responses(401, 404, 500)
        )

    Args:
        *status_codes: HTTP status codes to include

    Returns:
        Dictionary of error responses for OpenAPI schema
    """
    return {
        code: ERROR_RESPONSES[code]
        for code in status_codes
        if code in ERROR_RESPONSES
    }


# Common response combinations for convenience
CRUD_ERROR_RESPONSES = get_error_responses(400, 401, 403, 404, 422, 500)
LIST_ERROR_RESPONSES = get_error_responses(400, 401, 500)
CREATE_ERROR_RESPONSES = get_error_responses(400, 401, 409, 422, 500)
UPDATE_ERROR_RESPONSES = get_error_responses(400, 401, 403, 404, 422, 500)
DELETE_ERROR_RESPONSES = get_error_responses(401, 403, 404, 500)
