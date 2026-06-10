"""
Bucket service — business logic for creating and switching GCS buckets.
"""

from typing import Dict, Any

from backend.clients.datastore_client import DatastoreClient
from backend.clients.gcs_client import GCSClient
from backend.common.exceptions import InternalError, ValidationError
from backend.common.logging import biz_logger, tech_logger
from backend.common.utils.validators import validate_region, validate_storage_class
from backend.models.user import UserResponse
from backend.services._mappers import build_user_response

_db = DatastoreClient()
_gcs = GCSClient()


def create_bucket(
    current_user: Dict[str, Any],
    region: str,
    storage_class: str,
) -> UserResponse:
    """
    Create a new GCS bucket, attach it to the user, and return the
    updated profile.
    """
    validate_region(region)
    validate_storage_class(storage_class)

    try:
        bucket_name = _gcs.create_user_bucket(
            current_user["email"], region, storage_class
        )
    except Exception as exc:
        tech_logger.error("Bucket creation failed: %s", exc)
        raise InternalError(f"Failed to create GCS bucket: {exc}")

    # Attach bucket to user in Datastore
    key = _db.key("User", current_user["id"])
    entity = _db.get(key)
    if entity:
        buckets = list(entity.get("buckets", []))
        if not any(b["name"] == bucket_name for b in buckets):
            buckets.append(
                {
                    "name": bucket_name,
                    "region": region,
                    "storage_class": storage_class,
                }
            )
            entity["buckets"] = buckets
            _db.put(entity)

    # Re-read and return
    from backend.services.user_service import get_user_by_id

    updated = get_user_by_id(current_user["id"])
    biz_logger.info(
        "Bucket created: %s for user %s", bucket_name, current_user["email"]
    )
    return build_user_response(updated)


def set_active_bucket(
    current_user: Dict[str, Any],
    bucket_name: str,
) -> UserResponse:
    """
    Switch the user's active bucket.
    """
    key = _db.key("User", current_user["id"])
    entity = _db.get(key)
    if not entity:
        raise ValidationError("User not found.")

    buckets = entity.get("buckets", [])
    if not any(b["name"] == bucket_name for b in buckets):
        raise ValidationError(
            "Failed to change active bucket. Ensure you own this bucket."
        )

    entity["active_bucket"] = bucket_name
    _db.put(entity)

    from backend.services.user_service import get_user_by_id

    updated = get_user_by_id(current_user["id"])
    biz_logger.info(
        "Active bucket changed to %s for user %s",
        bucket_name,
        current_user["email"],
    )
    return build_user_response(updated)
