"""
JWT token creation and decoding.

Isolated from password management and FastAPI dependencies.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from jwt.exceptions import InvalidTokenError

from backend import config


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Encode *data* into a signed JWT string."""
    to_encode = data.copy()
    expire = datetime.now(tz=timezone.utc) + (
        expires_delta
        or timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT.  Returns the payload or *None*."""
    try:
        return jwt.decode(
            token, config.SECRET_KEY, algorithms=[config.ALGORITHM]
        )
    except InvalidTokenError:
        return None
