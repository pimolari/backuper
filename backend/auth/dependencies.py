"""
FastAPI dependencies for route-level authentication.

Usage in a route::

    from backend.auth.dependencies import get_current_user

    @router.get("/protected")
    def protected(current_user: dict = Depends(get_current_user)):
        ...
"""

from typing import Dict, Any

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from backend.auth.tokens import decode_access_token
from backend.common.exceptions import AppError

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login", auto_error=False
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> Dict[str, Any]:
    """
    Dependency that extracts and validates the Bearer token, then
    returns the full user dict from Datastore.

    Raises :class:`AppError` (401) on any authentication failure.
    """
    # Import here to avoid circular dependency (services → auth → services)
    from backend.services.user_service import get_user_by_email

    credentials_error = AppError(
        "Could not validate credentials", status_code=401
    )

    if not token:
        raise credentials_error

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_error

    email: str | None = payload.get("sub")
    if email is None:
        raise credentials_error

    user = get_user_by_email(email)
    if user is None:
        raise credentials_error

    return user
