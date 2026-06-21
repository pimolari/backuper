"""
Shared mappers: dict → Pydantic response models.

Centralises the ``build_user_response`` logic that was previously
copy-pasted in 5+ route handlers.
"""

from typing import Dict, Any

from backend.models.user import UserResponse
from backend.models.bucket import BucketInfo


def build_user_response(user: Dict[str, Any]) -> UserResponse:
    """
    Convert a raw Datastore user dict into a :class:`UserResponse`.
    """
    active_b = user.get("active_bucket", "")
    buckets_info = [
        BucketInfo(
            name=b["name"],
            region=b["region"],
            storage_class=b["storage_class"],
            is_active=(b["name"] == active_b),
        )
        for b in user.get("buckets", [])
    ]
    return UserResponse(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        buckets=buckets_info,
        active_bucket=active_b,
        role=user.get("role", "user"),
        enrolment_date=user.get("enrolment_date", ""),
        last_login_date=user.get("last_login_date"),
        is_active=user.get("is_active", True),
    )
