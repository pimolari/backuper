"""
User service — business logic for registration, login, and profile management.

No HTTP / FastAPI concepts live here; only pure business rules.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from backend import config
from backend.auth.passwords import hash_password, verify_password
from backend.auth.tokens import create_access_token
from backend.clients.datastore_client import DatastoreClient
from backend.clients.gcs_client import GCSClient
from backend.common.exceptions import ConflictError, InternalError
from backend.common.logging import biz_logger, tech_logger
from backend.common.utils.validators import validate_region, validate_storage_class
from backend.models.user import UserResponse
from backend.services._mappers import build_user_response

# Module-level singletons (cheap; the heavy SDK client is created once)
_db = DatastoreClient()
_gcs = GCSClient()


# ─── queries ────────────────────────────────────────────────────────

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Look up a user by email.  Returns *None* if not found."""
    query = _db.query(kind="User")
    query.add_filter("email", "=", email.lower().strip())
    results = list(query.fetch())
    if results:
        user = dict(results[0])
        user["id"] = results[0].key.name or str(results[0].key.id)
        return user
    return None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Look up a user by Datastore key.  Returns *None* if not found."""
    key = _db.key("User", user_id)
    entity = _db.get(key)
    if entity:
        user = dict(entity)
        user["id"] = user_id
        return user
    return None


# ─── commands ───────────────────────────────────────────────────────

def register_user(
    name: str,
    email: str,
    password: str,
    region: str,
    storage_class: str,
    invite_token: str,
) -> UserResponse:
    """
    Full registration flow: validate -> create GCS bucket -> persist user.
    """
    from datetime import datetime
    from backend.services.invite_service import validate_invite, mark_invite_accepted

    validate_region(region)
    validate_storage_class(storage_class)

    # Validate the invite token
    invite = validate_invite(invite_token)
    if invite["invited_email"] != email.lower().strip():
        from backend.common.exceptions import AppError
        raise AppError("Email does not match the invitation.", status_code=400)

    if get_user_by_email(email):
        raise ConflictError("A user with this email already exists.")

    try:
        bucket_name = _gcs.create_user_bucket(email, region, storage_class)
    except Exception as exc:
        tech_logger.error("Bucket creation failed for %s: %s", email, exc)
        raise InternalError(
            f"Failed to create Google Cloud Storage bucket: {exc}"
        )

    hashed_pw = hash_password(password)
    user_id = email.lower().strip()
    key = _db.key("User", user_id)
    user_data = {
        "name": name,
        "email": email.lower().strip(),
        "hashed_password": hashed_pw,
        "active_bucket": bucket_name,
        "buckets": [
            {
                "name": bucket_name,
                "region": region,
                "storage_class": storage_class,
            }
        ],
        "role": "user",
        "enrolment_date": datetime.now(tz=timezone.utc).isoformat(),
        "last_login_date": None,
        "is_active": True,
    }
    entity = _db.create_entity(key, user_data)
    _db.put(entity)
    user_data["id"] = user_id

    # Mark invite as accepted
    mark_invite_accepted(invite_token)

    biz_logger.info("User registered: %s", email)
    return build_user_response(user_data)


def login_user(email: str, password: str) -> dict:
    """
    Authenticate and return an access-token payload.
    """
    from backend.common.exceptions import AppError

    user = get_user_by_email(email)
    if not user or not verify_password(password, user["hashed_password"]):
        raise AppError(
            "Incorrect email or password.",
            status_code=401,
        )

    if not user.get("is_active", True):
        raise AppError("Your account has been deactivated.", status_code=403)

    access_token = create_access_token(
        data={"sub": user["email"]},
        expires_delta=timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # Update last login date
    user["last_login_date"] = datetime.now(tz=timezone.utc).isoformat()
    key = _db.key("User", user["id"])
    entity = _db.get(key)
    if entity:
        entity["last_login_date"] = user["last_login_date"]
        _db.put(entity)

    biz_logger.info("User logged in: %s", email)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "name": user["name"],
            "email": user["email"],
            "active_bucket": user["active_bucket"],
        },
    }


def get_profile(current_user: Dict[str, Any]) -> UserResponse:
    """Return the authenticated user's profile."""
    return build_user_response(current_user)


def update_profile(
    current_user: Dict[str, Any],
    name: str,
    email: str,
) -> UserResponse:
    """Update name / email.  Checks for email uniqueness."""
    if email.lower() != current_user["email"].lower():
        if get_user_by_email(email):
            raise ConflictError("A user with this email already exists.")

    key = _db.key("User", current_user["id"])
    entity = _db.get(key)
    if entity:
        entity["name"] = name
        entity["email"] = email.lower().strip()
        _db.put(entity)

    updated_user = get_user_by_id(current_user["id"])
    biz_logger.info("Profile updated: %s", email)
    return build_user_response(updated_user)

def list_users() -> list[UserResponse]:
    """Return all users in the system."""
    query = _db.query(kind="User")
    results = list(query.fetch())
    
    users = []
    for res in results:
        data = dict(res)
        data["id"] = res.key.name or str(res.key.id)
        users.append(build_user_response(data))
    return users

def deactivate_user(user_id: str) -> None:
    """Deactivates a user account."""
    from backend.common.exceptions import AppError
    key = _db.key("User", user_id)
    entity = _db.get(key)
    if not entity:
        raise AppError("User not found.", status_code=404)
        
    entity["is_active"] = False
    _db.put(entity)
    biz_logger.info("User deactivated: %s", user_id)
