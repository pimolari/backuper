"""
Unified application exceptions.

All business-level errors inherit from AppError so that FastAPI's
exception handling converts them automatically into JSON responses.
"""

from fastapi import HTTPException, status


class AppError(HTTPException):
    """Base for every business error raised inside services."""

    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail=detail)


class ConflictError(AppError):
    """Raised when a resource already exists (409)."""

    def __init__(self, detail: str = "Resource already exists."):
        super().__init__(detail=detail, status_code=status.HTTP_409_CONFLICT)


class NotFoundError(AppError):
    """Raised when a resource cannot be found (404)."""

    def __init__(self, detail: str = "Resource not found."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class ForbiddenError(AppError):
    """Raised when the caller lacks permission (403)."""

    def __init__(self, detail: str = "Not authorized."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class ValidationError(AppError):
    """Raised for business-rule validation failures (400)."""

    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class InternalError(AppError):
    """Raised for unexpected infrastructure failures (500)."""

    def __init__(self, detail: str = "Internal server error."):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
